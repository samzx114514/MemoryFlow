#!/usr/bin/env python3
"""Run the two frozen rounds with Qwen2.5-7B-Instruct (greedy) and freeze the texts.

The intermediate conclusion is the literal round-1 output and is inserted verbatim
into the round-2 prompt. The final sentence is the literal round-2 output; only these
frozen texts are scored afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core

SEED = 20261106


def sha256_file(path: str | Path) -> str:
    return core.sha256_file(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--physical-gpu", type=int, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args(argv)

    spec = core.read_json(args.spec)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.physical_gpu)
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.manual_seed(SEED)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False

    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = (
        AutoModelForCausalLM.from_pretrained(
            args.model, local_files_only=True, dtype=torch.bfloat16, attn_implementation="eager"
        )
        .to("cuda")
        .eval()
    )
    model.requires_grad_(False)

    def generate(prompt: str) -> dict:
        messages = [{"role": "user", "content": prompt}]
        rendered = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        encoded = tokenizer(rendered, add_special_tokens=False, return_tensors="pt").to("cuda")
        started = time.monotonic()
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        torch.cuda.synchronize()
        elapsed = time.monotonic() - started
        generated_ids = output[0][encoded["input_ids"].shape[1] :].tolist()
        text = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()
        return {
            "prompt": prompt,
            "rendered_prompt": rendered,
            "prompt_tokens": int(encoded["input_ids"].shape[1]),
            "generated_tokens": len(generated_ids),
            "generated_ids": generated_ids,
            "text": text,
            "sha256": core.sha256_text(text),
            "seconds": round(elapsed, 3),
            "finish_reason": (
                "eos" if generated_ids and generated_ids[-1] == tokenizer.eos_token_id else "length"
            ),
        }

    round1 = generate(spec["rounds"][0]["prompt"])
    round2_prompt = spec["rounds"][1]["prompt_template"].replace("[[ROUND1_ANSWER]]", round1["text"])
    round2 = generate(round2_prompt)

    frozen = json.loads(json.dumps(spec))
    frozen["rounds"][0]["prompt"] = round1["prompt"]
    frozen["rounds"][1].pop("prompt_template", None)
    frozen["rounds"][1]["prompt"] = round2["prompt"]
    frozen["rounds"][0]["answer"] = round1["text"]
    frozen["rounds"][1]["answer"] = round2["text"]
    frozen["generation"] = {
        "seed": SEED,
        "model_path": args.model,
        "model_config_sha256": core.sha256_file(Path(args.model) / "config.json"),
        "tokenizer_config_sha256": core.sha256_file(Path(args.model) / "tokenizer_config.json"),
        "dtype": "bfloat16",
        "attn_implementation": "eager",
        "decoding": "greedy",
        "max_new_tokens": args.max_new_tokens,
        "physical_gpu": args.physical_gpu,
        "round1": {k: round1[k] for k in ("rendered_prompt", "prompt_tokens", "generated_tokens",
                                          "generated_ids", "text", "sha256", "seconds", "finish_reason")},
        "round2": {k: round2[k] for k in ("rendered_prompt", "prompt_tokens", "generated_tokens",
                                          "generated_ids", "text", "sha256", "seconds", "finish_reason")},
        "torch": torch.__version__,
        "transformers": __import__("transformers").__version__,
    }
    frozen["frozen_sha256"] = core.sha256_text(
        core.canonical({k: v for k, v in frozen.items() if k != "frozen_sha256"})
    )
    core.write_json(args.out, frozen)
    print(json.dumps({
        "round1": frozen["rounds"][0]["answer"],
        "round2": frozen["rounds"][1]["answer"],
        "round1_tokens": frozen["generation"]["round1"]["generated_tokens"],
        "round2_tokens": frozen["generation"]["round2"]["generated_tokens"],
        "frozen_sha256": frozen["frozen_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
