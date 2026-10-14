# 光模块行业财报问答知识库

本次补交于2026-10-13完成。正式来源为巨潮资讯网披露的14家公司、28份报告全文：2025年度年报与2026年半年报各14份，共5,196页。证券代码匹配公司；博创科技的报告披露名称为长芯博创。十题实测统一使用2025年度，避免年报与半年报混比。

## 先查看实测材料

- `submission/一页结论.pdf`：单页总结；另有同内容JPG。
- `submission/screenshots/Q01.jpg`至`Q10.jpg`：真实问答网页完整截图，包含答案、评测和出处。Q01展开了实际原文块。
- `evaluation/final_10_questions_answers.md`：默认补证模式十题的参考答案、实际答案、召回块、得分、错因。
- `evaluation/六方法真实逐题答案与评分.md`：60次运行的全部答案和评测。
- `evaluation/final_results.jsonl`：完整答案、原文、块ID、检索/读取轨迹、核验明细；原始未评分运行另存`run_results.jsonl`。
- `evaluation/final_10_questions_scores.csv`：十题成绩；`retrieval_metrics.csv`与`answer_metrics.csv`分别保存召回和答案指标。
- `evaluation/panorama_by_company.md`：Q10的14家公司×4项逐项证据，不以行业综述替代公司取证。
- `data/source_verification.csv`：正式披露页、附件地址、SHA256、封面核验和全文页数；本地再次校验见`data/local_source_audit.json`。

## 实测结论

默认“按公司与义务补证”总分28/30：8题完整正确；Q05与Q10各2分，具体不足已保留。前五种固定Top8方法总分依次为9、14、16、11、10/30。收入分类题Q04六种方法均3分；去噪题Q07关键词BM25与规则精炼TF-IDF均3分。固定Top8在计算和全景题上容易遗漏完整表格或公司。

这些是Codex依据正式PDF原页的核验和可复现检查，不是教师评分或人工盲评，也不保证再次批改通过。0–3分规则、参考事实与逐项依据单独保存；运行时不会读取参考答案。

## 技术流程与边界

1. 正式报告全文核验、保存SHA256与全部页码。
2. PyMuPDF逐页解析正文，逐页识别表格，保留原始单元格、表格边界、逻辑行列、公司、章节和PDF物理页码。扫描页及复杂跨页表格仍可能需要OCR或人工核对。
3. jieba分词，建立TF-IDF词项向量与独立BM25索引。
4. 六种检索模式：TF-IDF、BM25、规则关键词BM25、规则精炼TF-IDF、两路混合、按公司与义务补证。
5. 输出原表指标、Decimal计算或原文摘录，保留来源；不同收入分类不作同口径排名。拒答/缺据表示本次证据不足，不表示公司没有该业务。
6. 召回按公司×义务的参考页命中计量，答案另按事实、完整性、口径和出处评价。参考页清单不是穷尽相关集，因此不冒称标准Recall/Precision。
7. 初始Top8与补证后的读取量分开。补证使用额外公司导航与表格定位，平均67.1块，Q10为441块；不能宣称同预算算法全面优胜。

TF-IDF是词项向量，规则精炼不是大模型改写，补证流程不是自治Agent。本版没有接入语义embedding或LLM。答复采用规则路由、原文摘录及表格计算，支持的题型见固定十题；并非通用财务分析聊天系统。

Q05阶段抽取仍漏识别“预研”，并有收入引文与阶段标签不一致的问题；Q10部分需求仅为行业背景、表格串读，立讯风险缺直接证据。这些已计入实际评分。

## 本地运行

需要Python 3.11以上。2026-10-14已恢复完整材料，并补充data/runtime/的三份压缩索引。首次启动会自动解压并核对SHA256，无需先解析全部PDF。大型未压缩索引仍不上传GitHub。

```powershell
python -m pip install -r requirements.txt
python -B -X utf8 scripts/verify_upload.py
python -X utf8 app.py --port 8765
```

安装依赖后也可双击“启动知识库.cmd”。“检查文件完整性.cmd”按上传清单逐文件核对路径、大小与SHA256；修改代码后需要重新生成清单。

仅在需要从原始报告重建索引时执行下面的完整流程：

本次实际运行的直接依赖版本保存在requirements.lock.txt；按原环境复现时使用该锁定清单。requirements.txt给出可兼容的最低版本。

```powershell
python -m pip install -r requirements.txt
python -X utf8 scripts/parse_verified_reports.py
python -X utf8 scripts/build_index.py
python -X utf8 app.py --port 8765
```

打开 http://127.0.0.1:8765/ 。服务需要保持运行；关闭进程或关机后本地网页会停止。

没有PDF时运行`python -X utf8 scripts/verify_sources.py`，从正式披露站点核验并下载全文；它会保存变更前的原件。此步骤需要网络。完整解析约数分钟，首次查询还会加载全部索引。

## 复现评测与图件

```powershell
python -X utf8 scripts/run_homework_evaluation.py
python -X utf8 scripts/review_homework.py
python -X utf8 scripts/render_submission.py
python -X utf8 scripts/capture_submission.py
python -X utf8 scripts/audit_submission.py
```

截图脚本使用本机Edge；其他系统须安装Playwright支持的Chrome。结论图默认使用Windows微软雅黑，可通过`KB_CJK_FONT`与`KB_CJK_BOLD_FONT`指定中文字体。重复评测会覆盖生成的评测文件，先保留需要的旧日志。

## GitHub补交

使用单独整理的“补交_GitHub上传文件”目录，保留`scripts/`、`data/`、`evaluation/`、`submission/`层级。按同名文件更新现有仓库；不要把目录全部展开成根目录文件。每份PDF、日志、JPG均低于GitHub网页单文件25MB门槛。

`data/parsed/*.jsonl`和`data/index/*.jsonl`是可重建的大文件，已在.gitignore排除；data/runtime/中的.gz文件和manifest.json需要上传，供首次运行自动恢复索引。也不上传日志、缓存、history或旧版评测模板。旧图和旧记录仅在本地history保留，不作为本次结论。具体文件见`submission/补交说明.md`。
