"""Bind the historic 47+49 targets and labels to recorded GenMem events.

This prepares review material, not semantic chain labels or model rankings.
"""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from zipfile import ZipFile


OLD_SHA = "f465eb1cd4ff79b2d3de20c0c95562492fdd0bef18b86dc7983fa878bbaf3d33"
NEW_SHA = "d5a4e4ffa8ef717ed1b8b657422bf786d4ba21424fd34a1f729cefa80f8d8d8e"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def resolve(log, location):
    location = location.replace("#decoded", "#")
    match = re.fullmatch(r"/memory_stack_log/(\d+)/(.*)", location)
    if not match:
        raise ValueError(f"Unknown recorded location: {location}")
    event = int(match[1])
    pointer, separator, decoded = match[2].partition("#")
    text = log[event]
    for part in pointer.split("/"):
        text = text[int(part)] if isinstance(text, list) else text[part]
    if separator:
        text = json.loads(text)
        for part in decoded.strip("/").split("/"):
            text = text[int(part)] if isinstance(text, list) else text[part]
    if not isinstance(text, str):
        raise ValueError(f"Recorded location is not text: {location}")
    return event, text, location


def fragment(log, location, span):
    event, body, location = resolve(log, location)
    start, end = span["start"], span["end"]
    if not 0 <= start < end <= len(body) or body[start:end] != span["text"]:
        raise ValueError(f"Label does not match recorded text: {location} {start}:{end}")
    return {"location": location, "event": event, "start": start, "end": end,
            "text": span["text"], "recorded_action": log[event]["action"]}


def review_record(legacy_id, family, raw, target, groups):
    log = raw["memory_stack_log"]
    event = target["event"]
    if log[event]["action"] != "agent" or log[event]["content"][target["start"]:target["end"]] != target["text"]:
        raise ValueError(f"Target does not match recorded output: {legacy_id}")
    variants = [a for g in groups for item in g["items"] for a in item["alternatives"]]
    if not variants or any(a["event"] > event or (a["event"] == event and a["end"] > target["start"]) for a in variants):
        raise ValueError(f"Missing or future evidence: {legacy_id}")
    previous = [i for i, row in enumerate(log[:event]) if row["action"] == "agent"]
    first = min(a["event"] for a in variants)
    latest = previous[-1] if previous else -1
    direct = any(all(any(a["recorded_action"] in {"tool", "user"} and a["event"] > latest
                         for a in item["alternatives"]) for item in g["items"]) for g in groups)
    return {"legacy_id": legacy_id, "family": family, "sample_id": raw["sample_id"],
            "dataset": raw["dataset"], "target": target, "evidence_groups": groups,
            "candidate_middle_events": [i for i in previous if first < i],
            "generated_evidence_events": sorted({a["event"] for a in variants if a["recorded_action"] == "agent"}),
            "complete_from_latest_tool_batch": direct,
            "chain_review": "pending_semantic_review",
            "visibility": "event order recorded; complete model requests unavailable"}


def unique_targets(rows):
    kept, duplicates = {}, []
    for row in rows:
        t = row["target"]
        key = (row["sample_id"], t["event"], t["start"], t["end"])
        if key in kept:
            if kept[key]["target"]["text"] != t["text"]:
                raise ValueError("Conflicting target text at the same recorded position")
            duplicates.append({"legacy_id": row["legacy_id"], "same_as": kept[key]["legacy_id"]})
        else:
            row["id"] = f"{row['sample_id']}:ev{t['event']}:{t['start']}-{t['end']}"
            kept[key] = row
    return list(kept.values()), duplicates


