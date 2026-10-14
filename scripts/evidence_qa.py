from __future__ import annotations

import re
import json
from decimal import Decimal
from functools import lru_cache

from common import COMPANY_NAMES, DATA
from qa_engine import HybridSearch

METHODS = {
    'vector': 'TF-IDF 向量', 'bm25': 'BM25 原句', 'keyword_bm25': '规则关键词 BM25',
    'query_rewrite_vector': '规则精炼 TF-IDF', 'hybrid': 'TF-IDF + BM25',
    'evidence': '按公司与义务补证',
}


@lru_cache(maxsize=1)
def searcher() -> HybridSearch:
    return HybridSearch()


@lru_cache(maxsize=1)
def profiles() -> dict:
    return json.loads((DATA / 'company_profiles.json').read_text(encoding='utf-8'))


def flat(text: str) -> str:
    return re.sub(r'\s+', '', text)


def route(query: str, company: str = '', period: str = '') -> dict:
    names = [c for c in COMPANY_NAMES.values() if c in query]
    if company:
        names = [c for c in re.split(r'[|,，、]', company) if c]
    if '三层' in query or '14家' in query:
        names = list(COMPANY_NAMES.values())
    detected = '2026H1' if re.search(r'2026.*(半年|上半年|1.?6月)', query) else '2025' if '2025' in query else ''
    period = period or detected
    if '差额' in query and '现金' in query:
        intent, topics = 'difference', ['营业收入 主要会计数据 归属于上市公司股东的净利润 经营活动产生的现金流量净额']
    elif '同比' in query:
        intent, topics = 'growth', ['营业收入 主要会计数据 财务指标']
    elif ('海外' in query or '境外' in query) and '占比' in query:
        intent, topics = 'overseas', ['营业收入 分地区 国外 境外']
    elif '比较' in query and '业务收入' in query:
        intent, topics = 'comparability', ['分产品 营业收入 高速光模块 传输 数据与接入']
    elif '营业收入' in query and ('净利润' in query or '归母' in query):
        intent, topics = 'metrics', ['营业收入 主要会计数据 归属于上市公司股东的净利润']
    elif '三层' in query or '14家' in query:
        intent, topics = 'panorama', ['主营业务 光模块 光器件 光芯片', '需求 市场 算力', '研发投入 产能', '风险 可能面对的风险']
    elif '速率升级' in query or '高速光模块' in query and len(names) > 3:
        intent, topics = 'speed', ['高速光模块 800G 1.6T 主要产品']
    elif '风险' in query and '研发' in query:
        intent, topics = 'multi', ['主要产品 光模块 数据通信', '研发投入金额 研发投入占营业收入比例', '风险 可能面对的风险']
    elif '研发' in query and '需求' in query:
        intent, topics = 'research', ['研发投入金额 研发投入占营业收入比例', '产品需求 算力 高速光模块']
    elif len(names) > 1:
        intent, topics = 'boundary', ['光模块 光通信 硅光 主要业务 小批量 送样 营收']
    else:
        intent, topics = 'business', ['主要业务 主要产品 光器件 无源 有源 光引擎']
    return {'intent': intent, 'companies': names, 'period': period, 'topics': topics}


def citation(item: dict) -> str:
    return f"[{item['source_id']}；{item['company_name']}；{item['report_period']}；PDF第{item['pdf_page_start']}页]"


