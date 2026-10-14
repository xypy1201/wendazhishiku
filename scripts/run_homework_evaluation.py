from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from common import ROOT, read_jsonl, write_jsonl
from evidence_qa import METHODS, ask


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--modes', default='all')
    args = parser.parse_args()
    modes = list(METHODS) if args.modes == 'all' else args.modes.split(',')
    questions = read_jsonl(ROOT / 'evaluation' / 'questions.jsonl')
    rows = []
    for q in questions:
        for mode in modes:
            start = time.perf_counter()
            result = ask(q['question'], period=q['period'], k=q['k'], mode=mode)
            row = {**q, **result, 'run_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                   'elapsed_seconds': round(time.perf_counter() - start, 3),
                   'prefetch_k': q['k'], 'code_version': 'verified-homework-2026-10-13'}
            rows.append(row)
            print(q['id'], mode, 'read', len(result['evidence']),
                  'claims', len(result['claims']), 'seconds', row['elapsed_seconds'], flush=True)
    name = 'run_results.jsonl' if args.modes == 'all' else 'run_results_' + args.modes + '.jsonl'
    write_jsonl(ROOT / 'evaluation' / name, rows)
    print('WROTE', name, len(rows), flush=True)


if __name__ == '__main__':
    main()
