from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote

from common import INDEX, cosine, read_jsonl, tokens


class HybridSearch:
    def __init__(self, index_dir: Path = INDEX):
        self.docs = read_jsonl(index_dir / "docs.jsonl")
        self.by_id = {d['source_id']: d for d in self.docs}
        self.vectors = [x["vector"] for x in read_jsonl(index_dir / "vectors.jsonl")]
        self.term_rows = read_jsonl(index_dir / "terms.jsonl")
        self.idf = {x["term"]: x["idf"] for x in self.term_rows}
        self.postings = {x["term"]: x["postings"] for x in self.term_rows}
        self.avg_len = sum(len(tokens(d.get("text", ""))) for d in self.docs) / max(1, len(self.docs))
        self.counts = [Counter(tokens(d.get('text', ''))) for d in self.docs]

    def _query_vector(self, query: str) -> dict[str, float]:
        counts = Counter(tokens(query))
        vector = {term: (1 + math.log(freq)) * self.idf.get(term, 0.0) for term, freq in counts.items() if term in self.idf}
        norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
        return {term: value / norm for term, value in vector.items()}

    def vector_search(self, query: str, k: int = 8, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        qv = self._query_vector(query)
        scores = [(i, cosine(qv, vector)) for i, vector in enumerate(self.vectors) if allowed is None or i in allowed]
        return sorted(scores, key=lambda x: x[1], reverse=True)[:k]

    def bm25_search(self, query: str, k: int = 8, allowed: set[int] | None = None) -> list[tuple[int, float]]:
        qterms = set(tokens(query))
        scores = []
        for i, doc in enumerate(self.docs):
            if allowed is not None and i not in allowed:
                continue
            doc_terms = self.counts[i]
            length = sum(doc_terms.values()) or 1
            score = 0.0
            for term in qterms:
                freq = doc_terms.get(term, 0)
                if not freq:
                    continue
                idf = self.idf.get(term, 0.0)
                score += idf * (freq * 2.0) / (freq + 1.5 * (0.25 + 0.75 * length / max(1, self.avg_len)))
            if score:
                scores.append((i, score))
        return sorted(scores, key=lambda x: x[1], reverse=True)[:k]

    def _allowed(self, company: str = "", period: str = "") -> set[int]:
        names = [x.strip() for x in re.split(r"[|,，、]", company) if x.strip()]
        return {i for i, d in enumerate(self.docs)
                if (not names or any(name in d.get("company_name", "") for name in names))
                and (not period or period in d.get("report_period", ""))}

    @staticmethod
    def _keywords(query: str) -> str:
        """Deterministic keyword selection used by the PPT-style keyword+BM25 mode."""
        words = tokens(query)
        keep = [w for w in words if len(w) > 1 or re.match(r"[a-z0-9]", w)]
        return " ".join(dict.fromkeys(keep)) or query

    @staticmethod
    def _rewrite(query: str) -> str:
        """Rule-based query cleanup; this is not an LLM rewrite."""
        q = re.sub(r"(请|帮我|我想知道|朋友说|只想知道|告诉我|请问)", " ", query)
        q = re.sub(r"[，。！？、；：]+", " ", q)
        for old, new in {'归母净利润': '归属于上市公司股东的净利润',
                         '营收': '营业收入', '研发投入': '研发投入金额',
                         '海外': '境外 国外'}.items():
            q = q.replace(old, new)
        return re.sub(r"\s+", " ", q).strip() or query

    def search(self, query: str, k: int = 8, company: str = "", period: str = "", mode: str = "hybrid") -> list[dict]:
        allowed = self._allowed(company, period)
        mode = mode if mode in {"vector", "bm25", "keyword_bm25", "query_rewrite_vector", "hybrid", "evidence"} else "hybrid"
        search_query = self._rewrite(query) if mode == "query_rewrite_vector" else query
        if mode == "vector" or mode == "query_rewrite_vector":
            vector = self.vector_search(search_query, k, allowed)
            merged = {i: {"index": i, "vector_score": score, "bm25_score": 0.0, "vector_rank": rank + 1} for rank, (i, score) in enumerate(vector)}
            score_key = "vector_score"
        elif mode == "bm25":
            bm25 = self.bm25_search(query, k, allowed)
            merged = {i: {"index": i, "vector_score": 0.0, "bm25_score": score, "bm25_rank": rank + 1} for rank, (i, score) in enumerate(bm25)}
            score_key = "bm25_score"
        elif mode == "keyword_bm25":
            bm25 = self.bm25_search(self._keywords(query), k, allowed)
            merged = {i: {'index': i, 'vector_score': 0.0, 'bm25_score': score,
                          'bm25_rank': rank + 1} for rank, (i, score) in enumerate(bm25)}
            score_key = 'bm25_score'
        else:
            bm25_query = self._keywords(query) if mode == "keyword_bm25" else query
            vector = self.vector_search(query, max(k * 3, 12), allowed)
            bm25 = self.bm25_search(bm25_query, max(k * 3, 12), allowed)
            merged: dict[int, dict] = {}
            for rank, (i, score) in enumerate(vector):
                merged.setdefault(i, {"index": i, "vector_score": 0.0, "bm25_score": 0.0})["vector_score"] = score
                merged[i]["vector_rank"] = rank + 1
            for rank, (i, score) in enumerate(bm25):
                merged.setdefault(i, {"index": i, "vector_score": 0.0, "bm25_score": 0.0})["bm25_score"] = score
                merged[i]["bm25_rank"] = rank + 1
            score_key = "hybrid_score"
        if mode == "evidence":
            # Larger candidate pool plus source diversity approximates the PPT evidence-obligation workflow.
            ranked = sorted(merged.values(), key=lambda x: (x.get("vector_score", 0.0) + min(1.0, x.get("bm25_score", 0.0) / 10.0)), reverse=True)
            chosen, seen = [], set()
            for item in ranked:
                doc = self.docs[item["index"]]
                key = (doc.get("company_name"), doc.get("report_period"))
                if key not in seen:
                    chosen.append(item); seen.add(key)
                if len(chosen) >= k:
                    break
            merged = {x["index"]: x for x in chosen}
            score_key = "hybrid_score"
        items = []
        for item in merged.values():
            item["hybrid_score"] = 0.6 * item["vector_score"] + 0.4 * min(1.0, item["bm25_score"] / 10.0)
            doc = self.docs[item["index"]]
            item["score"] = item.get(score_key, item["hybrid_score"])
            items.append({**doc, **item})
        return sorted(items, key=lambda x: x["score"], reverse=True)[:k]


def compact_answer(query: str, results: list[dict]) -> str:
    if not results:
        return "材料未覆盖：当前索引没有召回可用证据。"
    lines = ["基于当前检索到的原始报告片段，可能相关的证据如下："]
    for item in results[:5]:
        text = re.sub(r"\s+", " ", item.get("text", "")).strip()
        if len(text) > 460:
            text = text[:460] + "..."
        lines.append(f"- {text} [{item['source_id']}；{item['company_name']}；{item['report_period']}；PDF第{item['pdf_page_start']}-{item['pdf_page_end']}页]")
    lines.append("\n请以引用原文为准；若要计算或比较，请补充报告期、合并/母公司口径和指标定义。")
    return "\n".join(lines)


def ask(query: str, company: str = "", period: str = "", k: int = 8, mode: str = "hybrid") -> dict:
    searcher = HybridSearch()
    results = searcher.search(query, k=k, company=company, period=period, mode=mode)
    return {"query": query, "mode": mode, "answer": compact_answer(query, results), "evidence": results}
