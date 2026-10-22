"""Padded pairwise batches for C4A efficiency and reference scoring."""

from __future__ import annotations
from typing import Sequence
import torch
from memoryflow.anchor_attention import PackedLayout, build_anchor_attention_mask


def padded_pairwise_tensors(layouts: Sequence[PackedLayout], *, pad_token_id: int, device: str = "cuda"):
    if not layouts:
        raise ValueError("layouts cannot be empty")
    maximum=max(x.sequence_length for x in layouts);batch=len(layouts);blocked=torch.finfo(torch.float32).min
    ids=torch.full((batch,maximum),pad_token_id,dtype=torch.long,device=device);positions=torch.zeros((batch,maximum),dtype=torch.long,device=device);mask=torch.full((batch,1,maximum,maximum),blocked,dtype=torch.float32,device=device)
    for index,layout in enumerate(layouts):
        length=layout.sequence_length;ids[index,:length]=torch.tensor(layout.input_ids,dtype=torch.long,device=device);positions[index,:length]=torch.tensor(layout.position_ids,dtype=torch.long,device=device);local=build_anchor_attention_mask(layout,mode="anchor",dtype=torch.float32,device=device);mask[index,:,:length,:length]=local[0]
        for padding in range(length,maximum):mask[index,0,padding,padding]=0
    return ids,positions,mask


def inject_batched_anchor(base: torch.Tensor, layouts: Sequence[PackedLayout], anchor: torch.Tensor) -> torch.Tensor:
    if base.ndim!=3 or base.shape[0]!=len(layouts):raise ValueError("batch/layout mismatch")
    result=base.detach().clone()
    for index,layout in enumerate(layouts):
        result[index,layout.source_anchor_positions+[layout.target_anchor_position]]=anchor.to(result.dtype)
    return result


def batched_pairwise_raw_scores(attentions, layouts: Sequence[PackedLayout], last_n_layers: int = 8) -> torch.Tensor:
    values=[]
    for batch_index,layout in enumerate(layouts):
        per_layer=[layer[batch_index,:,layout.target_anchor_position,layout.source_anchor_positions[0]].float().mean() for layer in attentions[-last_n_layers:]]
        values.append(torch.stack(per_layer).mean())
    result=torch.stack(values)
    if not torch.isfinite(result).all():raise ValueError("nonfinite pairwise score")
    return result
