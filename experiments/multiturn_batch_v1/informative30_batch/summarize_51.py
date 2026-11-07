import json
from pathlib import Path

base = Path(r"F:/CodexProject/MemoryFlow-research/experiments/multiturn_batch_v1/informative30_batch")
results = json.loads((base / "reports/BATCH51_20261107.json").read_text(encoding="utf-8"))
disp = json.loads((base / "dispositions.json").read_text(encoding="utf-8"))
status = {f"{r['case']}:{r['target']}": r["status"] for r in disp}
rows = [r for r in results["cases"] if status.get(r["case_id"]) in ("recorded_agent_message", "controlled")]
n = len(rows)

methods = ("last_round", "bm25_history", "head_full_history", "memoryflow")

def metrics(selected):
    out = {}
    for m in methods:
        out[m] = {
            "hit": sum(1 for r in selected if r["methods"][m]["hit_at_3"]),
            "c5": sum(1 for r in selected if r["methods"][m]["complete_at_5"]),
            "c10": sum(1 for r in selected if r["methods"][m]["complete_at_10"]),
            "complete": round(sum((r["methods"][m]["complete_rank"] or 11) for r in selected) / len(selected), 2),
            "hitrank": round(sum((r["methods"][m]["hit_rank"] or 11) for r in selected) / len(selected), 2),
        }
    return out

def paired(selected):
    out = {}
    for baseline in ("last_round", "bm25_history", "head_full_history"):
        comp = {"win": 0, "tie": 0, "loss": 0}
        hit = {"win": 0, "tie": 0, "loss": 0}
        for r in selected:
            for key, target in (("complete_rank", comp), ("hit_rank", hit)):
                left = r["methods"]["memoryflow"][key] or 11
                right = r["methods"][baseline][key] or 11
                target["win" if left < right else "tie" if left == right else "loss"] += 1
        out[baseline] = {"complete": comp, "hit": hit}
    return out

real = [r for r in rows if status.get(r["case_id"]) == "recorded_agent_message"]
controlled = [r for r in rows if status.get(r["case_id"]) == "controlled"]
insufficient = [r for r in disp if r["status"] == "control-or-insufficient"]
controls = [r for r in disp if r["status"] == "control-final-round-sufficient"]
diagnostic = [r for r in disp if r["status"] == "diagnostic-no-transmission"]

lines = []
lines.append("# informative30 51 目标整批交付（2026-11-07）")
lines.append("")
lines.append(f"**状态：** 51 个目标逐条处理：**{n} 个合格并实测**（真实中间消息 {len(real)}、受控构造 {len(controlled)}），"
             f"最终轮自足对照 {len(controls)}，证据/时序不足 {len(insufficient)}，诊断 {len(diagnostic)}。覆盖 {len({r['trajectory_case'] for r in rows})} 条轨迹。")
lines.append("")
lines.append("## 数据与口径")
lines.append("")
lines.append("- 来源：《GenMem informative30 接入预检》36 优先 + 15 跨事件；按 (case,id) 连接 tasks/candidates/GT。")
lines.append("- 时间顺序：正证据和干扰项都检查事件号；R1 全部早于真实中间消息，R2 在中间消息之后、目标之前；目标及之后不进回放。")
lines.append("- case_03:T04 的 ev10 候选不进 ev8 输入；case_01:T10 的 C0036 是 ev29 中间消息，上游改用 ev28 的 C0034。")
lines.append("- 两轮并集、每跳 5、最终 10；四方法同池。矩阵按输入冻结后评分。")
lines.append("- 旧 batch10 的 17 题单列，不并入本表。")
lines.append("")

for title, selected in (("全部合格", rows), ("真实中间消息", real), ("受控构造", controlled)):
    if not selected:
        continue
    mm = metrics(selected)
    lines.append(f"## {title}（{len(selected)} 题）")
    lines.append("")
    lines.append("| 方法 | Hit@3 | 完整@5 | 完整@10 | 平均完整名次 | 平均首个证据名次 |")
    lines.append("|---|---|---|---|---|---|")
    for m in methods:
        d = mm[m]
        lines.append(f"| {m} | {d['hit']}/{len(selected)} | {d['c5']}/{len(selected)} | {d['c10']}/{len(selected)} | {d['complete']:.2f} | {d['hitrank']:.2f} |")
    lines.append("")

lines.append("## 配对（MemoryFlow 对基线，全部合格）")
lines.append("")
lines.append("| 基线 | 完整名次 W/T/L | 首个证据 W/T/L |")
lines.append("|---|---|---|")
for baseline, v in paired(rows).items():
    c, h = v["complete"], v["hit"]
    lines.append(f"| {baseline} | {c['win']}/{c['tie']}/{c['loss']} | {h['win']}/{h['tie']}/{h['loss']} |")
lines.append("")

lines.append("## 逐题（31 题）")
lines.append("")
lines.append("| 题 | 类型 | MF 完整 | BM25 | head | last | MF A/B |")
lines.append("|---|---|---|---|---|---|---|")
for r in rows:
    kind = "真实" if status.get(r["case_id"]) == "recorded_agent_message" else "受控"
    mf = r["methods"]["memoryflow"]
    lines.append(f"| {r['case_id']} | {kind} | {mf['complete_rank'] or '—'} | {r['methods']['bm25_history']['complete_rank'] or '—'} | "
                 f"{r['methods']['head_full_history']['complete_rank'] or '—'} | {r['methods']['last_round']['complete_rank'] or '—'} | "
                 f"{mf['label_ranks'].get('A') or '—'} / {mf['label_ranks'].get('B') or '—'} |")
lines.append("")

lines.append("## 51 目标去向")
lines.append("")
lines.append("| case | target | 状态 | 原因 |")
lines.append("|---|---|---|---|")
for r in disp:
    lines.append(f"| {r['case']} | {r['target']} | {r['status']} | {r['reason']} |")
lines.append("")

(base / "reports/SUMMARY_51_20261107.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
(base / "reports/SUMMARY_51_20261107.json").write_text(json.dumps({
    "total": len(disp), "qualified": n, "real": len(real), "controlled": len(controlled),
    "controls": len(controls), "insufficient": len(insufficient), "diagnostic": len(diagnostic),
    "trajectories": len({r["trajectory_case"] for r in rows}),
    "metrics_all": metrics(rows), "metrics_real": metrics(real), "metrics_controlled": metrics(controlled),
    "paired_all": paired(rows),
}, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({"qualified": n, "real": len(real), "controlled": len(controlled), "controls": len(controls),
                  "insufficient": len(insufficient)}, ensure_ascii=False))
