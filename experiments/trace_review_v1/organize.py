"""Move only this coordinator's stopped outputs into the existing 243 workspace."""
import hashlib
import json
from pathlib import Path

BASE = Path('/data2/pkuiti/songzhengxing_intern')
PROJECT = BASE / 'memoryflow'
MOVES = {
    'memoryflow_sp1_health_mst_33iq': 'runs/sp1/20261016_health',
    'memoryflow_sp1_smoke_i2zuod7k': 'runs/sp1/20261016_smoke_budget_stop',
    'memoryflow_sp1_smoke_6j118kbt': 'runs/sp1/20261016_smoke_complete',
    'memoryflow_sp1_insurance_v2u4h_rw': 'runs/sp1/20261016_insurance_budget_stop',
    'memoryflow_sp1_runner_N6lJqvkw': 'scripts/sp1_20261016',
    'memoryflow_yifeng_inspect_7tz3ufm9': 'artifacts/third_party/yifeng_20261016',
}


def hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob('*')) if p.is_file()}


def main():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            if b'sp1_bounded_run' in (proc/'cmdline').read_bytes():
                raise RuntimeError('SP1 runner still active; do not move')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    jobs = []
    for old, new in MOVES.items():
        src, dest = BASE/old, PROJECT/new
        assert src.is_dir() and not src.is_symlink()
        assert src.resolve().parent == BASE.resolve()
        assert dest.resolve().is_relative_to(PROJECT.resolve()) and not dest.exists()
        jobs.append((src, dest, hashes(src)))
    records = []
    manifest = PROJECT/'tasks/20261016_flow_review/path_migration.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    assert not manifest.exists()
    for src, dest, before in jobs:
        dest.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dest)
        assert hashes(dest) == before
        records.append({'old': str(src), 'new': str(dest), 'files': before, 'verified': True})
        manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    print(json.dumps({'moved_directories': len(records), 'verified_files': sum(len(x['files']) for x in records), 'manifest': str(manifest)}))


if __name__ == '__main__':
    main()
