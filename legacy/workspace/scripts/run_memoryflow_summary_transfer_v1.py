#!/usr/bin/env python3
"""Create-only two-track Researcher Memory Summary transfer experiment."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace"
sys.path.insert(0, str(WORKSPACE / "src"))

from memoryflow.lc_sent15_bm25 import GroupBM25
from memoryflow.lc_sent15_q2 import DirectionalFull64
from memoryflow.source_prior_relational import SymmetricRelation

INPUT = Path("/data2/pkuiti/songzhengxing_intern/all_samples.json")
SUPPLEMENT = Path("/data2/pkuiti/songzhengxing_intern/AAAI27_supplementary_material.zip")
MODEL = Path("/data2/pkuiti/songzhengxing_intern/model/Qwen2.5-7B-Instruct")
MODEL_MANIFEST = WORKSPACE / "results/c5f_ranking_continuation_243_v1/model_manifest/model_sha256_manifest.json"
Q1_ROOT = WORKSPACE / "results/lc_sent15_v1_q1c_rsym_convergence_v1/runs"
Q2_ROOT = WORKSPACE / "results/lc_sent15_v1_q2_head_loss_v1/runs/H3_D_FULL_64/L1_LISTWISE_CE"
FINAL = ROOT / "results/memoryflow_summary_transfer_v1"
EXPECTED_INPUT_SHA = "0dffd2ca7fcb917d9e2db6f190dc840208715f25f40b2d44d695eae521ff9796"
RANDOM_SEED = 20260827
MAX_CONTEXT = 32768

TRACK_A_TEMPLATE = """你是报告生成系统中的Researcher Agent。

用户最终任务：
{query}

检索文档：
{document}

请将该文档中与用户任务最相关的信息压缩为一条供下游Reporter使用的Memory Summary。

要求：
1. 只能依据给定文档；
2. 保留关键实体、时间、数字、政策、事件和因果关系；
3. 使用1至3个完整句子；
4. 不输出引用编号、文档编号、分析过程或额外说明；
5. 即使相关性较弱，也总结其中与任务最接近的信息。"""

TRACK_B_TEMPLATE = """你是报告生成系统中的Researcher Agent。

用户最终任务：
{query}

下面提供了多篇检索文档：
{multi_document_context}

请综合这些材料，为下游Reporter生成一份信息密集的Memory Summary。

要求：
1. 只依据给定材料；
2. 覆盖用户任务中最重要的方面；
3. 保留关键实体、时间、数字、政策、事件和因果关系；
4. 每个信息点使用1至2个完整句子；
5. 可以综合多篇文档，但不要输出引用编号、Document ID或分析过程；
6. 不要生成完整最终报告，只生成供Reporter使用的研究记忆。"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def language_of(text: str) -> str:
    return "zh" if re.search(r"[\u3400-\u9fff]", text) else "en"


def gpu_snapshot() -> list[dict]:
    cmd = ["nvidia-smi", "--query-gpu=index,uuid,name,memory.total,memory.used,memory.free,utilization.gpu", "--format=csv,noheader,nounits"]
    rows = []
    for line in subprocess.check_output(cmd, text=True).splitlines():
        index, uuid, name, total, used, free, util = [x.strip() for x in line.split(",")]
        rows.append({"physical_gpu": int(index), "uuid": uuid, "name": name, "total_mib": int(total), "used_mib": int(used), "free_mib": int(free), "utilization_percent": int(util)})
    return rows


def choose_gpu(rows: list[dict]) -> dict:
    # FP32 Q0 extraction measured ~29 GiB. Require at least 48 GiB free.
    safe = [x for x in rows if x["free_mib"] >= 48 * 1024 and x["utilization_percent"] <= 20]
    if not safe:
        raise RuntimeError("NO_SAFE_GPU_WITH_48_GIB_MARGIN")
    return max(safe, key=lambda x: (x["free_mib"], -x["utilization_percent"], -x["physical_gpu"]))


def verify_inputs() -> tuple[list[dict], dict]:
    if sha256(INPUT) != EXPECTED_INPUT_SHA:
        raise RuntimeError("all_samples.json SHA256 mismatch")
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    slots = sum(len(x["documents"]) for x in data)
    nonempty = sum(bool(v.strip()) for x in data for v in x["documents"].values())
    if len(data) != 10 or slots != 139 or nonempty != 138:
        raise RuntimeError("input count contract mismatch")
    d7 = data[6]["documents"]
    if d7["15"].strip() or normalize_text(d7["13"]) != normalize_text(d7["14"]):
        raise RuntimeError("sample-7 duplicate/empty contract mismatch")
    unique = sum(len({normalize_text(v) for v in x["documents"].values() if v.strip()}) for x in data)
    if unique != 137:
        raise RuntimeError("unique target count mismatch")
    return data, {"query_count": 10, "document_slots": slots, "nonempty_documents": nonempty, "unique_nonempty_documents": unique, "sample_7_document_15_empty": True, "sample_7_documents_13_14_normalized_identical": True}


