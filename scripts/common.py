from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable
from functools import lru_cache

import jieba

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
PARSED = DATA / "parsed"
INDEX = DATA / "index"

COMPANY_NAMES = {
    "300308": "\u4e2d\u9645\u65ed\u521b",
    "300502": "\u65b0\u6613\u76db",
    "300394": "\u5929\u5b5a\u901a\u4fe1",
    "002384": "\u4e1c\u5c71\u7cbe\u5bc6",
    "002475": "\u7acb\u8baf\u7cbe\u5bc6",
    "002281": "\u5149\u8fc5\u79d1\u6280",
    "603083": "\u5251\u6865\u79d1\u6280",
    "603052": "\u53ef\u5ddd\u79d1\u6280",
    "300548": "\u535a\u521b\u79d1\u6280",
    "300620": "\u5149\u5e93\u79d1\u6280",
    "688498": "\u6e90\u6770\u79d1\u6280",
    "688313": "\u4ed5\u4f73\u5149\u5b50",
    "301205": "\u8054\u7279\u79d1\u6280",
    "000988": "\u534e\u5de5\u79d1\u6280",
}

for folder in (RAW, PARSED, INDEX):
    folder.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(text: str) -> str:
    text = text.lower().replace("\u3000", " ")
    text = re.sub(r"[\r\n\t]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=16000)
def tokens(text: str) -> list[str]:
    text = normalize(text)
    words = [w.strip() for w in jieba.lcut(text, cut_all=False)
             if re.search(r"[a-z0-9\u4e00-\u9fff]", w)]
    stop = {"的", "了", "和", "与", "及", "在", "是", "为", "对", "本", "期", "公司", "报告"}
    return [w for w in words if w not in stop]


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def safe_filename(value: str) -> str:
    return re.sub(r"[^\w\-.\u4e00-\u9fff]+", "_", value).strip("_")[:180]
