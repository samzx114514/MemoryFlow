"""Bounded LongCite parsing and deterministic pilot dataset construction."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Iterable, Mapping, Sequence
import unicodedata


DATASET_NAME = "LongCite-45k"
LABEL_TYPE = "silver_longcite"
DEFAULT_CANDIDATE_SIZES = (8, 16, 32)
RANDOM_SEED_POLICY = (
    "SHA256('memoryflow-longcite-c0-v1' + example_id + candidate_size + purpose)"
)
CLEANING_RULE_VERSION = "longcite-clean-v0.6"

_DOCUMENT_RE = re.compile(
    r"\[Document Start\](.*?)\[Document End\]", re.IGNORECASE | re.DOTALL
)
_CHUNK_RE = re.compile(r"<C(\d+)>", re.IGNORECASE)
_STATEMENT_RE = re.compile(r"<statement\b[^>]*>(.*?)</statement>", re.IGNORECASE | re.DOTALL)
_CITE_RE = re.compile(r"<cite\b[^>]*>(.*?)</cite>", re.IGNORECASE | re.DOTALL)
_CITATION_TOKEN_RE = re.compile(r"\[\s*(\d+)\s*(?:-\s*(\d+)\s*)?\]")
_TAG_RE = re.compile(r"<[^>]+>")


class LongCiteParseError(ValueError):
    """Raised when a raw LongCite row cannot be structurally parsed."""


class CandidateBuildError(ValueError):
    """Raised when a target cannot support a requested candidate size."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class CleanTargetExclusion(ValueError):
    """Raised when a target must not enter the clean evaluation set."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SourceSentence:
    sentence_index: int
    text: str


@dataclass(frozen=True)
class PromptDocument:
    query: str
    sources: tuple[SourceSentence, ...]


@dataclass(frozen=True)
class ParsedTarget:
    text: str
    citation_indices: tuple[int, ...]


@dataclass(frozen=True)
class ResponseParseResult:
    targets: tuple[ParsedTarget, ...]
    filter_reasons: dict[str, int]


@dataclass(frozen=True)
class CandidateVariant:
    example: dict
    sources: tuple[dict, ...]


@dataclass(frozen=True)
class CleanCandidateVariant:
    example: dict
    sources: tuple[dict, ...]
    actions: dict[str, int]


def _normalize_text(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def parse_numbered_prompt(prompt: str) -> PromptDocument:
    """Parse all numbered source chunks and the query from a LongCite prompt."""
    match = _DOCUMENT_RE.search(prompt)
    if not match:
        raise LongCiteParseError("missing_document_boundaries")

    document_text = match.group(1)
    markers = list(_CHUNK_RE.finditer(document_text))
    if not markers:
        raise LongCiteParseError("missing_numbered_sources")

    sources: list[SourceSentence] = []
    seen_indices: set[int] = set()
    for position, marker in enumerate(markers):
        sentence_index = int(marker.group(1))
        if sentence_index in seen_indices:
            raise LongCiteParseError("duplicate_source_index")
        seen_indices.add(sentence_index)
        end = markers[position + 1].start() if position + 1 < len(markers) else len(document_text)
        text = _normalize_text(document_text[marker.end() : end])
        sources.append(SourceSentence(sentence_index=sentence_index, text=text))

    query = _normalize_text(prompt[match.end() :])
    if not query:
        raise LongCiteParseError("empty_query")
    return PromptDocument(query=query, sources=tuple(sources))


def is_low_value_text(text: str, *, kind: str) -> str | None:
    """Return a structural filtering reason for unusable target/source text."""
    normalized = _normalize_text(text)
    if not normalized:
        return f"empty_{kind}"
    if normalized.count("\ufffd") / len(normalized) >= 0.25:
        return f"{kind}_garbled"
    lexical_count = sum(character.isalpha() for character in normalized)
    if lexical_count == 0:
        return f"{kind}_no_lexical_content"
    if lexical_count < 4:
        return f"{kind}_too_short"
    return None


def _parse_citation_payload(payload: str) -> tuple[int, ...] | None:
    matches = list(_CITATION_TOKEN_RE.finditer(payload))
    if not matches:
        return None
    remainder = _CITATION_TOKEN_RE.sub("", payload)
    if re.sub(r"[\s,;，；]+", "", remainder):
        return None

    indices: list[int] = []
    for match in matches:
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) is not None else start
        if end < start:
            return None
        indices.extend(range(start, end + 1))
    return tuple(dict.fromkeys(indices))


def parse_response_statements(
    response: str, valid_source_indices: set[int]
) -> ResponseParseResult:
    """Parse statement/citation pairs and record target-level filtering reasons."""
    targets: list[ParsedTarget] = []
    reasons: Counter[str] = Counter()
    statements = list(_STATEMENT_RE.finditer(response))
    if not statements:
        return ResponseParseResult((), {"response_no_statements": 1})

    for statement_match in statements:
        body = statement_match.group(1)
        cite_matches = list(_CITE_RE.finditer(body))
        target_text = _normalize_text(_TAG_RE.sub("", _CITE_RE.sub("", body)))
        if not target_text:
            reasons["empty_target"] += 1
            continue
        low_value_reason = is_low_value_text(target_text, kind="target")
        if low_value_reason:
            reasons[low_value_reason] += 1
            continue
        if not cite_matches:
            reasons["no_valid_citation"] += 1
            continue
        if all(not cite_match.group(1).strip() for cite_match in cite_matches):
            reasons["no_valid_citation"] += 1
            continue

        citation_indices: list[int] = []
        malformed = False
        for cite_match in cite_matches:
            parsed = _parse_citation_payload(cite_match.group(1))
            if parsed is None:
                malformed = True
                break
            citation_indices.extend(parsed)
        if malformed:
            reasons["malformed_citation"] += 1
            continue
        unique_indices = tuple(dict.fromkeys(citation_indices))
        if not unique_indices:
            reasons["no_valid_citation"] += 1
            continue
        if any(index not in valid_source_indices for index in unique_indices):
            reasons["citation_out_of_range"] += 1
            continue
        targets.append(ParsedTarget(target_text, unique_indices))

    return ResponseParseResult(tuple(targets), dict(sorted(reasons.items())))


def _stable_seed(*parts: object) -> int:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def _short_hash(*parts: object, length: int = 20) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def build_candidate_variant(
    document: PromptDocument,
    target: ParsedTarget,
    raw_row_index: int,
    target_index: int,
    candidate_size: int,
    revision: str,
) -> CandidateVariant:
    """Build one exact-size, same-document deterministic candidate set."""
    if len(target.citation_indices) > candidate_size:
        raise CandidateBuildError("positive_count_exceeds_candidate_size")

    valid_sources = {
        source.sentence_index: source
        for source in document.sources
        if is_low_value_text(source.text, kind="source") is None
    }
    if any(index not in valid_sources for index in target.citation_indices):
        raise CandidateBuildError("invalid_cited_source")
    if len(valid_sources) < candidate_size:
        raise CandidateBuildError("insufficient_document_sources")

    row_key = _short_hash(revision, raw_row_index, document.query)
    run_id = f"longcite:{row_key}"
    document_group_id = f"longcite_document_{row_key}"
    target_key = _short_hash(document_group_id, target_index, target.text)
    target_id = f"target_{target_key}"
    target_group_id = f"longcite_target_{target_key}"
    example_id = f"{run_id}:{target_id}:c{candidate_size}"

    positives = list(target.citation_indices)
    negatives = sorted(set(valid_sources) - set(positives))
    negative_rng = random.Random(
        _stable_seed("memoryflow-longcite-c0-v1", example_id, candidate_size, "negatives")
    )
    negative_rng.shuffle(negatives)
    selected_indices = positives + negatives[: candidate_size - len(positives)]
    order_rng = random.Random(
        _stable_seed("memoryflow-longcite-c0-v1", example_id, candidate_size, "order")
    )
    order_rng.shuffle(selected_indices)

    id_by_index = {
        index: f"source_{_short_hash(example_id, index)}" for index in selected_indices
    }
    candidate_ids = [id_by_index[index] for index in selected_indices]
    gold_ids = [id_by_index[index] for index in positives]
    example = {
        "example_id": example_id,
        "run_id": run_id,
        "target_group_id": target_group_id,
        "document_group_id": document_group_id,
        "system": "longcite",
        "query": document.query,
        "target": {"target_id": target_id, "text": target.text},
        "gold_source_ids": gold_ids,
        "candidate_source_ids": candidate_ids,
        "label_type": LABEL_TYPE,
        "metadata": {
            "dataset": DATASET_NAME,
            "revision": revision,
            "raw_row_index": raw_row_index,
            "candidate_size": candidate_size,
        },
    }
    source_rows = tuple(
        {
            "source_id": id_by_index[index],
            "example_id": example_id,
            "sentence_index": index,
            "text": valid_sources[index].text,
            "is_cited": index in set(positives),
        }
        for index in selected_indices
    )
    return CandidateVariant(example=example, sources=source_rows)


def _write_jsonl(path: Path, rows: Sequence[Mapping]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_pilot_from_rows(
    rows: Iterable[Mapping[str, object]],
    output_dir: Path,
    revision: str,
    *,
    max_rows: int = 200,
    max_targets: int = 100,
    candidate_sizes: Sequence[int] = DEFAULT_CANDIDATE_SIZES,
    source_metadata: Mapping[str, object] | None = None,
) -> dict:
    """Build bounded pilot files from a raw-row iterable, stopping at either cap."""
    if max_rows > 200 or max_targets > 100:
        raise ValueError("Checkpoint C0 caps are max_rows<=200 and max_targets<=100")
    output_dir.mkdir(parents=True, exist_ok=True)
    examples: list[dict] = []
    source_catalog: list[dict] = []
    reasons: Counter[str] = Counter()
    size_skips: dict[str, Counter[str]] = {
        str(size): Counter() for size in candidate_sizes
    }
    size_counts: Counter[str] = Counter()
    raw_rows_scanned = 0
    valid_targets = 0
    filtered_targets = 0

    row_iterator = iter(rows)
    while raw_rows_scanned < max_rows and valid_targets < max_targets:
        try:
            row = next(row_iterator)
        except StopIteration:
            break
        raw_row_index = raw_rows_scanned
        raw_rows_scanned += 1
        try:
            prompt = row.get("prompt")
            response = row.get("response")
            if not isinstance(prompt, str) or not isinstance(response, str):
                raise LongCiteParseError("missing_prompt_or_response")
            document = parse_numbered_prompt(prompt)
        except LongCiteParseError as error:
            reasons[str(error)] += 1
            filtered_targets += 1
            continue

        parsed = parse_response_statements(
            response, {source.sentence_index for source in document.sources}
        )
        reasons.update(parsed.filter_reasons)
        filtered_targets += sum(parsed.filter_reasons.values())
        for target_index, target in enumerate(parsed.targets):
            if valid_targets >= max_targets:
                break
            variants: list[CandidateVariant] = []
            for candidate_size in candidate_sizes:
                try:
                    variant = build_candidate_variant(
                        document,
                        target,
                        raw_row_index,
                        target_index,
                        candidate_size,
                        revision,
                    )
                except CandidateBuildError as error:
                    size_skips[str(candidate_size)][error.reason] += 1
                    continue
                variants.append(variant)
                size_counts[str(candidate_size)] += 1
            if not variants:
                filtered_targets += 1
                reasons["no_supported_candidate_size"] += 1
                continue
            valid_targets += 1
            for variant in variants:
                examples.append(variant.example)
                source_catalog.extend(variant.sources)

    _write_jsonl(output_dir / "examples.jsonl", examples)
    _write_jsonl(output_dir / "source_catalog.jsonl", source_catalog)
    manifest = {
        "dataset": DATASET_NAME,
        "dataset_revision": revision,
        "raw_rows_scanned": raw_rows_scanned,
        "valid_targets": valid_targets,
        "filtered_targets": filtered_targets,
        "filter_reasons": dict(sorted(reasons.items())),
        "candidate_sizes": list(candidate_sizes),
        "candidate_size_counts": {
            str(size): size_counts[str(size)] for size in candidate_sizes
        },
        "candidate_size_skips": {
            str(size): dict(sorted(size_skips[str(size)].items())) for size in candidate_sizes
        },
        "example_variants": len(examples),
        "source_catalog_entries": len(source_catalog),
        "label_type": LABEL_TYPE,
        "random_seed_policy": RANDOM_SEED_POLICY,
        "grouping_fields": {
            "target_group_id": "stable across candidate sizes; candidate_size excluded",
            "document_group_id": "stable for every target from one raw LongCite document",
            "split_policy": "future train/dev/test splits must group by document_group_id",
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "limits": {"max_raw_rows": max_rows, "max_valid_targets": max_targets},
        "source_access": dict(source_metadata or {}),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                raise ValueError(f"blank JSONL line in {path.name}:{line_number}")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"non-object JSONL row in {path.name}:{line_number}")
            rows.append(value)
    return rows


def validate_pilot_files(output_dir: Path) -> dict:
    """Reload and cross-check the three C0 artifacts."""
    examples = _read_jsonl(output_dir / "examples.jsonl")
    sources = _read_jsonl(output_dir / "source_catalog.jsonl")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    example_ids = [example.get("example_id") for example in examples]
    if len(example_ids) != len(set(example_ids)):
        raise ValueError("duplicate example_id")
    source_ids = [source.get("source_id") for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate source_id")
    source_by_id = {source["source_id"]: source for source in sources}

    candidate_counts: Counter[str] = Counter()
    target_ids: set[str] = set()
    target_group_to_target: dict[str, tuple[str, str]] = {}
    row_to_document_group: dict[int, str] = {}
    for example in examples:
        if example.get("system") != "longcite" or example.get("label_type") != LABEL_TYPE:
            raise ValueError("invalid system or label_type")
        target = example.get("target", {})
        if not isinstance(target, dict) or is_low_value_text(str(target.get("text", "")), kind="target"):
            raise ValueError("invalid target text")
        target_ids.add(str(target.get("target_id")))
        target_group_id = example.get("target_group_id")
        document_group_id = example.get("document_group_id")
        if not isinstance(target_group_id, str) or not target_group_id:
            raise ValueError("missing target_group_id")
        if not isinstance(document_group_id, str) or not document_group_id:
            raise ValueError("missing document_group_id")
        target_signature = (str(target.get("target_id")), str(target.get("text")))
        previous_target = target_group_to_target.setdefault(target_group_id, target_signature)
        if previous_target != target_signature:
            raise ValueError("target_group_id collision")
        raw_row_index = example.get("metadata", {}).get("raw_row_index")
        if not isinstance(raw_row_index, int):
            raise ValueError("invalid raw_row_index")
        previous_document = row_to_document_group.setdefault(raw_row_index, document_group_id)
        if previous_document != document_group_id:
            raise ValueError("document_group_id mismatch within raw row")
        candidate_ids = example.get("candidate_source_ids")
        gold_ids = example.get("gold_source_ids")
        if not isinstance(candidate_ids, list) or len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("duplicate or invalid candidate_source_ids")
        if not isinstance(gold_ids, list) or not gold_ids:
            raise ValueError("missing gold_source_ids")
        if not set(gold_ids) <= set(candidate_ids):
            raise ValueError("gold source not included in candidates")
        if any(source_id not in source_by_id for source_id in gold_ids):
            raise ValueError("gold source missing from source catalog")
        if any(source_id not in source_by_id for source_id in candidate_ids):
            raise ValueError("candidate source missing from source catalog")
        for source_id in candidate_ids:
            source = source_by_id[source_id]
            if source.get("example_id") != example["example_id"]:
                raise ValueError("source/example relationship mismatch")
            if is_low_value_text(str(source.get("text", "")), kind="source"):
                raise ValueError("invalid source text")
            if not isinstance(source.get("sentence_index"), int) or source["sentence_index"] < 0:
                raise ValueError("invalid source sentence index")
            if bool(source.get("is_cited")) != (source_id in set(gold_ids)):
                raise ValueError("is_cited mismatch")
        size = example.get("metadata", {}).get("candidate_size")
        if size != len(candidate_ids):
            raise ValueError("candidate_size mismatch")
        candidate_counts[str(size)] += 1

    if manifest.get("example_variants") != len(examples):
        raise ValueError("manifest example count mismatch")
    if manifest.get("source_catalog_entries") != len(sources):
        raise ValueError("manifest source count mismatch")
    if manifest.get("candidate_size_counts") != dict(sorted(candidate_counts.items())):
        raise ValueError("manifest candidate size counts mismatch")
    if manifest.get("valid_targets") != len(target_ids):
        raise ValueError("manifest target count mismatch")
    if manifest.get("label_type") != LABEL_TYPE:
        raise ValueError("manifest label_type mismatch")
    grouping_fields = manifest.get("grouping_fields", {})
    if "document_group_id" not in grouping_fields or "target_group_id" not in grouping_fields:
        raise ValueError("manifest grouping fields missing")

    return {
        "valid": True,
        "example_count": len(examples),
        "source_count": len(sources),
        "target_count": len(target_ids),
        "target_group_count": len(target_group_to_target),
        "document_group_count": len(set(row_to_document_group.values())),
        "candidate_size_counts": dict(sorted(candidate_counts.items())),
    }


def _nfkc_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def normalize_candidate_text(text: str) -> str:
    """Conservative duplicate key: NFKC, whitespace folding, punctuation ignored."""
    folded = _nfkc_whitespace(text).casefold()
    return "".join(character for character in folded if not unicodedata.category(character).startswith("P"))


def clean_target_exclusion_reason(text: str) -> str | None:
    """Identify only clearly untraceable targets or true heading fragments."""
    folded = _nfkc_whitespace(text)
    if not folded or not any(character.isalpha() for character in folded):
        return "untraceable"
    heading = re.fullmatch(
        r"(?:\d+(?:\.\d+)*[.)、]?\s*)?(?:contents?|table of contents|introduction|references|appendix)\.?'?",
        folded,
        re.IGNORECASE,
    )
    chinese_heading = re.fullmatch(r"(?:目录|第[一二三四五六七八九十百0-9]+[章节篇部])", folded)
    if heading or chinese_heading:
        return "heading_fragment"
    return None


def source_noise_reason(text: str) -> str | None:
    """Conservatively classify sources that cannot function as evidence or negatives."""
    folded = _nfkc_whitespace(text)
    if not folded or not any(character.isalpha() for character in folded):
        return "numeric_symbol_or_empty"
    replacement_ratio = folded.count("\ufffd") / len(folded)
    if replacement_ratio >= 0.10 or ("\ufffd" in folded and len(normalize_candidate_text(folded)) < 12):
        return "garbled_fragment"
    without_url = re.sub(r"(?:https?://|www\.)\S+", "", folded, flags=re.IGNORECASE).strip()
    if without_url and without_url != folded:
        if sum(character.isalpha() for character in without_url) < 4:
            return "url_only_or_near_only"
    elif re.fullmatch(r"(?:https?://|www\.)\S+", folded, re.IGNORECASE):
        return "url_only_or_near_only"
    heading = re.fullmatch(
        r"(?:\d+(?:\.\d+)*[.)、]?\s*)?(?:contents?|table of contents|references|appendix|index)\.?'?",
        folded,
        re.IGNORECASE,
    )
    if heading or re.fullmatch(r"(?:目录|第[一二三四五六七八九十百0-9]+[章节篇部])", folded):
        return "heading_fragment"
    balance_text = re.sub(r"^[A-Za-z0-9]+[.)、]\s*", "", folded)
    if len(folded) <= 40 and (
        balance_text.count("[") != balance_text.count("]")
        or balance_text.count("(") != balance_text.count(")")
    ):
        return "malformed_short_fragment"
    if re.search(
        r"(?:page\s+\d+\s+of\s+\d+|required application materials checklist|返回首页|网站导航)",
        folded,
        re.IGNORECASE,
    ) and len(folded) <= 160:
        return "navigation_fragment"
    return None


def clean_candidate_variant(
    example: Mapping[str, object],
    source_by_id: Mapping[str, Mapping[str, object]],
    document_pool: Mapping[int, str],
    *,
    support_quality: str,
    original_source_ids_by_index: Mapping[int, Sequence[str]] | None = None,
) -> CleanCandidateVariant:
    """Clean and deterministically refill one candidate-size variant."""
    candidate_size = int(example["metadata"]["candidate_size"])  # type: ignore[index]
    gold_ids = list(example["gold_source_ids"])  # type: ignore[arg-type]
    candidate_ids = list(example["candidate_source_ids"])  # type: ignore[arg-type]
    gold_id_set = set(gold_ids)
    original_ids = original_source_ids_by_index or {}
    actions = {
        "noise_negatives_removed": 0,
        "duplicate_negatives_removed": 0,
        "replacement_negatives_added": 0,
        "near_duplicate_pairs_recorded": 0,
    }

    selected: list[tuple[int, str, bool]] = []
    used_keys: set[str] = set()
    positive_keys: set[str] = set()
    for source_id in gold_ids:
        source = source_by_id[source_id]
        text = str(source["text"])
        noise_reason = source_noise_reason(text)
        if noise_reason:
            raise CleanTargetExclusion(f"suspect_positive_source:{noise_reason}")
        key = normalize_candidate_text(text)
        if key in positive_keys:
            raise CleanTargetExclusion("duplicate_positive_sources")
        positive_keys.add(key)
        used_keys.add(key)
        selected.append((int(source["sentence_index"]), text, True))

    for source_id in candidate_ids:
        if source_id in gold_id_set:
            continue
        source = source_by_id[source_id]
        text = str(source["text"])
        if source_noise_reason(text):
            actions["noise_negatives_removed"] += 1
            continue
        key = normalize_candidate_text(text)
        if key in used_keys:
            actions["duplicate_negatives_removed"] += 1
            continue
        used_keys.add(key)
        selected.append((int(source["sentence_index"]), text, False))

    refill_indices = sorted(document_pool)
    refill_rng = random.Random(
        _stable_seed(CLEANING_RULE_VERSION, example["example_id"], candidate_size, "refill")
    )
    refill_rng.shuffle(refill_indices)
    selected_indices = {index for index, _, _ in selected}
    for sentence_index in refill_indices:
        if len(selected) >= candidate_size:
            break
        if sentence_index in selected_indices:
            continue
        text = document_pool[sentence_index]
        if source_noise_reason(text):
            continue
        key = normalize_candidate_text(text)
        if key in used_keys:
            continue
        used_keys.add(key)
        selected_indices.add(sentence_index)
        selected.append((sentence_index, text, False))
        actions["replacement_negatives_added"] += 1
    if len(selected) < candidate_size:
        raise CandidateBuildError("insufficient_clean_document_sources")

    for left_index, (_, left_text, _) in enumerate(selected):
        for _, right_text, _ in selected[left_index + 1 :]:
            left_key = normalize_candidate_text(left_text)
            right_key = normalize_candidate_text(right_text)
            if left_key != right_key and SequenceMatcher(None, left_key, right_key).ratio() >= 0.90:
                actions["near_duplicate_pairs_recorded"] += 1

    order_rng = random.Random(
        _stable_seed(CLEANING_RULE_VERSION, example["example_id"], candidate_size, "order")
    )
    order_rng.shuffle(selected)
    new_id_by_index = {
        sentence_index: f"clean_source_{_short_hash(CLEANING_RULE_VERSION, example['example_id'], sentence_index)}"
        for sentence_index, _, _ in selected
    }
    cleaned_sources = tuple(
        {
            "source_id": new_id_by_index[sentence_index],
            "example_id": example["example_id"],
            "document_group_id": example["document_group_id"],
            "sentence_index": sentence_index,
            "text": text,
            "is_cited": is_cited,
            "provenance_original_source_ids": sorted(original_ids.get(sentence_index, ())),
        }
        for sentence_index, text, is_cited in selected
    )
    cleaned_example = dict(example)
    cleaned_example["gold_source_ids"] = [
        new_id_by_index[sentence_index] for sentence_index, _, is_cited in selected if is_cited
    ]
    cleaned_example["candidate_source_ids"] = [source["source_id"] for source in cleaned_sources]
    cleaned_example["support_quality"] = support_quality
    cleaned_example["metadata"] = {
        **dict(example["metadata"]),  # type: ignore[arg-type]
        "original_example_id": example["example_id"],
        "cleaning_rule_version": CLEANING_RULE_VERSION,
        "cleaning_actions": actions,
    }
    return CleanCandidateVariant(cleaned_example, cleaned_sources, actions)


def build_clean_pilot(
    original_dir: Path,
    output_dir: Path,
    decisions_path: Path,
    audit_stats_path: Path,
) -> dict:
    """Build a traceable clean pilot exclusively from existing C0/C0.5 artifacts."""
    validate_pilot_files(original_dir)
    examples = _read_jsonl(original_dir / "examples.jsonl")
    sources = _read_jsonl(original_dir / "source_catalog.jsonl")
    original_manifest = json.loads((original_dir / "manifest.json").read_text(encoding="utf-8"))
    decisions = {row["target_group_id"]: row for row in _read_jsonl(decisions_path)}
    audit_stats = json.loads(audit_stats_path.read_text(encoding="utf-8"))
    audit_judgments = {
        sample["target_group_id"]: sample["judgment"]
        for sample in audit_stats.get("semantic_audit", {}).get("samples", [])
    }
    source_by_id = {source["source_id"]: source for source in sources}
    example_by_id = {example["example_id"]: example for example in examples}

    document_pool: dict[str, dict[int, str]] = defaultdict(dict)
    original_ids: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for source in sources:
        document_group_id = example_by_id[source["example_id"]]["document_group_id"]
        sentence_index = int(source["sentence_index"])
        previous = document_pool[document_group_id].setdefault(sentence_index, source["text"])
        if previous != source["text"]:
            raise ValueError("source text conflict within document_group_id/sentence_index")
        original_ids[document_group_id][sentence_index].append(source["source_id"])

    groups: dict[str, list[dict]] = defaultdict(list)
    for example in examples:
        groups[example["target_group_id"]].append(example)
    exclusions: Counter[str] = Counter()
    excluded_group_ids: dict[str, list[str]] = defaultdict(list)
    variant_skips: Counter[str] = Counter()
    action_totals: Counter[str] = Counter()
    clean_examples: list[dict] = []
    clean_sources: list[dict] = []
    clean_target_groups: set[str] = set()

    for target_group_id, group in groups.items():
        canonical = max(group, key=lambda item: item["metadata"]["candidate_size"])
        target_text = canonical["target"]["text"]
        decision = decisions.get(target_group_id)
        decision_name = decision["decision"] if decision else None
        exclusion_reason: str | None = None
        if decision_name in {"exclude_heading_fragment", "exclude_untraceable", "uncertain"}:
            exclusion_reason = f"target_review_{decision_name}"
        elif decision_name not in {None, "keep_complete_proposition"}:
            raise ValueError(f"unknown target review decision: {decision_name}")
        elif decision is None:
            automatic_reason = clean_target_exclusion_reason(target_text)
            if automatic_reason:
                exclusion_reason = f"automatic_target_{automatic_reason}"
        if exclusion_reason is None and audit_judgments.get(target_group_id) == "suspicious":
            exclusion_reason = "semantic_audit_suspicious"

        canonical_positive_rows = [source_by_id[source_id] for source_id in canonical["gold_source_ids"]]
        if exclusion_reason is None:
            positive_noise = [
                source_noise_reason(source["text"])
                for source in canonical_positive_rows
                if source_noise_reason(source["text"])
            ]
            if positive_noise:
                exclusion_reason = "suspect_positive_source"
        if exclusion_reason:
            exclusions[exclusion_reason] += 1
            excluded_group_ids[exclusion_reason].append(target_group_id)
            continue

        judgment = audit_judgments.get(target_group_id)
        support_quality = {
            "clearly_supported": "clearly_supported",
            "partially_supported": "partial",
        }.get(judgment, "unreviewed_silver")
        built_for_group = 0
        for example in sorted(group, key=lambda item: item["metadata"]["candidate_size"]):
            try:
                cleaned = clean_candidate_variant(
                    example,
                    source_by_id,
                    document_pool[example["document_group_id"]],
                    support_quality=support_quality,
                    original_source_ids_by_index=original_ids[example["document_group_id"]],
                )
            except CandidateBuildError as error:
                variant_skips[error.reason] += 1
                continue
            except CleanTargetExclusion as error:
                raise ValueError(f"group-level positive-source check missed {target_group_id}: {error.reason}") from error
            clean_examples.append(cleaned.example)
            clean_sources.extend(cleaned.sources)
            action_totals.update(cleaned.actions)
            built_for_group += 1
        if built_for_group:
            clean_target_groups.add(target_group_id)
        else:
            exclusions["no_clean_candidate_variant"] += 1
            excluded_group_ids["no_clean_candidate_variant"].append(target_group_id)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output_dir / "examples.jsonl", clean_examples)
    _write_jsonl(output_dir / "source_catalog.jsonl", clean_sources)
    size_counts = Counter(str(example["metadata"]["candidate_size"]) for example in clean_examples)
    document_groups = {example["document_group_id"] for example in clean_examples}
    decision_counts = Counter(row["decision"] for row in decisions.values())
    manifest = {
        "dataset": DATASET_NAME,
        "dataset_revision": original_manifest["dataset_revision"],
        "label_type": LABEL_TYPE,
        "cleaning_rule_version": CLEANING_RULE_VERSION,
        "original_data_directory": str(original_dir.absolute()),
        "original_target_count": original_manifest["valid_targets"],
        "clean_target_count": len(clean_target_groups),
        "target_group_count": len(clean_target_groups),
        "document_group_count": len(document_groups),
        "target_review_decision_counts": dict(sorted(decision_counts.items())),
        "exclusion_counts": dict(sorted(exclusions.items())),
        "excluded_target_group_ids": {
            reason: sorted(group_ids) for reason, group_ids in sorted(excluded_group_ids.items())
        },
        "noise_negatives_removed": action_totals["noise_negatives_removed"],
        "positive_source_noise_target_exclusions": exclusions["suspect_positive_source"],
        "exact_duplicate_candidates_removed": action_totals["duplicate_negatives_removed"],
        "replacement_negatives_added": action_totals["replacement_negatives_added"],
        "near_duplicate_pairs_not_automatically_removed": action_totals["near_duplicate_pairs_recorded"],
        "candidate_size_counts": {size: size_counts[size] for size in ("8", "16", "32")},
        "candidate_variant_count": len(clean_examples),
        "source_catalog_entries": len(clean_sources),
        "candidate_variant_skips": dict(sorted(variant_skips.items())),
        "grouping_fields": original_manifest["grouping_fields"],
        "created_at": original_manifest["created_at"],
        "created_at_policy": "inherits source manifest timestamp for byte-identical deterministic rebuilds",
        "traceability": {
            "target_decisions": str(decisions_path.absolute()),
            "quality_audit_stats": str(audit_stats_path.absolute()),
            "source_sentence_index_semantics_changed": False,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_clean_pilot_files(output_dir: Path) -> dict:
    """Validate all C0.6 invariants after reloading clean artifacts."""
    examples = _read_jsonl(output_dir / "examples.jsonl")
    sources = _read_jsonl(output_dir / "source_catalog.jsonl")
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    source_by_id = {source["source_id"]: source for source in sources}
    if len(source_by_id) != len(sources):
        raise ValueError("duplicate clean source_id")
    if len({example["example_id"] for example in examples}) != len(examples):
        raise ValueError("duplicate clean example_id")
    size_counts: Counter[str] = Counter()
    target_groups: set[str] = set()
    document_groups: set[str] = set()
    for example in examples:
        if example.get("label_type") != LABEL_TYPE:
            raise ValueError("clean label_type changed")
        if clean_target_exclusion_reason(example["target"]["text"]):
            raise ValueError("invalid target in clean data")
        target_group_id = example.get("target_group_id")
        document_group_id = example.get("document_group_id")
        if not isinstance(target_group_id, str) or not isinstance(document_group_id, str):
            raise ValueError("clean grouping field missing")
        target_groups.add(target_group_id)
        document_groups.add(document_group_id)
        candidate_ids = example.get("candidate_source_ids", [])
        gold_ids = example.get("gold_source_ids", [])
        if not gold_ids or not set(gold_ids) <= set(candidate_ids):
            raise ValueError("clean gold/candidate relationship invalid")
        if any(source_id not in source_by_id for source_id in candidate_ids):
            raise ValueError("clean candidate source missing")
        candidate_sources = [source_by_id[source_id] for source_id in candidate_ids]
        normalized_texts = [normalize_candidate_text(source["text"]) for source in candidate_sources]
        if len(normalized_texts) != len(set(normalized_texts)):
            raise ValueError("normalized duplicate candidate text")
        for source in candidate_sources:
            if source.get("document_group_id") != document_group_id:
                raise ValueError("clean candidate crossed document group")
            if bool(source.get("is_cited")) != (source["source_id"] in set(gold_ids)):
                raise ValueError("clean citation flag mismatch")
            if source_noise_reason(source["text"]):
                raise ValueError("noisy source remains in clean candidate set")
        size = example["metadata"]["candidate_size"]
        if len(candidate_ids) != size:
            raise ValueError("clean candidate size mismatch")
        size_counts[str(size)] += 1
    if manifest.get("clean_target_count") != len(target_groups):
        raise ValueError("clean manifest target count mismatch")
    if manifest.get("document_group_count") != len(document_groups):
        raise ValueError("clean manifest document count mismatch")
    if manifest.get("candidate_size_counts") != {size: size_counts[size] for size in ("8", "16", "32")}:
        raise ValueError("clean manifest candidate size count mismatch")
    if manifest.get("source_catalog_entries") != len(sources):
        raise ValueError("clean manifest source count mismatch")
    return {
        "valid": True,
        "target_group_count": len(target_groups),
        "document_group_count": len(document_groups),
        "example_count": len(examples),
        "source_count": len(sources),
        "candidate_size_counts": {size: size_counts[size] for size in ("8", "16", "32")},
    }
