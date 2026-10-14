from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


# These judgments were authored after reading each sampled Target and every
# corresponding gold Source Memory. They are intentionally about parse/mapping
# plausibility and text quality, not factual citation support.
JUDGMENTS = {
    "factstruct:5882202a-7df2-4f82-b8c9-60ce9ffd284f:target_0057": (True, False, "noisy", "Target uses the unresolved phrase ‘这一转变’; the AI/robotics article is readable but only gives broad industry context."),
    "factstruct:9a11d8a3-c8e9-4e42-9b48-4a74e285466d:target_0064": (True, True, "noisy", "The Target is a concrete AGV ultrasonic-sensor claim, while the broad non-contact-sensor article is truncated before the most relevant technical detail."),
    "factstruct:3c4492ee-2837-466a-a5a2-f0c29f41891f:target_0164": (False, False, "noisy", "The Source discusses CD8 T-cell differentiation but the visible Memory never identifies PD-1, and ‘这种互作’ lacks its antecedent."),
    "factstruct:8bcb1d09-ab86-450c-a7fc-7a849bca4bdb:target_0075": (True, True, "noisy", "The HGT review directly discusses metazoan transfer and desiccation-related conditions, though repository metadata and a DOI fragment add noise."),
    "factstruct:a50c8caa-f1c5-4d94-8850-e875997eaebc:target_0031": (False, True, "noisy", "The Target names a specific Moscow memorial, but the Source is only a generic OCR-heavy slide deck about historical narrative construction."),
    "factstruct:bdf64263-7f9e-4ed8-8ae9-a2e6a5c33184:target_0053": (True, True, "good", "The clean motor-shaft forging abstract makes the hollow-structure and stress-concentration pairing easy to interpret."),
    "factstruct:00797524-772b-4837-a715-2e9393daf7b4:target_0120": (True, True, "noisy", "The Khosla Ventures profile matches early-stage capital and long development cycles, but navigation-style company metadata dominates the Memory."),
    "factstruct:39d34404-5bd8-4dd0-b106-bc0aaf7509e8:target_0021": (True, True, "good", "The thesis abstract clearly studies nonlinear boom/bust housing-price relationships, making the quantile-varying inflation statement structurally understandable."),
    "factstruct:fb412ca8-d9d4-4fd9-9b0c-e6584dbd870e:target_0026": (False, True, "noisy", "Both Sources are practical student sustainability tip pages and do not describe institutional inertia or system integration."),
    "factstruct:6cbccd01-d103-4c61-8fc0-ddd3d7b2371d:target_0065": (True, True, "poor", "The topic maps to an abortion-harms document, but advocacy language and garbled OCR make the Source poor research text; no truth judgment is made here."),
    "factstruct:a179e647-9b23-4dd9-b20f-1441764df5e4:target_0108": (True, True, "noisy", "The Source is recognizably about gold-market drivers, but promotional market-report prose obscures the specific ETF-liquidity mechanism."),
    "factstruct:ebb3dfc8-c509-477f-bb10-bda0bf1ce604:target_0104": (True, False, "good", "The water-industry Source is readable, but the isolated Target says ‘两者’ without identifying the two compared items."),
    "factstruct:9a11d8a3-c8e9-4e42-9b48-4a74e285466d:target_0046": (True, True, "noisy", "The Source is on non-contact sensing and mentions infrared sensors, but its visible portion is broad and truncated before photodetector triangulation."),
    "factstruct:48dd5b9a-dc4b-499c-880a-9548da91f68f:target_0149": (True, True, "good", "The low-code article cleanly discusses delivery efficiency and business needs, so the business-user Target is coherent with the mapped Memory."),
    "factstruct:7b9075d3-e098-4755-a58f-d81ae1bffaf6:target_0010": (True, True, "noisy", "The Streamable HTTP article directly matches the protocol transition, although community-site and PR-number text adds minor noise."),
    "factstruct:81ea3f24-b741-437a-8b2f-a053b6b5e3f9:target_0142": (True, True, "noisy", "The Q&A explicitly identifies improvisation as jazz’s defining feature, but exam-question formatting makes it noisy Source text."),
    "factstruct:3e0c7082-7d74-4478-b1f8-95dd09815751:target_0114": (False, True, "poor", "The generic computer-industry teaser contains neither the stated Gartner percentage nor the architecture-job growth figures."),
    "factstruct:8bcb1d09-ab86-450c-a7fc-7a849bca4bdb:target_0007": (False, True, "noisy", "The Source covers plant–bacteria HGT generally but not incomplete T-DNA regulatory sequences across generations."),
    "factstruct:2c31f834-ea96-4d27-8d66-393ccfb22f71:target_0037": (False, True, "poor", "The fictional soul-reservoir failure claim is paired with a game page about armor upgrades and cosmetics, so the mapping is visibly off-topic."),
    "factstruct:e93d74ca-a4cd-4374-9946-07b9000e62dc:target_0069": (True, True, "noisy", "The homework-answer page directly discusses strategic behavior under hypercompetition, but solution-site boilerplate lowers text quality."),
    "factstruct:ebb3dfc8-c509-477f-bb10-bda0bf1ce604:target_0122": (False, True, "noisy", "The OCR-heavy innovation-systems paper is generic and does not identify the China–EU tax-audit mechanism described by the Target."),
    "factstruct:a94bae8a-2a53-4d5d-9d23-12feecb7be6e:target_0120": (False, True, "poor", "The Source is only a short evidence index for sports, arts, and labor education, not Chinese-language literary pedagogy."),
    "factstruct:38868ae1-976f-48d0-b177-92fb9de0a989:target_0011": (False, True, "noisy", "The catalog entry concerns modernization theory but does not visibly discuss nationalist backlash or great-power disruption of cultural exchange."),
    "factstruct:e16183be-af90-40d8-bd14-8b1b9fea07e6:target_0146": (False, True, "noisy", "The slide text covers CVD and PVD film deposition, while the Target’s ALD self-limiting mechanism and ±1Å figure are absent from the visible Memory."),
    "factstruct:2147d451-05a7-4ba8-abc4-0484d8c087e2:target_0056": (False, True, "good", "The dictionary entry cleanly defines ‘神’ but does not mention Heshang Gong or the claimed bodily-qi interpretation."),
    "factstruct:f049b08b-9a10-493c-83e9-322ab88973e6:target_0027": (True, True, "noisy", "The finance article explicitly covers LSTM price direction and volatility, though blog formatting and broad introductory material add noise."),
    "factstruct:01fbedbf-bc98-4661-83b5-339e7e655ab5:target_0019": (True, True, "noisy", "The thesis is directly about grammar-based 3D plant reconstruction, but repository metadata precedes the useful abstract."),
    "factstruct:62998bea-828a-4067-ae50-b5c686997ab6:target_0112": (False, True, "poor", "The bibliographic stub is about sex disparities in childhood and contains no visible GDP-growth or income-gap statistics."),
    "factstruct:c4eb9ed2-4a9a-466c-ab9d-5a07618d452f:target_0088": (False, False, "noisy", "The Target begins with an unexplained ‘3%’ fragment, and the Spanish oil-supply forecast does not identify that inflation measure."),
    "factstruct:fb412ca8-d9d4-4fd9-9b0c-e6584dbd870e:target_0008": (False, True, "good", "The Source is clean and readable about student eco-actions, but it does not present the paper-versus-digital impact comparison in the table row."),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--jsonl-output", type=Path, required=True)
    parser.add_argument("--md-output", type=Path, required=True)
    parser.add_argument("--dataset-report", type=Path)
    args = parser.parse_args()
    sample_ids = [json.loads(line)["example_id"] for line in args.sample.read_text(encoding="utf-8").splitlines()]
    if set(sample_ids) != set(JUDGMENTS) or len(sample_ids) != 30:
        raise SystemExit("manual judgments do not exactly cover the deterministic 30-example sample")
    examples = {}
    with args.examples.open("r", encoding="utf-8") as handle:
        for line in handle:
            example = json.loads(line)
            if example["example_id"] in JUDGMENTS:
                examples[example["example_id"]] = example
    rows = []
    for example_id in sample_ids:
        example = examples[example_id]
        mapping, understandable, quality, note = JUDGMENTS[example_id]
        gold_ids = set(example["gold_source_ids"])
        gold_sources = [{
            "source_id": source["id"],
            "title": source["title"],
            "memory_text": source["memory_text"],
        } for source in example["sources"] if source["id"] in gold_ids]
        if not note.strip() or quality not in {"good", "noisy", "poor"} or len(gold_sources) != len(gold_ids):
            raise SystemExit(f"invalid semantic audit judgment: {example_id}")
        rows.append({
            "example_id": example_id,
            "target_text": example["target"]["text"],
            "gold_sources": gold_sources,
            "parse_mapping_correct": mapping,
            "pair_is_understandable": understandable,
            "source_text_quality": quality,
            "obvious_label_leakage": False,
            "notes": note,
        })
    with args.jsonl_output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    quality_counts = Counter(row["source_text_quality"] for row in rows)
    md = [
        "# Semantic parse-and-text audit: deterministic 30 examples", "",
        "Seed: `20260727`. This is an executor-read audit of parsing plausibility, understandability, Source noise, and obvious label leakage. It is **not** a human citation-support or factual-truth audit.", "",
        f"- Parse mapping plausible: {sum(row['parse_mapping_correct'] for row in rows)}/30",
        f"- Pair understandable: {sum(row['pair_is_understandable'] for row in rows)}/30",
        f"- Obvious label leakage: {sum(row['obvious_label_leakage'] for row in rows)}",
        f"- Source quality: good={quality_counts['good']}, noisy={quality_counts['noisy']}, poor={quality_counts['poor']}", "",
    ]
    for index, row in enumerate(rows, 1):
        titles = "; ".join(source["title"] for source in row["gold_sources"])
        md.extend([
            f"## {index}. `{row['example_id']}`", "",
            f"- Target: {row['target_text']}",
            f"- Gold Source titles: {titles}",
            f"- Parse mapping plausible: {row['parse_mapping_correct']}",
            f"- Pair understandable: {row['pair_is_understandable']}",
            f"- Source text quality: {row['source_text_quality']}",
            f"- Obvious label leakage: {row['obvious_label_leakage']}",
            f"- Note: {row['notes']}", "",
        ])
    args.md_output.write_text("\n".join(md), encoding="utf-8")
    if args.dataset_report:
        report = json.loads(args.dataset_report.read_text(encoding="utf-8"))
        report["semantic_audit_30"] = {
            "sample_size": 30,
            "parse_mapping_correct": sum(row["parse_mapping_correct"] for row in rows),
            "pair_is_understandable": sum(row["pair_is_understandable"] for row in rows),
            "obvious_label_leakage": sum(row["obvious_label_leakage"] for row in rows),
            "source_text_quality": dict(quality_counts),
            "scope": "executor-read parse/mapping/text-quality audit; not citation support truth audit",
        }
        args.dataset_report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
