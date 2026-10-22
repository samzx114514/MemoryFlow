from __future__ import annotations

import random
import re
import hashlib
from collections import defaultdict
from typing import Any, Iterable

from .schema import FactStructRun


CITATION_RE = re.compile(r"\[\s*\d+\s*(?:,\s*\d+\s*)*\]")
SOURCE_CITATION_RE = re.compile(r"\[\s*\d[^\]]{0,30}\]")
CID_RE = re.compile(r"\d+")
SENTENCE_RE = re.compile(r"(?<=[.!?。！？])(?:\s+|(?=[^\s]))")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"\b(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|org|net|cn|edu|gov)(?:/\S*)?",
    re.IGNORECASE,
)
SPACED_DOMAIN_RE = re.compile(r"\bwww\s*\.[^\n]{0,100}?\b(?:com|org|net|cn|edu|gov)\b", re.IGNORECASE)
SPACED_PROTOCOL_RE = re.compile(r"\bhttps?\s*:\s*/\s*/(?:\s*[\w.%?=&/#:+-]+){0,40}", re.IGNORECASE)
NUMBER_PREFIX_RE = re.compile(r"(?im)^\s*(?:citation|source|ref(?:erence)?|url)\s*#?\d+\s*[:\-]\s*")
LINK_NUMBER_RE = re.compile(r"【\s*链接\s*\d+\s*】|\bURL\s*\d+\b", re.IGNORECASE)
REFERENCE_HEADING_RE = re.compile(r"^(?:references?|bibliography|citations?|参考文献|参考资料|引用来源|来源)$", re.I)
DOMAIN_PATH_RE = re.compile(r"(?:^|\s)(?:www\.)?[\w.-]*\.(?:com|org|net|cn|edu|gov)/|^com/", re.I)


def _token_units(text: str) -> list[str]:
    return re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9]+|[^\w\s]", text)


def _truncate_tokens(text: str, limit: int) -> str:
    units = list(re.finditer(r"[\u3400-\u9fff]|[A-Za-z0-9]+|[^\w\s]", text))
    if len(units) <= limit:
        return text.strip()
    return text[: units[limit - 1].end()].rstrip()


def _clean_visible_text(text: str) -> str:
    text = CITATION_RE.sub("", text)
    text = SOURCE_CITATION_RE.sub("", text)
    text = URL_RE.sub("", text)
    text = SPACED_PROTOCOL_RE.sub("", text)
    text = SPACED_DOMAIN_RE.sub("", text)
    text = DOMAIN_RE.sub("", text)
    text = LINK_NUMBER_RE.sub("", text)
    text = NUMBER_PREFIX_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def model_visible_text(text: str) -> str:
    return _clean_visible_text(text)


def _memory_text(source: dict[str, Any]) -> str:
    observation = source.get("observation") if isinstance(source.get("observation"), dict) else None
    if observation:
        parts = [str(observation.get("topic") or "").strip()]
        points = observation.get("points") or []
        if not isinstance(points, list):
            points = [points]
        parts.extend(str(point).strip() for point in points if str(point).strip())
        text = "\n".join(part for part in parts if part)
    else:
        text = "\n".join(part for part in (
            str(source.get("title") or "").strip(),
            str(source.get("cleaned_source_content") or source.get("content") or "").strip(),
        ) if part)
    return _truncate_tokens(_clean_visible_text(SOURCE_CITATION_RE.sub("", text)), 256)


def _language(text: str) -> str:
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return "zh" if cjk >= latin else "en"


def source_id(run_id: str, citation_id: str) -> str:
    run_key = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]
    return f"source_{run_key}_{citation_id}"


def iter_cited_sentences(report: str):
    heading = ""
    in_references = False
    previous_sentence = ""
    for raw_line in report.splitlines():
        line = raw_line.strip()
        if not line:
            previous_sentence = ""
            continue
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            in_references = bool(REFERENCE_HEADING_RE.match(heading.rstrip(":：")))
            previous_sentence = ""
            continue
        if in_references:
            continue
        sentences = [part.strip() for part in SENTENCE_RE.split(line) if part.strip()]
        for sentence in sentences:
            citations = CID_RE.findall("".join(CITATION_RE.findall(sentence)))
            clean = _clean_visible_text(sentence)
            if citations:
                if re.match(r"^[,;:，；：)）\]]", clean):
                    continue
                target = clean
                if len(re.sub(r"\s", "", clean)) < 20 and previous_sentence:
                    target = f"{previous_sentence} {clean}".strip()
                if target and not DOMAIN_PATH_RE.search(target):
                    yield target, list(dict.fromkeys(citations)), heading
            if clean:
                previous_sentence = clean


def extract_examples(run: FactStructRun) -> list[dict[str, Any]]:
    source_records = []
    for citation_id, source in run.sources.items():
        memory_text = _memory_text(source)
        if not memory_text:
            continue
        source_records.append({
            "id": source_id(run.run_id, citation_id),
            "title": _clean_visible_text(str(source.get("title") or "")),
            "memory_text": memory_text,
        })
    source_by_id = {record["id"]: record for record in source_records}
    available = set(source_by_id)
    examples: list[dict[str, Any]] = []
    for target_index, (text, citation_ids, heading) in enumerate(iter_cited_sentences(run.final_report), 1):
        gold = [source_id(run.run_id, citation_id) for citation_id in citation_ids]
        if not gold or not set(gold).issubset(available):
            continue
        examples.append({
            "example_id": f"factstruct:{run.run_id}:target_{target_index:04d}",
            "run_id": run.run_id,
            "system": "factstruct",
            "query": run.query,
            "target": {"id": f"target_{target_index:04d}", "text": _truncate_tokens(text, 192)},
            "sources": [source_by_id[source_id] for source_id in gold],
            "gold_source_ids": gold,
            "label_type": "silver_inline_citation",
            "metadata": {
                "target_heading": heading,
                "language": _language(text),
                "raw_citation_ids": citation_ids,
            },
        })
    return examples


