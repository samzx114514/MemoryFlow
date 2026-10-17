"""Offline trajectory extraction: observable text transfers, never semantic Gold."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def flatten_text(obj):
    if isinstance(obj, str):
        if obj.lstrip().startswith(('[', '{')):
            try:
                return flatten_text(json.loads(obj))
            except (ValueError, TypeError):
                pass
        return obj
    if isinstance(obj, list):
        return '\n'.join(flatten_text(v) for v in obj)
    if isinstance(obj, dict):
        if 'content' in obj:
            return flatten_text(obj['content'])
        return '\n'.join(flatten_text(v) for v in obj.values())
    return ''


def normalized(text):
    return re.sub(r'\s+', '', text)


def visible(source, target):
    text = normalized(source)
    return len(text) >= 24 and text in normalized(target)


def sid(prefix, text):
    return prefix + hashlib.sha256(text.encode()).hexdigest()[:16]


def add_visibility(flow):
    calls = [(n, normalized(n['input_text'])) for n in flow['nodes'] if n['kind'] == 'model_call']
    for source in flow['nodes']:
        if source['kind'] not in ['source_chunk', 'research_summary', 'report_output']:
            continue
        source_text = normalized(source.get('text', ''))
        for call, input_text in calls:
            if len(source_text) >= 24 and source_text in input_text:
                flow['edges'].append(dict(source=source['id'], target=call['id'], kind='text_visible_in_input',
                                          semantic_gold=False, evidence=call['origin']))


def validate(flow):
    ids = [n['id'] for n in flow['nodes']]
    assert len(ids) == len(set(ids))
    for edge in flow['edges']:
        assert edge['source'] in ids and edge['target'] in ids
        assert edge['semantic_gold'] is False


def role(text):
    start = text[:1000].lower()
    if 'professional reporter' in start:
        return 'reporter'
    if '`researcher`' in start:
        return 'researcher'
    if 'central agent' in start:
        return 'central'
    return 'unknown'


def sp1(path, name):
    meta = read(path/'run_summary.json')
    flow = dict(name=name, origin=str(path), state=meta['status'], query=meta['query'], nodes=[], edges=[], metrics=meta,
                limitations=['Sources are retrieved snippets, not necessarily complete web pages.',
                             'Text visibility is not actual semantic use or causal influence.',
                             'Missing summaries and reports are preserved as missing.'])
    sources = {}
    for f in sorted(path.glob('search_response_*.json')):
        for i, result in enumerate(read(f).get('results', [])):
            text = result.get('content', '')
            if not text:
                continue
            identity = sid('source_', result.get('url', '')+'\n'+text)
            if identity not in sources:
                sources[identity] = dict(id=identity, kind='source_chunk', text=text, url=result.get('url'), title=result.get('title'), origin=[])
            sources[identity]['origin'].append(f.name+f'#/results/{i}')
    flow['nodes'].extend(sources.values())
    callback_calls = {}
    request_order = {normalized(flatten_text(read(f)['messages'])): int(f.stem.split('_')[-1])
                     for f in sorted(path.glob('model_request_*.json'))}
    for f in sorted(path.glob('llm_input_*.json')):
        o = read(f); text = flatten_text(o['messages'])
        node = dict(id='call_'+o['run_id'], kind='model_call', agent=role(text), input_text=text, origin=f.name,
                    parent_run_id=o.get('parent_run_id'), call_index=request_order.get(normalized(text)))
        callback_calls[o['run_id']] = node
        flow['nodes'].append(node)
    outputs = []
    for f in sorted(path.glob('llm_output_*.json')):
        o = read(f); callid = f.stem.removeprefix('llm_output_')
        for groups in o.get('generations', []):
            for g in groups:
                text = g.get('text', '')
                outputs.append((callid, text, f.name))
    for f in sorted((path/'researcher_traces').glob('*.json')):
        o = read(f); identity='summary_'+o['event_id']
        flow['nodes'].append(dict(id=identity, kind='research_summary', text=o['summary'], origin=str(f.relative_to(path))))
        for callid, text, origin in outputs:
            if text == o['summary'] and callid in callback_calls:
                flow['edges'].append(dict(source='call_'+callid, target=identity, kind='model_output_exact_match', semantic_gold=False, evidence=origin))
    f = path/'final_report.json'
    if f.exists():
        text = read(f)['final_report'];identity='report_final'
        flow['nodes'].append(dict(id=identity, kind='report_output', text=text, origin=f.name))
        for callid, output, origin in outputs:
            if output == text and callid in callback_calls:
                flow['edges'].append(dict(source='call_'+callid, target=identity, kind='model_output_exact_match', semantic_gold=False, evidence=origin))
    add_visibility(flow)
    validate(flow)
    flow['counts'] = dict(Counter(n['kind'] for n in flow['nodes']))
    flow['counts']['visibility_edges'] = sum(e['kind']=='text_visible_in_input' for e in flow['edges'])
    flow['input_manifest'] = {str(f.relative_to(path)):hashlib.sha256(f.read_bytes()).hexdigest()
                              for f in path.rglob('*.json') if f.is_file()}
    return flow


def dcc(bundle):
    data=bundle['files']; result=data['result.json']; summary=data['researcher_result.json']
    flow=dict(name='CUAD dev: preferential rights', origin=bundle['source_directory'], state=result['status'],
              query=result['question_id'], nodes=[], edges=[], metrics=result['metrics'], input_manifest=bundle['manifest'],
              limitations=['CUAD span extraction is not exhaustive active compliance checking.',
                           'One selected nonempty-evidence dev example; no representativeness or accuracy claim.',
                           'The model interpretation of preemptive right as ROFR/ROFO/ROFN requires human review.'])
    sources={}
    for index,event in enumerate(data['tool_raw_results.jsonl']):
        for doc in event.get('raw_response', []):
            for chunk in doc.get('chunks', []):
                identity='source_'+chunk['id']
                if identity not in sources:
                    sources[identity]=dict(id=identity, kind='source_chunk', text=chunk['content'], chunk_id=chunk['id'],
                                           char_start=chunk.get('char_start'), char_end=chunk.get('char_end'), origin=[])
                sources[identity]['origin'].append(f'tool_raw_results.jsonl#line={index+1}')
    flow['nodes'].extend(sources.values())
    completed={}
    for i,event in enumerate(data['model_calls.jsonl']):
        if event['event_type']=='model.started':
            flow['nodes'].append(dict(id='call_'+event['call_id'], kind='model_call', agent=event['agent'],
                                     input_text=flatten_text(event['input']), origin=f'model_calls.jsonl#line={i+1}',
                                     call_index=event.get('call_index'), parent_run_id=event.get('parent_call_id')))
        elif event['event_type']=='model.completed':
            completed[event['call_id']]=(flatten_text(event.get('output')), i+1)
    flow['nodes'].append(dict(id='summary_final',kind='research_summary',text=summary['analysis'],origin='researcher_result.json',
                             selected_chunk_ids=summary['selected_chunk_ids'],evidence_sufficiency=summary['evidence_sufficiency'],
                             unresolved_questions=summary['unresolved_questions']))
    for call in [n for n in flow['nodes'] if n['kind']=='model_call']:
        output,line=completed.get(call['id'].removeprefix('call_'),('',0))
        if call['agent'].startswith('researcher') and visible(summary['analysis'],output):
            flow['edges'].append(dict(source=call['id'],target='summary_final',kind='model_output_contains_analysis',semantic_gold=False,evidence=f'model_calls.jsonl#line={line}'))
    for index,span in enumerate(result['spans']):
        identity=f'report_span_{index}'
        flow['nodes'].append(dict(id=identity,kind='report_output',text=span['text'],origin=f'result.json#/spans/{index}',
                                 chunk_id=span['chunk_id'],answer_start=span['answer_start'],answer_end=span['answer_end']))
        source=sources.get('source_'+span['chunk_id'])
        assert source is not None
        offset=span['answer_start']-source['char_start']
        assert source['text'][offset:offset+len(span['text'])]==span['text']
        flow['edges'].append(dict(source=source['id'],target=identity,kind='explicit_chunk_reference_and_verified_offset',semantic_gold=False,evidence=f'result.json#/spans/{index}'))
        for call in [n for n in flow['nodes'] if n['kind']=='model_call' and n['agent']=='reporter']:
            output,line=completed.get(call['id'].removeprefix('call_'),('',0))
            if visible(span['text'],output):
                flow['edges'].append(dict(source=call['id'],target=identity,kind='model_output_contains_span',semantic_gold=False,evidence=f'model_calls.jsonl#line={line}'))
    add_visibility(flow);validate(flow)
    flow['counts']=dict(Counter(n['kind'] for n in flow['nodes']))
    flow['counts']['visibility_edges']=sum(e['kind']=='text_visible_in_input' for e in flow['edges'])
    return flow


def write_case(flow, target):
    target.mkdir(parents=True,exist_ok=False)
    (target/'flow.json').write_text(json.dumps(flow,ensure_ascii=False,indent=2),encoding='utf8')
    lines=[f"# {flow['name']}",'',f"状态：{flow['state']}。来源：`{flow['origin']}`。",'',
           '这里的边只表示文本确实进入某次输入、输出对应关系或明确的来源引用；不是语义 Gold，也不是因果证明。','',
           '## 已提取内容','',json.dumps(flow['counts'],ensure_ascii=False),'','## 调用记录','',
           '| 调用 ID | 角色 | 输入字符数 | 原始证据 |','|---|---|---:|---|']
    for n in sorted([n for n in flow['nodes'] if n['kind']=='model_call'],key=lambda n:n.get('call_index') or 99999):
        lines.append(f"| {n.get('call_index')} / {n['id']} | {n['agent']} | {len(n['input_text'])} | {n['origin']} |")
    for kind,label in [('research_summary','Researcher Summary'),('report_output','Reporter 输出')]:
        items=[n for n in flow['nodes'] if n['kind']==kind]
        lines += ['',f'## {label}','']
        if not items:lines += ['未产出；不补造。']
        for n in items:lines += [f"节点：`{n['id']}`；证据：`{n['origin']}`。",'',n['text'],'']
    lines += ['','## 可见性核查','']
    for e in flow['edges']:
        source=next(n for n in flow['nodes'] if n['id']==e['source'])
        if source['kind'] in ['research_summary','report_output'] or e['kind']!='text_visible_in_input':
            lines.append(f"- `{e['source']}` → `{e['target']}`：{e['kind']}；证据 `{e['evidence']}`。")
    lines += ['','## 局限','']+['- '+s for s in flow['limitations']]
    (target/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf8')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sp1-root',type=Path,required=True)
    parser.add_argument('--dcc',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    flows=[('01_sp1_complete',sp1(args.sp1_root/'20261016_smoke_complete','SP1 完整短任务')),
           ('02_insurance_partial',sp1(args.sp1_root/'20261016_insurance_budget_stop','保险研究：未完成轨迹')),
           ('03_dcc_complete',dcc(read(args.dcc)))]
    args.output.mkdir(parents=True,exist_ok=False)
    for name,flow in flows:write_case(flow,args.output/name)
    summary={name:{'state':flow['state'],'counts':flow['counts']} for name,flow in flows}
    (args.output/'extraction_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
