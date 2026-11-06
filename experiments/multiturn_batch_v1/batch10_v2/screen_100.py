import csv
import json
from pathlib import Path

root = Path(r"F:/CodexProject/MemoryFlow-research")
gt_path = root / "artifacts/raw/genmem_batch10_v3/gt100/ground_truth_v2/ground_truth.jsonl"
rows = [json.loads(line) for line in gt_path.read_text(encoding="utf-8").splitlines() if line.strip()]

built_v2 = {
    "genmem_177236211632d6b8:selected_02",
    "genmem_874c34ceb20bf193:selected_05",
    "genmem_940c258011aac604:selected_10",
    "genmem_9f963d36b4935b97:selected_01",
    "genmem_58452c40de4bdcb9:selected_03",
    "genmem_40dc9b8b15c0c5b8:selected_04",
    "genmem_5c054943b1a987e0:selected_07",
    "genmem_f46a08bc62ee9b37:selected_01",
}
built_prev = {
    "genmem_874c34ceb20bf193:selected_03",
    "genmem_874c34ceb20bf193:selected_06",
    "genmem_874c34ceb20bf193:selected_09",
}

def group_stats(groups):
    group_count = len(groups)
    max_items = 0
    multi_event = 0
    for group in groups:
        items = group.get("all_of") or []
        max_items = max(max_items, len(items))
        events = {item.get("primary", {}).get("event_index") for item in items}
        events.discard(None)
        if len(items) >= 2 and len(events) >= 2:
            multi_event += 1
    return group_count, max_items, multi_event

out = []
for row in rows:
    tid = row["target_id"]
    case = row["case"]
    text = row["target"]["text"]
    status = row["reference_status"]
    if status == "full_explanation_found":
        groups = row.get("answer_groups") or []
        gc, mi, me = group_stats(groups)
        if tid in built_v2:
            code, reason = "built-v2", "首批 8 题之一（两轮受控）"
        elif tid in built_prev:
            code, reason = "built-prev", "batch10 三题表已用"
        elif me > 0:
            code, reason = "candidate-full", f"{me} 个跨事件组，最大 {mi} 项"
        else:
            code, reason = "excluded-single-event", "无跨事件组"
    else:
        groups = row.get("partial_support_groups") or []
        gc, mi, me = group_stats(groups)
        if me > 0:
            code, reason = "candidate-partial", f"partial 组跨事件（{me} 组），需补标"
        else:
            code, reason = "excluded-partial", "只有 partial 单事件/待核"
    out.append({
        "case": case,
        "target_id": tid,
        "target": text.replace("\n", " ")[:160],
        "reference_status": status,
        "status": code,
        "groups": gc,
        "max_items": mi,
        "multi_event_groups": me,
        "reason": reason,
    })

out_dir = root / "experiments/multiturn_batch_v1/batch10_v2/reports"
out_dir.mkdir(parents=True, exist_ok=True)
with (out_dir / "SCREENING_100_20261106.csv").open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(out[0]))
    writer.writeheader()
    writer.writerows(out)

from collections import Counter
counts = Counter(row["status"] for row in out)
lines = [
    "# GenMem batch10 100 目标筛选清单（第一版）",
    "",
    "来源：`ground_truth_v2/ground_truth.jsonl`（64 full + 36 partial）。"
    "本表是筛选清单，不是全部标注完成；partial 36 题只标出可补标候选，未当作已标注。",
    "",
    "## 状态计数",
    "",
    "| 状态 | 数量 |",
    "|---|---|",
]
for key in ("built-v2", "built-prev", "candidate-full", "excluded-single-event", "candidate-partial", "excluded-partial"):
    lines.append(f"| {key} | {counts.get(key, 0)} |")
lines.extend(["", "## 逐目标", "", "| case | target | status | 组/最大项/跨事件组 | 目标 | 备注 |", "|---|---|---|---|---|---|"])
for row in out:
    lines.append(
        f"| {row['case']} | {row['target_id'].split(':')[-1]} | {row['status']} | "
        f"{row['groups']}/{row['max_items']}/{row['multi_event_groups']} | {row['target'][:90]} | {row['reason']} |"
    )
(out_dir / "SCREENING_100_20261106.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(json.dumps(dict(counts), ensure_ascii=False, indent=1))
