"""Query reusable matrices by exact output spans and return all traced paths."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .full_batch import digest
from source_path_v1.replay_rich import token_span


def target_span(output: str, text: str, occurrence: int | None = None):
    found = [match.start() for match in re.finditer(f"(?={re.escape(text)})", output)] if text else []
    if not found:
        raise ValueError("Target text is absent")
    if occurrence is None and len(found) != 1:
        raise ValueError("Target repeats; select --occurrence or an explicit --span")
    index = 0 if occurrence is None else occurrence - 1
    if not 0 <= index < len(found):
        raise ValueError("Target occurrence out of range")
    return found[index], found[index] + len(text)


class FullQuery:
    def __init__(self, forest_path: Path, matrix_dir: Path, top_k: int, depth: int, candidate_selector=None):
        if top_k < 1 or depth < 1:
            raise ValueError("top-k and depth must be positive")
        self.matrix_dir = matrix_dir
        self.forest = json.loads(forest_path.read_text(encoding="utf-8"))
        manifest_path = matrix_dir / "manifest.json"
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if self.forest["manifest_sha256"] != digest(manifest_path):
            raise ValueError("Forest and matrix manifest do not describe the same replay")
        self.top_k, self.depth = top_k, depth
        self.candidate_selector = candidate_selector
        self.transfers, self.matrices = defaultdict(list), {}
        for link in self.forest["content_transfers"]:
            self.transfers[link["recipient_call"], link["column"]].append(link)
        self.tool_results = {(item["recipient_call"], item["message_index"]): item for item in self.forest["tool_results"]}

    def load(self, call_id):
        import numpy as np

        if call_id not in self.matrices:
            entry = self.manifest["calls"][call_id]
            meta_path, score_path = (self.matrix_dir / entry[key] for key in ("metadata", "scores"))
            if digest(meta_path) != entry["metadata_sha256"] or digest(score_path) != entry["scores_sha256"]:
                raise ValueError(f"Matrix integrity check failed for {call_id}")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            matrix = np.load(score_path, mmap_mode="r", allow_pickle=False)
            if matrix.shape != (meta["output_tokens"], len(meta["columns"])):
                raise ValueError(f"Matrix shape mismatch for {call_id}")
            if len(meta["output_offsets"]) != len(meta["prediction_rows"]) or len(meta["prediction_rows"]) != matrix.shape[0]:
                raise ValueError(f"Output row map mismatch for {call_id}")
            self.matrices[call_id] = meta, matrix
        return self.matrices[call_id]

    def walk(self, call_id: str, span: tuple[int, int]):
        import numpy as np

        paths = []
        roots = {}
        expanded = set()

        def trace(current, start, end, steps, score, seen):
            node = (current, start, end)
            if node in seen or len(steps) >= self.depth:
                paths.append({"steps": steps, "stop": "cycle" if node in seen else "depth_limit",
                              "next_call": current, "next_span": [start, end], "path_score": score})
                return
            meta, matrix = self.load(current)
            if not (0 <= start < end <= len(meta["output"])):
                raise ValueError(f"Invalid output span for {current}: {start}-{end}")
            rows = token_span(meta["output_offsets"], start, end)
            if rows is None:
                paths.append({"steps": steps, "stop": "no_output_tokens", "next_call": current,
                              "next_span": [start, end], "path_score": score})
                return
            left, right = rows
            expanded.add(node)
            masses = matrix[left:right].sum(axis=0, dtype=np.float64)
            first_prediction = meta["prediction_rows"][left]
            indices = sorted(range(len(masses)), key=lambda column: (-masses[column], column))
            selected = []
            for index in indices:
                column = meta["columns"][index]
                if masses[index] <= 0:
                    break
                prefix = column.get("response_char_span")
                if prefix and (prefix[1] > start or column["token_span"][1] - 1 > first_prediction):
                    continue
                selected.append(index)
                if self.candidate_selector is None and len(selected) == self.top_k:
                    break
            if self.candidate_selector is not None:
                selected = self.candidate_selector(masses, selected)
            if not selected:
                paths.append({"steps": steps, "stop": "no_positive_candidate", "next_call": current,
                              "next_span": [start, end], "path_score": score})
            for rank, index in enumerate(selected, 1):
                column = meta["columns"][index]
                local = float(masses[index])
                path_score = score * local / (right - left)
                evidence = {key: column[key] for key in ("column", "message_index", "section", "role", "text",
                                                          "token_span", "message_char_span", "prompt_char_span",
                                                          "response_char_span") if key in column}
                step = {"call_id": current, "output_span": [start, end], "output_text": meta["output"][start:end],
                        "row_slice": [left, right], "prediction_rows": [first_prediction, meta["prediction_rows"][right - 1] + 1],
                        "candidate": evidence, "score": local, "mean_attention": local / (right - left), "rank": rank}
                prefix = column.get("response_char_span")
                links = self.transfers[current, index]
                if prefix:
                    link = {"kind": "earlier_output", "producer_call": current, "producer_span": prefix}
                    trace(current, *prefix, [*steps, {**step, "transfer": link}], path_score, seen | {node})
                elif links:
                    for link in links:
                        trace(link["producer_call"], *link["producer_span"], [*steps, {**step, "transfer": link}],
                              path_score, seen | {node})
                else:
                    path = {"steps": [*steps, step], "path_score": path_score}
                    if column["role"] in {"user", "tool"}:
                        root_id = f"{current}:column{index}"
                        root = roots.setdefault(root_id, {"root_id": root_id, "call_id": current, **evidence})
                        tool = self.tool_results.get((current, column["message_index"]))
                        if tool is not None:
                            root["tool"] = tool
                        path.update(stop="material_input", root_id=root_id)
                    else:
                        path["stop"] = "no_recorded_producer"
                    paths.append(path)

        trace(call_id, *span, [], 1.0, set())
        paths.sort(key=lambda path: -path["path_score"])
        return {"schema": "memoryflow.full_query.v1", "call_id": call_id, "target_span": span,
                "target_text": self.load(call_id)[0]["output"][span[0]:span[1]], "top_k": self.top_k,
                "depth": self.depth, "expanded_spans": len(expanded), "roots": list(roots.values()), "paths": paths}
