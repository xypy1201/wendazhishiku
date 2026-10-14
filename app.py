from __future__ import annotations

import argparse
import html
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from common import COMPANY_NAMES, DATA, read_jsonl
from evidence_qa import METHODS, ask

QUESTIONS = read_jsonl(ROOT / 'evaluation' / 'questions.jsonl')


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def evaluations() -> list:
    return read_jsonl(ROOT / 'evaluation' / 'final_results.jsonl')


def frozen(query: str, mode: str, company: str, period: str, k: int) -> dict | None:
    if company or period not in ('', '2025') or k != 8:
        return None
    return next((r for r in evaluations() if r['question'] == query and r['mode'] == mode), None)


def chart(result: dict, review: dict | None) -> str:
    covered = len({c['company'] for c in result['claims'] if c['source_ids']})
    total = len(result['plan']['companies'])
    citations = len({s for c in result['claims'] for s in c['source_ids']})
    values = [('公司证据覆盖', covered, total), ('最终引用块', citations, len(result['evidence']))]
    if review:
        values += [('召回义务覆盖', review['retrieval']['covered'], review['retrieval']['total']),
                   ('答案得分', review['answer_score'], 3)]
    rows = ''
    for i, (label, numerator, denominator) in enumerate(values):
        y = 45 + i * 34
        width = int(430 * numerator / max(1, denominator))
        rows += f"<text x='16' y='{y+15}' font-size='13'>{label}</text><rect x='150' y='{y}' width='430' height='20' fill='#e5e7eb'/><rect x='150' y='{y}' width='{width}' height='20' fill='{'#16816d' if i<3 else '#ca7a25'}'/><text x='600' y='{y+15}' font-size='13'>{numerator}/{denominator}</text>"
    label = ('核验结论：' + review['verdict']) if review else '答案评分：本次参数没有对应的已核验记录'
    height = 78 + 34 * len(values)
    return f"<svg viewBox='0 0 710 {height}' role='img' aria-label='召回与答案分开评测' style='max-width:710px;width:100%'><text x='16' y='24' font-size='16'>{esc(label)}</text>{rows}</svg>"


def shell(body: str) -> bytes:
    css = """*{box-sizing:border-box}body{font:15px/1.7 'Microsoft YaHei',sans-serif;color:#252b2e;background:#fff;margin:0}main{max-width:1180px;margin:0 auto;padding:26px 24px}h1{font-size:26px;margin:0 0 16px}h2{font-size:20px;margin:26px 0 12px}h3{font-size:17px;margin:18px 0 8px}a{color:#126d64;overflow-wrap:anywhere}textarea{width:100%;min-height:115px;padding:12px;font:inherit;border:1px solid #aeb9bd;border-radius:4px}select,input,button{font:inherit;padding:7px;border:1px solid #aeb9bd;border-radius:4px;max-width:100%}button{background:#176f62;color:white;border:0;padding:8px 24px;cursor:pointer}.controls{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0;align-items:end}.controls label{display:flex;flex-direction:column;font-size:13px}header{border-bottom:2px solid #176f62;padding-bottom:12px;margin-bottom:18px}.meta{color:#68767b;font-size:13px}.answer{white-space:pre-wrap;overflow-wrap:anywhere;border-left:3px solid #176f62;padding:8px 18px;background:#f6f9f8}.evaluation{border-top:1px solid #ccd5d3;border-bottom:1px solid #ccd5d3;padding:12px 0;margin-top:20px}details{border-top:1px solid #d7dddd;padding:9px 0}summary{cursor:pointer;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 'Microsoft YaHei',sans-serif}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:7px;text-align:left;border-bottom:1px solid #d7dddd;vertical-align:top}.scroll{overflow-x:auto}.badge{color:#176f62;font-weight:bold}.questions li{padding:5px 0}.answer-source{font-size:12px}.error{color:#a33325}@media(max-width:600px){main{padding:16px 12px}h1{font-size:22px}.controls label{width:100%}.answer{padding:6px 10px}}"""
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>光模块财报问答知识库</title><style>{css}</style></head><body><main>{body}</main></body></html>".encode('utf-8')