def collect(args):
    if digest(args.old_archive) != OLD_SHA or digest(args.new_archive) != NEW_SHA:
        raise ValueError("Historic source archive identity changed")
    ids = set(read(args.old_metrics)["coverage"]["ids"])
    traces, rows, raw_checks = {}, [], []
    with ZipFile(args.old_archive) as archive, args.raw_history.open("rb") as history:
        prefix = "genmem_batch10_selection_v1/"
        labels = json.loads(archive.read(prefix+"contextual64_v4/ground_truth.json"))["annotations"]
        labels = [row for row in labels if row["target_id"] in ids and row["case"] not in {"case_02", "case_08"}]
        if len(labels) != 47:
            raise ValueError("The historic evaluation identity must contain exactly 47 targets")
        flows = {case: json.loads(archive.read(prefix+case+"/flow.json")) for case in sorted({x["case"] for x in labels})}
        for flow in flows.values():
            provenance = flow["provenance"]
            history.seek(provenance["byte_offset"])
            block = history.read(provenance["byte_length"])
            raw = json.loads(block)
            if raw["memory_stack_log"] != [e["recorded_event"] for e in flow["events"]]:
                raise ValueError("Archived events differ from the original NAS trajectory")
            traces[raw["sample_id"]] = raw
            raw_checks.append({"sample_id": raw["sample_id"], "byte_offset": provenance["byte_offset"],
                               "byte_length": len(block), "block_sha256": hashlib.sha256(block).hexdigest(),
                               "event_match": True})
        for label in labels:
            flow = flows[label["case"]]
            raw = traces[flow["run_metadata"]["sample_id"]]
            artifacts = {a["id"]: a for a in flow["artifacts"]}
            groups = []
            for group in label["answer_groups"]:
                if group.get("coverage") != "full":
                    continue
                spans = [s for bundle in group["self_contained_evidence"] for s in bundle["fragments"]]
                items = [{"alternatives": [fragment(raw["memory_stack_log"], artifacts[s["artifact_id"]]["anchor"]["json_pointer"], s)]} for s in spans]
                groups.append({"id": group["id"], "items": items})
            target = {**label["target"], "event": label["target"]["event_index"]}
            rows.append(review_record(label["target_id"], "old47", raw, target, groups))
    with ZipFile(args.new_archive) as archive:
        prefix = "genmem_informative30_v1/"
        index = json.loads(archive.read(prefix+"raw_runs/index.json"))["cases"]
        raw_by_case = {r["case"]: json.loads(archive.read(prefix+r["raw_file"])) for r in index}
    entries = read(args.new_frozen/"manifest.json")["cases"]
    if len(entries) != 49:
        raise ValueError("The expanded historic source pool must contain exactly 49 targets")
    for entry in entries:
        case = read(args.new_frozen/entry["case_path"])
        raw = raw_by_case[case["trajectory_case"]]
        traces[raw["sample_id"]] = raw
        locations = {c["artifact_id"]: c["location"] for c in case["candidates"]}
        groups = [{"id": g["group_id"], "items": [{"alternatives": [fragment(raw["memory_stack_log"], locations[a["artifact_id"]], a) for a in item["alternatives"]]} for item in g["items"]]} for g in case["evidence_groups"] if g.get("coverage") == "full"]
        target = {**case["target"], "event": case["provenance"]["target_event"]}
        rows.append(review_record(case["case_id"], "new49", raw, target, groups))
    rows, duplicates = unique_targets(rows)
    args.output.mkdir()
    write(args.output/"targets.json", rows)
    for sample_id, raw in traces.items():
        write(args.output/"traces"/(sample_id+".json"), {k: raw[k] for k in ("sample_id", "dataset", "question", "memory_stack_log")})
    report = {"schema": "memoryflow.genmem_merged.intake.v1", "initial_targets": 96,
              "unique_targets": len(rows), "families": dict(Counter(r["family"] for r in rows)),
              "trajectories": len(traces), "datasets": dict(Counter(r["dataset"] for r in rows)),
              "with_candidate_middle_events": sum(bool(r["candidate_middle_events"]) for r in rows),
              "generated_evidence_targets": sum(bool(r["generated_evidence_events"]) for r in rows),
              "complete_from_latest_tool_batch": sum(r["complete_from_latest_tool_batch"] for r in rows),
              "duplicates": duplicates, "old_nas_checks": raw_checks,
              "input_sha256": {str(p): digest(p) for p in (args.old_archive, args.new_archive, args.old_metrics, args.new_frozen/"manifest.json")},
              "targets_sha256": digest(args.output/"targets.json"), "chain_labels_frozen": False,
              "note": "Structural intake only. Recorded intermediate text still needs semantic review; no generated bridge or method score used."}
    write(args.output/"intake.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("old_archive", "old_metrics", "new_archive", "new_frozen", "raw_history", "output"):
        parser.add_argument("--"+name.replace("_", "-"), type=Path, required=True)
    collect(parser.parse_args())
