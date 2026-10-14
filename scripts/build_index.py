from __future__ import annotations

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import INDEX, PARSED, read_jsonl, tokens, write_jsonl


def main() -> None:
    docs = read_jsonl(PARSED / "chunks.jsonl")
    if not docs:
        raise SystemExit("chunks.jsonl 为空；请先运行 parse_reports.py")
    postings: dict[str, list[int]] = defaultdict(list)
    term_counts: list[dict[str, int]] = []
    for i, doc in enumerate(docs):
        counts = Counter(tokens(doc.get("text", "")))
        term_counts.append(dict(counts))
        for term in counts:
            postings[term].append(i)
    n = len(docs)
    idf = {term: math.log(1 + (n - len(ids) + 0.5) / (len(ids) + 0.5)) for term, ids in postings.items()}
    vectors: list[dict[str, float]] = []
    for counts in term_counts:
        vector = {term: (1 + math.log(freq)) * idf[term] for term, freq in counts.items()}
        norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
        vectors.append({term: value / norm for term, value in vector.items()})
    write_jsonl(INDEX / "docs.jsonl", docs)
    write_jsonl(INDEX / "vectors.jsonl", [{"vector": vector} for vector in vectors])
    write_jsonl(INDEX / "terms.jsonl", [{"term": term, "idf": value, "postings": postings[term]} for term, value in idf.items()])
    (INDEX / "stats.json").write_text(__import__("json").dumps({"documents": n, "avg_doc_len": sum(sum(x.values()) for x in term_counts) / n, "algorithm": "TF-IDF cosine + BM25"}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"INDEXED documents={n} terms={len(idf)}")


if __name__ == "__main__":
    main()
