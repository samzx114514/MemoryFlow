"""Choose source-collection tasks using public inputs, before method scores."""
import hashlib
import json
from pathlib import Path


def save_new(path, value):
    content = (json.dumps(value, ensure_ascii=False, indent=2)+"\n").encode()
    if path.exists() and path.read_bytes() != content:
        raise ValueError(f"Existing selection has a different identity: {path}")
    if not path.exists():
        path.write_bytes(content)


def task_file(public, row):
    path = public / f"mf-src-20261111-{row['id']}.jsonl"
    content = (json.dumps(row, ensure_ascii=False)+"\n").encode()
    if path.exists() and path.read_bytes() != content:
        raise ValueError("Task-file identity conflict")
    if not path.exists():
        path.write_bytes(content)
    return {"id": row["id"], "task_file": str(path), "sha256": hashlib.sha256(content).hexdigest(),
            "document_bytes": sum((public / item["path"]).stat().st_size for item in row["files"])}


def order(rows):
    return sorted(rows, key=lambda row: hashlib.sha256(("mf11-analysis:"+row["id"]).encode()).hexdigest())


def prepare(root):
    earlier = Path("/data1/songzhengxing_intern_dccv2/mf_yf_batch12_20261109")
    excluded = {job["task_id"] for job in json.loads((earlier / "frozen.json").read_text())["jobs"]}
    excluded.add("cuad_ambiguity_04dc45f69b796b86")
    public = earlier / "assets/clause/test/public"
    rows = [json.loads(line) for line in (public / "clause-files-l1-tasks.jsonl").read_text().splitlines() if line.strip()]
    chosen, documents = [], set()
    for row in order(rows):
        size = sum((public / item["path"]).stat().st_size for item in row["files"])
        key = tuple(item["path"] for item in row["files"])
        if row["id"] in excluded or not 20000 <= size <= 50000 or key in documents:
            continue
        chosen.append(task_file(public, row))
        documents.add(key)
        if len(chosen) == 4:
            break
    if len(chosen) != 4:
        raise ValueError("Insufficient distinct CLAUSE source documents")
    save_new(root / "source_tasks_clause_v2.json", chosen)
    print("clause", [(row["id"], row["document_bytes"]) for row in chosen], flush=True)
    public = root / "fin-files/public"
    rows = [json.loads(line) for line in (public / "tasks.jsonl").read_text().splitlines() if line.strip()]
    excluded = {"finauditing-finre-0", "finauditing-finmr-0", "finauditing-finsm-1"}
    chosen, groups = [], set()
    for family in ("finre", "finmr", "finsm"):
        candidates = order([row for row in rows if row["id"].startswith("finauditing-"+family+"-")])
        count = 0
        for row in candidates:
            size = sum((public / item["path"]).stat().st_size for item in row["files"])
            group = row.get("group_id") or tuple(item["path"] for item in row["files"])
            if row["id"] in excluded or not 45000 <= size <= 120000 or group in groups:
                continue
            chosen.append(task_file(public, row))
            groups.add(group)
            count += 1
            if count == 2:
                break
        if count != 2:
            raise ValueError(f"Insufficient {family} source tasks")
    save_new(root / "source_tasks_fin_v2.json", chosen)
    print("finauditing", [(row["id"], row["document_bytes"]) for row in chosen], flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    prepare(parser.parse_args().root)
