from __future__ import annotations

import json
import re
from concurrent.futures import ProcessPoolExecutor

import pymupdf

from common import COMPANY_NAMES, DATA, PARSED, read_csv, write_jsonl


def clean_cell(value: str | None) -> str:
    return re.sub(r'\s+', '', value or '')


def logical_rows(raw: list[list]) -> list[list[str]]:
    rows = []
    for row in raw:
        cells = [clean_cell(c) for c in row if clean_cell(c)]
        if not cells:
            continue
        # Wrapped PDF row labels can occupy several otherwise empty grid rows.
        if len(cells) == 1 and rows and len(rows[-1]) > 1 and not re.search(r'\d', cells[0]):
            if any(re.fullmatch(r'-?[\d,]+\.\d+%?', c) for c in rows[-1][1:]):
                rows[-1][0] += cells[0]
                continue
        rows.append(cells)
    return rows


def parse_one(row: dict) -> tuple[list, list, list]:
    path = DATA / row['local_file'].replace('\\','/')
    pages, chunks, tables = [], [], []
    section = '封面与目录'
    with pymupdf.open(path) as document:
        for number, page in enumerate(document, 1):
            text = page.get_text(sort=True)
            for line in text.splitlines():
                if re.match(r'^第[一二三四五六七八九十]+节\s*\S+', line.strip()):
                    section = line.strip()
            base = {'report_id': row['report_id'], 'company_id': row['company_id'],
                    'company_name': COMPANY_NAMES[row['company_id']],
                    'report_type': row['report_type'], 'report_period': row['report_period'],
                    'pdf_file': row['local_file'], 'pdf_page_start': number,
                    'pdf_page_end': number, 'section': section,
                    'official_url': row['official_url'], 'pdf_url': row['pdf_url']}
            pages.append({**base, 'pdf_page': number, 'text': text})
            # Keep the original grid and full-page context alongside each table.
            if text.strip():
                try:
                    found = page.find_tables().tables
                except Exception:
                    found = []
                for ti, table in enumerate(found):
                    raw = table.extract()
                    rows = logical_rows(raw)
                    if len(rows) < 2:
                        continue
                    sid = f"{row['report_id']}::p{number}::t{ti:02d}"
                    table_text = '\n'.join(' | '.join(r) for r in rows)
                    item = {**base, 'source_id': sid, 'content_type': 'table',
                            'rows': rows, 'raw_cells': raw, 'bbox': list(table.bbox),
                            'text': f"{base['company_name']} {row['report_period']} {section}\n"
                                    + text[:700] + '\n[表格行列]\n' + table_text}
                    tables.append(item)
                    chunks.append(item)
            chunks.append({**base, 'source_id': f"{row['report_id']}::p{number}::text",
                           'content_type': 'page',
                           'text': f"{base['company_name']} {row['report_period']} {section}\n{text}"})
    print('PARSED', row['report_id'], 'pages', len(pages), 'tables', len(tables), flush=True)
    return pages, chunks, tables


def main() -> None:
    rows = [r for r in read_csv(DATA / 'report_manifest.csv')
            if r['status'] == 'verified_official_pdf']
    if len({r['company_id'] for r in rows}) < 10:
        raise SystemExit('At least ten verified companies are required')
    pages, chunks, tables = [], [], []
    with ProcessPoolExecutor(max_workers=4) as executor:
        for p, c, t in executor.map(parse_one, rows):
            pages.extend(p)
            chunks.extend(c)
            tables.extend(t)
    write_jsonl(PARSED / 'pages.jsonl', pages)
    write_jsonl(PARSED / 'chunks.jsonl', chunks)
    write_jsonl(PARSED / 'tables.jsonl', tables)
    (PARSED / 'parse_summary.json').write_text(json.dumps({
        'reports': len(rows), 'companies': len({r['company_id'] for r in rows}),
        'pages': len(pages), 'chunks': len(chunks), 'tables': len(tables),
        'table_scope': 'all PDF pages; full text plus detected table cell grids',
        'chunk_policy': 'complete page or complete detected table, with original cell grid',
    }, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
