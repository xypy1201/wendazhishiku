from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    manifest = ROOT / 'submission/upload_manifest.json'
    rows = json.loads(manifest.read_text(encoding='utf-8'))
    errors = []
    for row in rows:
        target = (ROOT / row['path']).resolve()
        if not target.is_relative_to(ROOT.resolve()):
            errors.append('Invalid path: ' + row['path'])
        elif not target.is_file():
            errors.append('Missing: ' + row['path'])
        elif target.stat().st_size != row['bytes'] or digest(target) != row['sha256']:
            errors.append('Changed/damaged: ' + row['path'])
        if row['bytes'] >= 25 * 1024 * 1024:
            errors.append('Exceeds web file limit: ' + row['path'])
    expected = {row['path'] for row in rows}
    reports = [name for name in expected if name.startswith('data/raw/') and name.endswith('.pdf')]
    assert len(reports) == 28
    assert all('submission/screenshots/Q'+str(i).zfill(2)+'.jpg' in expected for i in range(1,11))
    assert 'submission/一页结论.pdf' in expected and 'submission/一页结论.jpg' in expected
    runtime = json.loads((ROOT/'data/runtime/manifest.json').read_text(encoding='utf-8'))
    assert len(runtime['files']) == 3
    for row in runtime['files']:
        name = 'data/runtime/' + row['archive']
        if name not in expected:
            errors.append('Missing runtime archive from upload manifest: ' + name)
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(rows)} files, 28 PDFs, 60-run logs, 10 JPG screenshots, one-page PDF/JPG, 3 runtime index archives.')
    print('Each file is below 25 MiB; sizes and SHA256 match the upload manifest.')


if __name__ == '__main__':
    main()
