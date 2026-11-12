"""Map legacy generated evidence to recorded material before formal scoring.

The original labels remain immutable. This records four reviewed replacements
and four unresolved claims, without reading method scores or creating bridges.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from intake import digest, fragment, read, write


REPLACEMENTS = {
    "genmem_940c258011aac604:selected_05": {
        "sources": [(11, 0, "Adam Searle (born 29 April 1969)"), (15, 0, "Adam Searle (born 29 April 1969)")], "separate_alternatives": True,
        "reason": "Both earlier tool results explicitly state Adam Searle's birth date; replace the Agent repetition."},
    "genmem_940c258011aac604:selected_10": {
        "sources": [(19, 0, "Leader of the New South Wales Labor Party. Acting. In office 25 March 2019 – 29 June 2019."),
                    (19, 0, "She has served as a member of the New South Wales Legislative Council since 2005, representing the Labor Party."),
                    (22, 3, "Penny Sharpe is the ALP Leader of the Opposition in the NSW Parliament’s Upper House")],
        "reason": "The first material states acting Labor leadership dates and Council membership; the second explicitly identifies Upper House Opposition Leader."},
    "genmem_40dc9b8b15c0c5b8:selected_04": {
        "sources": [(5, 0, "was an Irish international goalkeeper who played most of his career with Portsmouth in the Southern League."),
                    (15, 0, "South Hampshire is a term used mainly to refer to the conurbation formed by the city of Portsmouth, city of Southampton")],
        "reason": "The question identifies the player's club/city; original material links Reilly to Portsmouth and Portsmouth to South Hampshire. No Agent guess is used as root evidence."},
    "case_01:T06": {
        "sources": [(19, 0, "Andronikos Angelos Komnenos Doukas Palaiologos (Greek: Ἀνδρόνικος Ἄγγελος Κομνηνός Δούκας Παλαιολόγος, ca. 1282–1328)"),
                    (28, 3, "1282 to Demetrios Doukas Komnenos Koutroules, son of the ruler of Epirus, Michael II Komnenos Doukas, and Anna Komnene Palaiologina, the daughter of the Byzantine emperor Michael VIII Palaiologos.")],
        "reason": "Original material gives lifespan, father, mother and mother's father before the final statement."},
}

UNRESOLVED = {
    "genmem_177236211632d6b8:selected_04": "Earlier material confirms UCF and former Auburn assistant, but does not establish their order. The explicit ordering found at event 35 occurs after target event 34 and is excluded.",
    "genmem_9f963d36b4935b97:selected_03": "Recorded material says Mathematica was conceived by Stephen Wolfram; no earlier material explicitly establishes the language was named after him. A search query is generated content.",
    "genmem_58452c40de4bdcb9:selected_03": "Recorded material supports chapter/problem, gas pairs and a/b parameters. The McQuarrie attribution remains only in Agent text; full claim lacks a complete material group.",
    "genmem_40dc9b8b15c0c5b8:selected_06": "The district-versus-city assertion is in Agent text; earlier retrieved career lists do not establish it.",
}


def material_group(group):
    items = [{"alternatives": [a for a in item["alternatives"] if a["recorded_action"] in {"tool", "user"}]}
             for item in group["items"]]
    return {**group, "items": items} if all(i["alternatives"] for i in items) else None


def run(dataset, output):
    targets = read(dataset/"targets.json")
    rows = []
    for row in targets:
        key = row["legacy_id"]
        groups = [g for original in row["evidence_groups"] if (g := material_group(original))]
        status, reason = "legacy_material_group", "Existing full group contains only recorded material alternatives; semantic chain review remains separate."
        if key in REPLACEMENTS:
            review = REPLACEMENTS[key]
            log = read(dataset/"traces"/(row["sample_id"]+".json"))["memory_stack_log"]
            sources = []
            for event, result, quote in review["sources"]:
                body = json.loads(log[event]["content"])["results"][result]["content"]
                location = f"/memory_stack_log/{event}/content#/results/{result}/content"
                if body.count(quote) != 1:
                    raise ValueError(f"Reviewed quote is absent or ambiguous: {key}")
                start = body.index(quote)
                sources.append(fragment(log, location, {"start": start, "end": start+len(quote), "text": quote}))
            bundles = [[source] for source in sources] if review.get("separate_alternatives") else [sources]
            groups = [{"id": f"{key}:root_review_{i}", "items": [{"alternatives": [a]} for a in bundle]}
                      for i, bundle in enumerate(bundles)]
            status, reason = "reviewed_material_replacement", review["reason"]
        elif key in UNRESOLVED:
            if groups:
                raise ValueError(f"Unresolved claim unexpectedly has a full material group: {key}")
            status, reason = "incomplete_material_support", UNRESOLVED[key]
        if not groups and key not in UNRESOLVED:
            raise ValueError(f"Missing material review: {key}")
        if any(a["event"] > row["target"]["event"] for g in groups for i in g["items"] for a in i["alternatives"]):
            raise ValueError(f"Future material in root review: {key}")
        rows.append({"id": row["id"], "legacy_id": key, "sample_id": row["sample_id"],
                     "target": row["target"], "evidence_groups": groups, "review_status": status, "reason": reason})
    output.mkdir()
    write(output/"root_labels.json", rows)
    write(output/"review.json", {"schema": "memoryflow.genmem.material_review.v1",
          "targets_sha256": digest(dataset/"targets.json"), "labels_sha256": digest(output/"root_labels.json"),
          "status_counts": dict(Counter(r["review_status"] for r in rows)), "targets": len(rows),
          "replacement_methods_read": False, "chain_labels_frozen": False,
          "development_queries_read": ["genmem_177236211632d6b8:selected_02", "genmem_177236211632d6b8:selected_03"],
          "note": "Material-label review only. All 96 targets retained, four incomplete claims not silently counted as complete Gold. No artificial intermediate text or withheld older material."})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    run(args.dataset, args.output)
