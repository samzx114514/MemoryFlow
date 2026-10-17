"""Versioned input adapters; no Gold construction or implicit model calls."""
import math


CLM_INSTRUCTION = 'Which source passage best supports the statement above?'


def validate_record(record):
    for key in ('id', 'query', 'target'):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f'{key} must be nonempty text')
    if record.get('language') not in ('en', 'zh'):
        raise ValueError('language must be en or zh')
    sources = record.get('sources')
    if not isinstance(sources, list) or not sources:
        raise ValueError('sources must be a nonempty list')
    ids = []
    for source in sources:
        for key in ('id', 'text'):
            if not isinstance(source.get(key), str) or not source[key].strip():
                raise ValueError(f'source {key} must be nonempty text')
        ids.append(source['id'])
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate source id')


def clm_request(record):
    validate_record(record)
    return record['target'], {'source': dict(
        type='choice', instructions=CLM_INSTRUCTION,
        criteria={s['id']: s['text'] for s in record['sources']})}


def rank_scores(scores):
    if not scores or any(not math.isfinite(float(v)) for v in scores.values()):
        raise ValueError('empty or nonfinite scores')
    return sorted(scores, key=lambda key: (-float(scores[key]), key))


def clm_score(record, engine):
    state, questions = clm_request(record)
    result = engine.answer(state, questions, model='clm-latest', temperature=1.0)
    scores = result['answers']['source']['probabilities']
    if set(scores) != set(questions['source']['criteria']):
        raise ValueError('returned candidate IDs differ from input')
    return dict(id=record['id'], method='clm_source_ranking_adaptation_v1',
                scores=scores, ranking=rank_scores(scores), usage=result['usage'],
                score_semantics='candidate_set_softmax_not_edge_probability',
                evaluation='UNSCORED_NO_SEMANTIC_GOLD')


def yifeng_input(record):
    validate_record(record)
    parts, mapping, cursor = [], [], 0
    for source in record['sources']:
        if parts:
            parts.append('\n\n')
            cursor += 2
        start = cursor
        parts.append(source['text'])
        cursor += len(source['text'])
        mapping.append(dict(id=source['id'], start=start, end=cursor))
    native = dict(idx=record['id'], context=''.join(parts), query=record['query'],
                  language=record['language'], dataset='MemoryFlow_trace_adapter_v1')
    return native, mapping
