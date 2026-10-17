"""Two unlabelled smoke cases; local weights only, no service or package install."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import numpy as np


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    with path.open('x', encoding='utf8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def last_token_vector(hidden):
    """Single unpadded input; same L2 formula as author's Embedder."""
    v = hidden[0, -1].float().detach().cpu().numpy()
    norm = np.linalg.norm(v)
    if not np.isfinite(v).all() or not np.isfinite(norm) or norm == 0:
        raise ValueError('invalid encoder vector')
    return v / (norm + 1e-12)


def overlap_ids(start, end, mapping):
    return [s['id'] for s in mapping if max(start, s['start']) < min(end, s['end'])]


class LocalEmbedder:
    def __init__(self, tokenizer, model):
        self.tokenizer, self.model = tokenizer, model
        self.cache = {}

    def embed(self, texts):
        import torch
        vectors, spent = [], 0
        for text in texts:
            if text not in self.cache:
                tokens = self.tokenizer(text, add_special_tokens=True, return_tensors='pt')
                count = tokens['input_ids'].shape[1]
                if not 0 < count <= 2048:
                    raise ValueError(f'CLM token count {count}; no truncation allowed')
                with torch.inference_mode():
                    out = self.model(**tokens.to('cuda'), use_cache=False, return_dict=True)
                    self.cache[text] = last_token_vector(out.last_hidden_state)
                spent += count
            vectors.append(self.cache[text])
        return np.stack(vectors), spent


def clm_run(root, inputs, output, model_path):
    from transformers import AutoModel, AutoTokenizer
    import torch
    from adapters import clm_request, clm_score
    from acquire_head import SHA256
    upstream = root/'artifacts/third_party/clm_d5f9ef0'
    revision = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != 'd5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6':
        raise ValueError('unexpected CLM revision')
    sys.path.insert(0, str(upstream/'src'))
    from clm import Engine
    from clm.schema import build_pairs
    head = root/'artifacts/models/clm_reference_e939398/CLM_v0.1-8B.pt'
    if sha(head) != SHA256:
        raise ValueError('reference head identity mismatch')
    acquisition = json.loads((model_path/'acquisition_report.json').read_text())
    if acquisition['status'] != 'DOWNLOADED_VERIFIED_NOT_LOADED':
        raise ValueError('missing verified acquisition')
    cfg = json.loads((model_path/'config.json').read_text())
    if cfg['model_type'] != 'qwen3' or cfg['hidden_size'] != 4096:
        raise ValueError('wrong CLM backbone')
    tok = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    records = json.loads((inputs/'records.json').read_text())
    lengths = {}
    for r in records:
        state, questions = clm_request(r)
        text, keys, sources = build_pairs(state, questions)['source']
        counts = [len(tok(s, add_special_tokens=True)['input_ids']) for s in [text] + sources]
        if max(counts) > 2048:
            raise ValueError('CLM input exceeds frozen limit')
        lengths[r['id']] = counts
    model = AutoModel.from_pretrained(model_path, local_files_only=True,
                                     torch_dtype=torch.bfloat16, attn_implementation='sdpa').to('cuda').eval()
    engine = Engine(embedder=LocalEmbedder(tok, model), checkpoint=str(head), device='cpu', action_cache=0)
    results = []
    for r in records:
        result = clm_score(r, engine)
        results.append(result)
        print(json.dumps(dict(event='CASE_COMPLETE', method='clm', id=r['id'])), flush=True)
    write(output/'scores.json', results)
    return dict(cases=len(results), source_counts={r['id']:len(r['sources']) for r in records},
                token_counts=lengths, clm_commit=revision, head_sha256=SHA256,
                backbone_revision=acquisition['revision'],
                encoder='Transformers AutoModel / bf16 / SDPA / raw text / last-token / L2',
                backend_note='Official Engine and head; numerical equivalence to vLLM not measured',
                score_semantics='candidate_set_softmax_not_edge_probability')


