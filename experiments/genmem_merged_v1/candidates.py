"""Freeze model-independent material candidates from recorded full-history input.

Repeated appearances stay in the replay matrices. Ranking identities merge only
identical material text with the same decoded fragment interval.
"""
import argparse
import bisect
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provenance_v2.span_views import views
if __package__:
    from .intake import digest, read, resolve, write
else:
    from intake import digest, read, resolve, write


def material_id(text):
    return "material:"+hashlib.sha256(text.encode()).hexdigest()


def source_window(body, source, structured, body_views=None):
    left, right = source["span"]
    for view in body_views if body_views is not None else views(body, structured=structured):
        start, stop = view.span(0, len(view.text))
        if start <= left < right <= stop:
            if view.offsets is None:
                a, b = left-view.start, right-view.start
            else:
                a, b = bisect.bisect_left(view.offsets, left), bisect.bisect_left(view.offsets, right)
                if view.offsets[a] != left or view.offsets[b] != right:
                    raise ValueError("Candidate boundary splits a JSON escape")
            text = view.text[a:b]
            if text != source.get("match_text", source["text"]):
                raise ValueError("Decoded candidate differs from recorded replay column")
            return {"artifact_id": material_id(view.text), "start": a, "end": b, "text": text}
    raise ValueError("Candidate has no recorded text view")


def prepare(args):
    targets = read(args.dataset/"targets.json")
    labels = {r["legacy_id"]: r for r in read(args.review/"root_labels.json")}
    records, cases = [], []
    trace_cache, job_cache, view_cache, window_cache = {}, {}, {}, {}
    for row in targets:
        sample = row["sample_id"]
        if sample not in trace_cache:
            trace_cache[sample] = read(args.dataset/"traces"/(sample+".json"))
            job_cache[sample] = read(args.replay/sample/"inputs.json")
        trace = trace_cache[sample]
        jobs = job_cache[sample]
        job = next(j for j in jobs if j["event"] == row["target"]["event"])
        candidates = {}
        for source in job["sources"]:
            if source["role"] not in {"tool", "user"} or source.get("section") != "content":
                continue
            event = source["message_index"]
            body = trace["memory_stack_log"][event].get("content") or ""
            structured = source["role"] == "tool" and body.lstrip().startswith(("{", "["))
            if (sample, event) not in view_cache:
                view_cache[sample, event] = views(body, structured=structured)
            key = (sample, event, *source["span"])
            if key not in window_cache:
                window_cache[key] = source_window(body, source, structured, view_cache[sample, event])
            window = window_cache[key]
            cid = f"{window['artifact_id']}:{window['start']}:{window['end']}"
            candidate = candidates.setdefault(cid, {"canonical_id": cid, **window, "occurrences": []})
            candidate["occurrences"].append({"event": event, "span": source["span"]})
        groups = []
        for group in labels[row["legacy_id"]]["evidence_groups"]:
            items = []
            for item in group["items"]:
                alternatives = []
                for alt in item["alternatives"]:
                    _, body, _ = resolve(trace["memory_stack_log"], alt["location"])
                    alternatives.append({**alt, "artifact_id": material_id(body)})
                items.append({"alternatives": alternatives})
            groups.append({"group_id": group["id"], "items": items})
        records.append({"id": row["legacy_id"], "target": row["target"]["text"],
                        "query": "Identify earlier text relevant to the supplied statement.", "language": "en",
                        "sources": [{"id": cid, "text": c["text"]} for cid, c in candidates.items()]})
        cases.append({"case_id": row["legacy_id"], "sample_id": row["sample_id"], "call_id": job["id"],
                      "target": row["target"], "candidates": list(candidates.values()),
                      "evidence_groups": groups, "review_status": labels[row["legacy_id"]]["review_status"]})
    args.output.mkdir()
    write(args.output/"inputs/records.json", records)
    write(args.output/"cases.json", cases)
    identity = digest(args.dataset/"targets.json")
    write(args.output/"inputs/manifest.json", {"schema": "memoryflow.genmem.common_candidates.v1",
          "archive": {"path": str(args.dataset/"targets.json"), "archive_sha256": identity,
                      "note": "Merged target manifest; both original archives bound by intake.json."},
          "expected_archive_sha256": identity, "files": {"records.json": digest(args.output/"inputs/records.json")},
          "target_order": [r["id"] for r in records],
          "counts": {"candidate_counts": {r["id"]: len(r["sources"]) for r in records}}})
    write(args.output/"identity.json", {"targets_sha256": identity, "review_sha256": digest(args.review/"root_labels.json"),
          "records_sha256": digest(args.output/"inputs/records.json"), "cases_sha256": digest(args.output/"cases.json"),
          "targets": len(records), "candidate_counts": {r["id"]: len(r["sources"]) for r in records},
          "candidate_rule": "All recorded user/tool content fragments before target; identical material and decoded interval merge across appearances. Same frozen candidates for all models and baselines.",
          "grading": "Root labels only; semantic chain labels remain separately reviewed. Four incomplete material claims retained."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("dataset", "review", "replay", "output"):
        parser.add_argument("--"+key, type=Path, required=True)
    prepare(parser.parse_args())
