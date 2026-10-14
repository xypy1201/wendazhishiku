from __future__ import annotations

import json
import os
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from common import ROOT, read_jsonl

OUT = ROOT / 'submission'
FONT = Path(os.environ.get('KB_CJK_FONT','C:/Windows/Fonts/msyh.ttc'))
BOLD = Path(os.environ.get('KB_CJK_BOLD_FONT','C:/Windows/Fonts/msyhbd.ttc'))
SHORT = ['TF-IDF','BM25原句','关键词BM25','精炼TF-IDF','混合检索','按公司补证']
QUESTIONS = ['单公司财务表','调整后同比计算','主营及产业链','收入分类可比性','新业务/阶段边界',
             '两公司现金差额','传闻去噪及研发','产品/研发/风险','五公司速率全景','14公司四项全景']


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    summaries = json.loads((ROOT/'evaluation/summary.json').read_text(encoding='utf-8'))
    runs = read_jsonl(ROOT/'evaluation/final_results.jsonl')
    img=Image.new('RGB',(3000,2200),'white');d=ImageDraw.Draw(img)
    ink='#1c282b';muted='#52656a';green='#137d6b';line='#d2dedc'
    def font(size,bold=False):return ImageFont.truetype(str(BOLD if bold else FONT),size)
    def text(x,y,s,size=30,color=ink,bold=False):d.text((x,y),s,font=font(size,bold),fill=color)
    def wrap(x,y,s,width,size=30,color=ink,gap=12,bold=False):
        f=font(size,bold);curr='';lines=[]
        for c in s:
            if c=='\n':lines.append(curr);curr='';continue
            if d.textlength(curr+c,font=f)>width:lines.append(curr);curr=c
            else:curr+=c
        if curr:lines.append(curr)
        for i,l in enumerate(lines):text(x,y+i*(size+gap),l,size,color,bold)
        return y+len(lines)*(size+gap)
    text(90,60,'光模块财报问答知识库',68,bold=True)
    text(92,149,'真实十题 × 六种方法 | 来源、召回与答案分别核验 | 补交结论',34,muted)
    text(2380,86,'2026.10.13',34,muted)
    d.line((90,215,2910,215),fill=green,width=5)
    facts=[('14家 / 28份','正式披露全文'),('5,196页','全文与表格解析'),('60次','实际问答运行'),('8/10题','默认方法完整答对')]
    for i,(value,label) in enumerate(facts):
        x=90+i*705;text(x,244,value,50,green,True);text(x,309,label,28,muted)
    text(90,386,'逐题答案得分',38,bold=True)
    text(90,441,'0 无核心答案   1 回答不足   2 主要正确有遗漏   3 完整正确',27,muted)
    left=90;labelw=450;colw=192;top=509;rowh=70
    palette={0:('#f4dedb','#922e26'),1:('#f2e8d5','#805711'),2:('#dceae3','#31654f'),3:('#137d6b','#ffffff')}
    for i,s in enumerate(SHORT):text(left+labelw+i*colw+7,top-3,s,24,bold=True)
    for qi,label in enumerate(QUESTIONS):
        y=top+55+qi*rowh;text(left,y+11,f'Q{qi+1:02d}  {label}',29)
        for mi,s in enumerate(summaries):
            score=s['question_scores'][f'q{qi+1:02d}'];bg,fg=palette[score]
            x=left+labelw+mi*colw;d.rectangle((x,y,x+colw-10,y+rowh-9),fill=bg)
            text(x+75,y+7,str(score),36,fg,True)
    yy=top+55+10*rowh
    text(left,yy+10,'答案总分 / 30',28,bold=True)
    for mi,s in enumerate(summaries):text(left+labelw+mi*colw+53,yy+10,str(s['answer_total']),34,green,True)
    y=yy+94;text(left,y,'召回参考义务命中 / 81（单独评价）',32,bold=True)
    y+=62;text(left,y,'初始Top8',27,muted)
    for mi,s in enumerate(summaries):text(left+labelw+mi*colw+43,y,f"{s['initial_hits']}/81",27)
    y+=52;text(left,y,'补证后',27,muted)
    for mi,s in enumerate(summaries):text(left+labelw+mi*colw+43,y,f"{s['read_hits']}/81",27)
    y+=52;text(left,y,'平均读取块',27,muted)
    for mi,s in enumerate(summaries):text(left+labelw+mi*colw+52,y,str(s['average_read_blocks']),27)
    x=1840;y=386;text(x,y,'哪些题好答，哪些容易翻车？',36,bold=True);y+=72
    conclusions=[
        ('收入分类题：六种方法均3分','Q04含明确类别词，易定位原表；保留“传输/数据与接入”与“高速光模块”的边界，不作同口径排名。'),
        ('去噪：关键词/精炼方法有收益','Q07关键词BM25与精炼TF-IDF均3分，原句TF-IDF、BM25及混合均1分；删除传闻词后，研发投入表更易进入Top8。'),
        ('财务与计算：须读到完整主表','Q02、Q06固定Top8方法均0分；默认补证均3分。相关页面命中不代表完整指标行命中，还要核对年度、单位及追溯调整。'),
        ('全景：按公司补证提升覆盖','Q09补证3分，固定Top8方法均1分。Q10补证仍2分：部分需求只有行业背景，立讯风险缺直接证据，不能以“有引用”判满分。'),
    ]
    for title,body in conclusions:
        text(x,y,title,31,green,True);y+=53
        y=wrap(x,y,body,1040,29,gap=11)+41
    d.line((90,1700,2910,1700),fill=line,width=3)
    text(90,1732,'失败案例与下一步',34,bold=True)
    wrap(90,1795,'Q05仍为2分：阶段规则漏识别“预研”，收入来源引文与阶段标签不一致。Q10仍为2分：公司需求与行业预测未充分分开，表格串读与跨页摘录影响完整性。改进应围绕原表行列、公司义务和阶段同义词，不能只增加召回数量。',2770,30,gap=12)
    wrap(90,1932,'比较限制：前五方法固定Top8；补证方法均读67.1块，Q10读441块，额外使用公司导航与全文表格定位。不能据此宣称同预算算法全面优胜。TF-IDF为词项向量，精炼/补证为规则流程；未接入语义向量或大模型。',2770,27,color=muted,gap=10)
    wrap(90,2050,'评分：Codex依据正式PDF原页逐项复核及可复现数值/出处检查，非教师评分或人工盲评。参考页命中非穷尽相关集Recall。十题样本较小；完整60份答案与轨迹见evaluation/final_results.jsonl，实际网页截图见submission/screenshots。',2770,25,color=muted,gap=9)
    img.save(OUT/'一页结论.jpg',quality=95,subsampling=0,dpi=(180,180))
    img.save(OUT/'一页结论.pdf','PDF',resolution=180)
    pdf=pymupdf.open(OUT/'一页结论.pdf');assert len(pdf)==1;pdf.close()
    print('WROTE',OUT/'一页结论.jpg',OUT/'一页结论.pdf')


if __name__=='__main__':main()
