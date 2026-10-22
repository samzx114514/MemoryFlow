"""Frozen LC-Sent-15 Dev evaluation: CLM and selected-head target replay."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'baseline_adapters_v1'))
from adapters import rank_scores, validate_record, yifeng_input

EXPECTED = {
    'single_positive_15.jsonl': '8a87bf9254ec25a820e1da257c66fa656297207c9265b49d1c2afba6262d2e45',
    'source_catalog.jsonl': '6e90d8977e2e47002eea77ced522327d95b3e54f7c32f2ad5ffbf7c8c83038e1',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def prepare_records(rows, catalog):
    records, gold, seen = [], [], set()
    for row in rows:
        ids = [c['source_id'] for c in row['candidates']]
        positives = [c['source_id'] for c in row['candidates'] if c['label'] == 1]
        if (row['split'] != 'dev' or len(ids) != 15 or len(set(ids)) != 15
                or len(positives) != 1 or row['example_id'] in seen
                or any(c['label'] not in (0, 1) for c in row['candidates'])):
            raise ValueError('invalid frozen Dev case')
        record = dict(id=row['example_id'], query=row['query'], target=row['target']['text'],
                      language=row['language'], sources=[dict(id=s, text=catalog[s]) for s in ids])
        validate_record(record)
        records.append(record)
        gold.append(dict(id=record['id'], language=record['language'], candidate_ids=ids,
                         gold_id=positives[0]))
        seen.add(record['id'])
    return records, gold


def prepare(args):
    dev = args.root / 'artifacts/legacy/workspace/data/lc_sent15_v1/dev'
    hashes = {name: sha(dev / name) for name in EXPECTED}
    if hashes != EXPECTED:
        raise ValueError('Dev identity mismatch')
    rows = [json.loads(line) for line in (dev / 'single_positive_15.jsonl').read_text().splitlines()]
    sources = [json.loads(line) for line in (dev / 'source_catalog.jsonl').read_text().splitlines()]
    records, gold = prepare_records(rows, {s['id']: s['text'] for s in sources})
    if len(records) != 228 or len(sources) != 3411:
        raise ValueError('unexpected Dev size')
    args.output.mkdir(parents=True, exist_ok=False)
    write(args.output / 'records.json', records)
    write(args.output / 'gold.json', gold)
    write(args.output / 'manifest.json', dict(source_sha256=hashes, targets=228, pairs=3420,
          files={name: sha(args.output / name) for name in ('records.json', 'gold.json')}))
    print('PREPARED 228 targets / 3420 candidates', flush=True)


def evaluate(gold, predictions):
    by_id = {p['id']: p for p in predictions}
    if len(by_id) != len(predictions) or set(by_id) != {g['id'] for g in gold}:
        raise ValueError('prediction coverage mismatch')
    ranks = []
    for g in gold:
        scores = by_id[g['id']]['scores']
        if set(scores) != set(g['candidate_ids']):
            raise ValueError('candidate coverage mismatch')
        ranking = rank_scores(scores)
        ranks.append(dict(id=g['id'], language=g['language'], gold_rank=ranking.index(g['gold_id']) + 1,
                          predicted_id=ranking[0]))
    result = dict(targets=ranks)
    for group in ('overall', 'zh', 'en'):
        values = [r['gold_rank'] for r in ranks if group == 'overall' or r['language'] == group]
        if values:
            n = len(values)
            result[group] = dict(count=n, correct_at_1=sum(r == 1 for r in values),
                hit_at_1=sum(r == 1 for r in values) / n,
                mrr=sum(1 / r for r in values) / n,
                ndcg_at_5=sum(1 / math.log2(r + 1) if r <= 5 else 0 for r in values) / n)
    return result


def prediction_positions(prompt_length, target_length):
    return list(range(prompt_length - 1, prompt_length + target_length - 1))


def replay_attention(model, prompt_ids, target_ids, layer, head, start, end):
    """Upstream decode loop with prescribed next tokens, not argmax tokens."""
    import torch
    device = model.get_input_embeddings().weight.device
    prompt_ids = prompt_ids.to(device)
    history = []
    with torch.inference_mode():
        prefill = model(input_ids=prompt_ids[:, :-1], use_cache=True,
                        return_dict=True, output_attentions=False)
        past = prefill.past_key_values
        del prefill
        current = prompt_ids[:, -1:]
        for token in target_ids:
            output = model(input_ids=current, past_key_values=past, use_cache=True,
                           return_dict=True, output_attentions=True)
            past = output.past_key_values
            history.append(output.attentions[layer][0, head, -1, start:end].float().detach().cpu().numpy())
            current = torch.tensor([[token]], device=device)
            del output
    return history


def yifeng_run(args):
    import numpy as np
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from citation_common import TextSpan, render_prompt, char_spans_to_token_ranges, aggregate_attention
    model_path = args.root.parent / 'model/Qwen2.5-7B-Instruct'
    tok = AutoTokenizer.from_pretrained(model_path, local_files_only=True, use_fast=True)
    records = read(args.inputs / 'records.json')
    prepared = []
    for r in records:
        native, mapping = yifeng_input(r)
        prompt, origin, _ = render_prompt(tok, native['context'], native['query'])
        encoded = tok(prompt, add_special_tokens=False, return_offsets_mapping=True, return_tensors='pt')
        offsets = encoded.pop('offset_mapping')[0].tolist()
        spans = [TextSpan(s['text'], m['start'], m['end']) for s, m in zip(r['sources'], mapping)]
        ranges = char_spans_to_token_ranges(offsets, spans, base_offset=origin)
        target_ids = tok(r['target'], add_special_tokens=False)['input_ids']
        length = encoded['input_ids'].shape[1]
        if not target_ids or length + len(target_ids) > 8192:
            raise ValueError(f'Yifeng length limit: {r["id"]}, no truncation')
        prepared.append((r, encoded['input_ids'], target_ids, ranges))
    model = AutoModelForCausalLM.from_pretrained(model_path, local_files_only=True,
                torch_dtype=torch.bfloat16, attn_implementation='eager').to('cuda').eval()
    scores = []
    with (args.output / 'predictions.jsonl').open('x', encoding='utf8') as stream:
        for r, prompt_ids, target_ids, ranges in prepared:
            start, end = min(a for a, b in ranges), max(b for a, b in ranges)
            history = replay_attention(model, prompt_ids, target_ids, 19, 15, start, end)
            row = aggregate_attention(history, [(0, len(target_ids))],
                                      [(a - start, b - start) for a, b in ranges])[0]
            if not np.isfinite(row).all() or row.sum() <= 0:
                raise ValueError('invalid attention scores')
            result = dict(id=r['id'], scores={s['id']:float(v) for s, v in zip(r['sources'], row)},
                          prompt_tokens=prompt_ids.shape[1], target_tokens=len(target_ids))
            scores.append(result)
            stream.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
            stream.flush()
            print(json.dumps(dict(event='CASE_COMPLETE', method='yifeng', count=len(scores), id=r['id'])), flush=True)
    write(args.output / 'scores.json', scores)
    return dict(head=[19, 15], mode='fixed_target_teacher_forcing', query='original_dataset_query',
                aggregation='upstream mean target-token attention then normalize and sum source-token mass',
                selection='rank all 15; no abstention; no re-probing', model_path=str(model_path),
                model_config_sha256=sha(model_path / 'config.json'),
                upstream_sha256={p.name:sha(p) for p in args.upstream.glob('*.py')})


def run(args):
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TORCH_FORCE_WEIGHTS_ONLY_LOAD='1')
    import numpy as np
    import torch
    import transformers
    from run_local_models import clm_run
    torch.set_num_threads(2)
    torch.manual_seed(0)
    np.random.seed(0)
    if torch.cuda.device_count() != 1:
        raise ValueError('Expose exactly one safely selected GPU')
    free, total = torch.cuda.mem_get_info()
    if free < 40 * 1024**3:
        raise RuntimeError('Need >=40 GiB free before model load')
    torch.cuda.set_per_process_memory_fraction(32 * 1024**3 / total)
    manifest = read(args.inputs / 'manifest.json')
    if manifest['source_sha256'] != EXPECTED:
        raise ValueError('wrong Dev manifest')
    for name, expected in manifest['files'].items():
        if sha(args.inputs / name) != expected:
            raise ValueError('prepared input changed')
    args.output.mkdir(parents=True, exist_ok=False)
    snapshot = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.free,memory.used,utilization.gpu',
                                        '--format=csv,noheader'], text=True)
    write(args.output / 'started.json', dict(method=args.action, seed=0, gpu=os.environ.get('CUDA_VISIBLE_DEVICES'),
          gpu_snapshot=snapshot, free_before_bytes=free, status='STARTED', input_manifest=manifest))
    started = time.monotonic()
    details = (clm_run(args.root, args.inputs, args.output, args.root / 'artifacts/models/Qwen3-8B', max_tokens=8192)
               if args.action == 'clm' else yifeng_run(args))
    predictions = read(args.output / 'scores.json')
    # Labels first enter the evaluator here, after all model scores have been saved.
    metrics = evaluate(read(args.inputs / 'gold.json'), predictions)
    if metrics['overall']['count'] != 228:
        raise ValueError('incomplete Dev evaluation')
    write(args.output / 'metrics.json', metrics)
    torch.cuda.synchronize()
    report = dict(status='COMPLETED_LC_SENT15_DEV', method=args.action, seed=0,
          input_manifest=manifest, gpu=os.environ.get('CUDA_VISIBLE_DEVICES'),
          torch=torch.__version__, transformers=transformers.__version__, numpy=np.__version__,
          seconds=round(time.monotonic() - started, 3), allocator_cap_gib=32,
          peak_allocated_bytes=torch.cuda.max_memory_allocated(),
          runner_sha256=sha(__file__),
          reused_code_sha256={name:sha(Path(__file__).resolve().parents[1] / 'baseline_adapters_v1' / name)
                              for name in ('run_local_models.py', 'adapters.py', 'acquire_head.py')},
          paid_api_calls=0, training=False, reserve_blind_read=False, details=details,
          metrics={k:v for k,v in metrics.items() if k != 'targets'},
          output_sha256={p.name:sha(p) for p in args.output.iterdir() if p.is_file()})
    write(args.output / 'report.json', report)
    print(json.dumps(dict(status=report['status'], method=args.action, metrics=report['metrics'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'clm', 'yifeng'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.upstream = args.root / 'artifacts/third_party/yifeng_20261016/AAAI27_supplementary_material'
    sys.path.insert(0, str(args.upstream))
    (prepare if args.action == 'prepare' else run)(args)
