from __future__ import annotations

from collections.abc import Hashable, Mapping, Sequence
from typing import Literal

import torch

ChunkType = Literal["source", "target"]


def _validate_layout(
    token_chunk_ids: Sequence[Hashable],
    chunk_types: Mapping[Hashable, ChunkType],
    anchor_positions: Mapping[Hashable, int],
    sequence_length: int,
) -> list[Hashable]:
    if sequence_length <= 0 or len(token_chunk_ids) != sequence_length:
        raise ValueError("sequence_length must be positive and match token_chunk_ids")

    chunk_ids = set(token_chunk_ids)
    if chunk_ids != set(chunk_types) or chunk_ids != set(anchor_positions):
        raise ValueError("token chunks, chunk_types, and anchor_positions must name the same chunks")
    if any(chunk_type not in ("source", "target") for chunk_type in chunk_types.values()):
        raise ValueError("chunk type must be 'source' or 'target'")

    ordered_chunks = []
    for chunk_id in token_chunk_ids:
        if not ordered_chunks or ordered_chunks[-1] != chunk_id:
            ordered_chunks.append(chunk_id)
    if len(ordered_chunks) != len(chunk_ids):
        raise ValueError("each chunk must occupy one contiguous span")

    for chunk_id in ordered_chunks:
        positions = [index for index, value in enumerate(token_chunk_ids) if value == chunk_id]
        if anchor_positions[chunk_id] != positions[-1]:
            raise ValueError(f"anchor for chunk {chunk_id!r} must be its final token")

    ordered_types = [chunk_types[chunk_id] for chunk_id in ordered_chunks]
    first_target = next((index for index, value in enumerate(ordered_types) if value == "target"), len(ordered_types))
    if "source" in ordered_types[first_target:]:
        raise ValueError("matrix-packed layout requires every Source chunk before every Target chunk")
    if first_target == 0 or first_target == len(ordered_types):
        raise ValueError("matrix-packed layout requires at least one Source and one Target chunk")
    return ordered_chunks


def build_memoryflow_4d_attention_mask(
    *,
    token_chunk_ids: Sequence[Hashable],
    chunk_types: Mapping[Hashable, ChunkType],
    anchor_positions: Mapping[Hashable, int],
    sequence_length: int,
    dtype: torch.dtype,
    device: torch.device | str | None = None,
) -> torch.Tensor:
    """Build the MemoryFlow v0.1 additive mask with shape ``[1, 1, L, L]``.

    Allowed query/key entries are zero. Masked entries are
    ``torch.finfo(dtype).min``. The returned tensor uses ``dtype`` and ``device``.
    """
    _validate_layout(token_chunk_ids, chunk_types, anchor_positions, sequence_length)
    if not dtype.is_floating_point:
        raise TypeError("additive attention mask dtype must be floating point")

    positions = torch.arange(sequence_length, device=device)
    chunk_index = {chunk_id: index for index, chunk_id in enumerate(dict.fromkeys(token_chunk_ids))}
    token_chunks = torch.tensor([chunk_index[value] for value in token_chunk_ids], device=device)
    same_chunk = token_chunks[:, None] == token_chunks[None, :]
    within_chunk_causal = same_chunk & (positions[None, :] <= positions[:, None])

    source_anchor_keys = torch.zeros(sequence_length, dtype=torch.bool, device=device)
    target_anchor_queries = torch.zeros(sequence_length, dtype=torch.bool, device=device)
    for chunk_id, anchor_position in anchor_positions.items():
        if chunk_types[chunk_id] == "source":
            source_anchor_keys[anchor_position] = True
        else:
            target_anchor_queries[anchor_position] = True
    target_to_source_anchors = target_anchor_queries[:, None] & source_anchor_keys[None, :]

    allowed = within_chunk_causal | target_to_source_anchors
    mask = torch.full(
        (sequence_length, sequence_length),
        fill_value=torch.finfo(dtype).min,
        dtype=dtype,
        device=device,
    )
    mask.masked_fill_(allowed, 0)
    return mask.unsqueeze(0).unsqueeze(0)


def extract_anchor_relation_matrix(
    attentions: Sequence[torch.Tensor],
    *,
    source_anchor_positions: Sequence[int],
    target_anchor_positions: Sequence[int],
) -> torch.Tensor:
    """Average raw anchor probabilities over layers and heads into ``[target, source]``."""
    if not attentions:
        raise ValueError("at least one Attention tensor is required")
    per_layer = []
    for attention in attentions:
        if attention.ndim != 4 or attention.shape[0] != 1:
            raise ValueError("Attention tensors must have shape [1, heads, query, key]")
        selected_queries = attention[0][:, list(target_anchor_positions), :]
        per_layer.append(selected_queries[:, :, list(source_anchor_positions)])
    return torch.stack(per_layer).float().mean(dim=(0, 1))
