"""Freeze a small trajectory-level development cohort without method scores."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def required(case):
    return min(len(g["items"]) for g in case["evidence_groups"])


def choose(cases, mandatory):
    by_sample = defaultdict(list)
    for case in cases:
        if case["evidence_groups"]:
            by_sample[case["sample_id"]].append(case)
    selected = [mandatory]
    selected.append(next(s for s in sorted(by_sample) if s not in selected and any(required(c)>=3 for c in by_sample[s])))
    selected.append(next(s for s in sorted(by_sample) if s not in selected
                         and any(required(c)==1 for c in by_sample[s]) and any(required(c)>=3 for c in by_sample[s])))
    return selected


def freeze(common, config_path, output):
    config = read(config_path)
    identity = read(common/"identity.json")
    if sha(common/"cases.json") != identity["cases_sha256"]:
        raise ValueError("Frozen cases changed")
    cases = read(common/"cases.json")
    selected = choose(cases, config["mandatory_sample"])
    dev = [c for c in cases if c["sample_id"] in selected]
    protocol = {"config": config, "config_sha256": sha(config_path),
                "cases_sha256": sha(common/"cases.json"), "records_sha256": sha(common/"inputs/records.json"),
                "development_samples": selected,
                "development_target_ids": [c["case_id"] for c in dev if c["evidence_groups"]],
                "retained_unscored_dev_ids": [c["case_id"] for c in dev if not c["evidence_groups"]],
                "not_run_samples": sorted({c["sample_id"] for c in cases}-set(selected)),
                "support_counts": dict(Counter(str(min(3,required(c))) for c in dev if c["evidence_groups"])),
                "selection": "Mandatory coach trajectory; lexicographically first other >=3-item trajectory; first other trajectory with both single and >=3-item targets. Labels only, no method ranks.",
                "scope": "Previously evaluated GenMem pool only; all targets of a trajectory stay together. Prior v1 results are known; remainder is not newly unseen validation. Reserve/Blind are not inputs."}
    output.mkdir(parents=True)
    write(output/"protocol.json", protocol)
    return protocol
