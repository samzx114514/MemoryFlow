"""Frozen CPU-only BM25 scoring for the LC-Sent-15-v1 baseline core."""

from __future__ import annotations

from collections import Counter
import math
import re
import unicodedata
from typing import Iterable, Mapping


K1 = 1.2
B = 0.75


def mixed_v1_tokenize(text: str) -> list[str]:
    """NFKC/casefold text; emit Latin words and CJK unigram/bigram tokens."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    for match in re.finditer(r"[a-z0-9]+|[\u3400-\u9fff]+", normalized):
        span = match.group(0)
        if "\u3400" <= span[0] <= "\u9fff":
            tokens.extend(span)
            tokens.extend(span[index : index + 2] for index in range(len(span) - 1))
        else:
            tokens.append(span)
    return tokens


class GroupBM25:
    """BM25 fit only to one target's fixed 15 candidate documents."""

    def __init__(self, documents: Mapping[str, str], *, tokenizer=mixed_v1_tokenize) -> None:
        if not documents:
            raise ValueError("empty candidate group")
        self._tokenizer = tokenizer
        self._tf = {source_id: Counter(tokenizer(text)) for source_id, text in documents.items()}
        self._length = {source_id: sum(counts.values()) for source_id, counts in self._tf.items()}
        self._average_length = sum(self._length.values()) / len(self._length)
        df: Counter[str] = Counter()
        for counts in self._tf.values():
            df.update(counts.keys())
        count = len(documents)
        self._idf = {
            token: math.log(1.0 + (count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in df.items()
        }

    def score(self, query: str) -> dict[str, float]:
        query_terms = set(self._tokenizer(query))
        scores: dict[str, float] = {}
        for source_id, frequencies in self._tf.items():
            norm = K1 * (1.0 - B + B * self._length[source_id] / self._average_length)
            scores[source_id] = sum(
                self._idf[token] * (frequency * (K1 + 1.0) / (frequency + norm))
                for token in query_terms
                if (frequency := frequencies.get(token, 0))
            )
        return scores


def rank_by_score_then_source_id(scores: Mapping[str, float]) -> list[str]:
    if any(not math.isfinite(float(score)) for score in scores.values()):
        raise ValueError("non-finite BM25 score")
    return sorted(scores, key=lambda source_id: (-float(scores[source_id]), source_id))


def legacy_tokenize(text: str) -> list[str]:
    """Imported lazily to bind the documented historical tokenizer lineage."""
    from memoryflow.ranking_baselines import mixed_tokenize

    return mixed_tokenize(text)


def score_group(query: str, documents: Mapping[str, str], *, implementation: str) -> dict[str, float]:
    if implementation == "BM25_MIXED_V1":
        return GroupBM25(documents, tokenizer=mixed_v1_tokenize).score(query)
    if implementation == "BM25_LEGACY":
        # The legacy implementation is corpus-global. LC-Sent-15 deliberately
        # freezes a per-group corpus, while retaining its exact tokenizer/formula.
        from memoryflow.ranking_baselines import BM25Index

        return BM25Index(documents, k1=K1, b=B).score(query, documents.keys())
    raise ValueError(f"unknown BM25 implementation: {implementation}")