def metric(evidence: list[dict], name: str, primary: bool = False) -> dict | None:
    for doc in sorted(evidence, key=lambda d: d['pdf_page_start']):
        if doc.get('content_type') != 'table':
            continue
        if primary and not (doc['pdf_page_start'] <= 15 and '主要会计数据' in flat(doc['text'])):
            continue
        headers = ''.join(''.join(r) for r in doc.get('rows', [])[:3])
        if primary and ('季度' in headers or '2025年' not in headers and '2026年' not in headers):
            continue
        for row in doc.get('rows', []):
            aliases = {'研发投入金额': ('研发投入金额','研发投入合计'),
                       '研发投入占营业收入比例': ('研发投入占营业收入比例','研发投入总额占营业收入比例')}
            if not row or not any(a in row[0] for a in aliases.get(name,(name,))) or '扣除' in row[0] or '资本化' in row[0]:
                continue
            numbers = [c for c in row[1:] if re.fullmatch(r'-?[\d,]+(?:\.\d+)?%?', c)]
            if not numbers:
                continue
            if name == '研发投入占营业收入比例' and not numbers[0].endswith('%'):
                if '%' in row[0]:
                    numbers[0] += '%'
                else:
                    continue
            return {'label': row[0], 'current': numbers[0], 'values': numbers,
                    'adjusted': '调整后' in flat(doc['text']), 'source': doc}
    return None


def number(value: str) -> Decimal:
    return Decimal(value.replace(',', '').replace('%', ''))


def excerpt(evidence: list[dict], terms: list[str], limit: int = 2, topic: str = '') -> list[tuple[str, dict]]:
    candidates = []
    for doc in evidence:
        if doc.get('content_type') != 'page' or doc['pdf_page_start'] > 80:
            continue
        if topic in ('光通信披露与阶段','高速产品与速率','业务与产品') and doc['pdf_page_start'] < 9:
            continue
        raw_lines = doc['text'].splitlines()[1:]
        raw_lines = [l for l in raw_lines if not re.fullmatch(r'[\d\s/\-%]+', l.strip())
                     and '年度报告全文' not in l and '年年度报告' not in l]
        text = flat('\n'.join(raw_lines))
        sentences = re.split(r'(?<=[。；])', text)
        for sentence in sentences:
            if len(sentence) < 25 or len(sentence) > 1200:
                continue
            if any(t in sentence for t in ('主要交流以下问题','投资者关系活动记录表')):
                continue
            if topic == '风险' and not ('风险' in sentence and any(t in sentence for t in
                ('可能','如果','若','下降','不利','波动','不确定','面临','影响','依赖','未达'))):
                continue
            if topic == '研发或产能' and (not any(t in sentence for t in ('研发','产能','扩产')) or '风险' in sentence):
                continue
            if topic == '需求' and '需求' not in sentence:
                continue
            if topic == '高速产品与速率' and not ('光模块' in sentence and any(t in sentence for t in
                ('公司','支持','项目','推出','提供','系列'))):
                continue
            if len(re.findall(r'\d+\.\d+',sentence)) > (12 if topic == '高速产品与速率' else 4):
                continue
            score = sum(t in sentence for t in terms)
            if topic == '业务与产品':
                score += 3 * ('光引擎' in sentence and '公司' in sentence)
            if topic == '光通信披露与阶段':
                score += 3 * any(t in sentence for t in ('小批量供货','首次流片','主要业务','主营业务','公司新增','公司的营业收入'))
                score -= 4 * any(t in sentence for t in ('液冷板','散热方案','盲插','线缆误码率'))
            if topic == '风险':
                score += 3 * any(t in sentence for t in ('可能导致','可能提高','不利影响','可能会','若公司','如果'))
                score -= 4 * any(t in sentence for t in ('公司将','分散市场风险','降低对单一','应对措施'))
            if topic == '高速产品与速率':
                score += 2 * any(t in sentence for t in ('项目','样机','量产','推出','提供'))
                score += 3 * ('800G' in sentence or '800Gb/s' in sentence) + 3 * ('1.6T' in sentence)
            if score:
                candidates.append((score, sentence, doc))
    chosen, seen = [], set()
    for _, sentence, doc in sorted(candidates, key=lambda x: (-x[0], x[2]['pdf_page_start'])):
        if sentence in seen:
            continue
        chosen.append((sentence, doc))
        seen.add(sentence)
        if len(chosen) >= limit:
            break
    return chosen


