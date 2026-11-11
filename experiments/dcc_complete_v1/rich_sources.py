"""Map recorded content, JSON strings and historical tool calls to exact tokens."""
import copy

from provenance_v2.span_views import fragments, views
from pipeline import offsets, token_span


def full_sources(tokenizer, request, ids, basic_sources, generated):
    prompt, prompt_offsets = offsets(tokenizer, ids)
    messages = copy.deepcopy(request["messages"])
    sections = []
    by_message = {}
    for source in basic_sources:
        by_message.setdefault(source["message_index"], source)
    for index, source in by_message.items():
        value = messages[index].get("content") or ""
        begin = len(value)-len(value.lstrip())
        stop = len(value.rstrip())
        base = source["prompt_span"][0]-source["span"][0]
        sections.append((index, "content", base+begin, base+stop, base))
    # Name markers identify tool sections for both Qwen2 JSON and Qwen3 XML.
    markers = []
    for index, message in enumerate(messages):
        for number, tool in enumerate(message.get("tool_calls") or []):
            function = tool.get("function") or {"name": tool["name"], "arguments": tool.get("args", {})}
            import json
            arguments = function.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            marker = f"MF11ToolName{index}x{number}v983q"
            markers.append((index, marker, function["name"]))
            tool["function"] = {**function, "name": marker, "arguments": arguments}
        message["content"] = message.get("content") or ""
    probe = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                          tools=request.get("tools") or None, enable_thinking=False)
    for index, marker, name in markers:
        if probe.count(marker) != 1:
            raise ValueError("Historical tool marker is not unique")
        position = probe.index(marker)
        start = probe.rfind("<tool_call>", 0, position)
        stop = probe.find("</tool_call>", position)
        if start < 0 or stop < 0:
            raise ValueError("Historical tool call has no bounded template section")
        stop += len("</tool_call>")
        probe = probe.replace(marker, name, 1)
        stop += len(name)-len(marker)
        sections.append((index, "tool_calls", start, stop, None))
    if probe != prompt:
        raise ValueError("Historical tool sections changed the actual input")
    result = []
    for index, section, start, stop, base in sorted(sections):
        role = messages[index]["role"]
        value = prompt[start:stop]
        structured = section == "tool_calls" or (role == "tool" and value.lstrip().startswith(("{", "["))) or "<sp-subagent-task>" in value
        for view in views(value, start=start, structured=structured):
            for match_text, (left, right), match_offsets in fragments(view):
                interval = token_span(prompt_offsets, left, right)
                if interval is None:
                    continue
                result.append({"source_id": f"m{index}:{section}:{left-start}:{right-start}",
                               "message_index": index, "section": section, "role": role,
                               "text": prompt[left:right], "match_text": match_text, "match_offsets": match_offsets,
                               "span": [left-base, right-base] if base is not None else None,
                               "prompt_span": [left, right], "token_span": interval})
    text, output_offsets = offsets(tokenizer, generated)
    for view in views(text, structured=True):
        for match_text, (left, right), _ in fragments(view):
            interval = token_span(output_offsets, left, right)
            if interval is not None:
                result.append({"source_id": f"output:{left}:{right}", "message_index": None,
                               "section": "output_prefix", "role": "assistant", "text": text[left:right],
                               "match_text": match_text, "span": None, "prompt_span": None,
                               "response_char_span": [left, right],
                               "token_span": [len(ids)+interval[0], len(ids)+interval[1]]})
    return result
