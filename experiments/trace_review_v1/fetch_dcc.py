"""Read-only SSH export of one explicitly selected CUAD dev trajectory."""
import argparse
import json
from pathlib import Path
import subprocess

REMOTE = r'''
from pathlib import Path
import hashlib,json,re
root=Path('/home/qiuzh/work/StackPlanner_tender_audit_backend_20261005')
case=root/'reports/cuad_runs/dev_all820_v3_20261008/traces/00923364ccde0fd5'
secrets=[]
for filename in ['.env','conf.yaml']:
 p=root/filename
 if p.exists():
  for line in p.read_text().splitlines():
   m=re.match(r'\s*(?:export\s+)?([\w]+)\s*[:=]\s*(.*?)\s*$',line)
   if m and re.search(r'key|password|secret|access_token',m[1],re.I):
    value=m[2].strip('"\'')
    if len(value)>5 and not value.startswith('$'):secrets.append(value)
def clean(x):
 if isinstance(x,dict):
  return {k:('<REDACTED>' if re.fullmatch(r'api[_-]?key|password|secret|authorization|access_token',k,re.I) else clean(v)) for k,v in x.items()}
 if isinstance(x,list):return [clean(v) for v in x]
 if isinstance(x,str):
  for s in secrets:x=x.replace(s,'<REDACTED>')
  return re.sub(r'Bearer\s+[A-Za-z0-9._~+/-]{12,}','Bearer <REDACTED>',x)
 return x
names=['model_calls.jsonl','tool_raw_results.jsonl','researcher_result.json','evidence_ledger.json','result.json','trace.jsonl','execution_report.json']
files={};manifest={}
for name in names:
 p=case/name;b=p.read_bytes();manifest[name]={'sha256_original':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 files[name]=clean([json.loads(l) for l in b.decode().splitlines() if l.strip()] if name.endswith('.jsonl') else json.loads(b))
print(json.dumps({'source_directory':str(case),'split':'dev','selection':'one previously inspected nonempty-evidence case; not a representative accuracy sample','manifest':manifest,'files':files},ensure_ascii=False))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                             '-o', 'ConnectTimeout=10', '245', 'python3', '-'],
                            input=REMOTE.encode(), capture_output=True, check=True, timeout=60)
    obj = json.loads(result.stdout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8') as handle:
        json.dump(obj, handle, ensure_ascii=False)
    print(json.dumps({'output': str(args.output), 'bytes': args.output.stat().st_size, 'files': len(obj['files'])}))


if __name__ == '__main__':
    main()