def collect(query: str, plan: dict, mode: str, k: int) -> tuple[list[dict], list[dict]]:
    engine = searcher()
    names = plan['companies']
    scope = '|'.join(names)
    initial = engine.search(query, k=k, company=scope, period=plan['period'],
                            mode='hybrid' if mode == 'evidence' else mode)
    evidence = {d['source_id']: d for d in initial}
    trace = [{'tool': 'search', 'phase': 'prefetch', 'query': query, 'company': scope,
              'source_ids': [d['source_id'] for d in initial]}]
    if mode == 'evidence':
        for name in names:
            located = []
            for d in engine.docs:
                if d['company_name'] != name or d['report_period'] != plan['period'] or d['content_type'] != 'table':
                    continue
                headers = ''.join(''.join(r) for r in d['rows'][:3])
                needed = plan['intent'] in ('metrics','growth','difference') and d['pdf_page_start'] <= 15 and '主要会计数据' in flat(d['text']) and '季度' not in headers and ('2025年' in headers or '2026年' in headers)
                needed |= plan['intent'] in ('research','multi','panorama') and any(r and any(t in r[0] for t in ('研发投入金额','研发投入合计')) for r in d['rows']) and d['pdf_page_start'] <= 80
                needed |= plan['intent']=='speed' and d['pdf_page_start'] <= 30 and any(t in headers for t in ('速率','产品系列','产品类别')) and not any(t in headers for t in ('项目','进展','目的','经营模式')) and any('800G' in ''.join(r) or '1.6T' in ''.join(r) for r in d['rows'])
                if needed:
                    evidence[d['source_id']] = d
                    located.append(d['source_id'])
                    sid = f"{d['report_id']}::p{d['pdf_page_start']}::text"
                    if sid in engine.by_id:
                        evidence[sid] = engine.by_id[sid]
            if located:
                trace.append({'tool':'find_table/read','phase':'table_schema_lookup','company':name,
                              'query':'年度主表 / 研发投入 / 产品速率列定位','source_ids':located})
            if plan['period'] == '2025' and plan['intent'] in ('panorama','business','boundary','speed'):
                code = next(code for code, value in COMPANY_NAMES.items() if value == name)
                sid = f"{code}_annual_2025::p{profiles()[code]['business_page']}::text"
                if sid in engine.by_id:
                    evidence[sid] = engine.by_id[sid]
                    trace.append({'tool': 'read', 'phase': 'company_catalog', 'company': name,
                                  'source_ids': [sid], 'query': '主营业务导航页'})
            if any('风险' in topic for topic in plan['topics']):
                code = next(code for code, value in COMPANY_NAMES.items() if value == name)
                report_id = f"{code}_{'annual_2025' if plan['period']=='2025' else 'semiannual_2026H1'}"
                risk_ids = []
                for p in range(1, 6):
                    sid = f'{report_id}::p{p}::text'
                    if sid in engine.by_id and '风险' in engine.by_id[sid]['text']:
                        evidence[sid] = engine.by_id[sid]
                        risk_ids.append(sid)
                trace.append({'tool':'read','phase':'important_notice_risk','company':name,
                              'query':'重要提示中的风险披露','source_ids':risk_ids})
                section_ids = []
                for d in engine.docs:
                    if (d['company_name'] == name and d['report_period'] == plan['period']
                            and d['content_type'] == 'page' and d['pdf_page_start'] <= 80
                            and any(term in flat(d['text']) for term in
                                    ('可能面临的风险','可能面对的风险','可能面对的主要风险','技术升级风险','宏观环境风险','市场竞争风险'))):
                        evidence[d['source_id']] = d
                        section_ids.append(d['source_id'])
                        following = f"{d['report_id']}::p{d['pdf_page_start']+1}::text"
                        if following in engine.by_id:
                            evidence[following] = engine.by_id[following]
                            section_ids.append(following)
                trace.append({'tool':'find_section/read','phase':'risk_section','company':name,
                              'query':'风险章节及相邻页','source_ids':section_ids})
            for topic in plan['topics']:
                found = engine.search(topic, k=8, company=name, period=plan['period'], mode='hybrid')
                # Read full pages for every candidate, so a table cannot hide its units,
                # column headings, or a limiting statement in surrounding text.
                ids = []
                for d in found:
                    evidence[d['source_id']] = d
                    ids.append(d['source_id'])
                    if d['content_type'] == 'table':
                        page_id = f"{d['report_id']}::p{d['pdf_page_start']}::text"
                        if page_id in engine.by_id:
                            evidence[page_id] = engine.by_id[page_id]
                trace.append({'tool': 'search/read', 'phase': 'by_company_obligation',
                              'query': topic, 'company': name, 'source_ids': ids})
    return list(evidence.values()), trace


