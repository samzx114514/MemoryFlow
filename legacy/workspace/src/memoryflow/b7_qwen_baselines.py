from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
from torch.nn import functional as F


PROMPT_TEMPLATE = """Source:
{source}

Target statement:
{target}

Question: Does the source provide evidence that supports or was used to derive the target statement?
Answer only Yes or No.
"""
YES_TEXT = "Yes"
NO_TEXT = "No"


def left_pad(sequences: list[list[int]], pad_token_id: int) -> tuple[torch.Tensor, torch.Tensor]:
    maximum = max(map(len, sequences))
    input_ids = torch.full((len(sequences), maximum), pad_token_id, dtype=torch.long)
    attention_mask = torch.zeros((len(sequences), maximum), dtype=torch.long)
    for index, sequence in enumerate(sequences):
        input_ids[index, maximum - len(sequence) :] = torch.tensor(sequence, dtype=torch.long)
        attention_mask[index, maximum - len(sequence) :] = 1
    return input_ids, attention_mask


def build_independent_chunks(
    tokenizer: Any,
    source_texts: list[str],
    target_text: str,
    anchor_id: int,
    max_ordinary_tokens: int = 192,
    anchor_position_id: int = 192,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, list[int]]:
    texts = list(source_texts) + [target_text]
    sequences = [tokenizer.encode(text, add_special_tokens=False, truncation=True, max_length=max_ordinary_tokens) + [anchor_id] for text in texts]
    input_ids, attention_mask = left_pad(sequences, tokenizer.pad_token_id)
    position_ids = torch.zeros_like(input_ids)
    lengths = []
    for index, sequence in enumerate(sequences):
        ordinary_length = len(sequence) - 1
        lengths.append(ordinary_length)
        start = input_ids.shape[1] - len(sequence)
        position_ids[index, start : start + ordinary_length] = torch.arange(ordinary_length)
        position_ids[index, -1] = anchor_position_id
    return input_ids, attention_mask, position_ids, lengths


def format_relevance_prompt(source: str, target: str) -> str:
    return PROMPT_TEMPLATE.format(source=source, target=target)


def truncate_prompt_ids(tokenizer: Any, source: str, target: str, maximum_length: int) -> list[int]:
    prefix = tokenizer.encode("Source:\n", add_special_tokens=False)
    source_ids = tokenizer.encode(source, add_special_tokens=False)
    middle = tokenizer.encode("\n\nTarget statement:\n", add_special_tokens=False)
    target_ids = tokenizer.encode(target, add_special_tokens=False)
    suffix = tokenizer.encode(
        "\n\nQuestion: Does the source provide evidence that supports or was used to derive the target statement?\nAnswer only Yes or No.\n",
        add_special_tokens=False,
    )
    fixed = len(prefix) + len(middle) + len(suffix)
    available = maximum_length - fixed
    if available <= 0:
        raise ValueError("model context is too small for the frozen prompt")
    if len(target_ids) > available:
        target_ids = target_ids[:available]
        source_ids = []
    else:
        source_ids = source_ids[: available - len(target_ids)]
    return prefix + source_ids + middle + target_ids + suffix


def single_token_answer_scores(
    logits: torch.Tensor, yes_token_id: int, no_token_id: int
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    log_probabilities = F.log_softmax(logits.float(), dim=-1)
    yes = log_probabilities[:, yes_token_id]
    no = log_probabilities[:, no_token_id]
    return yes, no, yes - no


def conditional_sequence_loglikelihood(
    model: Any,
    prompt_ids: list[int],
    answer_ids: list[int],
    device: torch.device | str,
) -> float:
    if not answer_ids:
        raise ValueError("answer sequence must not be empty")
    sequence = prompt_ids + answer_ids
    input_ids = torch.tensor([sequence], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(input_ids)
    with torch.inference_mode():
        outputs = model(input_ids=input_ids, attention_mask=attention_mask, use_cache=False, return_dict=True)
    prompt_length = len(prompt_ids)
    log_probabilities = F.log_softmax(outputs.logits[0, prompt_length - 1 : -1].float(), dim=-1)
    targets = torch.tensor(answer_ids, dtype=torch.long, device=log_probabilities.device)
    return float(log_probabilities.gather(1, targets[:, None]).sum().item())


def cosine_scores(anchor_hidden: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Return final-layer and mean-last-four cosine for [5, 28, hidden]."""
    if anchor_hidden.ndim != 3 or anchor_hidden.shape[0] != 5:
        raise ValueError("anchor_hidden must have shape [5, layers, hidden_size]")
    final = anchor_hidden[:, -1, :].float()
    last_four = anchor_hidden[:, -4:, :].float().mean(dim=1)
    final_scores = F.cosine_similarity(final[:4], final[4].unsqueeze(0), dim=-1)
    last_four_scores = F.cosine_similarity(last_four[:4], last_four[4].unsqueeze(0), dim=-1)
    return final_scores, last_four_scores
