"""Deterministic local embeddings for Company V2 report QA.

Phase 6T-D must not depend on a paid external vector database or upload whole
reports. This service uses a local lexical hashing vector that is stable,
batchable, and good enough to combine with keyword retrieval for Chinese
financial report QA.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re


DEFAULT_EMBEDDING_DIM = 384
EMBEDDING_MODEL = "company-v2-hash-keyword"
EMBEDDING_VERSION = "company-v2-hash-keyword-v1"

FINANCIAL_TERMS = [
    "营业收入",
    "归属于上市公司股东的净利润",
    "净利润",
    "经营活动产生的现金流量净额",
    "现金流量净额",
    "经营活动",
    "主要风险",
    "风险",
    "前五名客户",
    "客户",
    "销售额占比",
    "主营业务",
    "主营产品",
    "未来利润保证",
    "利润保证",
    "单位",
    "万元",
    "亿元",
]


@dataclass(slots=True)
class EmbeddedText:
    text_hash: str
    embedding: list[float]
    embedding_model: str = EMBEDDING_MODEL
    embedding_version: str = EMBEDDING_VERSION


def stable_text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_retrieval_terms(text: str) -> list[str]:
    text = text or ""
    terms: list[str] = []
    for term in FINANCIAL_TERMS:
        if term in text:
            terms.append(term)
    terms.extend(re.findall(r"\d{4}年?|\d+(?:,\d{3})*(?:\.\d+)?%?|[A-Za-z][A-Za-z0-9_%-]+", text))
    chinese = re.sub(r"\s+", "", "".join(re.findall(r"[\u4e00-\u9fff]+", text)))
    for width in (2, 3, 4):
        for idx in range(0, max(0, len(chinese) - width + 1)):
            token = chinese[idx : idx + width]
            if token:
                terms.append(token)
    return terms


def embed_text(text: str, *, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    vector = [0.0] * dim
    for term in extract_retrieval_terms(text):
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        weight = 2.5 if term in FINANCIAL_TERMS else 1.0
        vector[bucket] += weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return max(0.0, sum(left[i] * right[i] for i in range(size)))


class CompanyV2ReportEmbeddingService:
    def __init__(self, dim: int = DEFAULT_EMBEDDING_DIM, batch_size: int = 32) -> None:
        self.dim = dim
        self.batch_size = batch_size
        self.embedding_model = EMBEDDING_MODEL
        self.embedding_version = EMBEDDING_VERSION

    def embed_batch(self, texts: list[str], *, existing_hashes: set[str] | None = None) -> tuple[list[EmbeddedText], int]:
        existing_hashes = existing_hashes or set()
        results: list[EmbeddedText] = []
        skipped = 0
        for text in texts:
            h = stable_text_hash(text)
            if h in existing_hashes:
                skipped += 1
                continue
            results.append(EmbeddedText(text_hash=h, embedding=embed_text(text, dim=self.dim)))
        return results, skipped


company_v2_report_embedding_service = CompanyV2ReportEmbeddingService()
