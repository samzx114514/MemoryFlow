"""Packed Anchor and token-attention mechanics for LongCite C2A."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Literal, Sequence

import torch


AttentionMode = Literal["anchor", "token"]


@dataclass(frozen=True)
class PackedLayout:
    input_ids: list[int]
    position_ids: list[int]
    token_chunk_ids: list[int]
    source_content_positions: list[list[int]]
    source_anchor_positions: list[int]
    target_content_positions: list[int]
    target_anchor_position: int
    ordinary_lengths: list[int]
    source_truncated: list[bool]
    target_truncated: bool

    @property
    def sequence_length(self) -> int:
        return len(self.input_ids)


def build_packed_layout(
    source_token_ids: Sequence[Sequence[int]],
    target_token_ids: Sequence[int],
    *,
    anchor_token_id: int,
    max_source_tokens: int = 128,
    max_target_tokens: int = 128,
) -> PackedLayout:
    """Pack ``[S1,A1,...,SN,AN,T,AT]`` with chunk-local positions."""
    if not source_token_ids:
        raise ValueError("at least one source chunk is required")
    if max_source_tokens <= 0 or max_target_tokens <= 0:
        raise ValueError("token limits must be positive")

    input_ids: list[int] = []
    position_ids: list[int] = []
    token_chunk_ids: list[int] = []
    source_content_positions: list[list[int]] = []
    source_anchor_positions: list[int] = []
    ordinary_lengths: list[int] = []
    source_truncated: list[bool] = []

    for chunk_index, original in enumerate(source_token_ids):
        tokens = list(original[:max_source_tokens])
        if not tokens:
            raise ValueError("source chunks must contain at least one token")
        source_truncated.append(len(original) > max_source_tokens)
        ordinary_lengths.append(len(tokens))
        positions = list(range(len(input_ids), len(input_ids) + len(tokens)))
        source_content_positions.append(positions)
        input_ids.extend(tokens)
        position_ids.extend(range(len(tokens)))
        token_chunk_ids.extend([chunk_index] * len(tokens))
        source_anchor_positions.append(len(input_ids))
        input_ids.append(anchor_token_id)
        position_ids.append(len(tokens))
        token_chunk_ids.append(chunk_index)

    target_original = list(target_token_ids)
    target_tokens = target_original[:max_target_tokens]
    if not target_tokens:
        raise ValueError("target chunk must contain at least one token")
    target_chunk = len(source_token_ids)
    target_content_positions = list(range(len(input_ids), len(input_ids) + len(target_tokens)))
    input_ids.extend(target_tokens)
    position_ids.extend(range(len(target_tokens)))
    token_chunk_ids.extend([target_chunk] * len(target_tokens))
    target_anchor_position = len(input_ids)
    input_ids.append(anchor_token_id)
    position_ids.append(len(target_tokens))
    token_chunk_ids.append(target_chunk)
    ordinary_lengths.append(len(target_tokens))

    return PackedLayout(
        input_ids=input_ids,
        position_ids=position_ids,
        token_chunk_ids=token_chunk_ids,
        source_content_positions=source_content_positions,
        source_anchor_positions=source_anchor_positions,
        target_content_positions=target_content_positions,
        target_anchor_position=target_anchor_position,
        ordinary_lengths=ordinary_lengths,
        source_truncated=source_truncated,
        target_truncated=len(target_original) > max_target_tokens,
    )


def build_anchor_attention_mask(
    layout: PackedLayout,
    *,
    mode: AttentionMode,
    dtype: torch.dtype,
    device: torch.device | str | None = None,
) -> torch.Tensor:
    """Return the C2A additive 4D mask as ``[1,1,L,L]``."""
    if mode not in ("anchor", "token"):
        raise ValueError("mode must be 'anchor' or 'token'")
    if not dtype.is_floating_point:
        raise TypeError("mask dtype must be floating point")
    length = layout.sequence_length
    chunks = torch.tensor(layout.token_chunk_ids, device=device)
    indices = torch.arange(length, device=device)
    allowed = (chunks[:, None] == chunks[None, :]) & (indices[None, :] <= indices[:, None])

    target_anchor = layout.target_anchor_position
    if mode == "anchor":
        allowed[target_anchor, layout.source_anchor_positions] = True
    else:
        for content_positions in layout.source_content_positions:
            allowed[target_anchor, content_positions] = True
        allowed[target_anchor, layout.source_anchor_positions] = False

    if not bool(torch.diagonal(allowed).all().item()):
        raise ValueError("every query must be able to attend to itself")
    mask = torch.full((length, length), torch.finfo(dtype).min, dtype=dtype, device=device)
    mask.masked_fill_(allowed, 0)
    return mask[None, None]


def validate_no_fully_masked_rows(mask: torch.Tensor) -> None:
    if mask.ndim != 4 or mask.shape[:2] != (1, 1) or mask.shape[-1] != mask.shape[-2]:
        raise ValueError("attention mask must have shape [1,1,L,L]")
    if not bool((mask[0, 0] == 0).any(dim=-1).all().item()):
        raise ValueError("attention mask contains a fully masked query row")


def aggregate_candidate_scores(
    attentions: Sequence[torch.Tensor],
    layout: PackedLayout,
    *,
    mode: AttentionMode,
    last_n_layers: int = 4,
) -> tuple[torch.Tensor, torch.Tensor | None]:
    """Aggregate heads/layers and normalize scores only across source candidates.

    Returns ``(mean_scores, sum_diagnostic)``. The second item is only populated
    for token mode.
    """
    if not attentions or last_n_layers <= 0 or len(attentions) < last_n_layers:
        raise ValueError("insufficient attention layers")
    rows = []
    for attention in attentions[-last_n_layers:]:
        if attention.ndim != 4 or attention.shape[0] != 1:
            raise ValueError("attention must have shape [1,heads,query,key]")
        if not bool(torch.isfinite(attention).all().item()):
            raise ValueError("attention contains NaN or Inf")
        rows.append(attention[0, :, layout.target_anchor_position, :].float().mean(dim=0))
    target_row = torch.stack(rows).mean(dim=0)
    if mode == "anchor":
        raw = target_row[layout.source_anchor_positions]
        diagnostic = None
    elif mode == "token":
        raw = torch.stack([target_row[positions].mean() for positions in layout.source_content_positions])
        diagnostic = torch.stack([target_row[positions].sum() for positions in layout.source_content_positions])
    else:
        raise ValueError("mode must be 'anchor' or 'token'")
    denominator = raw.sum()
    if not bool(torch.isfinite(raw).all().item()) or float(denominator.item()) <= 0:
        raise ValueError("candidate attention scores are non-finite or sum to zero")
    return raw / denominator, diagnostic


def maximum_masked_attention(attentions: Sequence[torch.Tensor], mask: torch.Tensor) -> float:
    blocked = mask[0, 0] != 0
    maximum = 0.0
    for attention in attentions:
        values = attention[0].float().masked_select(blocked.unsqueeze(0))
        if values.numel():
            maximum = max(maximum, float(values.abs().max().item()))
    return maximum


def stable_tolerance_ranking(
    source_ids: Sequence[str], scores: Sequence[float], *, tolerance: float = 1e-6
) -> list[str]:
    """Rank scores with source-hash tie breaks for near-equal values."""
    if len(source_ids) != len(scores) or len(source_ids) != len(set(source_ids)):
        raise ValueError("source IDs and scores must have equal unique lengths")
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")
    ordered = sorted(zip(source_ids, scores), key=lambda item: (-item[1], item[0]))
    groups: list[list[tuple[str, float]]] = []
    for item in ordered:
        if not groups or abs(item[1] - groups[-1][0][1]) >= tolerance:
            groups.append([item])
        else:
            groups[-1].append(item)
    result: list[str] = []
    for group in groups:
        result.extend(
            source_id
            for source_id, _ in sorted(
                group, key=lambda item: hashlib.sha256(item[0].encode("utf-8")).hexdigest()
            )
        )
    return result


def kendall_tau_for_rankings(first: Sequence[str], second: Sequence[str]) -> float:
    """Compute Kendall tau-a for two complete rankings without tied IDs."""
    if len(first) != len(second) or set(first) != set(second) or len(first) != len(set(first)):
        raise ValueError("rankings must contain the same unique IDs")
    positions = {source_id: index for index, source_id in enumerate(second)}
    concordant = discordant = 0
    for left in range(len(first)):
        for right in range(left + 1, len(first)):
            if positions[first[left]] < positions[first[right]]:
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return 1.0 if total == 0 else (concordant - discordant) / total