def verify_model() -> dict:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = MODEL / entry["name"]
        if not path.is_file() or path.stat().st_size != entry["size_bytes"] or sha256(path) != entry["sha256"]:
            raise RuntimeError(f"model verification failed: {entry['name']}")
    return {"path": str(MODEL), "revision": manifest.get("revision", "unavailable"), "manifest_path": str(MODEL_MANIFEST), "manifest_file_sha256": sha256(MODEL_MANIFEST), "internal_manifest_sha256": manifest["manifest_sha256"], "files": manifest["files"]}


def checkpoint_manifest() -> dict:
    result = {"q1c_rsym": {}, "q2_d_full_64_l1_listwise_ce": {}}
    for seed in (0, 1, 2):
        q1 = Q1_ROOT / f"seed_{seed}/best.pt"
        q2 = Q2_ROOT / f"seed_{seed}/best.pt"
        result["q1c_rsym"][str(seed)] = {"path": str(q1), "sha256": sha256(q1)}
        result["q2_d_full_64_l1_listwise_ce"][str(seed)] = {"path": str(q2), "sha256": sha256(q2)}
    return result


def render(tokenizer, user_text: str) -> str:
    return tokenizer.apply_chat_template([{"role": "user", "content": user_text}], tokenize=False, add_generation_prompt=True, enable_thinking=False)


def load_generation_model():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(str(MODEL), local_files_only=True, dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda").eval()
    model.requires_grad_(False)
    return tokenizer, model


def unload(model) -> None:
    del model
    gc.collect()
    torch.cuda.empty_cache()


def generate_one(tokenizer, model, user_text: str, max_new_tokens: int) -> tuple[str, dict]:
    prompt = render(tokenizer, user_text)
    encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to("cuda")
    prompt_tokens = int(encoded.input_ids.shape[1])
    if prompt_tokens + max_new_tokens > MAX_CONTEXT:
        raise RuntimeError(f"context contract exceeded: {prompt_tokens}+{max_new_tokens}")
    torch.cuda.synchronize()
    started = time.time()
    with torch.inference_mode():
        output = model.generate(**encoded, do_sample=False, temperature=0.0, max_new_tokens=max_new_tokens, pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id)
    torch.cuda.synchronize()
    elapsed = time.time() - started
    generated = output[0, prompt_tokens:]
    summary = tokenizer.decode(generated, skip_special_tokens=True).strip()
    return summary, {"prompt": prompt, "prompt_tokens": prompt_tokens, "generated_tokens": int(generated.numel()), "elapsed_seconds": elapsed, "tokens_per_second": float(generated.numel() / elapsed) if elapsed else 0.0}


def load_embedding_model():
    from transformers import AutoModel, AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL), local_files_only=True)
    model = AutoModel.from_pretrained(str(MODEL), local_files_only=True, dtype=torch.float32, attn_implementation="eager").to("cuda").eval()
    model.requires_grad_(False)
    return tokenizer, model


def encode_texts(tokenizer, model, texts: list[str], *, batch_size: int = 8) -> tuple[np.ndarray, list[int]]:
    output, lengths = [], []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        lengths.extend(len(tokenizer(x, add_special_tokens=True, truncation=False)["input_ids"]) for x in batch)
        enc = tokenizer(batch, padding=True, truncation=True, max_length=512, return_tensors="pt")
        enc = {k: v.to("cuda") for k, v in enc.items()}
        with torch.inference_mode():
            hidden = model(**enc, return_dict=True).last_hidden_state.float()
        mask = enc["attention_mask"].unsqueeze(-1).to(hidden.dtype)
        vec = (hidden * mask).sum(1) / mask.sum(1).clamp_min(1.0)
        vec = torch.nn.functional.normalize(vec, p=2, dim=1)
        output.append(vec.cpu().numpy().astype(np.float32, copy=False))
    return np.concatenate(output), lengths


