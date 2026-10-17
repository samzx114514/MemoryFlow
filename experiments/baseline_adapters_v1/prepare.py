"""Create unlabelled adapter inputs from the two complete reviewed traces."""
import argparse
import hashlib
import json
from pathlib import Path

from adapters import clm_request, yifeng_input


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def write(path, value):
    with path.open('x', encoding='utf8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)


def prepare(review, dcc_bundle, output):
    output.mkdir(parents=True, exist_ok=False)
    records, requests, native_records, source_maps = [], [], [], {}
    manifest = {}
    for folder, language in [('01_sp1_complete', 'zh'), ('03_dcc_complete', 'en')]:
        path = review / folder / 'flow.json'
        flow = read(path)
        summaries = [n for n in flow['nodes'] if n['kind'] == 'research_summary']
        if len(summaries) != 1:
            raise ValueError('expected exactly one complete summary per example')
        query = flow['query']
        if folder.startswith('03'):
            query = read(dcc_bundle)['files']['execution_report.json']['user_query']
        record = dict(id=folder, query=query, language=language,
                      target=summaries[0]['text'], target_granularity='whole_research_summary',
                      sources=[dict(id=n['id'], text=n['text']) for n in flow['nodes']
                               if n['kind'] == 'source_chunk'], gold=None,
                      candidate_policy='all_retrieved_in_case_not_visibility_or_support_gold')
        state, questions = clm_request(record)
        native, mapping = yifeng_input(record)
        records.append(record)
        requests.append(dict(id=record['id'], state=state, questions=questions,
                             model='clm-latest', temperature=1.0, status='NOT_SENT'))
        native_records.append(native)
        source_maps[record['id']] = mapping
        manifest[folder] = hashlib.sha256(path.read_bytes()).hexdigest()
    write(output/'records.json', records)
    write(output/'clm_requests.json', requests)
    write(output/'yifeng_native_inputs.json', native_records)
    write(output/'source_map.json', source_maps)
    summary = dict(status='INPUTS_READY_NOT_MODEL_EVALUATED', cases=len(records),
                   source_counts={r['id']: len(r['sources']) for r in records},
                   input_sha256=manifest,
                   dcc_bundle_sha256=hashlib.sha256(dcc_bundle.read_bytes()).hexdigest(),
                   restrictions=['No semantic Gold; no accuracy calculation.',
                                 'Whole-summary targets are interface examples, not frozen atomic claims.',
                                 'Yifeng regenerates an answer to the original query over retrieved snippets; '
                                 'it does not explain the original SP1 answer or reproduce the official benchmark.',
                                 'No truncation here. Token budgets must be checked before inference.'])
    write(output/'preparation_report.json', summary)
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--review', type=Path, required=True)
    p.add_argument('--dcc-bundle', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(prepare(a.review, a.dcc_bundle, a.output)))
