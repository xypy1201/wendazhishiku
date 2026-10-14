from __future__ import annotations

import json
import gzip
import hashlib
import shutil
from pathlib import Path

from common import ROOT

SCRIPTS=['common.py','qa_engine.py','evidence_qa.py','verify_sources.py','parse_verified_reports.py',
         'build_index.py','run_homework_evaluation.py','review_homework.py','render_submission.py',
         'capture_submission.py','audit_submission.py','package_submission.py']
SCRIPTS += ['prepare_runtime.py', 'verify_upload.py']
EVALUATION=['questions.jsonl','reference_answers.json','panorama_reference_pages.json',
            'run_results.jsonl','final_results.jsonl','final_10_questions_answers.md',
            'final_10_questions_scores.csv','all_methods_scores.csv','retrieval_metrics.csv',
            'answer_metrics.csv','item_review.csv','summary.json','六方法真实逐题答案与评分.md',
            'panorama_by_company.md']


def checksum(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def main():
    dest=ROOT.parent/'补交_GitHub上传文件';dest.mkdir(exist_ok=True)
    if dest.resolve()==ROOT.resolve():
        raise SystemExit('当前已是上传材料目录；请在原知识库目录整理材料。')
    runtime = ROOT/'data/runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    archives = []
    for name in ('docs.jsonl', 'vectors.jsonl', 'terms.jsonl'):
        source = ROOT/'data/index'/name
        packed = runtime/(name+'.gz')
        with source.open('rb') as incoming, packed.open('wb') as raw:
            with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as outgoing:
                shutil.copyfileobj(incoming, outgoing)
        if packed.stat().st_size >= 25*1024**2:
            raise ValueError('Compressed runtime file exceeds web limit: '+name)
        archives.append({'name':name, 'bytes':source.stat().st_size,
                         'sha256':checksum(source),
                         'archive':packed.name, 'archive_bytes':packed.stat().st_size,
                         'archive_sha256':checksum(packed)})
    (runtime/'manifest.json').write_text(json.dumps({'files':archives},indent=2),encoding='utf-8')
    files=[ROOT/n for n in ['app.py','README.md','requirements.txt','requirements.lock.txt','.gitignore','启动知识库.cmd','检查文件完整性.cmd','一页结论.md']]
    files += [ROOT/'scripts'/n for n in SCRIPTS]
    files += [ROOT/'evaluation'/n for n in EVALUATION]
    files += [ROOT/'data'/n for n in ['company_registry.csv','company_profiles.json','report_manifest.csv',
                                    'source_verification.csv','source_verification.json','local_source_audit.json',
                                    '来源清单与全文核验.md','parsed/parse_summary.json','index/stats.json']]
    files += list((ROOT/'data/raw').glob('*.pdf'))
    files += list(runtime.iterdir())
    files += [p for p in (ROOT/'submission').rglob('*') if p.is_file()]
    records=[]
    for source in files:
        assert source.exists(),source
        assert source.stat().st_size < 25*1024**2,source
        relative=source.relative_to(ROOT);target=dest/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        with source.open('rb') as handle:
            file_hash=hashlib.file_digest(handle,'sha256').hexdigest()
        records.append({'path':relative.as_posix(),'bytes':source.stat().st_size,'sha256':file_hash})
    for cache in (dest/'scripts/__pycache__',dest/'__pycache__'):
        if cache.exists() and cache.resolve().is_relative_to(dest.resolve()):
            shutil.rmtree(cache)
    (dest/'submission/upload_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    # Keep previous plots/templates available locally, outside the upload set.
    old=ROOT/'history/pre_resubmission';old.mkdir(parents=True,exist_ok=True)
    legacy=[p for p in (ROOT/'evaluation').iterdir() if p.is_file() and p.name not in EVALUATION]
    legacy += [p for p in ROOT.glob('一页结论_评测总结图.*')]
    for p in legacy:
        target=old/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copy2(p,target)
    (old/'README.txt').write_text('这些是2026-10-13补交前的旧版记录与图件，仅供历史追溯。当前提交以evaluation/final_results.jsonl及submission/结论和实际截图为准。旧数据未参与新版统计。',encoding='utf-8')
    print('UPLOAD DIRECTORY',dest)
    print('FILES',len(records),'MAX_MB',round(max(x['bytes'] for x in records)/1024**2,2),
          'TOTAL_MB',round(sum(x['bytes'] for x in records)/1024**2,2))


if __name__=='__main__':main()
