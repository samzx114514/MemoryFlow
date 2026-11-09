"""Teacher-force a whole recorded call and reduce one attention head by source span."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from source_path_v1.replay_rich import token_span

from .span_views import fragments, views

TURN_END = "<|im_end|>\n"
MODEL = "Qwen2.5-7B-Instruct"


def tool_call(tool):
    function = tool.get("function") or {"name": tool["name"], "arguments": tool.get("args", {})}
    args = function.get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            pass
    return {**tool, "function": {**function, "arguments": args}}


def render_call(tokenizer, request, generation):
    messages = []
    for original in request["messages"]:
        message = {**original, "content": original.get("content") or ""}
        if not isinstance(message["content"], str):
            raise ValueError("This replay format requires recorded text messages")
        if message.get("tool_calls"):
            message["tool_calls"] = [tool_call(tool) for tool in message["tool_calls"]]
        messages.append(message)
    options = {"tokenize": False, "tools": request.get("tools") or None}
    prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, **options)
    marker = uuid.uuid4().hex
    marked = []
    markers = {}
    for index, message in enumerate(messages):
        entry = dict(message)
        if message["content"]:
            left, right = f"{marker}open{index}end", f"{marker}close{index}end"
            markers[index] = left, right
            entry["content"] = left + entry["content"] + right
        marked.append(entry)
    marked_prompt = tokenizer.apply_chat_template(marked, add_generation_prompt=True, **options)
    spans = {}
    for index, (left, right) in markers.items():
        if marked_prompt.count(left) != 1 or marked_prompt.count(right) != 1:
            raise ValueError(f"Cannot uniquely align message {index}")
        start = marked_prompt.index(left)
        stop = marked_prompt.index(right)
        spans[index] = (start, stop - len(left))
        marked_prompt = marked_prompt[:start] + marked_prompt[start + len(left):stop] + marked_prompt[stop + len(right):]
    if marked_prompt != prompt:
        raise ValueError("Chat template did not preserve message content")

    # Find history tool blocks in rendered order, bounded by adjacent message content.
    sections = []
    cursor = 0
    for index, message in enumerate(messages):
        if index in spans:
            start, stop = spans[index]
            if start < cursor or prompt[start:stop] != message["content"]:
                raise ValueError(f"Misaligned message {index}")
            sections.append((index, "content", start, stop))
            cursor = stop
        if message.get("tool_calls"):
            later = [left for i, (left, _) in spans.items() if i > index]
            limit = later[0] if later else len(prompt)
            for tool in message["tool_calls"]:
                start = prompt.find("<tool_call>\n", cursor, limit)
                stop = prompt.find("\n</tool_call>", max(start, cursor), limit)
                if start < 0 or stop < 0:
                    raise ValueError(f"Cannot align historical tool call in message {index}")
                stop += len("\n</tool_call>")
                function = tool["function"]
                payload = json.loads(prompt[start + len("<tool_call>\n"):stop - len("\n</tool_call>")])
                if payload != {"name": function["name"], "arguments": function["arguments"]}:
                    raise ValueError(f"Historical tool call mismatch in message {index}")
                sections.append((index, "tool_calls", start, stop))
                cursor = stop

    text = generation.get("text") or ""
    assistant = {"role": "assistant", "content": text,
                 "tool_calls": [tool_call(tool) for tool in generation.get("tool_calls") or []]}
    rendered = tokenizer.apply_chat_template([*messages, assistant], add_generation_prompt=False, **options)
    if not rendered.startswith(prompt) or not rendered.endswith(TURN_END):
        raise ValueError("Recorded assistant response did not align to the replay template")
    output = rendered[len(prompt):-len(TURN_END)]
    if not output.startswith(text):
        raise ValueError("Replay template modified the recorded response text")
    return messages, prompt, output, len(text), sections


def replay_inputs(tokenizer, request, generation):
    messages, prompt, output, text_length, sections = render_call(tokenizer, request, generation)
    prompt_encoding = tokenizer(prompt, add_special_tokens=False, return_offsets_mapping=True)
    output_encoding = tokenizer(output, add_special_tokens=False, return_offsets_mapping=True)
    prompt_ids, output_ids = prompt_encoding["input_ids"], output_encoding["input_ids"]
    prompt_offsets = prompt_encoding["offset_mapping"]
    output_offsets = output_encoding["offset_mapping"]
    columns = []
    for index, section, start, stop in sections:
        role = messages[index]["role"]
        if role == "system":
            continue
        value = prompt[start:stop]
        structured = section == "tool_calls" or (role == "tool" and value.lstrip().startswith(("{", "["))) or "<sp-subagent-task>" in value
        for view in views(value, structured=structured):
            for fragment, (left, right), offsets in fragments(view):
                span = token_span(prompt_offsets, start + left, start + right)
                if span is None:
                    raise ValueError(f"No input tokens for {index}:{left}-{right}")
                columns.append({"message_index": index, "section": section, "role": role,
                                "text": value[left:right], "match_text": fragment,
                                "match_offsets": offsets, "message_char_span": [left, right] if section == "content" else None,
                                "prompt_char_span": [start + left, start + right], "token_span": span})
    prompt_size = len(prompt_ids)
    # These columns are causal at each token row and can be traversed only when
    # the whole fragment precedes the queried output range.
    for view in [*views(output[:text_length]), *views(output[text_length:], start=text_length, structured=True)]:
        for fragment, (left, right), _ in fragments(view):
            span = token_span(output_offsets, left, right)
            if span is None:
                raise ValueError(f"No output tokens for {left}-{right}")
            columns.append({"message_index": None, "section": "output_prefix", "role": "assistant",
                            "text": output[left:right], "match_text": fragment, "response_char_span": [left, right],
                            "token_span": [prompt_size + span[0], prompt_size + span[1]]})
    for index, candidate in enumerate(columns):
        candidate["column"] = index
    return prompt_ids, output_ids, output_offsets, output, text_length, columns


class FixedHeadReplay:
    def __init__(self, model_dir: Path, layer: int, head: int, memory_cap_gib: float):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        if not self.tokenizer.is_fast:
            raise ValueError("A fast tokenizer is required for source offsets")
        if memory_cap_gib:
            capacity = torch.cuda.get_device_properties(0).total_memory
            torch.cuda.set_per_process_memory_fraction(min(memory_cap_gib * (1 << 30) / capacity, 1))
        self.model = AutoModelForCausalLM.from_pretrained(
            model_dir, local_files_only=True, dtype=torch.bfloat16, attn_implementation="sdpa",
        ).to("cuda").eval()
        self.model.requires_grad_(False)
        self.layer, self.head = layer, head
        config = self.model.config
        if not (0 <= layer < config.num_hidden_layers and 0 <= head < config.num_attention_heads):
            raise ValueError("Fixed attention head is out of bounds")
        self.kv_head = head // (config.num_attention_heads // config.num_key_value_heads)

    def run(self, request, generation):
        import numpy as np
        import transformers.models.qwen2.modeling_qwen2 as qwen

        prompt_ids, output_ids, offsets, output, text_length, columns = replay_inputs(self.tokenizer, request, generation)
        p, t = len(prompt_ids), len(output_ids)
        ids = prompt_ids + output_ids[:-1] if t else prompt_ids
        if not p or len(ids) > self.model.config.max_position_embeddings:
            raise ValueError(f"Replay requires {len(ids)} tokens; model limit is {self.model.config.max_position_embeddings}")
        scores = np.zeros((t, len(columns)), dtype=np.float32)
        if t:
            torch = self.torch
            captured = {}
            active = False
            original = qwen.apply_rotary_pos_emb

            def start(*_):
                nonlocal active
                active = True

            def stop(*_):
                nonlocal active
                active = False

            def capture(*args, **kwargs):
                q, k = original(*args, **kwargs)
                if active:
                    captured["q"] = q[0, self.head, p - 1:p - 1 + t].detach().contiguous()
                    captured["k"] = k[0, self.kv_head].detach().contiguous()
                return q, k

            module = self.model.model.layers[self.layer].self_attn
            pre = module.register_forward_pre_hook(start)
            post = module.register_forward_hook(stop)
            qwen.apply_rotary_pos_emb = capture
            try:
                with torch.inference_mode():
                    input_ids = torch.tensor([ids], device="cuda")
                    self.model(input_ids=input_ids, use_cache=False, logits_to_keep=1)
            finally:
                qwen.apply_rotary_pos_emb = original
                pre.remove()
                post.remove()
            q, k = captured["q"], captured["k"]
            if len(q) != t or len(k) != len(ids):
                raise RuntimeError("Fixed-head positions do not match the replay")
            with torch.inference_mode():
                keys = torch.arange(len(ids), device="cuda")
                starts = torch.tensor([min(c["token_span"][0], len(ids)) for c in columns], device="cuda", dtype=torch.long)
                ends = torch.tensor([min(c["token_span"][1], len(ids)) for c in columns], device="cuda", dtype=torch.long)
                for offset in range(0, t, 128):
                    block = q[offset:offset + 128]
                    rows = torch.arange(p - 1 + offset, p - 1 + offset + len(block), device="cuda")
                    logits = (block @ k.T * (k.shape[-1] ** -0.5)).float()
                    weights = logits.masked_fill(keys[None, :] > rows[:, None], float("-inf")).softmax(dim=-1)
                    prefix = torch.nn.functional.pad(weights.cumsum(dim=-1, dtype=torch.float64), (1, 0))
                    scores[offset:offset + len(block)] = (prefix[:, ends] - prefix[:, starts]).float().cpu().numpy()
        return {"prompt_tokens": p, "output_tokens": t, "output": output, "response_text_length": text_length,
                "output_offsets": offsets, "prediction_rows": list(range(p - 1, p - 1 + t)),
                "columns": columns, "model": MODEL, "layer": self.layer, "head": self.head}, scores


def select_gpu(index: int):
    os.environ["CUDA_VISIBLE_DEVICES"] = str(index)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