def zscore(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    std = float(values.std())
    return np.zeros_like(values) if std == 0 else (values - values.mean()) / std


def score_heads(target: np.ndarray, sources: np.ndarray) -> dict[str, dict[int, np.ndarray]]:
    t = torch.from_numpy(target.astype(np.float32))
    s = torch.from_numpy(sources.astype(np.float32))
    result: dict[str, dict[int, np.ndarray]] = {"rsym": {}, "dfull": {}}
    for seed in (0, 1, 2):
        for name, cls, path in (
            ("rsym", lambda: SymmetricRelation(3584), Q1_ROOT / f"seed_{seed}/best.pt"),
            ("dfull", DirectionalFull64, Q2_ROOT / f"seed_{seed}/best.pt"),
        ):
            head = cls().eval()
            head.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
            with torch.inference_mode():
                result[name][seed] = head(t, s).cpu().numpy().astype(np.float64)
    return result


def ranks_metrics(ranks: Sequence[int]) -> dict:
    a = np.asarray(ranks, dtype=np.int64)
    return {"target_count": int(len(a)), "hit_at_1": float(np.mean(a == 1)), "mrr": float(np.mean(1.0 / a)), "ndcg_at_5": float(np.mean(np.where(a <= 5, 1.0 / np.log2(a + 1), 0.0))), "mean_gold_rank": float(np.mean(a)), "top1_successes": int(np.sum(a == 1)), "top1_failures": int(np.sum(a != 1))}


def multiclass_ndcg(ranking: list[str], gold: set[str], k: int = 5) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, x in enumerate(ranking[:k]) if x in gold)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(k, len(gold))))
    return dcg / ideal


def method_metrics(rows: list[dict]) -> dict:
    return {"target_count": len(rows), "hit_at_1": float(np.mean([x["rank"] == 1 for x in rows])), "mrr": float(np.mean([1 / x["rank"] for x in rows])), "ndcg_at_5": float(np.mean([x["ndcg_at_5"] for x in rows])), "mean_gold_rank": float(np.mean([x["rank"] for x in rows])), "top1_successes": sum(x["rank"] == 1 for x in rows), "top1_failures": sum(x["rank"] != 1 for x in rows)}