def compose(plan: dict, evidence: list[dict]) -> tuple[str, list[dict], list[dict]]:
    intent = plan['intent']
    lines = [f"报告期：{plan['period']}。财务金额为人民币元；主要会计数据采用上市公司合并口径。"]
    claims, coverage = [], []

    def add(company, topic, text, sources, status='已覆盖'):
        lines.append(f"\n{company} · {topic}\n{text}")
        claims.append({'company': company, 'topic': topic, 'text': text,
                       'source_ids': [d['source_id'] for d in sources], 'status': status})
        coverage.append({'company': company, 'obligation': topic, 'status': status,
                         'source_ids': [d['source_id'] for d in sources]})

    for company in plan['companies']:
        docs = [d for d in evidence if d['company_name'] == company and d['report_period'] == plan['period']]
        if intent in ('metrics', 'growth', 'difference'):
            names = ['营业收入', '归属于上市公司股东的净利润'] if intent == 'metrics' else ['营业收入'] if intent == 'growth' else ['经营活动产生的现金流量净额', '归属于上市公司股东的净利润']
            values = [metric(docs, name, primary=True) for name in names]
            for name, value in zip(names, values):
                if value:
                    detail = f"{name}：{value['current']} 元。{citation(value['source'])}"
                    if intent == 'growth':
                        ns = value['values']
                        previous = ns[2] if value['adjusted'] and len(ns) >= 5 else ns[1] if len(ns) >= 2 else ''
                        if previous and number(previous) != 0:
                            pct = (number(ns[0]) / number(previous) - 1) * 100
                            detail += f"\n上年{'调整后' if value['adjusted'] else '同期'}：{previous} 元；同比 = ({ns[0]} ÷ {previous} - 1) × 100% = {pct:.2f}%。"
                    add(company, name, detail, [value['source']])
                else:
                    add(company, name, '材料未覆盖：本次读取的证据中没有可验证的完整指标行。', [], '缺据')
            if intent == 'difference':
                if all(values):
                    diff = number(values[0]['current']) - number(values[1]['current'])
                    add(company, '差额计算', f"差额 = 经营现金流净额 - 归母净利润 = {diff:,.2f} 元。" + citation(values[0]['source']), [v['source'] for v in values])
                else:
                    add(company, '差额计算', '缺少输入值，不能计算。', [], '缺据')
            continue
        if intent == 'comparability':
            relevant = []
            for d in docs:
                if d['content_type'] == 'table' and '营业收入' in ''.join(''.join(r) for r in d['rows'][:6]) and '分产品' in flat(d['text']):
                    rows = [r for r in d['rows'] if any(k in r[0] for k in ('高速光模块','传输','数据与接入','电信宽带','无线网络'))]
                    if rows:
                        relevant.append((d, rows))
            if relevant:
                d, rows = sorted(relevant, key=lambda v: v[0]['pdf_page_start'])[0]
                detail = '\n'.join(f"{re.split('主营业务分地区', r[0])[0]}：{r[1]} 元（收入）；其他原表列：{' | '.join(r[2:])}" for r in rows)
                detail += '\n以上为收入分类及原表前列。' + citation(d)
                add(company, '收入拆分口径', detail, [d])
            else:
                add(company, '收入拆分口径', '材料未覆盖：没有召回可核对的分产品收入表。', [], '缺据')
            continue
        if intent == 'overseas':
            rows = [(d,r) for d in docs if d['content_type']=='table' for r in d['rows']
                    if r and any(t in r[0] for t in ('国外','境外','海外','营业收入合计'))]
            total = next(((d,r) for d,r in rows if '营业收入合计' in r[0]), None)
            foreign = next(((d,r) for d,r in rows if any(t in r[0] for t in ('国外','境外','海外'))), None)
            if total and foreign:
                amount = number(foreign[1][1]); denominator = number(total[1][1])
                add(company, '海外营业收入占比', f"{amount:,.2f} ÷ {denominator:,.2f} × 100% = {amount / denominator * 100:.2f}%。\n{citation(foreign[0])}{citation(total[0])}", [foreign[0],total[0]])
            else:
                add(company, '海外营业收入占比', '材料未覆盖：需要同一表中境外收入和营业收入合计，不能用光模块境外收入代替公司境外收入。', [], '缺据')
            continue
        topics = [('业务与产品', ['主营','主要业务','光器件','无源','有源','光引擎'])]
        if intent == 'speed':
            topics = [('高速产品与速率', ['800G','1.6T','高速','光模块'])]
        elif intent == 'boundary':
            topics = [('光通信披露与阶段', ['光模块','硅光','送样','暂未','小批量','光芯片'])]
        elif intent == 'research':
            topics = [('研发投入', []), ('需求表述', ['需求','算力','光模块','高速'])]
        elif intent == 'multi':
            topics = [('产品', ['高速','数据通信','800G','光模块']), ('研发投入', []), ('风险', ['风险','竞争','技术','贸易'])]
        elif intent == 'panorama':
            topics = [('业务层级', ['主营','主要业务','光模块','光器件','芯片']),
                      ('需求', ['需求','市场','算力']), ('研发或产能', ['研发','产能','扩产']),
                      ('风险', ['风险','竞争','技术','贸易'])]
        for topic, terms in topics:
            if intent == 'boundary' and plan['period'] == '2025':
                code = next(code for code, value in COMPANY_NAMES.items() if value == company)
                profile = profiles()[code]
                sid = f"{code}_annual_2025::p{profile['business_page']}::text"
                catalog = next((d for d in docs if d['source_id'] == sid), None)
                if catalog:
                    lines.append(f"\n业务定位：{company}，{profile['note']}。{citation(catalog)}")
            if topic == '业务层级' and plan['period'] == '2025':
                code = next(code for code, value in COMPANY_NAMES.items() if value == company)
                profile = profiles()[code]
                sid = f"{code}_annual_2025::p{profile['business_page']}::text"
                catalog = next((d for d in docs if d['source_id'] == sid), None)
                if catalog:
                    add(company, topic, f"{profile['layer']}；{profile['note']}。{citation(catalog)}", [catalog])
                    continue
            if not terms:
                amount = metric(docs, '研发投入金额')
                ratio = metric(docs, '研发投入占营业收入比例')
                if amount and ratio:
                    add(company, topic, f"研发投入 {amount['current']} 元；占营业收入 {ratio['current']}。\n{citation(amount['source'])}{citation(ratio['source'])}", [amount['source'],ratio['source']])
                else:
                    add(company, topic, '材料未覆盖：金额或比例缺失，不能用研发费用替代研发投入。', [], '缺据')
            else:
                if topic == '研发或产能':
                    amount = metric(docs, '研发投入金额')
                    ratio = metric(docs, '研发投入占营业收入比例')
                    if amount:
                        detail = f"研发投入 {amount['current']} 元"
                        detail += f"，占营业收入 {ratio['current']}" if ratio else '；营收占比本次未核实'
                        detail += '。此为公司整体研发口径，不能等同于光模块专属研发。' + citation(amount['source'])
                        add(company, topic, detail, [amount['source']] + ([ratio['source']] if ratio else []))
                        continue
                if topic == '高速产品与速率':
                    product_tables = [d for d in docs if d['content_type']=='table' and d['pdf_page_start']<=30
                                      and any(t in ''.join(''.join(r) for r in d['rows'][:3]) for t in ('速率','产品系列','产品类别'))
                                      and not any(t in ''.join(''.join(r) for r in d['rows'][:3]) for t in ('项目','进展','目的','经营模式'))]
                    supported = [(d,[s for s in ('800G','1.6T') if s in ''.join(''.join(r) for r in d['rows'])]) for d in product_tables]
                    supported = [(d,rates) for d,rates in supported if rates]
                    if supported:
                        rates = sorted({r for _,rs in supported for r in rs})
                        add(company, topic, '产品表明确列示速率：' + '、'.join(rates) + '。产品列示不等于所有型号均规模量产。\n' + '\n'.join(citation(d) for d,_ in supported), [d for d,_ in supported])
                        continue
                candidates = docs
                if topic == '业务与产品' and plan['period'] == '2025':
                    code = next(code for code, value in COMPANY_NAMES.items() if value == company)
                    primary = [d for d in docs if d['content_type']=='page' and d['pdf_page_start']==profiles()[code]['business_page']]
                    candidates = primary or docs
                snippets = excerpt(candidates, terms, limit=1 if intent=='panorama' else 3 if topic in ('业务与产品','高速产品与速率','光通信披露与阶段','产品') else 2, topic=topic)
                if snippets:
                    add(company, topic, '\n'.join(s + citation(d) for s,d in snippets), [d for _,d in snippets])
                    if intent == 'boundary':
                        quoted = ''.join(s for s,_ in snippets)
                        stages = []
                        for stage, keywords in {'研发':['研发','流片'], '送样':['送样'],
                                                '小批量供货':['小批量供货'], '形成收入':['形成营收','形成收入']}.items():
                            stages.append(stage + ('：原文明确提及（具体状态见引文）' if any(k in quoted for k in keywords) else '：本次证据未核实'))
                        lines.append('阶段核验：' + '；'.join(stages) + '。')
                else:
                    add(company, topic, '材料未覆盖：本次检索未取得直接表述；不据此推断公司没有该业务。', [], '缺据')
    if intent == 'comparability':
        lines.append('\n比较结论：高速光模块、传输、数据与接入是不同收入分类；未核对到相同业务边界时，不进行光模块收入排名。总营业收入也不能替代光模块收入。')
    if intent == 'panorama':
        lines.append('\n可比性结论：模块、器件/芯片、综合制造企业有交叉业务，不能互斥归类。以下披露用于定性比较；公司总收入、不同产能单位、送样与量产阶段不能直接混排。只把已读取的原文作为证据，缺据不等于没有业务。')
    if intent == 'boundary':
        lines.append('\n边界：研发、送样、小批量供货、规模量产和形成收入分别判断；没有收入拆分时不能推算光模块收入。')
    return '\n'.join(lines), claims, coverage


def ask(query: str, company: str = '', period: str = '', k: int = 8, mode: str = 'evidence') -> dict:
    mode = mode if mode in METHODS else 'evidence'
    plan = route(query, company, period)
    if not plan['period'] or not plan['companies']:
        return {'query': query, 'mode': mode, 'plan': plan, 'answer': '请明确公司范围和报告期后再问答。',
                'evidence': [], 'trace': [], 'claims': [], 'coverage': []}
    evidence, trace = collect(query, plan, mode, k)
    answer, claims, coverage = compose(plan, evidence)
    trace.append({'tool': 'compose', 'phase': 'final', 'source_ids': sorted({s for c in claims for s in c['source_ids']})})
    return {'query': query, 'mode': mode, 'plan': plan, 'answer': answer, 'evidence': evidence,
            'trace': trace, 'claims': claims, 'coverage': coverage,
            'answer_method': 'deterministic table extraction, Decimal calculation, verbatim cited statements'}