def yifeng_run(root, inputs, output, model_path):
    from transformers import AutoTokenizer
    upstream = root/'artifacts/third_party/yifeng_20261016/AAAI27_supplementary_material'
    sys.path.insert(0, str(upstream))
    import generate_attention as generate
    import add_citations as cite
    from citation_common import render_prompt, split_source_sentences
    records = json.loads((inputs/'yifeng_native_inputs.json').read_text())
    mapping = json.loads((inputs/'source_map.json').read_text())
    tok = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    token_counts, sentence_map = {}, {}
    for r in records:
        context = r['context']
        document = context.strip()
        origin = len(context) - len(context.lstrip())
        prompt, _, _ = render_prompt(tok, document, r['query'].strip())
        count = len(tok(prompt, add_special_tokens=False)['input_ids'])
        if count > 8192:
            raise ValueError('Yifeng input exceeds 8192; no truncation allowed')
        token_counts[r['idx']] = count
        sentence_map[r['idx']] = {
            f'S{i}': dict(start=s.start+origin, end=s.end+origin,
                         source_ids=overlap_ids(s.start+origin, s.end+origin, mapping[r['idx']]))
            for i, s in enumerate(split_source_sentences(document, r['language']))}
    # Observe stop conditions without changing the author's decoder or selection rule.
    decode = generate.greedy_decode_selected_head
    stops = []
    def tracked_decode(*args, **kwargs):
        tokens, attention = decode(*args, **kwargs)
        ended = bool(tokens and tokens[-1] in generate.stop_token_ids(args[0], args[1]))
        stops.append(dict(generated_tokens=len(tokens), ended_with_eos=ended,
                          reached_output_cap=not ended and len(tokens) == 600))
        return tokens, attention
    generate.greedy_decode_selected_head = tracked_decode
    generate.run(SimpleNamespace(data=inputs/'yifeng_native_inputs.json', model=str(model_path),
                                layer=19, head=15, head_ranking=None, output=output/'generated.json',
                                matrix_dir=output/'matrices', max_new_tokens=600))
    cite.run(SimpleNamespace(input=output/'generated.json', matrix_dir=output/'matrices',
                             output=output/'citations.json', threshold=-0.7, relative_cutoff=0.5))
    write(output/'source_sentence_map.json', sentence_map)
    results = json.loads((output/'citations.json').read_text())
    stats = {}
    for r, stop in zip(results, stops):
        matrix = np.load(output/'matrices'/r['attention_matrix'], allow_pickle=False)
        if not r['response'] or matrix.shape != (len(r['output']), len(r['input'])) or not np.isfinite(matrix).all():
            raise ValueError('invalid generation or matrix')
        if r['citation_head'] != dict(layer=19, head=15):
            raise ValueError('head changed')
        for clause in r['output'].values():
            clause['source_chunk_ids'] = sorted({source_id for s in clause['citation_list']
                for source_id in sentence_map[r['idx']][s]['source_ids']})
        stats[r['idx']] = dict(input_tokens=token_counts[r['idx']], matrix_shape=list(matrix.shape),
                              clauses_with_citations=sum(bool(c['citation_list']) for c in r['output'].values()),
                              **stop)
    write(output/'citations_with_source_ids.json', results)
    return dict(cases=len(results), case_stats=stats, citation_head=dict(layer=19, head=15),
                head_selection='paper_table_explicit_user_choice_2026-10-18_not_raw_ranking',
                raw_head_scores_sha256='89dbd7cdc665e87ddfc71c69c6f613fcc78d5a9be15a2f3b3bfe00fcc4c11e84',
                raw_ranking_note='sum rank 1=(14,0), chosen (19,15) rank 5; no re-probing',
                threshold=-0.7, relative_cutoff=0.5, max_new_tokens=600,
                upstream_sha256={p.name:sha(p) for p in sorted(upstream.glob('*.py'))},
                source_mapping='all positive character-span overlaps; cross-chunk sentences retain all IDs')


def main(args):
    import torch
    import transformers
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'] = '1'
    torch.set_num_threads(2)
    torch.manual_seed(0)
    np.random.seed(0)
    if torch.cuda.device_count() != 1:
        raise ValueError('Expose exactly one authorized GPU via CUDA_VISIBLE_DEVICES')
    free, total = torch.cuda.mem_get_info()
    if free < 40 * 1024**3:
        raise RuntimeError('Less than 40 GiB free; do not contend for remaining memory')
    torch.cuda.set_per_process_memory_fraction(32 * 1024**3 / total)
    args.output.mkdir(parents=True, exist_ok=False)
    inputs = args.root/'runs/baseline_adapters_v1/inputs_20261017'
    model = (args.root/'artifacts/models/Qwen3-8B' if args.method == 'clm'
             else args.root.parent/'model/Qwen2.5-7B-Instruct')
    started = time.monotonic()
    write(args.output/'started.json', dict(method=args.method, seed=0, status='STARTED',
                                         gpu=os.environ.get('CUDA_VISIBLE_DEVICES')))
    details = (clm_run if args.method == 'clm' else yifeng_run)(args.root, inputs, args.output, model)
    torch.cuda.synchronize()
    report = dict(status='COMPLETED_UNLABELLED_SMOKE_NOT_ACCURACY', method=args.method,
                  seed=0, torch=torch.__version__, transformers=transformers.__version__,
                  numpy=np.__version__, gpu=os.environ.get('CUDA_VISIBLE_DEVICES'),
                  device=torch.cuda.get_device_name(0), allocator_cap_gib=32,
                  peak_allocated_bytes=torch.cuda.max_memory_allocated(),
                  peak_reserved_bytes=torch.cuda.max_memory_reserved(),
                  inference_and_load_seconds=round(time.monotonic()-started, 3),
                  input_sha256={p.name:sha(p) for p in sorted(inputs.glob('*.json'))},
                  runner_sha256=sha(__file__), adapters_sha256=sha(Path(__file__).with_name('adapters.py')),
                  model_files_sha256={p.name:sha(p) for p in sorted(model.iterdir())
                                      if p.is_file() and p.suffix in ('.json', '.safetensors')},
                  paid_api_calls=0, **details)
    report['output_sha256'] = {str(p.relative_to(args.output)):sha(p)
                              for p in sorted(args.output.rglob('*')) if p.is_file()}
    write(args.output/'report.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('method', choices=['clm', 'yifeng'])
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args())
