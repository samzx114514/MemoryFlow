"""Launch two bounded jobs on distinct currently idle GPUs; no fixed GPU IDs."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

from evaluate import write


def main(root, run):
    snapshot = subprocess.check_output(['nvidia-smi', '--query-gpu=index,memory.free,utilization.gpu',
                                       '--format=csv,noheader,nounits'], text=True)
    cards = [tuple(int(s.strip()) for s in line.split(',')) for line in snapshot.splitlines()]
    safe = sorted((c for c in cards if c[1] >= 40 * 1024 and c[2] == 0), key=lambda c: (-c[1], c[0]))
    if len(safe) < 2:
        raise RuntimeError('Need two distinct idle GPUs with >=40 GiB free')
    if any((run / name).exists() for name in ('clm', 'yifeng', 'launch.json', 'clm.log', 'yifeng.log')):
        raise FileExistsError('Existing run outputs; do not overwrite')
    jobs = []
    for method, card in zip(('clm', 'yifeng'), safe):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(card[0]), HF_HUB_OFFLINE='1',
                   TRANSFORMERS_OFFLINE='1', TORCH_FORCE_WEIGHTS_ONLY_LOAD='1')
        command = [sys.executable, '-u', str(Path(__file__).with_name('evaluate.py')), method,
                   '--root', str(root), '--inputs', str(run / 'inputs'), '--output', str(run / method)]
        with (run / f'{method}.log').open('x') as log:
            proc = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        jobs.append(dict(method=method, physical_gpu=card[0], logical_gpu=0, pid=proc.pid, command=command))
    write(run / 'launch.json', dict(snapshot=snapshot, jobs=jobs))
    print(jobs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.run)
