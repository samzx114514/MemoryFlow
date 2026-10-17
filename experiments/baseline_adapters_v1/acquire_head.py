"""Download one pinned, 75.6 MB official CLM head; never a backbone."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = 'e939398d4556fcd9400c76fa8c5a513202f42b0a'
SHA256 = 'b2b4a8c9c2d39263eff78a351eb909a342ce9b3bf21a3f07c1d1bf15f1c4eda5'
BYTES = 75557149
URL = f'https://huggingface.co/Contrastive-LM/CLM-v0.1-8B/resolve/{REVISION}/CLM_v0.1-8B.pt'


def acquire(directory):
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory/'CLM_v0.1-8B.pt'
    if not dest.exists():
        partial = directory/'CLM_v0.1-8B.pt.partial'
        with urllib.request.urlopen(URL, timeout=45) as response, partial.open('xb') as handle:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > BYTES:
                    raise ValueError('download exceeds pinned size')
                handle.write(chunk)
        if partial.stat().st_size != BYTES or hashlib.sha256(partial.read_bytes()).hexdigest() != SHA256:
            raise ValueError('checkpoint identity mismatch')
        partial.rename(dest)
    if dest.stat().st_size != BYTES or hashlib.sha256(dest.read_bytes()).hexdigest() != SHA256:
        raise ValueError('existing checkpoint identity mismatch')
    report = dict(repo='Contrastive-LM/CLM-v0.1-8B', revision=REVISION,
                  filename=dest.name, bytes=BYTES, sha256=SHA256,
                  backbone='Qwen/Qwen3-8B', pooling='last_token', backbone_downloaded=False)
    manifest = directory/'acquisition.json'
    if not manifest.exists():
        with manifest.open('x') as handle:
            json.dump(report, handle, indent=2)
    print(json.dumps(report))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('directory', type=Path)
    acquire(p.parse_args().directory)
