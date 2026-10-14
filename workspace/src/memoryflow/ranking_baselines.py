"""Zero-training ranking baselines and evaluation for LongCite."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import math
from pathlib import Path
import re
import statistics
from typing import Iterable, Mapping, Sequence
import unicodedata
import json


METRIC_NAMES = (
    "hit_at_1",
    "hit_at_3",
    "hit_at_5",
    "recall_at_1",
    "recall_at_3",
    "recall_at_5",
    "mrr",
    "ndcg_at_5",
)


def _stable_hex(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def mixed_tokenize(text: str) -> list[str]:
    """Tokenize Latin alphanumerics and Chinese unigrams plus adjacent bigrams."""
    normalized = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).casefold()
    tokens: list[str] = []
    for match in re.finditer(r"[a-z0-9]+|[\u3400-\u9fff]+", normalized):
        span = match.group(0)
        if "\u3400" <= span[0] <= "\u9fff":
            tokens.extend(span)
            tokens.extend(span[index : index + 2] for index in range(len(span) - 1))
        else:
            tokens.append(span)
    return tokens


class BM25Index:
    """Small dependency-free BM25 index with corpus-global IDF."""

    def __init__(self, documents: Mapping[str, str], *, k1: float = 1.2, b: float = 0.75):
        if not documents:
            raise ValueError("BM25 corpus is empty")
        self.k1 = k1
        self.b = b
        self.term_frequencies = {
            document_id: Counter(mixed_tokenize(text)) for document_id, text in documents.items()
        }
        self.document_lengths = {
            document_id: sum(frequencies.values())
            for document_id, frequencies in self.term_frequencies.items()
        }
        self.average_document_length = statistics.fmean(self.document_lengths.values())
        document_frequency: Counter[str] = Counter()
        for frequencies in self.term_frequencies.values():
            document_frequency.update(frequencies.keys())
        count = len(documents)
        self.idf = {
            term: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def score(self, query: str, document_ids: Iterable[str] | None = None) -> dict[str, float]:
        query_terms = set(mixed_tokenize(query))
        requested = list(document_ids) if document_ids is not None else list(self.term_frequencies)
        scores: dict[str, float] = {}
        for document_id in requested:
            if document_id not in self.term_frequencies:
                raise ValueError(f"unknown BM25 document: {document_id}")
            frequencies = self.term_frequencies[document_id]
            document_length = self.document_lengths[document_id]
            normalization = self.k1 * (
                1.0 - self.b + self.b * document_length / self.average_document_length
            )
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if frequency:
                    score += self.idf.get(term, 0.0) * (
                        frequency * (self.k1 + 1.0) / (frequency + normalization)
                    )
            scores[document_id] = score
        return scores


def rank_scored_candidates(
    candidate_ids: Sequence[str],
    scores: Mapping[str, float],
    *,
    tie_namespace: str,
) -> list[str]:
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate candidate source_id")
    if set(candidate_ids) != set(scores):
        raise ValueError("score keys do not exactly match candidates")
    if any(not math.isfinite(float(scores[source_id])) for source_id in candidate_ids):
        raise ValueError("non-finite candidate score")
    return sorted(
        candidate_ids,
        key=lambda source_id: (
            -float(scores[source_id]),
            _stable_hex(tie_namespace, source_id),
        ),
    )


def random_ranking(candidate_ids: Sequence[str], *, example_id: str, seed: int) -> list[str]:
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate candidate source_id")
    return sorted(
        candidate_ids,
        key=lambda source_id: _stable_hex("longcite-c1-random", seed, example_id, source_id),
    )


def compute_ranking_metrics(ranking: Sequence[str], gold_source_ids: set[str]) -> dict[str, float]:
    if not ranking or len(ranking) != len(set(ranking)):
        raise ValueError("ranking must be nonempty and unique")
    if not gold_source_ids or not gold_source_ids <= set(ranking):
        raise ValueError("gold sources must be a nonempty subset of ranking")
    metrics: dict[str, float] = {}
    for cutoff in (1, 3, 5):
        relevant = sum(source_id in gold_source_ids for source_id in ranking[:cutoff])
        metrics[f"hit_at_{cutoff}"] = float(relevant > 0)
        metrics[f"recall_at_{cutoff}"] = relevant / len(gold_source_ids)
    first_positive_rank = next(
        rank for rank, source_id in enumerate(ranking, 1) if source_id in gold_source_ids
    )
    metrics["mrr"] = 1.0 / first_positive_rank
    dcg = sum(
        (1.0 / math.log2(rank + 1))
        for rank, source_id in enumerate(ranking[:5], 1)
        if source_id in gold_source_ids
    )
    ideal_count = min(5, len(gold_source_ids))
    ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
    metrics["ndcg_at_5"] = dcg / ideal_dcg
    return metrics


def aggregate_metrics_by_candidate_size(rows: Iterable[Mapping[str, object]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[Mapping[str, float]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["candidate_size"])].append(row["metrics"])  # type: ignore[arg-type]
    result: dict[str, dict[str, float]] = {}
    for candidate_size, size_rows in sorted(grouped.items(), key=lambda item: int(item[0])):
        names = sorted({name for metrics in size_rows for name in metrics})
        result[candidate_size] = {
            name: statistics.fmean(float(metrics[name]) for metrics in size_rows)
            for name in names
        }
    return result


def validate_complete_ranking(
    ranking: Sequence[str], candidate_ids: Sequence[str], candidate_size: int
) -> None:
    if len(ranking) != candidate_size:
        raise ValueError("ranking length does not equal candidate_size")
    if len(ranking) != len(set(ranking)):
        raise ValueError("ranking contains duplicate source_id")
    if set(ranking) != set(candidate_ids):
        raise ValueError("ranking has missing or unexpected source_id")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_frozen_files(data_dir: Path) -> dict[str, object]:
    frozen = json.loads((data_dir / "FROZEN.json").read_text(encoding="utf-8"))
    observed: dict[str, str] = {}
    for name, metadata in frozen.get("files", {}).items():
        digest = file_sha256(data_dir / name)
        observed[name] = digest
        if digest != metadata.get("sha256"):
            raise ValueError(f"frozen hash mismatch for {name}")
    required = {"examples.jsonl", "source_catalog.jsonl", "manifest.json"}
    if set(observed) != required:
        raise ValueError("FROZEN.json does not cover exactly the three clean data files")
    return {
        "valid": True,
        "dataset_version": frozen.get("dataset_version"),
        "sha256": observed,
        "target_group_count": frozen.get("target_group_count"),
        "document_group_count": frozen.get("document_group_count"),
        "candidate_size_counts": frozen.get("candidate_size_counts"),
    }