def build_source_catalog(
    examples: Iterable[dict[str, Any]],
    audit_metadata: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Return one conflict-checked row per globally unique Source ID."""
    audit_metadata = audit_metadata or {}
    catalog: dict[str, dict[str, Any]] = {}
    for example in examples:
        for source in example["sources"]:
            source_id = source["id"]
            row = {
                "id": source_id,
                "title": model_visible_text(source.get("title", "")),
                "memory_text": model_visible_text(source.get("memory_text", "")),
                "url": audit_metadata.get(source_id, {}).get("url", ""),
                "metadata": {"system": "factstruct"},
            }
            existing = catalog.get(source_id)
            if existing is not None and existing != row:
                raise ValueError(f"conflicting Source ID: {source_id}")
            catalog[source_id] = row
    return [catalog[source_id] for source_id in sorted(catalog)]


def candidate_seed(seed: int, example_id: str, candidate_count: int) -> int:
    digest = hashlib.sha256(f"{seed}:{example_id}:{candidate_count}".encode("utf-8")).digest()
    return int.from_bytes(digest, "big")


def build_candidate_sets(
    examples: list[dict[str, Any]],
    source_catalog: list[dict[str, Any]],
    seed: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int] | dict[str, bool]]]:
    catalog_ids = {source["id"] for source in source_catalog}
    source_run: dict[str, str] = {}
    by_run: dict[str, set[str]] = defaultdict(set)
    for example in examples:
        for source in example["sources"]:
            source_id = source["id"]
            if source_id not in catalog_ids:
                raise ValueError(f"Source missing from catalog: {source_id}")
            prior_run = source_run.setdefault(source_id, example["run_id"])
            if prior_run != example["run_id"]:
                raise ValueError(f"Source ID appears in conflicting runs: {source_id}")
            by_run[example["run_id"]].add(source["id"])
    all_ids = sorted(catalog_ids)
    stats = {
        "available": {str(size): 0 for size in (4, 8, 16, 32)},
        "unavailable_gold_exceeds": {str(size): 0 for size in (4, 8, 16, 32)},
        "unavailable_insufficient_catalog": {str(size): 0 for size in (4, 8, 16, 32)},
        "strict_length_all": {str(size): True for size in (4, 8, 16, 32)},
    }
    output = []
    for example in examples:
        gold = list(dict.fromkeys(example["gold_source_ids"]))
        if not set(gold).issubset(catalog_ids):
            raise ValueError(f"Gold Source missing from catalog: {example['example_id']}")
        same = sorted(by_run[example["run_id"]] - set(gold))
        cross = [source_id for source_id in all_ids if source_run.get(source_id) != example["run_id"]]
        negatives = same + cross
        pools: dict[str, list[str]] = {str(size): [] for size in (4, 8, 16, 32)}
        unavailable: dict[str, str] = {}
        for size in (4, 8, 16, 32):
            key = str(size)
            if len(gold) > size:
                unavailable[key] = "gold_count_exceeds_candidate_count"
                stats["unavailable_gold_exceeds"][key] += 1
                continue
            if len(catalog_ids) < size or len(negatives) < size - len(gold):
                unavailable[key] = "insufficient_source_catalog"
                stats["unavailable_insufficient_catalog"][key] += 1
                continue
            ids = gold + negatives[: size - len(gold)]
            random.Random(candidate_seed(seed, example["example_id"], size)).shuffle(ids)
            if len(ids) != size or len(ids) != len(set(ids)):
                stats["strict_length_all"][key] = False
                raise ValueError(f"invalid candidate pool: {example['example_id']} K={size}")
            pools[str(size)] = ids
            stats["available"][key] += 1
        row = {"example_id": example["example_id"], "candidate_sets": pools}
        if unavailable:
            row["unavailable"] = unavailable
        output.append(row)
    return output, stats


def candidate_position_report(
    examples: Iterable[dict[str, Any]], rows: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    example_by_id = {example["example_id"]: example for example in examples}
    report: dict[str, dict[str, Any]] = {}
    for size in (4, 8, 16, 32):
        counts = [0] * size
        total = 0
        for row in rows:
            example = example_by_id[row["example_id"]]
            pool = row["candidate_sets"].get(str(size), [])
            gold = list(dict.fromkeys(example["gold_source_ids"]))
            if pool and len(gold) == 1:
                counts[pool.index(gold[0])] += 1
                total += 1
        item: dict[str, Any] = {
            "candidate_count": size,
            "single_positive_example_count": total,
        }
        item.update({f"position_{index}_count": count for index, count in enumerate(counts)})
        item["position_bias_max_ratio"] = max(counts) / total if total else 0.0
        if total and max(counts) == total:
            raise ValueError(f"all single-positive gold fixed at one position for K={size}")
        report[str(size)] = item
    return report


def split_by_run(examples: list[dict[str, Any]], seed: int) -> dict[str, Any]:
    run_ids = sorted({example["run_id"] for example in examples})
    rng = random.Random(seed)
    rng.shuffle(run_ids)
    dev_runs = sorted(run_ids[:2])
    test_runs = sorted(run_ids[2:])
    dev_set = set(dev_runs)
    return {
        "seed": seed,
        "split_unit": "run",
        "train": [],
        "dev_runs": dev_runs,
        "test_runs": test_runs,
        "dev": [example["example_id"] for example in examples if example["run_id"] in dev_set],
        "test": [example["example_id"] for example in examples if example["run_id"] not in dev_set],
    }
