from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_NAMES = ('docs.jsonl', 'vectors.jsonl', 'terms.jsonl')


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def ensure_index(root: Path = ROOT) -> None:
    index = root / 'data/index'
    bundle = root / 'data/runtime'
    manifest = bundle / 'manifest.json'
    if not manifest.exists():
        if all((index / name).is_file() for name in INDEX_NAMES):
            return
        raise RuntimeError('Missing index bundle: restore data/runtime or run parse_verified_reports.py and build_index.py.')
    rows = json.loads(manifest.read_text(encoding='utf-8'))['files']
    if {row['name'] for row in rows} != set(INDEX_NAMES):
        raise ValueError('Unexpected runtime index manifest')
    index.mkdir(parents=True, exist_ok=True)
    for row in rows:
        target = index / row['name']
        if target.is_file() and digest(target) == row['sha256']:
            continue
        packed = bundle / row['archive']
        if packed.parent != bundle or not packed.name.endswith('.gz'):
            raise ValueError('Invalid runtime archive path')
        if not packed.is_file() or digest(packed) != row['archive_sha256']:
            raise ValueError(f'Missing or damaged runtime archive: {packed.name}')
        temp = index / (row['name'] + '.tmp')
        try:
            with gzip.open(packed, 'rb') as source, temp.open('wb') as destination:
                shutil.copyfileobj(source, destination)
            if temp.stat().st_size != row['bytes'] or digest(temp) != row['sha256']:
                raise ValueError(f'Index integrity check failed: {row["name"]}')
            temp.replace(target)
        finally:
            if temp.exists():
                temp.unlink()
        print('RESTORED INDEX', row['name'], flush=True)


if __name__ == '__main__':
    ensure_index()
    print('Runtime index ready.')
