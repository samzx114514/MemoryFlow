"""Lossless structured-result transport repairs; raw generation stays unchanged."""
import json


def recorded_tool_calls(message):
    calls = []
    for tool in message.get("tool_calls") or []:
        function = tool["function"]
        arguments = function["arguments"]
        try:
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
            valid = True
        except json.JSONDecodeError:
            valid = False
        calls.append({"id": tool["id"], "name": function["name"], "args": arguments,
                      "arguments_valid_json": valid})
    return calls


def structured_value(value):
    for _ in range(3):
        if isinstance(value, (dict, list)):
            return value
        if not isinstance(value, str):
            return None
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            try:
                value = json.loads('"'+value+'"')
            except json.JSONDecodeError:
                return None
    return value if isinstance(value, (dict, list)) else None


def normalize(response, request, benchmark):
    schemas = {tool["function"]["name"]: tool["function"]["parameters"] for tool in request.get("tools") or []}
    changes = []
    for choice in response.get("choices") or []:
        message = choice["message"]
        for tool in message.get("tool_calls") or []:
            function = tool["function"]
            if function["name"] != "write_file":
                continue
            prop = schemas.get("write_file", {}).get("properties", {}).get("json_content", {})
            allowed = {part.get("type") for part in prop.get("anyOf", [])}
            if not {"object", "array"} <= allowed or "string" in allowed:
                continue
            try:
                arguments = json.loads(function["arguments"])
            except json.JSONDecodeError:
                continue
            value = arguments.get("json_content")
            if not isinstance(value, str):
                continue
            decoded = structured_value(value)
            if decoded is not None:
                arguments["json_content"] = decoded
                function["arguments"] = json.dumps(arguments, ensure_ascii=False)
                changes.append({"tool_call_id": tool["id"], "field": "json_content", "repair": "decode_complete_structured_value"})
        if benchmark == "clause" and not message.get("tool_calls"):
            text = message.get("content") or ""
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            keys = {"artifact_content", "artifact_path", "output_path", "artifact_type"}
            if isinstance(value, dict) and set(value) <= keys and isinstance(value.get("artifact_content"), list):
                message["content"] = json.dumps(value["artifact_content"], ensure_ascii=False)
                changes.append({"field": "content", "repair": "unwrap_existing_artifact_content_array"})
    return changes
