"""Acquire and verify a pinned Qwen3 snapshot on 243; never load a model."""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import time
from concurrent.futures import ThreadPoolExecutor


def download_modelscope(manifest, destination):
    import requests
    from huggingface_hub import hf_hub_download
    api = 'https://modelscope.cn/api/v1/models/Qwen/Qwen3-8B/repo'
    response = requests.get(api+'/files', params={'Revision': 'master', 'Recursive': 'true'}, timeout=15)
    response.raise_for_status()
    metadata = {row['Name']: row for row in response.json()['Data']['Files']}
    origins = {}

    def download(expected):
        name = expected['name']
        dest = destination/name
        if dest.exists():
            verify_file(dest, expected)
            return
        if 'sha256' not in expected:
            hf_hub_download(manifest['repo_id'], name, revision=manifest['revision'],
                            local_dir=str(destination), endpoint='https://hf-mirror.com', token=False)
            return
        row = metadata[name]
        if row['Sha256'] != expected['sha256'] or row['Size'] != expected['bytes']:
            raise ValueError('ModelScope identity differs from official pinned HF metadata')
        origins[name] = row['Revision']
        partial = destination/(name+'.modelscope.partial')
        for attempt in range(3):
            start = partial.stat().st_size if partial.exists() else 0
            if start == expected['bytes']:
                break
            if start > expected['bytes']:
                raise ValueError('partial download exceeds expected size')
            try:
                with requests.get(api, params={'Revision': row['Revision'], 'FilePath': name},
                                  headers={'Range': f'bytes={start}-'} if start else {},
                                  stream=True, timeout=(15, 45)) as response:
                    response.raise_for_status()
                    if start and (response.status_code != 206 or
                                  not response.headers.get('Content-Range', '').startswith(f'bytes {start}-')):
                        raise ValueError('server did not honor resume offset')
                    with partial.open('ab') as handle:
                        for chunk in response.iter_content(1024*1024):
                            if handle.tell()+len(chunk) > expected['bytes']:
                                raise ValueError('download exceeds expected size')
                            handle.write(chunk)
            except requests.RequestException:
                if attempt == 2:
                    raise
        verify_file(partial, expected)
        partial.rename(dest)
        print(json.dumps(dict(status='DOWNLOADED_FILE', name=name)), flush=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(download, manifest['files']))
    return origins


def verify_file(path, expected):
    size = path.stat().st_size
    if size != expected['bytes']:
        raise ValueError(f'size mismatch: {path.name}')
    sha = hashlib.sha256()
    blob = hashlib.sha1(f'blob {size}\0'.encode())
    with path.open('rb') as handle:
        while chunk := handle.read(8*1024*1024):
            sha.update(chunk)
            blob.update(chunk)
    actual = sha.hexdigest() if 'sha256' in expected else blob.hexdigest()
    if actual != expected.get('sha256', expected.get('git_blob')):
        raise ValueError(f'hash mismatch: {path.name}')
    return dict(name=path.name, bytes=size, sha256=sha.hexdigest(), official_identity_match=True)


def main(args):
    manifest = json.loads(Path(__file__).with_name('qwen3_snapshot.json').read_text())
    args.destination.mkdir(parents=True, exist_ok=True)
    report_path = args.destination/'acquisition_report.json'
    if report_path.exists():
        raise FileExistsError('Completed report exists; do not overwrite it')
    required = sum(f['bytes'] for f in manifest['files'] if not (args.destination/f['name']).exists())
    if shutil.disk_usage(args.destination).free < required + 5*1024**3:
        raise OSError('Insufficient disk: need remaining files plus 5 GiB')
    os.environ.update(HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_XET='1',
                      HF_HUB_DISABLE_PROGRESS_BARS='1', HF_HUB_DOWNLOAD_TIMEOUT='45',
                      HF_HUB_ETAG_TIMEOUT='15', CUDA_VISIBLE_DEVICES='')
    logging.disable(logging.CRITICAL)
    from huggingface_hub import snapshot_download
    started = time.time()
    print(json.dumps(dict(status='DOWNLOADING', repo=manifest['repo_id'], revision=manifest['revision'],
                          bytes=sum(f['bytes'] for f in manifest['files']), gpu_used=False)), flush=True)
    origins = {}
    if args.source == 'modelscope':
        origins = download_modelscope(manifest, args.destination)
    else:
        snapshot_download(repo_id=manifest['repo_id'], revision=manifest['revision'],
                          local_dir=str(args.destination), endpoint='https://hf-mirror.com',
                          token=False, max_workers=2, allow_patterns=[f['name'] for f in manifest['files']])
    files = []
    for expected in manifest['files']:
        files.append(verify_file(args.destination/expected['name'], expected))
        print(json.dumps(dict(status='VERIFIED_FILE', name=expected['name'])), flush=True)
    cfg = json.loads((args.destination/'config.json').read_text())
    index = json.loads((args.destination/'model.safetensors.index.json').read_text())
    shards = {f['name'] for f in manifest['files'] if f['name'].endswith('.safetensors')}
    if set(index['weight_map'].values()) != shards or cfg['model_type'] != 'qwen3' or cfg['hidden_size'] != 4096:
        raise ValueError('model config/index mismatch')
    result = dict(status='DOWNLOADED_VERIFIED_NOT_LOADED', repo_id=manifest['repo_id'],
                  revision=manifest['revision'], source=args.source,
                  modelscope_file_revisions=origins,
                  official_metadata=manifest['metadata_source'], destination=str(args.destination),
                  files=files, bytes=sum(f['bytes'] for f in files),
                  seconds=round(time.time()-started, 2), disk_free_bytes=shutil.disk_usage(args.destination).free,
                  gpu_used=False, model_loaded=False, paid_api_calls=0)
    with report_path.open('x') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k:v for k,v in result.items() if k!='files'}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--destination', type=Path, required=True)
    p.add_argument('--source', choices=['hf-mirror', 'modelscope'], default='hf-mirror')
    try:
        main(p.parse_args())
    except Exception as error:
        # Avoid writing any signed CDN URL or token embedded in library exceptions.
        print(json.dumps(dict(status='FAILED', error_type=type(error).__name__)), flush=True)
        raise SystemExit(1)
