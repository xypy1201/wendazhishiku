from __future__ import annotations

import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pymupdf
import requests

from common import COMPANY_NAMES, DATA, ROOT, read_csv, sha256


def discover(row: dict) -> dict:
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cninfo.com.cn/'})
    code = row['company_id']
    title = '2025年年度报告' if row['report_type'] == 'annual' else '2026年半年度报告'
    response = session.post('https://www.cninfo.com.cn/new/hisAnnouncement/query', data={
        'pageNum': 1, 'pageSize': 50, 'column': 'szse' if code[0] in '03' else 'sse',
        'tabName': 'fulltext', 'searchkey': ('长芯博创' if code == '300548' else COMPANY_NAMES[code]) + ' ' + title,
        'seDate': '2026-01-01~2026-10-13', 'isHLtitle': 'false',
        'sortName': 'time', 'sortType': 'desc',
    }, timeout=40)
    response.raise_for_status()
    announcements = response.json().get('announcements') or []
    candidates = [a for a in announcements if a['secCode'] == code
                  and title in re.sub(r'<[^>]+>', '', a['announcementTitle'])
                  and not any(t in a['announcementTitle'] for t in
                              ('摘要', '英文', '取消', '关于', '公告', '说明', '提示', '问询', '回复'))]
    if not candidates:
        raise ValueError(f'CNINFO full report not found: {code} {title}')
    a = candidates[0]
    pdf_url = 'https://static.cninfo.com.cn/' + a['adjunctUrl']
    pdf = session.get(pdf_url, timeout=90)
    pdf.raise_for_status()
    if not pdf.content.startswith(b'%PDF'):
        raise ValueError('Official attachment is not a PDF')
    import hashlib
    official_hash = hashlib.sha256(pdf.content).hexdigest()
    local = DATA / row['local_file'].replace('\\','/')
    local_hash = sha256(local) if local.exists() else ''
    # Replace only after validating the official attachment's cover and all pages.
    with pymupdf.open(stream=pdf.content, filetype='pdf') as document:
        cover = ''.join(document[0].get_text().split())
        period_ok = ('2025' if row['report_type'] == 'annual' else '2026') in cover
        title_ok = ('年度报告' if row['report_type'] == 'annual' else '半年度报告') in cover
        code_ok = code in cover or COMPANY_NAMES[code] in cover or (
            code == '300548' and '博创' in cover)
        if not (period_ok and title_ok and code_ok):
            raise ValueError(f'Official cover does not match registry: {cover[:160]}')
        page_count = len(document)
        if page_count < 20:
            raise ValueError('Attachment is too short to be a full annual/semiannual report')
        empty_pages = sum(not p.get_text().strip() for p in document)
        end_text = ' '.join(document[-1].get_text().split())[:180]
        broken_pages = sum(not bool(p.rect.width and p.rect.height) for p in document)
    if broken_pages:
        raise ValueError('Invalid PDF page geometry')
    if local_hash != official_hash:
        history = ROOT / 'history' / 'original_sources'
        history.mkdir(parents=True, exist_ok=True)
        backup = history / local.name
        if not backup.exists() and local.exists():
            backup.write_bytes(local.read_bytes())
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(pdf.content)
    announcement_url = ('https://www.cninfo.com.cn/new/disclosure/detail?'
                        f'stockCode={code}&announcementId={a["announcementId"]}&orgId={a["orgId"]}')
    row.update(company_name=COMPANY_NAMES[code], official_url=announcement_url,
               pdf_url=pdf_url, sha256=official_hash, source_pages=str(page_count),
               status='verified_official_pdf', error='', verification_date='2026-10-13',
               version_note='CNINFO formal disclosure PDF; cover and all pages opened; official SHA256 verified')
    return {'report_id': row['report_id'], 'company_id': code, 'company_name': COMPANY_NAMES[code],
            'report_period': row['report_period'], 'report_title': a['announcementTitle'],
            'official_url': announcement_url, 'pdf_url': pdf_url, 'local_file': row['local_file'],
            'page_count': page_count, 'empty_text_pages': empty_pages,
            'sha256': official_hash, 'original_local_sha256': local_hash,
            'original_matched_official': local_hash == official_hash,
            'cover_text': cover[:250], 'last_page_excerpt': end_text,
            'checked_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'verification': 'official_attachment_verified'}


def main() -> None:
    rows = read_csv(DATA / 'report_manifest.csv')
    output = []
    def check(row):
        try:
            result = discover(row)
            print('VERIFIED', result['report_id'], result['page_count'], flush=True)
            return result
        except Exception as error:
            print('FAILED', row['report_id'], repr(error), flush=True)
            return {'report_id': row['report_id'], 'company_name': row['company_name'],
                    'verification': 'failed', 'error': str(error)}
    with ThreadPoolExecutor(max_workers=4) as executor:
        output = list(executor.map(check, rows))
    dest = DATA / 'source_verification.json'
    dest.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    fields = sorted({key for row in rows for key in row})
    with (DATA / 'report_manifest.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    fields = sorted({key for row in output for key in row})
    with (DATA / 'source_verification.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    if any(r['verification'] == 'failed' for r in output):
        raise SystemExit('Some official sources failed verification; inspect source_verification.json')


if __name__ == '__main__':
    main()
