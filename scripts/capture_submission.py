from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

from common import ROOT, read_jsonl


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:8765')
    args=parser.parse_args()
    out=ROOT/'submission/screenshots';out.mkdir(parents=True,exist_ok=True)
    runs=[r for r in read_jsonl(ROOT/'evaluation/final_results.jsonl') if r['mode']=='evidence']
    log=[]
    with sync_playwright() as p:
        edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
        browser=p.chromium.launch(executable_path=str(edge)) if edge.exists() else p.chromium.launch(channel='chrome')
        context=browser.new_context(viewport={'width':1440,'height':1000},device_scale_factor=1)
        page=context.new_page()
        page.goto(args.base_url,wait_until='networkidle',timeout=120000)
        page.screenshot(path=str(out/'00_首页.jpg'),type='jpeg',quality=92,full_page=True)
        for r in runs:
            params=urlencode({'q':r['question'],'period':'2025','mode':'evidence','k':8})
            live=context.request.get(args.base_url+'/api/ask?'+params,timeout=120000).json()
            assert live['answer']==r['answer'],r['id']+' live answer differs from measured answer'
            assert [d['source_id'] for d in live['evidence']]==[d['source_id'] for d in r['evidence']]
            page.goto(args.base_url+'/?'+params,wait_until='networkidle',timeout=120000)
            assert page.locator('.answer').inner_text()==r['answer']
            assert page.locator('.evaluation').inner_text().find(str(r['answer_score'])+'/3')>=0
            if r['id']=='q01':
                page.locator('details').first.locator('summary').click()
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
            name=r['id'].upper()+'.jpg'
            page.screenshot(path=str(out/name),type='jpeg',quality=94,full_page=True)
            with Image.open(out/name) as shot:
                assert shot.width==1440 and shot.height>900
                assert shot.convert('L').getextrema()[0]<50
                size=shot.size
            log.append({'question':r['id'],'file':name,'url':args.base_url+'/?'+params,
                        'size':size,'api_answer_matched_log':True,'overflow':False})
            print('SCREENSHOT',name,size,flush=True)
        mobile=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1)
        mp=mobile.new_page();mp.goto(args.base_url,wait_until='networkidle')
        assert mp.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
        q=runs[0];params=urlencode({'q':q['question'],'period':'2025','mode':'evidence','k':8})
        mp.goto(args.base_url+'/?'+params,wait_until='networkidle')
        assert mp.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
        mp.screenshot(path=str(out/'11_移动端核验.jpg'),type='jpeg',quality=92,full_page=True)
        browser.close()
    (ROOT/'submission/screenshot_verification.json').write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8')
    sheet=Image.new('RGB',(2400,1780),'#edf2f1');d=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',32)
    d.text((40,20),'十题实际网页截图概览（各题完整长图另附）',font=font,fill='#1a302d')
    for i,r in enumerate(runs):
        x=40+(i%5)*470;y=95+(i//5)*825
        with Image.open(out/(r['id'].upper()+'.jpg')) as shot:
            crop=shot.crop((0,0,1440,min(2450,shot.height)))
            crop.thumbnail((445,750))
            sheet.paste(crop,(x,y+45))
        d.text((x,y),r['id'].upper()+f" · {r['answer_score']}/3",font=font,fill='#1a302d')
    sheet.save(ROOT/'submission/十题截图概览.jpg',quality=94,subsampling=0)


if __name__=='__main__':main()
