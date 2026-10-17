"""Score prepared records via the official head and a 243-local Qwen3 encoder.

Does not download models, start services, silently truncate, or compute accuracy.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

from adapters import clm_request, clm_score
from acquire_head import SHA256


def main(args):
    endpoint = urlparse(args.encoder_url)
    if endpoint.hostname not in ('127.0.0.1', 'localhost', '::1') or endpoint.username or endpoint.password:
        raise ValueError('Only a local encoder endpoint is allowed; no paid API routing')
    if args.output.exists():
        raise FileExistsError(args.output)
    revision = subprocess.check_output(['git', '-C', str(args.clm_root), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != 'd5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6':
        raise ValueError('CLM source revision differs from frozen adapter contract')
    if hashlib.sha256(args.head.read_bytes()).hexdigest() != SHA256:
        raise ValueError('reference head checksum mismatch')
    cfg = json.loads((args.tokenizer/'config.json').read_text())
    if cfg.get('model_type') != 'qwen3' or cfg.get('hidden_size') != 4096:
        raise ValueError('Reference head requires Qwen3-8B, not Qwen2.5/F_mean')
    os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'] = '1'
    sys.path.insert(0, str(args.clm_root/'src'))
    from clm import Engine, Embedder
    from clm.schema import build_pairs
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True)
    records = json.loads(args.records.read_text(encoding='utf8'))
    lengths = {}
    for record in records:
        state, questions = clm_request(record)
        text, keys, sources = build_pairs(state, questions)['source']
        counts = [len(tok(s, add_special_tokens=True)['input_ids']) for s in [text]+sources]
        if max(counts) > args.max_tokens:
            raise ValueError(f"{record['id']} has {max(counts)} tokens; cap {args.max_tokens}; no implicit truncation")
        lengths[record['id']] = dict(state=counts[0], sources=dict(zip(keys, counts[1:])))
    # max_tokens=None: upstream Embedder must not send truncate_prompt_tokens.
    embedder = Embedder(url=args.encoder_url, model='qwen3-8b', max_tokens=None, batch=1)
    engine = Engine(embedder=embedder, checkpoint=str(args.head), device='cpu', action_cache=0)
    started = time.monotonic()
    results = [clm_score(record, engine) for record in records]
    report = dict(status='SCORED_UNLABELLED_NOT_ACCURACY', results=results, token_counts=lengths,
                  input_sha256=hashlib.sha256(args.records.read_bytes()).hexdigest(),
                  clm_commit=revision, head_sha256=SHA256, encoder='Qwen3-8B:last-token',
                  seed=None, seconds=round(time.monotonic()-started, 3),
                  note='Encoder service revision and pooling configuration must accompany this output.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--records', type=Path, required=True)
    p.add_argument('--clm-root', type=Path, required=True)
    p.add_argument('--head', type=Path, required=True)
    p.add_argument('--tokenizer', type=Path, required=True)
    p.add_argument('--encoder-url', required=True)
    p.add_argument('--max-tokens', type=int, default=2048)
    p.add_argument('--output', type=Path, required=True)
    main(p.parse_args())
