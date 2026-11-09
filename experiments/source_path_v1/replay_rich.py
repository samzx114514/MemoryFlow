"""Rich replay v2: exact message-local / prompt-global / token spans, no re-find.

Fixes versus v1:
- fragments are produced by scanning the raw message content with offsets; no stripped-text
  re-find, so repeated sentences keep their distinct positions;
- candidates keep message_char_span, prompt_char_span, token_span and response_char_span (for the
  current output prefix), plus a class and a source field;
- target uses the saved response span when available (first occurrence only if absent, with a flag);
- coverage reports both the summed candidate mass and the union-of-keys covered mass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path("/data2/pkuiti/songzhengxing_intern/memoryflow")
SPLIT = re.compile(r"(?<=[.!?;])\s+")


def scan_fragments(content: str, max_chars: int = 240, min_chars: int = 8, cap: int = 4000):
    """Yield (start, end, text) in content coordinates; preserves repeated occurrences."""
    out = []
    truncated = False
    for line_match in re.finditer(r"[^\n]*", content):
        start, end = line_match.start(), line_match.end()
        while start < end and content[start].isspace():
            start += 1
        while end > start and content[end - 1].isspace():
            end -= 1
        if start >= end:
            continue
        pieces = [(start, end)]
        if end - start > max_chars:
            pieces = []
            cursor = start
            for match in SPLIT.finditer(content, start, end):
                cut = match.end()
                if cut - cursor > 0:
                    pieces.append((cursor, cut))
                cursor = cut
            if cursor < end:
                pieces.append((cursor, end))
            # merge pieces shorter than the minimum with the next piece, so section numbers
            # such as "6." do not split the following heading away from its number
            merged = []
            pending_left = None
            for left, right in pieces:
                if pending_left is not None:
                    left = pending_left
                    pending_left = None
                if right - left < min_chars:
                    pending_left = left
                    continue
                merged.append((left, right))
            if pending_left is not None and merged:
                merged[-1] = (merged[-1][0], end)
            elif pending_left is not None:
                merged.append((pending_left, end))
            pieces = merged
        for left, right in pieces:
            while left < right and content[left].isspace():
                left += 1
            while right > left and content[right - 1].isspace():
                right -= 1
            if right - left < min_chars:
                continue
            out.append((left, right, content[left:right]))
            if len(out) >= cap:
                truncated = True
                return out, truncated
    return out, truncated


def token_span(offsets, start: int, end: int):
    indices = [i for i, (a, b) in enumerate(offsets) if b > start and a < end]
    return (min(indices), max(indices) + 1) if indices else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--call", type=int, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--layer", type=int, default=19)
    parser.add_argument("--head", type=int, default=15)
    args = parser.parse_args()

    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import transformers.models.qwen2.modeling_qwen2 as qwen2mod
    from transformers.models.qwen2.modeling_qwen2 import repeat_kv

    run = pathlib.Path(args.run)
    rows_raw = [json.loads(line) for line in (run / "calls.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    row = rows_raw[args.call]
    messages = (row.get("request") or {}).get("messages") or []
    response = (((row.get("response") or {}).get("generations") or [{}])[0].get("text") or "")
    pos = response.find(args.target)
    if pos < 0:
        print("target not found", file=sys.stderr)
        return 1
    if response.find(args.target, pos + 1) >= 0:
        print("warning: target occurs multiple times; using first occurrence", file=sys.stderr)
    prefix, target = response[:pos], args.target

    model_dir = str(ROOT.parent / "model/Qwen2.5-7B-Instruct")
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    prompt_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    prompt_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
    encoded = tokenizer(prompt_text, add_special_tokens=False, return_offsets_mapping=True)
    offsets = encoded["offset_mapping"]
    prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
    target_ids = tokenizer(target, add_special_tokens=False)["input_ids"]
    P, C, T = len(prompt_ids), len(prefix_ids), len(target_ids)
    full_ids = prompt_ids + prefix_ids + target_ids[:-1]
    rows_to_read = list(range(P + C - 1, P + C - 1 + T))

    model = AutoModelForCausalLM.from_pretrained(model_dir, local_files_only=True, dtype=torch.bfloat16,
                                                 attn_implementation="sdpa").to("cuda").eval()
    model.requires_grad_(False)
    cfg = model.config
    heads = cfg.num_attention_heads
    kv = getattr(cfg, "num_key_value_heads", heads)
    head_dim = getattr(cfg, "head_dim", cfg.hidden_size // heads)
    scaling = head_dim ** -0.5
    captured, state = {}, {"active": False}
    original = qwen2mod.apply_rotary_pos_emb

    def patched(q, k, cos, sin, unsqueeze_dim=1):
        out = original(q, k, cos, sin, unsqueeze_dim)
        if state["active"]:
            captured["q"], captured["k"] = out[0].detach(), out[1].detach()
        return out

    pre = model.model.layers[args.layer].self_attn.register_forward_pre_hook(lambda m, a: state.update(active=True))
    post = model.model.layers[args.layer].self_attn.register_forward_hook(lambda m, a, o: state.update(active=False))
    qwen2mod.apply_rotary_pos_emb = patched
    try:
        with torch.inference_mode():
            model(input_ids=torch.tensor([full_ids], device="cuda"),
                  attention_mask=torch.ones((1, len(full_ids)), dtype=torch.long, device="cuda"),
                  position_ids=torch.tensor([list(range(len(full_ids)))], device="cuda"), use_cache=False)
    finally:
        qwen2mod.apply_rotary_pos_emb = original
        pre.remove()
        post.remove()

    q = captured["q"][:, :, rows_to_read, :]
    k = repeat_kv(captured["k"], heads // kv)
    key_idx = torch.arange(len(full_ids), device="cuda").unsqueeze(0)
    row_idx = torch.tensor(rows_to_read, device="cuda").unsqueeze(1)
    causal = key_idx > row_idx
    probs = torch.softmax((q @ k.transpose(2, 3) * scaling).float()
                          .masked_fill(causal.unsqueeze(0).unsqueeze(0), float("-inf")), dim=-1)
    head_probs = probs[0, args.head]

    candidates = []
    unmapped = []
    cursor = 0
    for message_index, message in enumerate(messages):
        role = str(message.get("role"))
        if role == "system":
            continue
        content = str(message.get("content") or "")
        if not content.strip():
            continue
        message_start = prompt_text.find(content, cursor)
        if message_start < 0:
            message_start = prompt_text.find(content)
        if message_start < 0:
            unmapped.append({"message_index": message_index, "role": role, "chars": len(content),
                             "reason": "content_not_found_in_rendered_prompt"})
            continue
        cursor = message_start + len(content)
        fragments, truncated = scan_fragments(content)
        if truncated:
            unmapped.append({"message_index": message_index, "role": role, "reason": "fragment_cap_hit"})
        for local_start, local_end, text in fragments:
            prompt_start = message_start + local_start
            prompt_end = message_start + local_end
            tokens = token_span(offsets, prompt_start, prompt_end)
            if tokens is None:
                unmapped.append({"message_index": message_index, "role": role,
                                 "reason": "no_tokens", "message_char_span": [local_start, local_end]})
                continue
            candidates.append({
                "candidate_id": None,
                "class": "tool_return" if role == "tool" else ("prior_output" if role == "assistant" else "task_facts"),
                "role": role,
                "message_index": message_index,
                "message_char_span": [local_start, local_end],
                "prompt_char_span": [prompt_start, prompt_end],
                "token_span": [tokens[0], tokens[1]],
                "text": text,
                "source": "history_message",
            })

    if prefix.strip():
        pref_tokens = (P, P + C)
        candidates.append({
            "candidate_id": None, "class": "prior_output_current", "role": "assistant",
            "message_index": None, "message_char_span": [0, len(prefix)],
            "prompt_char_span": None, "token_span": [pref_tokens[0], pref_tokens[1]],
            "text": prefix, "source": "current_output_prefix",
            "response_char_span": [0, len(prefix)],
        })

    unique, seen_positions = [], set()
    for candidate in candidates:
        key = (candidate["message_index"], tuple(candidate["token_span"]))
        if key in seen_positions:
            continue
        seen_positions.add(key)
        unique.append(candidate)
    candidates = unique

    mass = []
    for candidate in candidates:
        start, end = candidate["token_span"]
        mass.append(float(head_probs[:, start:end].sum()))
    total = sum(mass) or 1.0
    rows_count = len(rows_to_read)
    covered = torch.zeros(len(full_ids), dtype=torch.bool, device="cuda")
    for candidate in candidates:
        start, end = candidate["token_span"]
        covered[start:end] = True
    covered_mass = float(head_probs[:, covered].sum())
    for index, candidate in enumerate(candidates):
        candidate["candidate_id"] = f"c{index:04d}"
        candidate["score"] = round(mass[index], 6)
        candidate["abs_share"] = round(mass[index] / rows_count, 8)
        candidate["norm_share"] = round(mass[index] / total, 8)
        candidate["excerpt"] = candidate["text"][:200]
    ranked = sorted(candidates, key=lambda item: (-item["score"], item["candidate_id"]))

    record = {
        "schema": "memoryflow.replay_rich.v2",
        "run": str(run),
        "run_identity": {"calls_sha256": hashlib.sha256((run / "calls.jsonl").read_bytes()).hexdigest(),
                         "call": args.call, "messages": len(messages)},
        "call": args.call,
        "target": target,
        "target_char_span": [pos, pos + len(target)],
        "target_occurrences": len(re.findall(re.escape(target), response)),
        "target_token_range": [P + C - 1, P + C - 1 + T],
        "prompt_tokens": P, "prefix_tokens": C, "target_tokens": T, "rows": rows_count,
        "classes": {cls: sum(1 for c in candidates if c["class"] == cls)
                    for cls in ("task_facts", "tool_return", "prior_output", "prior_output_current")},
        "candidate_mass_sum": round(total, 6),
        "covered_mass_union": round(covered_mass, 6),
        "uncovered_share_union": round(1 - covered_mass / rows_count, 8),
        "overlap_mass": round(total - covered_mass, 6),
        "unmapped": unmapped,
        "candidates": ranked,
    }
    pathlib.Path(args.out).write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"event": "RICH2_DONE", "call": args.call, "rows": rows_count,
                      "classes": record["classes"], "unmapped": len(unmapped),
                      "candidates": len(candidates), "covered_union": record["covered_mass_union"],
                      "overlap": record["overlap_mass"],
                      "top": [(c["class"], c["message_index"], round(c["score"], 3)) for c in ranked[:6]],
                      "out": args.out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