def result_html(result: dict, review: dict | None) -> str:
    plan = result['plan']
    text = result['answer']
    cited = {s for c in result['claims'] for s in c['source_ids']}
    evidence = sorted(result['evidence'], key=lambda d: (d['source_id'] not in cited, d['company_name'], d['pdf_page_start']))
    body = f"<header><h1>光模块财报问答知识库</h1><a href='/'>返回提问</a></header><h2>{esc(result['query'])}</h2><p class='meta'>报告期 {esc(plan['period'])} · {esc(METHODS[result['mode']])} · 公司 {len(plan['companies'])} 家 · 最终引用 {len(cited)} 块</p><section class='answer'>{esc(text)}</section>"
    body += "<section class='evaluation'><h2>召回与答案评测</h2>" + chart(result, review)
    if review:
        body += f"<p>答案得分 <b>{review['answer_score']}/3</b> · {esc(review['verdict'])} · 错误：{esc('；'.join(review['errors']) or '未发现')}</p><p class='meta'>{esc(review['review_note'])}</p>"
    body += "</section><h2>证据覆盖地图</h2><div class='scroll'><table><tr><th>公司</th><th>义务</th><th>覆盖状态</th><th>引用页</th></tr>"
    for row in result['coverage']:
        pages = [s.split('::')[1] for s in row['source_ids']]
        checked = next((d for d in review['review_details'] if d['company']==row['company'] and d['topic']==row['obligation']),None) if review else None
        status = f"原文复核 {checked['answer_points']}/2" if checked else row['status']
        body += f"<tr><td>{esc(row['company'])}</td><td>{esc(row['obligation'])}</td><td>{esc(status)}</td><td>{esc(', '.join(pages))}</td></tr>"
    body += f"</table></div><h2>召回与读取记录（{len(evidence)} 块）</h2>"
    extra_open = False
    for d in evidence:
        if d['source_id'] not in cited and not extra_open:
            body += f"<details><summary>其余未引用候选块（{len(evidence)-len(cited)} 块）</summary>"
            extra_open = True
        pdf = '/reports/' + Path(d['pdf_file'].replace('\\','/')).name
        body += f"<details><summary>{'<span class=\"badge\">已引用</span> ' if d['source_id'] in cited else ''}{esc(d['company_name'])} · {esc(d['report_period'])} · PDF第{d['pdf_page_start']}页 · {esc(d['content_type'])}</summary><p class='meta'>{esc(d['source_id'])}</p><p><a href='{esc(pdf)}#page={d['pdf_page_start']}'>查看PDF原页</a> · <a href='{esc(d.get('official_url',''))}'>正式披露来源</a></p><pre>{esc(d['text'])}</pre></details>"
    if extra_open:
        body += '</details>'
    body += f"<details><summary>取证轨迹（{len(result['trace'])} 条）</summary><pre>{esc(json.dumps(result['trace'],ensure_ascii=False,indent=2))}</pre></details>"
    return body


class Handler(BaseHTTPRequestHandler):
    def send(self, data: bytes, content_type: str = 'text/html; charset=utf-8', status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/health':
            self.send(b'{"status":"ok","version":"verified-homework-2026-10-13"}', 'application/json')
            return
        if parsed.path.startswith('/reports/'):
            name = parsed.path.rsplit('/', 1)[-1]
            path = DATA / 'raw' / name
            if name.endswith('.pdf') and path.is_file():
                self.send(path.read_bytes(), 'application/pdf')
            else:
                self.send(b'Not found', 'text/plain', 404)
            return
        if parsed.path == '/assets/eval.jpg':
            path = ROOT / 'submission' / '一页结论.jpg'
            if path.exists():
                self.send(path.read_bytes(), 'image/jpeg')
                return
        params = parse_qs(parsed.query)
        query = params.get('q', [''])[0].strip()
        company = params.get('company', [''])[0].strip()
        period = params.get('period', ['2025'])[0]
        mode = params.get('mode', ['evidence'])[0]
        try:
            k = max(1, min(20, int(params.get('k', ['8'])[0])))
        except ValueError:
            k = 8
        if query:
            try:
                result = ask(query, company, period, k, mode)
                if parsed.path == '/api/ask':
                    self.send(json.dumps(result, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')
                    return
                body = result_html(result, frozen(query, mode, company, period, k))
            except Exception as error:
                self.send(shell(f"<h1>问答暂不可用</h1><p class='error'>{esc(error)}</p>"), status=500)
                return
        else:
            options = ''.join(f"<option value='{key}' {'selected' if key==mode else ''}>{esc(value)}</option>" for key,value in METHODS.items())
            companies = ''.join(f"<option>{esc(n)}</option>" for n in COMPANY_NAMES.values())
            body = f"<header><h1>光模块行业财报问答知识库</h1><p class='meta'>14 家公司 · 2025 年年报 / 2026 年半年报 · 正式披露全文</p></header><form><textarea aria-label='问题' name='q' required placeholder='中际旭创2025年度营业收入和归母净利润是多少？'></textarea><div class='controls'><label>公司<select name='company'><option value=''>按问题识别</option>{companies}</select></label><label>报告期<select name='period'><option value='2025'>2025 年度</option><option value='2026H1'>2026 上半年</option></select></label><label>检索模式<select name='mode'>{options}</select></label><label>预取数量<input type='number' name='k' value='8' min='1' max='20' style='width:80px'></label><button>查询</button></div></form><h2>十题实测</h2><ol class='questions'>"
            for q in QUESTIONS:
                url = '/?' + urlencode({'q':q['question'],'period':q['period'],'mode':'evidence','k':8})
                body += f"<li><a href='{esc(url)}'>{esc(q['question'])}</a></li>"
            body += '</ol>'
        self.send(shell(body))

    def log_message(self, format, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    from prepare_runtime import ensure_index
    ensure_index()
    print(f'http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
