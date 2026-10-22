"""Independent rank-count verification of saved results, without model imports."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def verify(root, run):
    gold = read(run / 'inputs/gold.json')
    manifest = read(run / 'inputs/manifest.json')
    for name, expected in manifest['files'].items():
        assert sha(run / 'inputs' / name) == expected
    reports = {}
    for method, folder in [('clm', 'clm_fulltext'), ('yifeng', 'yifeng')]:
        output = run / folder
        report = read(output / 'report.json')
        assert report['status'] == 'COMPLETED_LC_SENT15_DEV'
        assert report['input_manifest'] == manifest
        for name, expected in report['output_sha256'].items():
            assert sha(output / name) == expected, name
        predictions = read(output / 'scores.json')
        assert len(gold) == len(predictions) == 228
        assert len({p['id'] for p in predictions}) == 228
        ranks = []
        for g, p in zip(gold, predictions):
            assert g['id'] == p['id']
            assert list(p['scores']) == g['candidate_ids']
            assert len(p['scores']) == 15 and all(math.isfinite(v) for v in p['scores'].values())
            score = p['scores'][g['gold_id']]
            # Count candidates strictly ahead, independent of the runner's sorted-list implementation.
            rank = 1 + sum(v > score or (v == score and k < g['gold_id']) for k,v in p['scores'].items())
            ranks.append((g['id'], g['language'], rank))
        saved = read(output / 'metrics.json')
        assert [(r['id'], r['language'], r['gold_rank']) for r in saved['targets']] == ranks
        for group in ('overall', 'zh', 'en'):
            rr = [r for _, lang, r in ranks if group == 'overall' or lang == group]
            assert saved[group]['count'] == len(rr)
            values = dict(hit_at_1=sum(r == 1 for r in rr)/len(rr), mrr=sum(1/r for r in rr)/len(rr),
                          ndcg_at_5=sum(1/math.log2(r+1) for r in rr if r<=5)/len(rr))
            for key, value in values.items():
                assert abs(saved[group][key] - value) < 1e-12
                assert abs(report['metrics'][group][key] - value) < 1e-12
        prior = root / 'runs/baseline_adapters_v1/models_20261018_v1' / method / 'report.json'
        reports[method] = dict(targets=228, pairs=3420, independent_metrics='PASS',
                               report_sha256=sha(output / 'report.json'),
                               model_identity_reference=str(prior), model_identity_reference_sha256=sha(prior),
                               model_files_sha256=read(prior)['model_files_sha256'])
    # Yifeng loaded the initial runner before the CLM-only length-limit fix.
    runner = Path(__file__).with_name('evaluate.py').read_bytes()
    new = b"args.root / 'artifacts/models/Qwen3-8B', max_tokens=8192)"
    old = b"args.root / 'artifacts/models/Qwen3-8B')"
    assert runner.count(new) == 1
    provenance = dict(yifeng_loaded_runner_sha256=hashlib.sha256(runner.replace(new, old)).hexdigest(),
        note='Yifeng runner hash in report was taken at finalization after the CLM-only max_tokens argument was added. '
             'The Yifeng code path did not change. Model weight hashes reference the prior verified run; no weight download or rehash in this run.')
    result = dict(status='VERIFIED_228_EACH', methods=reports, code_provenance=provenance,
                  verification_script_sha256=sha(Path(__file__)))
    with (run / 'verification.json').open('x') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    verify(args.root, args.run)