def track_a(data: list[dict], root: Path) -> dict:
    out_tmp = root / ".track_a.tmp"
    out = root / "track_a"
    if out.exists() or out_tmp.exists():
        raise RuntimeError("Track A create-only collision")
    out_tmp.mkdir(parents=True)
    stage_start = time.time()
    tokenizer, model = load_generation_model()
    torch.cuda.reset_peak_memory_stats()
    targets = []
    for sample in data:
        seen: dict[str, dict] = {}
        for doc_id, text in sample["documents"].items():
            if not text.strip():
                continue
            key = normalize_text(text)
            if key in seen:
                seen[key]["gold_document_ids"].append(f"D{doc_id}")
                continue
            rec = {"target_id": f"Q{sample['id']}_D{doc_id}", "sample_id": sample["id"], "query": sample["query"], "source_document_id": f"D{doc_id}", "gold_document_ids": [f"D{doc_id}"], "source_document": text}
            seen[key] = rec
            targets.append(rec)
        # D13/D14 is discovered before generation and represented by one target.
    for i, rec in enumerate(targets, 1):
        user = TRACK_A_TEMPLATE.format(query=rec["query"], document=rec["source_document"])
        summary, info = generate_one(tokenizer, model, user, 192)
        rec.update({"user_prompt": user, "rendered_prompt": info.pop("prompt"), "summary": summary, "generation": info})
        print(f"TRACK_A_GENERATED {i}/137 {rec['target_id']} tokens={info['generated_tokens']} sec={info['elapsed_seconds']:.3f}", flush=True)
    generation_peak = int(torch.cuda.max_memory_allocated())
    unload(model)

    tokenizer, model = load_embedding_model()
    torch.cuda.reset_peak_memory_stats()
    all_source_keys, all_source_texts = [], []
    for sample in data:
        for doc_id, text in sample["documents"].items():
            if text.strip():
                all_source_keys.append((sample["id"], f"D{doc_id}")); all_source_texts.append(text)
    source_vecs, source_lengths = encode_texts(tokenizer, model, all_source_texts)
    target_vecs, _ = encode_texts(tokenizer, model, [x["summary"] for x in targets])
    embedding_peak = int(torch.cuda.max_memory_allocated())
    unload(model)
    source_vector = dict(zip(all_source_keys, source_vecs)); source_length = dict(zip(all_source_keys, source_lengths))

    random_gen = random.Random(RANDOM_SEED)
    target_rows: list[dict] = []
    for idx, rec in enumerate(targets):
        sample = next(x for x in data if x["id"] == rec["sample_id"])
        ids = [f"D{k}" for k, v in sample["documents"].items() if v.strip()]
        texts = {f"D{k}": v for k, v in sample["documents"].items() if v.strip()}
        sources = np.stack([source_vector[(rec["sample_id"], x)] for x in ids])
        qvec = target_vecs[idx]
        score_map: dict[str, np.ndarray] = {}
        rand = np.asarray([random_gen.random() for _ in ids]); score_map["random"] = rand
        bm = GroupBM25(texts).score(rec["summary"]); score_map["bm25"] = np.asarray([bm[x] for x in ids], dtype=np.float64)
        score_map["qwen"] = sources @ qvec
        heads = score_heads(np.repeat(qvec[None, :], len(ids), axis=0), sources)
        for name in ("rsym", "dfull"):
            for seed in (0, 1, 2): score_map[f"{name}_seed_{seed}"] = heads[name][seed]
        for seed in (0, 1, 2): score_map[f"fusion_seed_{seed}"] = 0.65 * zscore(score_map[f"dfull_seed_{seed}"]) + 0.35 * zscore(score_map["bm25"])
        gold = set(rec["gold_document_ids"])
        predictions = {}
        for method, values in score_map.items():
            order = sorted(range(len(ids)), key=lambda j: (-float(values[j]), ids[j]))
            ranking = [ids[j] for j in order]
            rank = min(ranking.index(x) + 1 for x in gold)
            predictions[method] = {"ranking": ranking, "top1_document_id": ranking[0], "rank": rank, "ndcg_at_5": multiclass_ndcg(ranking, gold), "scores": [{"document_id": ids[j], "raw_score": float(values[j]), "z_score": float(zscore(values)[j])} for j in range(len(ids))]}
        target_rows.append({"target_id": rec["target_id"], "sample_id": rec["sample_id"], "gold_document_ids": rec["gold_document_ids"], "source_document_id": rec["source_document_id"], "source_document_token_length": source_length[(rec["sample_id"], rec["source_document_id"])], "summary": rec["summary"], "predictions": predictions})

    methods = list(target_rows[0]["predictions"])
    metrics = {m: method_metrics([{"rank": r["predictions"][m]["rank"], "ndcg_at_5": r["predictions"][m]["ndcg_at_5"]} for r in target_rows]) for m in methods}
    for family in ("rsym", "dfull", "fusion"):
        members = [metrics[f"{family}_seed_{s}"] for s in (0, 1, 2)]
        metrics[f"{family}_three_seed_mean"] = {k: float(np.mean([x[k] for x in members])) for k in ("hit_at_1", "mrr", "ndcg_at_5", "mean_gold_rank")}
        metrics[f"{family}_three_seed_mean"]["target_count_per_seed"] = 137

    ordered = sorted(range(len(target_rows)), key=lambda i: (target_rows[i]["source_document_token_length"], target_rows[i]["target_id"]))
    bucket_index = {}
    for pos, idx in enumerate(ordered): bucket_index[idx] = min(2, pos * 3 // len(ordered)) + 1
    buckets = {}
    for method in methods:
        buckets[method] = []
        for b in (1, 2, 3):
            chosen = [target_rows[i] for i in range(len(target_rows)) if bucket_index[i] == b]
            buckets[method].append({"tercile": b, "target_count": len(chosen), "min_tokens": min(x["source_document_token_length"] for x in chosen), "max_tokens": max(x["source_document_token_length"] for x in chosen), "hit_at_1": float(np.mean([x["predictions"][method]["rank"] == 1 for x in chosen]))})
    for family in ("rsym", "dfull", "fusion"):
        buckets[f"{family}_three_seed_mean"] = [{"tercile": b, "target_count": buckets[f"{family}_seed_0"][b-1]["target_count"], "min_tokens": buckets[f"{family}_seed_0"][b-1]["min_tokens"], "max_tokens": buckets[f"{family}_seed_0"][b-1]["max_tokens"], "hit_at_1": float(np.mean([buckets[f"{family}_seed_{s}"][b-1]["hit_at_1"] for s in (0,1,2)]))} for b in (1,2,3)]

    cases = []
    for wanted in (True, False):
        pool = [r for r in target_rows if (r["predictions"]["fusion_seed_0"]["rank"] == 1) == wanted]
        pool.sort(key=lambda r: (r["predictions"]["bm25"]["rank"] == r["predictions"]["dfull_seed_0"]["rank"], -r["source_document_token_length"], r["target_id"]))
        for r in pool[:4 if wanted else 6]:
            original = next(x for x in targets if x["target_id"] == r["target_id"])
            cases.append({"outcome": "success" if wanted else "failure", "target_id": r["target_id"], "query": original["query"], "summary": r["summary"], "gold_document_ids": r["gold_document_ids"], "source_excerpt": original["source_document"][:600], "top1": {m: r["predictions"][m]["top1_document_id"] for m in ("bm25", "qwen", "rsym_seed_0", "dfull_seed_0", "fusion_seed_0")}})
    write_jsonl(out_tmp / "generations.jsonl", targets)
    write_jsonl(out_tmp / "predictions.jsonl", target_rows)
    dump(out_tmp / "metrics.json", metrics)
    dump(out_tmp / "length_tercile_hit_at_1.json", buckets)
    dump(out_tmp / "representative_cases.json", cases[:10])
    runtime = {"elapsed_seconds": time.time() - stage_start, "generation_peak_memory_allocated_bytes": generation_peak, "embedding_peak_memory_allocated_bytes": embedding_peak, "generated_target_count": len(targets), "candidate_document_slots": len(all_source_keys), "random_seed": RANDOM_SEED}
    dump(out_tmp / "runtime.json", runtime)
    (out_tmp / "MEMORYFLOW_SUMMARY_TRACK_A_COMPLETE").write_text("MEMORYFLOW_SUMMARY_TRACK_A_COMPLETE\n", encoding="utf-8")
    os.replace(out_tmp, out)
    print("MEMORYFLOW_SUMMARY_TRACK_A_COMPLETE", flush=True)
    return runtime


class TextSpan:
    def __init__(self, text: str, start: int, end: int): self.text, self.start, self.end = text, start, end


def split_spans(text: str, language: str) -> list[TextSpan]:
    terminal = r"[。！？；]" if language == "zh" else r"[.!?;]"
    spans, start = [], 0
    for match in re.finditer(terminal + r"|(?:\r?\n){2,}", text):
        end = match.end(); stripped = text[start:end].strip()
        if stripped:
            left = text.find(stripped, start, end); spans.append(TextSpan(stripped, left, left + len(stripped)))
        start = end
    tail = text[start:].strip()
    if tail:
        left = text.find(tail, start); spans.append(TextSpan(tail, left, left + len(tail)))
    return spans


def split_source_sentences(text: str, language: str) -> list[TextSpan]:
    spans = split_spans(text, language)
    return [TextSpan(span.text, 0 if i == 0 else span.start, spans[i+1].start if i+1 < len(spans) else len(text)) for i, span in enumerate(spans)]


def char_to_token_spans(tokenizer, text: str, spans: Sequence[TextSpan]) -> list[list[int]]:
    offsets = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
    result = []
    for span in spans:
        ids = [i for i, (a, b) in enumerate(offsets) if b > span.start and a < span.end]
        result.append([ids[0], ids[-1] + 1] if ids else [0, 0])
    return result


def generated_token_spans(tokenizer, summary: str, clauses: Sequence[TextSpan]) -> list[list[int]]:
    ids = tokenizer(summary, add_special_tokens=False)["input_ids"]
    prefix = [0] + [len(tokenizer.decode(ids[:i], skip_special_tokens=True)) for i in range(1, len(ids)+1)]
    result=[]
    for span in clauses:
        overlap=[i for i,(a,b) in enumerate(zip(prefix[:-1],prefix[1:])) if b>span.start and a<span.end]
        result.append([overlap[0],overlap[-1]+1] if overlap else [0,0])
    return result


def build_context(sample: dict, tokenizer) -> tuple[str, list[dict], list[dict]]:
    parts, docs, sentences, cursor = [], [], [], 0
    lang = language_of(sample["query"])
    for doc_id, text in sample["documents"].items():
        if not text.strip(): continue
        prefix = f"[DOCUMENT D{doc_id} START]\n"; suffix = f"\n[DOCUMENT D{doc_id} END]"
        if parts: parts.append("\n\n"); cursor += 2
        block_start=cursor; parts.append(prefix); cursor += len(prefix); text_start=cursor
        parts.append(text); cursor += len(text); text_end=cursor; parts.append(suffix); cursor += len(suffix)
        docs.append({"document_id":f"D{doc_id}","block_char_span":[block_start,cursor],"text_char_span":[text_start,text_end]})
        for i, span in enumerate(split_source_sentences(text, lang)):
            sentences.append({"sentence_id":f"D{doc_id}_S{i}","document_id":f"D{doc_id}","text":span.text,"document_char_span":[span.start,span.end],"context_char_span":[text_start+span.start,text_start+span.end]})
    context="".join(parts)
    spans=[TextSpan("",x["text_char_span"][0],x["text_char_span"][1]) for x in docs]
    for rec,tokspan in zip(docs,char_to_token_spans(tokenizer,context,spans)): rec["context_token_span"]=tokspan
    sspans=[TextSpan("",x["context_char_span"][0],x["context_char_span"][1]) for x in sentences]
    for rec,tokspan in zip(sentences,char_to_token_spans(tokenizer,context,sspans)): rec["context_token_span"]=tokspan
    return context, docs, sentences


def prediction_record(ids: list[str], doc_ids: list[str], texts: list[str], raw: np.ndarray) -> dict:
    standardized=zscore(raw); order=sorted(range(len(ids)),key=lambda i:(-float(raw[i]),ids[i])); top=order[:3]
    return {"top1":{"sentence_id":ids[top[0]],"document_id":doc_ids[top[0]],"text":texts[top[0]],"raw_score":float(raw[top[0]]),"z_score":float(standardized[top[0]])},"top3":[{"sentence_id":ids[i],"document_id":doc_ids[i],"text":texts[i],"raw_score":float(raw[i]),"z_score":float(standardized[i])} for i in top],"all_scores":[{"sentence_id":ids[i],"document_id":doc_ids[i],"raw_score":float(raw[i]),"z_score":float(standardized[i])} for i in range(len(ids))]}


def judge_records(generations: list[dict], predictions: list[dict], method: str) -> list[dict]:
    by_q={x["sample_id"]:x for x in predictions}; output=[]
    for gen in generations:
        pred=by_q[gen["sample_id"]]; sources={f"S{i}":x["text"] for i,x in enumerate(gen["source_sentences"])}; sid_to_cite={x["sentence_id"]:f"S{i}" for i,x in enumerate(gen["source_sentences"])}
        clauses={}
        for row in pred["clauses"]:
            clause=row["clause"]
            clauses[f"C{row['clause_index']}"]={"content":clause,"citation_list":[sid_to_cite[row["methods"][method]["top1"]["sentence_id"]]]}
        output.append({"idx":gen["sample_id"],"dataset":"all_samples_summary_transfer","query":gen["query"],"response":gen["summary"],"input":sources,"output":clauses})
    return output


def track_b(data: list[dict], root: Path) -> dict:
    out_tmp=root/".track_b.tmp"; out=root/"track_b"
    if out.exists() or out_tmp.exists(): raise RuntimeError("Track B create-only collision")
    out_tmp.mkdir(parents=True); started=time.time()
    tokenizer, model=load_generation_model(); torch.cuda.reset_peak_memory_stats(); generations=[]
    for i,sample in enumerate(data,1):
        context,docs,sentences=build_context(sample,tokenizer)
        user=TRACK_B_TEMPLATE.format(query=sample["query"],multi_document_context=context)
        summary,info=generate_one(tokenizer,model,user,600); clauses=split_spans(summary,language_of(sample["query"])); clause_tokens=generated_token_spans(tokenizer,summary,clauses)
        clause_rows=[{"clause_id":f"C{j}","text":x.text,"char_span":[x.start,x.end],"token_span":clause_tokens[j]} for j,x in enumerate(clauses)]
        generations.append({"sample_id":sample["id"],"query":sample["query"],"language":language_of(sample["query"]),"user_prompt":user,"rendered_prompt":info.pop("prompt"),"multi_document_context":context,"documents":docs,"source_sentences":sentences,"summary":summary,"clauses":clause_rows,"generation":info})
        print(f"TRACK_B_GENERATED {i}/10 Q{sample['id']} clauses={len(clauses)} sources={len(sentences)} tokens={info['generated_tokens']} sec={info['elapsed_seconds']:.3f}",flush=True)
    generation_peak=int(torch.cuda.max_memory_allocated()); unload(model)

    tokenizer,model=load_embedding_model(); torch.cuda.reset_peak_memory_stats(); predictions=[]
    for gen in generations:
        clauses=[x["text"] for x in gen["clauses"]]; sentences=[x["text"] for x in gen["source_sentences"]]
        cvec,_=encode_texts(tokenizer,model,clauses); svec,_=encode_texts(tokenizer,model,sentences)
        ids=[x["sentence_id"] for x in gen["source_sentences"]]; doc_ids=[x["document_id"] for x in gen["source_sentences"]]
        rows=[]
        bm_index=GroupBM25(dict(zip(ids,sentences)))
        for ci,clause in enumerate(clauses):
            raw={}; bm=bm_index.score(clause); raw["bm25"]=np.asarray([bm[x] for x in ids]); raw["qwen"]=svec@cvec[ci]
            heads=score_heads(np.repeat(cvec[ci][None,:],len(ids),axis=0),svec)
            for family in ("rsym","dfull"):
                for seed in (0,1,2): raw[f"{family}_seed_{seed}"]=heads[family][seed]
            for seed in (0,1,2): raw[f"fusion_seed_{seed}"]=.65*zscore(raw[f"dfull_seed_{seed}"])+.35*zscore(raw["bm25"])
            methods={m:prediction_record(ids,doc_ids,sentences,v) for m,v in raw.items()}
            doc_diag={}
            for m,v in raw.items():
                zv=zscore(v); doc_diag[m]=[]
                for did in dict.fromkeys(doc_ids):
                    ii=[j for j,x in enumerate(doc_ids) if x==did]; best=max(ii,key=lambda j:(float(v[j]),ids[j])); doc_diag[m].append({"document_id":did,"sentence_id":ids[best],"document_score":float(v[best]),"document_z_score":float(zv[best])})
            rows.append({"clause_index":ci,"clause_id":f"C{ci}","clause":clause,"methods":methods,"document_max_diagnostics":doc_diag})
        predictions.append({"sample_id":gen["sample_id"],"clauses":rows})
        print(f"TRACK_B_SCORED Q{gen['sample_id']} clauses={len(rows)} sources={len(sentences)}",flush=True)
    embedding_peak=int(torch.cuda.max_memory_allocated()); unload(model)

    variants=list(predictions[0]["clauses"][0]["methods"]); total=sum(len(x["clauses"]) for x in predictions)
    agreement={a:{b:float(np.mean([row["methods"][a]["top1"]["sentence_id"]==row["methods"][b]["top1"]["sentence_id"] for p in predictions for row in p["clauses"]])) for b in variants} for a in variants}
    stats={}
    for m in variants:
        tops=[row["methods"][m]["top1"] for p in predictions for row in p["clauses"]]
        stats[m]={"clause_count":len(tops),"unique_top1_sentences":len({x["sentence_id"] for x in tops}),"unique_top1_documents":len({(p["sample_id"],row["methods"][m]["top1"]["document_id"]) for p in predictions for row in p["clauses"]})}
    complement={}
    for seed in (0,1,2):
        pairs=[(row["methods"]["bm25"],row["methods"][f"dfull_seed_{seed}"]) for p in predictions for row in p["clauses"]]
        complement[str(seed)]={"clause_count":len(pairs),"top1_sentence_agreement":float(np.mean([a["top1"]["sentence_id"]==b["top1"]["sentence_id"] for a,b in pairs])),"top1_document_agreement":float(np.mean([a["top1"]["document_id"]==b["top1"]["document_id"] for a,b in pairs])),"top3_sentence_any_overlap":float(np.mean([bool({x["sentence_id"] for x in a["top3"]}&{x["sentence_id"] for x in b["top3"]}) for a,b in pairs]))}
    write_jsonl(out_tmp/"generations.jsonl",generations); write_jsonl(out_tmp/"clause_source_predictions.jsonl",predictions)
    dump(out_tmp/"prediction_statistics.json",stats); dump(out_tmp/"top1_agreement_matrix.json",agreement); dump(out_tmp/"bm25_dfull_complementarity.json",complement)
    judge_dir=out_tmp/"judge_inputs"; judge_dir.mkdir()
    for method in variants: dump(judge_dir/f"{method}.json",judge_records(generations,predictions,method))
    citation={"status":"MEMORYFLOW_SUMMARY_TRACK_B_NEEDS_JUDGE","reason":"OPENAI_API_KEY was not configured in the execution environment","judge_model":"gpt-4o-2024-05-13","protocol":"unmodified evaluate_citations.py from supplementary package","method_files":[x.name for x in sorted(judge_dir.glob("*.json"))],"aggregation_note":"Evaluate BM25 and Qwen once; evaluate each R-SYM/D-Full/fusion seed separately and report the arithmetic mean of the three seed metrics. No logits were averaged."}
    dump(out_tmp/"citation_evaluation_status.json",citation)
    code_dir=out_tmp/"supplementary_code"; code_dir.mkdir()
    with zipfile.ZipFile(SUPPLEMENT) as z:
        for name in ("README.md","citation_common.py","evaluate_citations.py","requirements.txt"):
            member=f"AAAI27_supplementary_material/{name}"; (code_dir/name).write_bytes(z.read(member))
    sys.path.insert(0,str(code_dir)); import citation_common  # noqa: F401
    compile(citation_common.__loader__.get_source("citation_common"),str(code_dir/"citation_common.py"),"exec")
    runtime={"elapsed_seconds":time.time()-started,"generation_peak_memory_allocated_bytes":generation_peak,"embedding_peak_memory_allocated_bytes":embedding_peak,"summary_count":len(generations),"clause_count":total,"source_sentence_count":sum(len(x["source_sentences"]) for x in generations),"supplementary_code_import_ok":True,"attention_probe_run":False}
    dump(out_tmp/"runtime.json",runtime); (out_tmp/"MEMORYFLOW_SUMMARY_TRACK_B_NEEDS_JUDGE").write_text("MEMORYFLOW_SUMMARY_TRACK_B_NEEDS_JUDGE\n",encoding="utf-8")
    os.replace(out_tmp,out); print("MEMORYFLOW_SUMMARY_TRACK_B_NEEDS_JUDGE",flush=True); return runtime


def finalize(root: Path, metadata: dict) -> None:
    dump(root/"run_summary.json",metadata)
    files=[]
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in ("checksums.sha256","MEMORYFLOW_SUMMARY_TRANSFER_V1_COMPLETE"):
            files.append(f"{sha256(path)}  {path.relative_to(root)}")
    (root/"checksums.sha256").write_text("\n".join(files)+"\n",encoding="utf-8")
    (root/"MEMORYFLOW_SUMMARY_TRANSFER_V1_COMPLETE").write_text("MEMORYFLOW_SUMMARY_TRANSFER_V1_COMPLETE\n",encoding="utf-8")


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=FINAL); args=parser.parse_args()
    if args.output.exists(): raise RuntimeError(f"create-only result exists: {args.output}")
    tmp=args.output.with_name("."+args.output.name+".tmp")
    if tmp.exists(): raise RuntimeError(f"create-only temporary result exists: {tmp}")
    data,audit=verify_inputs(); model=verify_model(); checkpoints=checkpoint_manifest(); before=gpu_snapshot(); chosen=choose_gpu(before)
    args.output.parent.mkdir(parents=True,exist_ok=True); tmp.mkdir()
    os.environ["CUDA_VISIBLE_DEVICES"]=str(chosen["physical_gpu"]); os.environ["HF_HUB_OFFLINE"]="1"; os.environ["TRANSFORMERS_OFFLINE"]="1"
    started=time.time()
    base={"inputs":{"all_samples":{"path":str(INPUT),"sha256":sha256(INPUT)},"supplement":{"path":str(SUPPLEMENT),"sha256":sha256(SUPPLEMENT)},"audit":audit},"model":model,"checkpoints":checkpoints,"generation_contract":{"greedy":True,"temperature":0,"enable_thinking":False,"track_a_max_new_tokens":192,"track_b_max_new_tokens":600},"gpu":{"snapshot_before":before,"selected":chosen,"logical_gpu":0,"selection_rule":"free >= 48 GiB and utilization <= 20%; maximum free, then lower utilization/index"},"prohibitions":{"reserve_accessed":False,"blind_accessed":False,"historical_results_modified":False,"training":False,"tuning":False,"bootstrap":False,"attention_probe_run":False,"summary_to_reporter_run":False},"judge_credentials_present":bool(os.environ.get("OPENAI_API_KEY"))}
    dump(tmp/"input_manifest.json",base)
    ta=track_a(data,tmp); tb=track_b(data,tmp)
    base["runtime"]={"total_elapsed_seconds":time.time()-started,"track_a":ta,"track_b":tb,"gpu_snapshot_after":gpu_snapshot()}; base["status"]="MEMORYFLOW_SUMMARY_TRANSFER_V1_COMPLETE"
    finalize(tmp,base); os.replace(tmp,args.output)
    print("MEMORYFLOW_SUMMARY_TRANSFER_V1_COMPLETE",flush=True); return 0


if __name__ == "__main__": raise SystemExit(main())
