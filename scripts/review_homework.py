from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from statistics import mean

import pymupdf

from common import ROOT, DATA, COMPANY_NAMES, read_jsonl, write_jsonl
from evidence_qa import METHODS

EVAL = ROOT / 'evaluation'
RND = {
    '中际旭创':'1,675,931,098.18', '新易盛':'702,143,848.24',
    '天孚通信':'266,580,928.65', '东山精密':'1,431,775,054.82',
    '立讯精密':'11,428,041,090.59', '光迅科技':'1,135,613,332.65',
    '剑桥科技':'456,160,943.26', '可川科技':'54,755,613.10',
    '博创科技':'127,317,189.59', '光库科技':'176,394,431.17',
    '源杰科技':'80,843,055.86', '仕佳光子':'132,727,812.08',
    '联特科技':'102,229,429.71', '华工科技':'1,091,561,114.87',
}


def norm(s):
    return re.sub(r'\s+|,|，', '', str(s)).lower().replace('gb/s','g')


def write_csv(name, rows):
    with (EVAL / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    refs = json.loads((EVAL / 'reference_answers.json').read_text(encoding='utf-8'))
    panorama = json.loads((EVAL / 'panorama_reference_pages.json').read_text(encoding='utf-8'))
    runs = read_jsonl(EVAL / 'run_results.jsonl')
    assert len(runs) == 60 and len({(r['id'],r['mode']) for r in runs}) == 60
    originals = {}
    for code, name in COMPANY_NAMES.items():
        doc = pymupdf.open(DATA / 'raw' / f'{code}_annual_2025.pdf')
        originals[name] = [p.get_text() for p in doc]
        doc.close()
    final, items, metrics = [], [], []
    for r in runs:
        ref = refs['questions'][r['id']]
        requirements = ref['requirements']
        if r['id'] == 'q10':
            requirements = [{'company':c,'topic':t,'pages':ps,
                             'values':[RND[c]] if t=='研发或产能' else []}
                            for c, topics in panorama.items() for t, ps in topics.items()]
        claims = {(c['company'],c['topic']):c for c in r['claims']}
        details = []
        for req in requirements:
            company, topic = req['company'], req['topic']
            claim = claims.get((company,topic), {'text':'','source_ids':[]})
            docs = [d for d in r['evidence'] if d['company_name']==company]
            anchors = [d['source_id'] for d in docs if d['pdf_page_start'] in req['pages']]
            # Reference-page hit is a retrieval measure; it does not grade the answer.
            prefetched = r['trace'][0]['source_ids']
            initial = [sid for sid in anchors if sid in prefetched]
            text = norm(claim['text'])
            missing = [v for v in req.get('values',[]) if norm(v) not in text]
            missing += [v for v in req.get('concepts',[]) if norm(v) not in text]
            citations = [d for d in docs if d['source_id'] in claim['source_ids']]
            valid = bool(citations) and all(d['report_period']=='2025' for d in citations)
            source_text = ''.join(norm(originals[company][d['pdf_page_start']-1]) for d in citations)
            direct_values = req.get('values',[]) if topic not in ('差额计算',) else []
            if r['id']=='q02':
                direct_values = direct_values[:2]
            invalid_values = [v for v in direct_values if norm(v) not in source_text]
            points, notes = (2 if valid and not missing and not invalid_values else 1 if valid else 0), []
            if not valid:
                notes.append('未给出该公司该义务的可核对答案及出处')
            if missing:
                notes.append('遗漏参考要点：' + '、'.join(missing))
            if invalid_values:
                points = 0
                notes.append('引用原页不支持数值：' + '、'.join(invalid_values))
            if r['id']=='q05' and company=='立讯精密' and '小批量供货' not in text:
                points = min(points,1)
                notes.append('没有取到800G/1.6T光模块小批量供货；线缆或散热部件阶段不能替代')
            if r['id']=='q03' and '主要交流以下问题' in claim['text']:
                points = min(points,1)
                notes.append('投资者提出的问题不能代替公司主营业务答案')
            if r['id']=='q10' and valid:
                if topic=='需求':
                    if '公司' not in claim['text'] or '《' in claim['text']:
                        points = min(points,1)
                        notes.append('仅有行业背景/政策或预测，缺少公司需求取证，不能当成订单或业绩')
                    elif '项目' in claim['text'] and len(claim['text'])>200:
                        points = min(points,1)
                        notes.append('页面表格行列串读，需求与项目进展混杂')
                    elif company=='可川科技':
                        points = min(points,1)
                        notes.append('通用客户导向表述没有交代光通信新业务需求')
                if topic=='风险' and not any(t in claim['text'] for t in ('可能','若','如果','下降','不利','波动')):
                    points = min(points,1)
                    notes.append('只摘录风险标题或背景，没有具体影响机制')
                if topic=='业务层级' and not any(t in claim['text'] for t in ('模块；','器件/芯片；','其他相关','交叉')):
                    points = min(points,1)
                    notes.append('有业务引文，但没有完成三层定位')
            detail = {'company':company,'topic':topic,'reference_pages':req['pages'],
                      'reference_available':bool(req['pages']), 'recalled_reference_ids':anchors,
                      'initial_reference_ids':initial,'answer_points':points,'max_points':2,
                      'answer_source_ids':claim['source_ids'],'notes':notes}
            details.append(detail)
            items.append({'question':r['id'],'method':r['mode'],'company':company,'obligation':topic,
                          'initial_hit':int(bool(initial)),'read_hit':int(bool(anchors)),
                          'reference_available':int(bool(req['pages'])), 'answer_points':points,
                          'reference_pages':','.join(map(str,req['pages'])),
                          'citation_ids':' | '.join(claim['source_ids']), 'errors':'；'.join(notes)})
        ratio = sum(d['answer_points'] for d in details) / (2 * len(details))
        score = 3 if ratio == 1 else 2 if ratio >= .65 else 1 if ratio > 0 else 0
        errors = [d['company']+' / '+d['topic']+'：'+'；'.join(d['notes']) for d in details if d['notes']]
        # Conservative whole-answer judgments after the item checks.
        if r['id']=='q05' and score==3:
            score = 2
            errors.append('阶段与产品对应关系仍需逐行判断；未核实标签只表示本次答案不足，不能等同年报未披露')
        if r['id']=='q05' and r['mode']=='evidence':
            errors.append('东山引用已写收入来源，但阶段标签仍未核实；立讯引文写深度预研，阶段规则没有识别预研同义词')
        if r['id']=='q09' and score!=3:
            completed = sum(d['answer_points']==2 for d in details)
            score = 2 if completed>=4 else 1 if any(d['answer_points'] for d in details) else 0
        if r['id']=='q10':
            score = min(score,2)
            if not panorama['立讯精密']['风险']:
                errors.append('立讯风险：年报第2页只有导航，52–53页展望无明确主要风险；参考集也缺证，未判定公司不存在风险')
        verdict = {3:'核心答案正确且完整',2:'主要正确，仍有遗漏',1:'部分有据，核心回答不足',0:'没有可用核心答案'}[score]
        retrieval = {'covered':sum(bool(d['recalled_reference_ids']) for d in details),
                     'total':len(details),'initial_covered':sum(bool(d['initial_reference_ids']) for d in details),
                     'auditable_reference_total':sum(d['reference_available'] for d in details),
                     'read_blocks':len(r['evidence']),
                     'definition':'公司×义务参考页命中率；初始Top8和补证后分开。非穷尽相关集的标准Recall/Precision。'}
        note = 'Codex依据PDF原页逐项复核，并执行数值、出处与遗漏检查；非教师评分、非人工盲评。0–3分规则见reference_answers.json。'
        final.append({**r,'retrieval':retrieval,'answer_score':score,'verdict':verdict,
                      'errors':errors,'review_note':note,'review_details':details,
                      'reference_answer':ref['reference_answer'],
                      'raw_run_sha256':hashlib.sha256((EVAL/'run_results.jsonl').read_bytes()).hexdigest()})
        metrics.append({'question_id':r['id'],'mode':r['mode'],'method':METHODS[r['mode']],
                        'initial_covered':retrieval['initial_covered'],'read_covered':retrieval['covered'],
                        'obligations':retrieval['total'],'read_blocks':len(r['evidence']),
                        'answer_score':score,'verdict':verdict,'errors':'；'.join(errors),
                        'run_at':r['run_at'],'elapsed_seconds':r['elapsed_seconds']})
    write_jsonl(EVAL / 'final_results.jsonl', final)
    write_csv('item_review.csv',items)
    write_csv('all_methods_scores.csv',metrics)
    write_csv('final_10_questions_scores.csv',[m for m in metrics if m['mode']=='evidence'])
    write_csv('retrieval_metrics.csv',[{k:v for k,v in m.items() if k in ('question_id','mode','method','initial_covered','read_covered','obligations','read_blocks')} for m in metrics])
    write_csv('answer_metrics.csv',[{k:v for k,v in m.items() if k in ('question_id','mode','method','answer_score','verdict','errors')} for m in metrics])
    header = '# 真实逐题答案与评测（2026-10-13）\n\n报告期固定2025年度，6种方法分别真实运行；默认方法为按公司与义务补证。召回与答案分别评价。\n\n3分完整正确；2分主要正确有遗漏；1分核心回答不足；0分没有可用核心答案。\n\n'
    for filename, selected in [('final_10_questions_answers.md',[r for r in final if r['mode']=='evidence']),('六方法真实逐题答案与评分.md',final)]:
        lines = [header]
        for r in selected:
            lines += [f"## {r['id'].upper()} · {METHODS[r['mode']]}\n\n{r['question']}\n",
                      f"### 参考答案\n\n{r['reference_answer']}\n",
                      f"### 实际系统答案（原样保存）\n\n{r['answer']}\n",
                      f"### 评测\n\n答案：{r['answer_score']}/3，{r['verdict']}。初始Top8义务命中 {r['retrieval']['initial_covered']}/{r['retrieval']['total']}；补证后 {r['retrieval']['covered']}/{r['retrieval']['total']}；读取 {len(r['evidence'])} 块。\n\n错误/不足：{'；'.join(r['errors']) or '本次核验未发现'}。\n\n{r['review_note']}\n",
                      '### 召回/读取块\n\n'+'\n'.join(f"- `{d['source_id']}`：{d['company_name']}，2025年度，PDF第{d['pdf_page_start']}页，{d['content_type']}，{'最终引用' if any(d['source_id'] in c['source_ids'] for c in r['claims']) else '未引用'}。" for d in r['evidence'])+'\n',
                      '### 公司×义务核验\n\n|公司|义务|答案完成度|出处|不足|\n|---|---|---|---|---|\n'+ '\n'.join(f"|{d['company']}|{d['topic']}|{d['answer_points']}/2|{', '.join(d['answer_source_ids'])}|{'；'.join(d['notes']) or '未发现'}|" for d in r['review_details'])+'\n']
        (EVAL/filename).write_text('\n'.join(lines),encoding='utf-8')
    pan = next(r for r in final if r['id']=='q10' and r['mode']=='evidence')
    lines = ['# 14家公司全景逐项取证\n\n每项2分=完整，1分=部分，0分=缺据。仅有引用不自动算正确。公司整体研发不是光模块专项研发。\n']
    for company in COMPANY_NAMES.values():
        lines.append('## '+company+'\n')
        for claim in [c for c in pan['claims'] if c['company']==company]:
            review = next(d for d in pan['review_details'] if d['company']==company and d['topic']==claim['topic'])
            lines.append(f"### {claim['topic']} · {review['answer_points']}/2\n\n{claim['text']}\n\n核验：{'；'.join(review['notes']) or '对应原文，未发现核心错误'}。\n")
    (EVAL/'panorama_by_company.md').write_text('\n'.join(lines),encoding='utf-8')
    summaries = []
    for mode in METHODS:
        group=[r for r in final if r['mode']==mode]
        summaries.append({'mode':mode,'method':METHODS[mode],'answer_total':sum(r['answer_score'] for r in group),
                          'answer_max':30,'fully_correct':sum(r['answer_score']==3 for r in group),
                          'initial_hits':sum(r['retrieval']['initial_covered'] for r in group),
                          'read_hits':sum(r['retrieval']['covered'] for r in group),
                          'obligations':sum(r['retrieval']['total'] for r in group),
                          'average_read_blocks':round(mean(len(r['evidence']) for r in group),1),
                          'question_scores':{r['id']:r['answer_score'] for r in group}})
    (EVAL/'summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summaries,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
