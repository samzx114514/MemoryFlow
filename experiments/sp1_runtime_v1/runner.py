"""External SP1 smoke/insurance runner. Never imports credentials into artifacts."""
import argparse
import asyncio
import contextlib
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path('/data2/pkuiti/songzhengxing_intern/SP1.0')
SMOKE = '请检索 Python 官方教程，用中文写一段不超过150字的简短介绍，说明 Python 的两个特点并附来源网址。只做一个研究子任务，检索一次即可，然后生成最终报告；不要编写或运行代码，不要下载文件。'
INSURANCE = '收集整理目前国际综合实力前十的保险公司的相关资料，横向比较各公司的融资情况、信誉度、过往五年的增长幅度、实际分红、未来在中国发展潜力等维度，并为我评估出最有可能在未来资产排名靠前的2-3家公司。同时包含中资与外资保险集团。综合实力的评价口径由系统提出并说明，未来资产排名预测请保持资产统计口径可比；不要直接把“综合实力前十”等同于“总资产前十”。'


class BudgetExceeded(BaseException):
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['smoke', 'insurance'], required=True)
    args = parser.parse_args()
    smoke = args.stage == 'smoke'
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.umask(0o077)
    logging.disable(logging.CRITICAL)
    from dotenv import load_dotenv
    import yaml
    load_dotenv(ROOT / '.env')
    conf = yaml.safe_load((ROOT / 'conf.yaml').read_text())
    secrets = [v for k, v in os.environ.items() if any(t in k.upper() for t in ['KEY', 'TOKEN', 'SECRET', 'PASSWORD']) and len(v) > 5]
    def collect(value):
        if isinstance(value, dict):
            for k, v in value.items():
                if any(t in k.lower() for t in ['api_key', 'password', 'secret']) and isinstance(v, str) and not v.startswith('$'):
                    secrets.append(v)
                else:
                    collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)
    collect(conf)
    output_root = ROOT.parent / 'memoryflow' / 'runs' / 'sp1'
    output_root.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=f'{args.stage}_', dir=output_root))
    trace = out / 'researcher_traces'
    trace.mkdir()
    os.environ.update(MEMORYFLOW_TRACE_DIR=str(trace), MEMORYFLOW_TRACE_RUN_ID=out.name, MEMORYFLOW_TRACE_QUERY_ID=args.stage)
    if smoke:
        os.environ['AGENT_RECURSION_LIMIT'] = '8'
    limits = dict(seconds=300 if smoke else 3600, model_attempts=12 if smoke else 80, search_attempts=3 if smoke else 40, max_output_tokens=8192, input_chars=500000 if smoke else 4000000)
    report = dict(stage=args.stage, query=SMOKE if smoke else INSURANCE, limits=limits, model_calls=0, search_calls=0, input_chars=0, nodes=[], artifact_directory=str(out), pid=os.getpid(), status='RUNNING', started_at=time.time(), seed=None, seed_note='No seed supplied; existing model defaults preserved.')
    report['versions'] = {n: importlib.metadata.version(n) for n in ['langgraph', 'langgraph-prebuilt', 'langchain-core', 'langchain-openai']}
    report['git_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['model'] = conf['BASIC_MODEL'].get('model')
    report['model_revision'] = 'API provider revision not supplied'
    report['query_sha256'] = hashlib.sha256(report['query'].encode()).hexdigest()
    report['source_sha256'] = {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['src/agents/ResearcherAgent_SP.py', 'src/agents/CommonReactAgent.py', 'src/graph/builder.py']}
    def default(value):
        return value.model_dump() if hasattr(value, 'model_dump') else str(value)
    def save(name, value):
        text = json.dumps(value, ensure_ascii=False, default=default)
        for secret in secrets:
            if secret:
                text = text.replace(secret, '<REDACTED>')
        dest = out / name
        pending = out / (name + '.tmp')
        pending.write_text(text, encoding='utf8')
        pending.replace(dest)
    def progress():
        report['elapsed_seconds'] = round(time.time() - report['started_at'], 2)
        save('run_summary.json', report)
    progress()
    print(json.dumps({'artifact_directory': str(out), 'pid': os.getpid()}), flush=True)
    lock = threading.Lock()
    def deadline(*unused):
        raise BudgetExceeded('wall_time')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(limits['seconds'])
    try:
        with open(os.devnull, 'w') as null, contextlib.redirect_stdout(null), contextlib.redirect_stderr(null):
            from src.llms.llm import get_llm_by_type
            llm = get_llm_by_type('basic')
            llm.max_tokens = limits['max_output_tokens']
            llm.max_retries = 0
            llm.root_client = llm.root_client.with_options(max_retries=0, timeout=60)
            llm.client = llm.root_client.chat.completions
            llm.root_async_client = llm.root_async_client.with_options(max_retries=0, timeout=60)
            llm.async_client = llm.root_async_client.chat.completions
            from langchain_core.callbacks import BaseCallbackHandler
            class CaptureModel(BaseCallbackHandler):
                def on_chat_model_start(self, serialized, messages, *, run_id, parent_run_id=None, **kwargs):
                    save(f'llm_input_{run_id}.json', {'run_id': str(run_id), 'parent_run_id': str(parent_run_id), 'messages': messages})

                def on_llm_end(self, response, *, run_id, **kwargs):
                    save(f'llm_output_{run_id}.json', response)

                def on_llm_error(self, error, *, run_id, **kwargs):
                    save(f'llm_error_{run_id}.json', {'error_type': type(error).__name__, 'message': str(error)[:800]})
            llm.callbacks = [CaptureModel()]
            import httpx
            import requests
            import aiohttp
            def model_guard(request):
                if '/chat/completions' not in str(request.url):
                    return
                with lock:
                    body = json.loads(request.content)
                    chars = len(json.dumps(body.get('messages', []), ensure_ascii=False))
                    if report['model_calls'] >= limits['model_attempts'] or report['input_chars'] + chars > limits['input_chars']:
                        raise BudgetExceeded('model_budget')
                    report['model_calls'] += 1
                    report['input_chars'] += chars
                    save(f"model_request_{report['model_calls']:03d}.json", body)
                    progress()
            old_send, old_asend = httpx.Client.send, httpx.AsyncClient.send
            def send(self, request, *a, **kw):
                model_guard(request)
                return old_send(self, request, *a, **kw)
            async def asend(self, request, *a, **kw):
                model_guard(request)
                return await old_asend(self, request, *a, **kw)
            httpx.Client.send, httpx.AsyncClient.send = send, asend
            def search_guard(url):
                if 'tavily' not in str(url) or '/search' not in str(url):
                    return None
                with lock:
                    if report['search_calls'] >= limits['search_attempts']:
                        raise BudgetExceeded('search_budget')
                    report['search_calls'] += 1
                    progress()
                    return report['search_calls']
            old_req, old_areq = requests.sessions.Session.request, aiohttp.ClientSession._request
            def req(self, method, url, *a, **kw):
                index = search_guard(url)
                kw.setdefault('timeout', 45)
                result = old_req(self, method, url, *a, **kw)
                if index is not None and result.status_code == 200:
                    save(f'search_response_{index:03d}.json', result.json())
                return result
            async def areq(self, method, url, *a, **kw):
                index = search_guard(url)
                kw.setdefault('timeout', aiohttp.ClientTimeout(total=45))
                result = await old_areq(self, method, url, *a, **kw)
                if index is not None and result.status == 200:
                    save(f'search_response_{index:03d}.json', await result.json())
                return result
            requests.sessions.Session.request, aiohttp.ClientSession._request = req, areq
            from src.graph.sp_nodes import init_agents
            from src.graph.builder import sp_graph
            from loguru import logger
            logger.remove()
            init_agents('sp')
            async def run():
                state = dict(messages=[{'role': 'user', 'content': report['query']}], auto_accepted_plan=True, enable_background_investigation=False, user_query=report['query'], locale='zh-CN')
                config = {'configurable': {'thread_id': out.name, 'max_plan_iterations': 1, 'max_step_num': 1 if smoke else 10, 'graph_format': 'sp'}, 'recursion_limit': 16 if smoke else 100}
                async for update in sp_graph.astream(state, config=config, stream_mode='updates'):
                    report['nodes'].extend(update.keys())
                    save(f"graph_update_{len(report['nodes']):03d}.json", update)
                    for value in update.values():
                        if isinstance(value, dict) and value.get('final_report'):
                            save('final_report.json', {'final_report': value['final_report']})
                            report['final_report_chars'] = len(value['final_report'])
                    progress()
            asyncio.run(run())
            report['status'] = 'GRAPH_COMPLETED'
    except BaseException as error:
        report['status'] = 'BUDGET_STOP' if isinstance(error, BudgetExceeded) else 'FAILED'
        report['error_type'] = type(error).__name__
        report['error_message'] = str(error)[:800]
        import traceback
        report['error_frames'] = [dict(file=f.filename, line=f.lineno, function=f.name) for f in traceback.extract_tb(error.__traceback__)[-8:]]
    finally:
        signal.alarm(0)
        report['researcher_trace_count'] = len(list(trace.glob('*.json')))
        final_path = out / 'final_report.json'
        final_text = json.loads(final_path.read_text())['final_report'] if final_path.exists() else ''
        report['smoke_gate_pass'] = report['status'] == 'GRAPH_COMPLETED' and report['search_calls'] > 0 and report['researcher_trace_count'] > 0 and bool(final_text) and not final_text.startswith('报告生成失败')
        progress()
        print(json.dumps({k: report[k] for k in ['status', 'model_calls', 'search_calls', 'nodes', 'researcher_trace_count', 'smoke_gate_pass', 'artifact_directory']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
