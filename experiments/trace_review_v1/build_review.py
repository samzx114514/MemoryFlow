"""Build a small human-readable packet from already extracted, local-only flows."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from extract import normalized, visible


def excerpt(node, needle, length):
    start=node['text'].index(needle)
    if length == 0:
        length=node['text'].index('\n\n',start)-start
    text=node['text'][start:start+length]
    return dict(node_id=node['id'],origin=node['origin'],start=start,end=start+len(text),text=text)


def build(root):
    examples=[]
    for folder,source_id,needle,length in [
        ('01_sp1_complete','source_fe3db3c85eeb0cde','Python 是一门易于学习',0),
        ('03_dcc_complete','source_cuad_aa43b2240f866f2f:2593:3850','2.1 Party A shall',111),
    ]:
        flow=json.loads((root/folder/'flow.json').read_text(encoding='utf8'))
        byid={n['id']:n for n in flow['nodes']}
        source=excerpt(byid[source_id],needle,length)
        summary=next(n for n in flow['nodes'] if n['kind']=='research_summary')
        report=next(n for n in flow['nodes'] if n['kind']=='report_output')
        if folder.startswith('01'):
            se=excerpt(summary,'1. **易于学习',340)
            re=excerpt(report,'- 根据 Python',330)
        else:
            se=excerpt(summary,'The contract',len(summary['text']))
            re=excerpt(report,'2.1 Party A shall',len(report['text']))
        recipients=[]
        for call in byid.values():
            if call['kind']=='model_call' and visible(source['text'],call['input_text']):
                direct=None
                if call['agent']=='reporter':
                    if folder.startswith('01'):
                        marker='Below are data collected in previous tasks:'
                        direct=marker in call['input_text'] and visible(source['text'],call['input_text'].split(marker,1)[1])
                    else:
                        direct=visible(byid[source_id]['text'],call['input_text'])
                    assert direct
                recipients.append(dict(id=call['id'],agent=call['agent'],call_index=call.get('call_index'),evidence=call['origin'],direct_source_lane_verified=direct))
        assert any(n['agent']=='researcher' for n in recipients)
        assert any(n['agent']=='reporter' for n in recipients)
        summary_to_report=[e for e in flow['edges'] if e['source']==summary['id'] and byid[e['target']].get('agent')=='reporter']
        assert summary_to_report
        examples.append(dict(case=folder,source=source,summary=se,report=re,source_excerpt_visible_to=recipients,
                             summary_visible_to_reporter=summary_to_report,semantic_support='HUMAN_REVIEW_REQUIRED',causal_influence='NOT_TESTED'))
    (root/'review_examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2),encoding='utf8')
    lines=['# 给师兄看的 MemoryFlow 信息流样例','',
           '整理日期：2026-10-17。这里展示的是从真实轨迹中恢复出来的输入可见性和文本传递，不是已经训练完成的语义信息流模型。未调用模型评审，也没有新增实验调用。','',
           '## 先看结论','',
           '- 243 的短报告任务已有完整链路；保险长任务未完成，没有 Summary 和最终报告。',
           '- 245 的一个 CUAD 开发集案例已有完整链路，还能把输出精确定位到合同字符区间。',
           '- **两例中 Reporter 都看到了来源原文片段和 Researcher Summary。不能把流程简单画成只有 Source → Summary → Report 的单一路径，更不能据此断言报告只依赖 Summary。**',
           '- 可以继续做 chunk 级支持关系标注和基线比较；目前只能验证日志具备提取条件，不能给出语义边准确率。','',
           '## 三份材料是什么','',
           '| 材料 | 提取结果 | 能说明什么 |','|---|---|---|',
           '| SP1 短任务 | 10 个去重网页片段、9 次调用、1 个 Summary、1 个最终报告 | 验证真实记录能串起来；任务简单，不作主实验 |',
           '| 保险长任务 | 379 个去重检索片段、16 个调用开始事件（15 个实际 HTTP 请求）、无完成的 Summary/报告 | 展示搜索膨胀和异常传播，不能充当完整链路 |',
           '| CUAD dev 单例 | 13 个去重合同 chunk、8 次模型调用、1 个最终 Researcher 结果、1 个输出片段 | 可对原文、解释、输出进行逐项讨论 |','',
           '模型输入、已提取的总结与报告、文本可见性关系在各子目录的 flow.json；原始响应通过其中的来源路径回查，不全部打包。精确原文偏移和核查结果在 review_examples.json。以下是便于直接阅读的摘录。']
    labels=['报告生成：Python 教程','DCC/CUAD：优先权条款']
    for label,e in zip(labels,examples):
        lines += ['',f'## {label}','', '### 1. 来源原文片段','',f"来源节点 `{e['source']['node_id']}`；节点内字符区间 [{e['source']['start']}, {e['source']['end']})。",'',
                  '> '+e['source']['text'].replace('\n','\n> '),'','### 2. Researcher 保留了什么','',
                  '> '+e['summary']['text'].replace('\n','\n> '),'','### 3. Reporter 写出了什么','',
                  '> '+e['report']['text'].replace('\n','\n> '),'','### 4. 实际输入核查','',
                  '下列调用输入中包含了上面的完整原文摘录（只忽略空白差异，不做语义猜测）：','',
                  '| 次序 | Agent | 调用 ID |','|---:|---|---|']
        for r in sorted(e['source_excerpt_visible_to'],key=lambda n:n.get('call_index') or 9999):
            lines.append(f"| {r.get('call_index')} | {r['agent']} | `{r['id']}` |")
        lines += ['', 'Researcher 的完整 analysis/Summary 也实际出现在 Reporter 的输入中。由此确认“两路输入都可见”，不确认某一句最终由哪一路造成。']
    lines += ['', '## DCC 这个例子尤其值得讨论什么','',
              '原文写的是 preemptive right（优先权），Researcher 把它解释为接近 ROFR/ROFO/ROFN（优先拒绝权/优先要约权/优先谈判权），同时写明应由律师审查。最终输出定位到了原文第 2.1 条，字符区间 [3212, 3323)。偏移已逐字核对，但这种法律概念映射是否成立没有被本次提取证明。',
              '', '这个案例可以用来讨论：不确定性的限定语有没有在下游保留？证据位置正确是否足以保证判断正确？它不是一次法律意见，也不是整个 CUAD 或 DCC 的准确率结论。',
              '', '## 保险任务为什么不能展示完整流','',
              '运行约 287 秒，发出 15 个模型 HTTP 请求、40 个 Tavily 搜索请求，保存了 38 份成功搜索返回。一次模型回复最多提出 4 个工具调用。输入正文从约 1 万字符增长到约 68 万字符，搜索材料持续累积。',
              '', '第一次失败记录是累计模型输入预算触发的 BudgetExceeded；旧异步调用链随后把异常当成模型返回，出现 “BudgetExceeded object has no attribute generations”。SP1 将其记录成 Researcher 失败并再次委派，最终在搜索预算处停止。因此，这不是可以直接归因于记忆压缩的科学结果，也不能简单说是缺少 API 配置。',
              '', '本次 runner 的累计字符预算是工程保护，不是模型上下文窗口。记录到的 API usage 合计约 115 万 Token，包含重复上下文；不能据此推算实际费用，也不能认为这些都是新增独立信息。',
              '', '## 建议师兄先判断三件事','',
              '1. 这些实际输入、来源片段与中间结果，是否足以定义我们要标注的 chunk 级支持关系？',
              '2. 应先研究 Source→Summary，还是同时标注 Source→Reporter 和 Summary→Reporter，避免忽略直达路径？',
              '3. DCC 中“原文支持事实”与“事实支持判断/限定条件”是否需要分开标注？',
              '', '本轮只选了一个已知有证据的 CUAD dev 案例和一个短任务展示，不声称代表性。建议先据此确认信息流粒度与标注规则，再扩样本。保险任务不应直接放宽预算重跑：先修复预算异常传播，并限制单个研究子任务的规模。']
    (root/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    files=sorted(p for p in root.rglob('*') if p.is_file() and p.name not in ['manifest.json','MemoryFlow_flow_review.zip'])
    manifest={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    with zipfile.ZipFile(root/'MemoryFlow_flow_review.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in files+[root/'manifest.json']:
            archive.write(path,path.relative_to(root).as_posix())
    print(json.dumps({'examples':len(examples),'source_excerpt_visible_to_reporter':True,'output':str(root/'README.md')},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);build(p.parse_args().root)
