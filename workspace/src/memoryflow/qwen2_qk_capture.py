from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import torch
from transformers.models.qwen2.modeling_qwen2 import apply_rotary_pos_emb, repeat_kv


class Qwen2TargetQKCapture:
    """Capture the exact scaled QK row used by Qwen2 eager attention."""

    def __init__(self, model: torch.nn.Module, target_position: int) -> None:
        self.model = model
        self.target_position = target_position
        self._handles: list[Any] = []
        self._pending: dict[int, dict[str, torch.Tensor]] = {}
        self.target_qk_logits: dict[int, torch.Tensor] = {}

    def __enter__(self) -> Qwen2TargetQKCapture:
        layers = self.model.model.layers
        for layer_index, layer in enumerate(layers):
            attention = layer.self_attn
            self._handles.append(
                attention.register_forward_pre_hook(
                    self._make_attention_pre_hook(layer_index), with_kwargs=True
                )
            )
            self._handles.append(
                attention.q_proj.register_forward_hook(self._make_projection_hook(layer_index, "query"))
            )
            self._handles.append(
                attention.k_proj.register_forward_hook(self._make_projection_hook(layer_index, "key"))
            )
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        for handle in self._handles:
            handle.remove()
        self._handles.clear()
        self._pending.clear()

    def _make_attention_pre_hook(self, layer_index: int):
        def hook(module: torch.nn.Module, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
            position_embeddings = kwargs.get("position_embeddings")
            if position_embeddings is None or len(position_embeddings) != 2:
                raise RuntimeError("Qwen2 attention did not receive the expected (cos, sin) position embeddings")
            cos, sin = position_embeddings
            self._pending[layer_index] = {"cos": cos, "sin": sin}

        return hook

    def _make_projection_hook(self, layer_index: int, projection: str):
        def hook(module: torch.nn.Module, args: tuple[Any, ...], output: torch.Tensor) -> None:
            pending = self._pending.get(layer_index)
            if pending is None:
                raise RuntimeError(f"missing attention context for layer {layer_index}")
            pending[projection] = output
            if "query" not in pending or "key" not in pending:
                return

            attention = self.model.model.layers[layer_index].self_attn
            query_projection = pending["query"]
            key_projection = pending["key"]
            batch_size, sequence_length, _ = query_projection.shape
            query = query_projection.view(
                batch_size, sequence_length, attention.config.num_attention_heads, attention.head_dim
            ).transpose(1, 2)
            key = key_projection.view(
                batch_size, sequence_length, attention.config.num_key_value_heads, attention.head_dim
            ).transpose(1, 2)
            query, key = apply_rotary_pos_emb(query, key, pending["cos"], pending["sin"])
            key = repeat_kv(key, attention.num_key_value_groups)
            target_query = query[:, :, self.target_position : self.target_position + 1, :]
            scaled_logits = torch.matmul(target_query, key.transpose(2, 3)) * attention.scaling
            self.target_qk_logits[layer_index] = scaled_logits[0, :, 0, :].detach()
            pending.clear()

        return hook

    def stacked(self) -> torch.Tensor:
        expected_layers = len(self.model.model.layers)
        missing = sorted(set(range(expected_layers)) - set(self.target_qk_logits))
        if missing:
            raise RuntimeError(f"QK capture is incomplete; missing layers: {missing}")
        return torch.stack([self.target_qk_logits[index] for index in range(expected_layers)])


def reconstruct_target_attention(
    target_qk_logits: torch.Tensor,
    additive_mask: torch.Tensor,
    target_position: int,
) -> torch.Tensor:
    """Reproduce eager attention's float32 softmax and cast-back behavior."""

    if additive_mask.ndim != 4 or additive_mask.shape[0] != 1 or additive_mask.shape[1] != 1:
        raise ValueError("additive_mask must have shape [1, 1, sequence_length, sequence_length]")
    mask_row = additive_mask[0, 0, target_position, :]
    return torch.softmax(target_qk_logits + mask_row, dim=-1, dtype=torch.float32).to(target_qk_logits.dtype)


def extract_source_anchor_logits(
    target_qk_logits: torch.Tensor, source_anchor_positions: Sequence[int]
) -> torch.Tensor:
    return target_qk_logits[:, :, list(source_anchor_positions)]
