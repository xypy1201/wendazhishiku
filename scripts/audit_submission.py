from __future__ import annotations

import json
import re
from datetime import datetime

import pymupdf
from PIL import Image

from common import ROOT, DATA, read_csv, read_jsonl, sha256


def main():
    manifest=read_csv(DATA/'report_manifest.csv')
    assert len(manifest)==28 and len({r['company_id'] for r in manifest})>=10
    records=[]
    for r in manifest:
        assert r['status']=='verified_official_pdf' and not r['error']
        assert r['official_url'].startswith('https://www.cninfo.com.cn/new/disclosure/detail?')
        assert r['pdf_url'].startswith('https://static.cninfo.com.cn/')
        path=DATA/r['local_file'].replace('\\','/')
        digest=sha256(path);assert digest==r['sha256'],r['report_id']
        doc=pymupdf.open(path);assert len(doc)==int(r['source_pages']) and len(doc)>20
        cover=''.join(doc[0].get_text().split())
        assert ('2025' if r['report_period']=='2025' else '2026') in cover
        assert ('年度报告' if r['report_period']=='2025' else '半年度报告') in cover
        for page in doc:assert page.rect.width>0 and page.rect.height>0
        records.append({'report_id':r['report_id'],'company':r['company_name'],
                        'period':r['report_period'],'pages':len(doc),'bytes':path.stat().st_size,
                        'sha256':digest,'official_url':r['official_url'],'pdf_url':r['pdf_url'],
                        'cover':cover[:200],'all_pages_opened':True})
        doc.close()
    parse=json.loads((DATA/'parsed/parse_summary.json').read_text(encoding='utf-8'))
    assert sum(r['pages'] for r in records)==parse['pages']==5196
    index=json.loads((DATA/'index/stats.json').read_text(encoding='utf-8'))
    assert index['documents']==parse['chunks']==13320
    final=read_jsonl(ROOT/'evaluation/final_results.jsonl')
    raw=read_jsonl(ROOT/'evaluation/run_results.jsonl')
    assert len(final)==len(raw)==60
    assert len({r['id'] for r in final})==10
    assert sum(q['type']=='cross_company_panorama' for q in read_jsonl(ROOT/'evaluation/questions.jsonl'))>=2
    raw_sha=sha256(ROOT/'evaluation/run_results.jsonl')
    for result,original in zip(final,raw):
        assert result['answer']==original['answer'] and result['trace']==original['trace']
        assert result['raw_run_sha256']==raw_sha
        ids={d['source_id'] for d in result['evidence']}
        for c in result['claims']:assert set(c['source_ids'])<=ids
        assert all(d['report_period']=='2025' for d in result['evidence'])
    default={r['id']:r for r in final if r['mode']=='evidence'}
    assert '38,239,935,640.67' in default['q01']['answer']
    assert '10,797,254,300.45' in default['q01']['answer']
    assert '8,646,831,134.32' in default['q02']['answer'] and '187.29%' in default['q02']['answer']
    assert '98,871,859.58' in default['q06']['answer'] and '-1,830,688,079.17' in default['q06']['answer']
    assert len(default['q10']['review_details'])==56
    assert len({d['company'] for d in default['q10']['review_details']})==14
    assert '1,675,931,098.18' in default['q07']['answer'] and '4.38%' in default['q07']['answer']
    pdf=pymupdf.open(ROOT/'submission/一页结论.pdf');assert len(pdf)==1;pdf.close()
    shots=json.loads((ROOT/'submission/screenshot_verification.json').read_text(encoding='utf-8'))
    assert len(shots)==10 and all(s['api_answer_matched_log'] and not s['overflow'] for s in shots)
    for shot in shots:
        im=Image.open(ROOT/'submission/screenshots'/shot['file'])
        assert im.format=='JPEG' and im.width==1440 and im.height>900
        im.close()
    payload={'checked_at':datetime.now().isoformat(),'companies':14,'reports':28,
             'pages':5196,'report_audits':records,
             'checks':{'raw_pdf_hashes':True,'covers_and_all_pages_opened':True,
                       'source_manifest_complete':True,'index_count':True,
                       '60_actual_answers_preserved':True,'all_citations_in_read_blocks':True,
                       'annual_not_mixed_with_semiannual':True,'adjusted_yoy':True,
                       'cash_difference':True,'rnd_not_expense':True,'two_panoramas':True,
                       'one_page_pdf':True,'10_actual_web_screenshots':True},
             'code_hashes':{str(p.relative_to(ROOT)):sha256(p) for p in
                            [ROOT/'app.py',ROOT/'scripts/evidence_qa.py',ROOT/'scripts/qa_engine.py',
                             ROOT/'scripts/common.py',ROOT/'scripts/review_homework.py']},
             'reviewer':'Codex source-based review plus programmatic checks; not human blind review',
             'remaining_limitations':['Q05 stage-label mismatch and synonyms','Q10 industry/company demand boundary, table text order and missing Luxshare risk evidence',
                                      'Lexical TF-IDF and rule QA; no LLM/semantic embedding',
                                      'Evidence mode reads more than Top8 methods']}
    (DATA/'local_source_audit.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'submission/verification_report.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 正式来源与全文核验\n\n14家公司各有2025年年报、2026年半年报，合计28份、5,196页。所有原件SHA256与正式附件匹配；可打开全文全部页。状态表示附件取得及完整性核验，不表示每张表均已正确抽取。\n\n|公司|报告期|页数|PDF大小MB|正式披露|全文附件|SHA256|\n|---|---|---|---|---|---|---|']
    for r in records:
        lines.append(f"|{r['company']}|{r['period']}|{r['pages']}|{r['bytes']/1024**2:.2f}|[披露页]({r['official_url']})|[PDF]({r['pdf_url']})|{r['sha256']}|")
    lines.append('\n博创科技按证券代码300548匹配报告披露名长芯博创；分类以主营原页为准，非所有公司的收入都是光模块收入。表格保留原始单元格与逻辑行列；复杂表格仍需按原PDF核对。')
    (DATA/'来源清单与全文核验.md').write_text('\n'.join(lines),encoding='utf-8')
    print('PASS: 28 official PDFs, 60 real answers, citations, 10 screenshots, 1-page PDF')


if __name__=='__main__':main()
