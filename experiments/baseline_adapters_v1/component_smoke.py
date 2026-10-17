"""Run upstream numerical components on 243 CPU, not a benchmark evaluation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

from adapters import clm_score, clm_request, yifeng_input
from acquire_head import SHA256


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    started = time.monotonic()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'] = '1'
    sys.path.insert(0, str(args.clm_root/'src'))
    sys.path.insert(0, str(args.yifeng_root))
    import numpy as np
    import torch
    import transformers
    from clm import Engine
    from clm.schema import build_pairs
    from citation_common import aggregate_attention, select_citations, split_source_sentences
    from generate_attention import greedy_decode_selected_head
    from probe_citation_head import score_instance

    torch.set_num_threads(2)
    torch.manual_seed(20261017)
    assert sha(args.head) == SHA256
    upstream = subprocess.check_output(['git', '-C', str(args.clm_root), 'rev-parse', 'HEAD'], text=True).strip()
    assert upstream == 'd5f9ef0fd9bde185df0ceaad4f4ecc6cfe8c34f6'
    checks = []
    record = dict(id='component', query='Which animal can fly?', target='Birds can fly.',
                  language='en', sources=[dict(id='s2', text='Birds can fly.'),
                                           dict(id='s1', text='Fish can swim.')])
    state, questions = clm_request(record)
    state_text, keys, texts = build_pairs(state, questions)['source']
    assert keys == ['s2', 's1'] and texts == ['Birds can fly.', 'Fish can swim.']
    checks.append('CLM upstream schema preserves candidate IDs and text')

    class FixtureEmbedder:
        """Deterministic simulated vectors: not a substitute language encoder."""
        def __init__(self):
            rng = np.random.default_rng(20261017)
            self.vectors = {}
            for text in [state_text] + texts:
                v = rng.normal(size=4096).astype(np.float32)
                self.vectors[text] = v/np.linalg.norm(v)

        def embed(self, texts):
            return np.stack([self.vectors[t] for t in texts]), 0

    embedder = FixtureEmbedder()
    engine = Engine(embedder=embedder, checkpoint=str(args.head), device='cpu', action_cache=0)
    result = clm_score(record, engine)
    head = engine.heads['clm-latest']
    zq = head.project_states(embedder.embed([state_text])[0])
    za = head.project_actions(embedder.embed(texts)[0])
    expected = torch.softmax(head.scale * (za @ zq[0]), dim=0).tolist()
    actual = [result['scores'][key] for key in keys]
    assert np.allclose(actual, expected, rtol=1e-6, atol=1e-7)
    checks.append('Released CLM head: Engine equals direct projected scaled-cosine softmax')
    swapped = dict(record, sources=list(reversed(record['sources'])))
    swapped_scores = clm_score(swapped, engine)['scores']
    permutation_error = max(abs(swapped_scores[k]-result['scores'][k]) for k in keys)
    assert np.allclose([swapped_scores[k] for k in keys], actual, rtol=1e-6, atol=1e-7)
    checks.append('CLM candidate permutation preserves score-to-ID mapping')
    duplicate = dict(record, sources=[dict(id='a', text=texts[0]), dict(id='b', text=texts[0])])
    duplicate_scores = clm_score(duplicate, engine)['scores']
    duplicate_error = max(abs(v-.5) for v in duplicate_scores.values())
    assert set(duplicate_scores) == {'a', 'b'}
    assert np.allclose(list(duplicate_scores.values()), [.5, .5], rtol=1e-6, atol=1e-7)
    checks.append('CLM duplicate text keeps separate identities; scores equal within float32 tolerance')

    matrix = aggregate_attention([np.array([4., 4., 1., 1.])], [(0, 1)], [(0, 2), (2, 4)])
    assert np.allclose(matrix, [[0.8, 0.2]])
    checks.append('Yifeng original normalize-then-sum aggregation')
    assert select_citations(matrix[0])[0] == [0]
    assert select_citations(np.ones(15)/15)[0] == []
    assert select_citations(np.zeros(15))[0] == []
    assert select_citations(np.array([.5, .25, .25]))[0] == [0]
    checks.append('Yifeng default threshold, strict relative cutoff and abstention')
    probe = score_instance([np.array([[0, 2]]), np.array([[0, 2]])],
                           [(0, 1), (1, 2)], np.array([.9, .1]), np.array([0, 0]),
                           [(0, 2), (2, 4)], .5, .1)
    assert np.allclose(probe, [[0., -1.]])
    checks.append('Yifeng probe valid-grounding minus invalid-concentration equation')

    native, mapping = yifeng_input(record)
    sentences = split_source_sentences(native['context'], 'en')
    assert [s.text for s in sentences] == texts
    assert all(native['context'][m['start']:m['end']] == t for m, t in zip(mapping, texts))
    np.save(args.output/'fixture_attention.npy', matrix)
    fixture = [dict(idx='fixture', attention_matrix='fixture_attention.npy',
                    input={'S0': texts[0], 'S1': texts[1]},
                    output={'C0': {'content': record['target']}})]
    with (args.output/'fixture_results.json').open('x') as handle:
        json.dump(fixture, handle)
    subprocess.run([sys.executable, str(args.yifeng_root/'add_citations.py'),
                    '--input', str(args.output/'fixture_results.json'),
                    '--matrix-dir', str(args.output),
                    '--output', str(args.output/'fixture_citations.json')], check=True)
    cited = json.loads((args.output/'fixture_citations.json').read_text())
    assert cited[0]['output']['C0']['citation_list'] == ['S0']
    checks.append('Yifeng unmodified add_citations CLI produces expected citation ID')

    config = transformers.Qwen2Config(vocab_size=32, hidden_size=16, intermediate_size=32,
                                      num_hidden_layers=2, num_attention_heads=2,
                                      num_key_value_heads=2, eos_token_id=None)
    config._attn_implementation = 'eager'
    model = transformers.Qwen2ForCausalLM(config).eval()
    tokens, history = greedy_decode_selected_head(
        model, SimpleNamespace(eos_token_id=None), torch.tensor([[1, 2, 3, 4, 5]]),
        layer=0, head=0, document_start=1, document_end=4, max_new_tokens=3)
    assert len(tokens) == len(history) == 3
    assert all(v.shape == (3,) and np.isfinite(v).all() for v in history)
    checks.append('Yifeng unmodified greedy decoder works with current Transformers cache/attention API')
    report = dict(status='COMPONENT_ONLY_NOT_MODEL_EVALUATION', passed=len(checks), checks=checks,
                  seed=20261017, device='cpu', gpu_used=False, paid_api_calls=0,
                  seconds=round(time.monotonic()-started, 3),
                  versions=dict(torch=torch.__version__, transformers=transformers.__version__, numpy=np.__version__),
                  clm_commit=upstream, clm_head_sha256=sha(args.head), clm_head_parameters=head.n_params,
                  yifeng_code_sha256={p.name: sha(p) for p in args.yifeng_root.glob('*.py')},
                  adapter_code_sha256={p.name: sha(p) for p in Path(__file__).parent.glob('*.py')},
                  numerical_max_abs_error=float(np.max(np.abs(np.array(expected)-actual))),
                  permutation_max_abs_error=permutation_error,
                  duplicate_probability_abs_error=duplicate_error,
                  limitations=['CLM inputs are synthetic encoder vectors, not Qwen3 embeddings.',
                               'Decoder check uses a tiny random Qwen2, not trained Qwen2.5-7B.',
                               'No head selected for the real model; no benchmark scores or semantic claims.'])
    with (args.output/'component_report.json').open('x') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--clm-root', type=Path, required=True)
    p.add_argument('--yifeng-root', type=Path, required=True)
    p.add_argument('--head', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    run(p.parse_args())
