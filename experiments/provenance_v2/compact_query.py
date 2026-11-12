"""Development-only DAG query: exact path sums without enumerating all paths.

The default FullQuery and author citation implementation remain unchanged.
"""
from collections import Counter, defaultdict
import time

from .full_query import FullQuery
from source_path_v1.replay_rich import token_span


class QueryLimit(RuntimeError):
    pass


class CompactQuery(FullQuery):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.local_cache = {}
        self.call_order = {call: i for i, call in enumerate(self.manifest["calls"])}

    def _local(self, node):
        import numpy as np

        self.used_nodes[node] = None
        self._check()
        if node in self.local_cache:
            self.stats["local_cache_hits"] += 1
            return self.local_cache[node]
        self.stats["local_reads"] += 1
        current, start, end = node
        meta, matrix = self.load(current)
        if not 0 <= start < end <= len(meta["output"]):
            raise ValueError(f"Invalid output span: {node}")
        rows = token_span(meta["output_offsets"], start, end)
        entry = {"call_id": current, "span": [start, end], "row_slice": rows, "edges": []}
        if rows is None:
            entry["stop"] = "no_output_tokens"
        else:
            left, right = rows
            masses = matrix[left:right].sum(axis=0, dtype=np.float64)
            first_prediction = meta["prediction_rows"][left]
            selected = []
            for index in sorted(range(len(masses)), key=lambda i: (-masses[i], i)):
                if masses[index] <= 0:
                    break
                col = meta["columns"][index]
                prefix = col.get("response_char_span")
                if prefix and (prefix[1] > start or col["token_span"][1]-1 > first_prediction):
                    continue
                selected.append(index)
                if self.candidate_selector is None and len(selected) == self.top_k:
                    break
            if self.candidate_selector is not None:
                selected = self.candidate_selector(masses, selected)
            if not selected:
                entry["stop"] = "no_positive_candidate"
            for rank, index in enumerate(selected, 1):
                col = meta["columns"][index]
                evidence = {k: col[k] for k in ("column", "message_index", "section", "role", "text",
                            "token_span", "message_char_span", "prompt_char_span", "response_char_span") if k in col}
                local = float(masses[index])
                step = {"call_id": current, "output_span": [start, end], "output_text": meta["output"][start:end],
                        "row_slice": [left, right], "prediction_rows": [first_prediction, meta["prediction_rows"][right-1]+1],
                        "candidate": evidence, "score": local, "mean_attention": local/(right-left), "rank": rank}
                prefix = col.get("response_char_span")
                links = ([{"kind": "earlier_output", "producer_call": current, "producer_span": prefix}]
                         if prefix else self.transfers[current, index])
                if links:
                    for link in links:
                        child = (link["producer_call"], *link["producer_span"])
                        # Actual full-replay forests only go to earlier calls or earlier output.
                        earlier = self.call_order[child[0]] < self.call_order[current]
                        same_prior = child[0] == current and child[2] <= start and child[1] < start
                        if not (earlier or same_prior):
                            raise QueryLimit(f"noncausal transfer: {node} -> {child}")
                        entry["edges"].append({"child": child, "weight": step["mean_attention"],
                                               "step": {**step, "transfer": link}})
                elif col["role"] in {"tool", "user"}:
                    root_id = f"{current}:column{index}"
                    root = {"root_id": root_id, "call_id": current, **evidence}
                    tool = self.tool_results.get((current, col["message_index"]))
                    if tool is not None:
                        root["tool"] = tool
                    entry["edges"].append({"root": root, "weight": step["mean_attention"], "step": step})
                else:
                    entry["edges"].append({"stop": "no_recorded_producer", "weight": step["mean_attention"], "step": step})
        self.local_cache[node] = entry
        return entry

    def _check(self):
        for name, value in [("max_nodes", len(self.used_nodes)), ("max_states", len(self.memo)),
                            ("max_root_entries", self.stats["root_cache_entries"])]:
            if value > self.limits[name]:
                raise QueryLimit(f"{name} exceeded: {value}")
        if time.perf_counter()-self.started > self.limits["wall_seconds"]:
            raise QueryLimit("wall_seconds exceeded")

    def walk(self, call_id, span, root_key=None, limits=None):
        self.started = time.perf_counter()
        self.limits = {"max_nodes": 2000, "max_states": 20000, "max_root_entries": 500000, "wall_seconds": 30,
                       **(limits or {})}
        self.used_nodes, self.memo, self.raw_roots = {}, {}, {}
        self.stats = {"local_reads": 0, "local_cache_hits": 0, "state_cache_hits": 0,
                      "root_cache_entries": 0, "state_edge_visits": 0}
        root_key = root_key or (lambda root: root["root_id"])

        def solve(node, remaining):
            self._check()
            state = (node, remaining)
            if state in self.memo:
                self.stats["state_cache_hits"] += 1
                return self.memo[state]
            if remaining == 0:
                result = ({}, {}, Counter(depth_limit=1))
            else:
                entry = self._local(node)
                totals, best, stops = defaultdict(float), {}, Counter()
                if entry.get("stop"):
                    stops[entry["stop"]] += 1
                for edge in entry["edges"]:
                    self.stats["state_edge_visits"] += 1
                    weight, step = edge["weight"], edge["step"]
                    if "root" in edge:
                        root = edge["root"]
                        self.raw_roots[root["root_id"]] = root
                        key = root_key(root)
                        totals[key] += weight
                        candidate = (weight, (step,), root["root_id"])
                        if key not in best or weight > best[key][0]:
                            best[key] = candidate
                        stops["material_input"] += 1
                    elif "child" in edge:
                        scores, paths, child_stops = solve(tuple(edge["child"]), remaining-1)
                        stops.update(child_stops)
                        for key, value in scores.items():
                            totals[key] += weight*value
                            candidate = (weight*paths[key][0], (step,)+paths[key][1], paths[key][2])
                            if key not in best or candidate[0] > best[key][0]:
                                best[key] = candidate
                    else:
                        stops[edge["stop"]] += 1
                result = (dict(totals), best, stops)
            self.memo[state] = result
            self.stats["root_cache_entries"] += len(result[0])
            self._check()
            return result

        reason = None
        try:
            scores, best, stops = solve((call_id, *span), self.depth)
            status = "complete"
        except QueryLimit as error:
            status, reason, scores, best, stops = "unfinished", str(error), {}, {}, Counter()
        paths = [{"steps": list(value[1]), "path_score": value[0], "root_id": value[2],
                  "canonical_root_id": key, "stop": "material_input"} for key, value in best.items()]
        paths.sort(key=lambda path: -path["path_score"])
        graph = [self.local_cache[n] for n in self.used_nodes if n in self.local_cache]
        return {"schema": "memoryflow.compact_query.dev.v1", "status": status, "reason": reason,
                "call_id": call_id, "target_span": list(span), "top_k": self.top_k, "depth": self.depth,
                "root_scores": scores, "roots": list(self.raw_roots.values()), "paths": paths,
                "paths_are_representative": True, "path_count": sum(stops.values()) if status == "complete" else None,
                "path_stop_counts": dict(stops), "expanded_spans": sum(g["row_slice"] is not None for g in graph),
                "states": len(self.memo), "graph": graph, "stats": dict(self.stats),
                "limits": self.limits, "query_seconds": time.perf_counter()-self.started}
