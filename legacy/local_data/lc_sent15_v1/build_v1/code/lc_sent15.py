"""Pure parsing and deterministic candidate helpers for LC-Sent-15-v1."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable, Iterator


DOCUMENT_START = "[Document Start]"
DOCUMENT_END = "[Document End]"
SOURCE_TAG_RE = re.compile(r"<C(\d+)>")
STATEMENT_RE = re.compile(r"<statement>(.*?)</statement>", re.DOTALL)
CITE_TAG_RE = re.compile(r"<cite>(.*?)</cite>", re.DOTALL)
CITE_RANGE_RE = re.compile(r"\[(\d+)-(\d+)\]")
STRICT_CITE_RE = re.compile(r"(?:\s*\[\d+-\d+\]\s*)+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")
WHITESPACE_RE = re.compile(r"\s+")


class ParseError(ValueError):
    """A row-level prompt or response format error."""


@dataclass(frozen=True)
class SourceUnit:
    sentence_index: int
    text: str


@dataclass(frozen=True)
class ParsedPrompt:
    query: str
    document_id: str
    document_sha256: str
    sources: tuple[SourceUnit, ...]


@dataclass(frozen=True)
class ParsedStatement:
    statement_index: int
    text: str
    raw_statement_block: str
    raw_citation_expression: str
    citation_ranges: tuple[tuple[int, int], ...]
    citation_ids: tuple[int, ...]
    status: str
    error: str | None = None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip().casefold()


def detect_language(query: str) -> str:
    if CJK_RE.search(query):
        return "zh"
    if LATIN_RE.search(query):
        return "en"
    return "other"


def parse_prompt(prompt: str) -> ParsedPrompt:
    start = prompt.find(DOCUMENT_START)
    end = prompt.rfind(DOCUMENT_END)
    if start < 0 or end < 0 or end <= start:
        raise ParseError("missing_or_misordered_document_markers")
    body_start = start + len(DOCUMENT_START)
    document_body = prompt[body_start:end]
    query = prompt[end + len(DOCUMENT_END) :].strip()
    if not query:
        raise ParseError("empty_query")
    matches = list(SOURCE_TAG_RE.finditer(document_body))
    if not matches:
        raise ParseError("no_source_tags")
    sources: list[SourceUnit] = []
    seen: set[int] = set()
    for index, match in enumerate(matches):
        sentence_index = int(match.group(1))
        if sentence_index in seen:
            raise ParseError("duplicate_source_index")
        seen.add(sentence_index)
        text_start = match.end()
        text_end = matches[index + 1].start() if index + 1 < len(matches) else len(document_body)
        sources.append(SourceUnit(sentence_index=sentence_index, text=document_body[text_start:text_end]))
    canonical = json.dumps(
        [[source.sentence_index, source.text] for source in sources],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    document_sha = sha256_text(canonical)
    return ParsedPrompt(
        query=query,
        document_id=f"lc45k-doc:{document_sha}",
        document_sha256=document_sha,
        sources=tuple(sources),
    )


def expand_ranges(ranges: Iterable[tuple[int, int]]) -> tuple[int, ...]:
    ordered: list[int] = []
    seen: set[int] = set()
    for start, end in ranges:
        if start > end:
            raise ParseError("reversed_citation_range")
        for value in range(start, end + 1):
            if value not in seen:
                seen.add(value)
                ordered.append(value)
    return tuple(ordered)


def parse_response(response: str, valid_source_ids: set[int]) -> tuple[ParsedStatement, ...]:
    matches = list(STATEMENT_RE.finditer(response))
    if not matches:
        raise ParseError("no_statement_tags")
    residue = STATEMENT_RE.sub("", response)
    if residue.strip():
        raise ParseError("text_outside_statement_tags")
    statements: list[ParsedStatement] = []
    for statement_index, match in enumerate(matches):
        block = match.group(1)
        cite_matches = list(CITE_TAG_RE.finditer(block))
        if len(cite_matches) != 1:
            statements.append(
                ParsedStatement(statement_index, "", block, "", (), (), "malformed", "cite_tag_count_not_one")
            )
            continue
        cite_match = cite_matches[0]
        citation_expression = cite_match.group(1)
        text = (block[: cite_match.start()] + block[cite_match.end() :]).strip()
        if not text:
            statements.append(
                ParsedStatement(statement_index, text, block, citation_expression, (), (), "empty_statement", "empty_statement")
            )
            continue
        if not citation_expression.strip():
            statements.append(
                ParsedStatement(statement_index, text, block, citation_expression, (), (), "no_citation", None)
            )
            continue
        if not STRICT_CITE_RE.fullmatch(citation_expression):
            statements.append(
                ParsedStatement(statement_index, text, block, citation_expression, (), (), "malformed", "malformed_citation_expression")
            )
            continue
        ranges = tuple((int(a), int(b)) for a, b in CITE_RANGE_RE.findall(citation_expression))
        try:
            citation_ids = expand_ranges(ranges)
        except ParseError as error:
            statements.append(
                ParsedStatement(statement_index, text, block, citation_expression, ranges, (), "malformed", str(error))
            )
            continue
        missing = [value for value in citation_ids if value not in valid_source_ids]
        if missing:
            statements.append(
                ParsedStatement(
                    statement_index,
                    text,
                    block,
                    citation_expression,
                    ranges,
                    citation_ids,
                    "out_of_range",
                    "missing_source_ids:" + ",".join(map(str, missing)),
                )
            )
            continue
        statements.append(
            ParsedStatement(statement_index, text, block, citation_expression, ranges, citation_ids, "valid", None)
        )
    return tuple(statements)


def iter_jsonl(path: str) -> Iterator[tuple[int, dict]]:
    with open(path, "r", encoding="utf-8") as handle:
        for row_index, line in enumerate(handle):
            if not line.strip():
                raise ParseError(f"blank_jsonl_line:{row_index}")
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ParseError(f"json_decode_error:{row_index}:{error.msg}") from error
            yield row_index, row


def split_for_document(document_id: str) -> str:
    value = int(hashlib.sha256(("LC-Sent-15-v1:split:" + document_id).encode("utf-8")).hexdigest()[:16], 16)
    bucket = value / float(2**64)
    if bucket < 0.66:
        return "train"
    if bucket < 0.84:
        return "dev"
    return "reserve"


def source_id(document_sha256: str, sentence_index: int) -> str:
    return f"lc15:d{document_sha256}:c{sentence_index}"


def target_id(row_index: int, statement_index: int) -> str:
    return f"lc15:r{row_index}:s{statement_index}"


def deterministic_candidates(
    example_id: str,
    positive_ids: Iterable[str],
    all_source_ids: Iterable[str],
    candidate_count: int = 15,
) -> tuple[str, ...]:
    positives = tuple(dict.fromkeys(positive_ids))
    if not positives or len(positives) > candidate_count:
        raise ValueError("invalid_positive_count")
    positive_set = set(positives)
    negatives = [item for item in all_source_ids if item not in positive_set]
    needed = candidate_count - len(positives)
    if len(negatives) < needed:
        raise ValueError("insufficient_negatives")
    negative_seed = sha256_text(f"LC-Sent-15-v1:negative:{example_id}:{candidate_count}")
    negatives.sort(key=lambda item: (sha256_text(f"{negative_seed}:{item}"), item))
    chosen = list(positives) + negatives[:needed]
    order_seed = sha256_text(f"LC-Sent-15-v1:order:{example_id}:{candidate_count}")
    chosen.sort(key=lambda item: (sha256_text(f"{order_seed}:{item}"), item))
    if len(chosen) != candidate_count or len(set(chosen)) != candidate_count:
        raise AssertionError("candidate_invariant_failed")
    return tuple(chosen)
