"""Phase 6T-J1: independent-process RAG persistence smoke.

Reads ONLY from the database-backed repository. This script must never:
- create or refresh an index;
- use the memory repository backend;
- fall back on any in-process object from the indexing run.

Usage:
    cd backend && .venv/bin/python scripts/company_v2_rag_persistence_smoke.py \
        [--report-ids 2,3,4,5] [--out-json PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_CHUNKS = {2: 211, 3: 299, 4: 311, 5: 396}
QUERIES_DEFAULT = ["营业收入", "净利润", "经营活动产生的现金流量净额", "资产总计"]
QUERIES_BANK = ["营业收入", "净利润", "经营活动产生的现金流量净额", "吸收存款"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Company V2 RAG persistence smoke (DB-only, no indexing)")
    parser.add_argument("--report-ids", default="2,3,4,5")
    parser.add_argument("--out-json", default=str(ROOT / "docs" / "artifacts" / "company_v2_rag_persistence_smoke_phase6tj1.json"))
    args = parser.parse_args()

    from app.services.company_v2_report_rag_repository_factory import (
        get_company_v2_report_rag_repository,
        repository_status,
    )

    status = repository_status()
    if status["repository_backend"] != "database" or not status["persistent"]:
        print(json.dumps({"ok": False, "error_code": "MEMORY_BACKEND_FORBIDDEN", "status": status}))
        return 2

    repo = get_company_v2_report_rag_repository()
    from app.services.company_v2_report_rag_retriever import CompanyV2ReportRagRetriever

    retriever = CompanyV2ReportRagRetriever(repo)

    report_ids = [int(x) for x in args.report_ids.split(",") if x.strip()]
    results: list[dict[str, Any]] = []
    all_ok = True
    for report_id in report_ids:
        doc = repo.get_document(report_id)
        entry: dict[str, Any] = {
            "report_id": report_id,
            "repository_backend": status["repository_backend"],
            "persistent": status["persistent"],
        }
        if doc is None:
            entry.update({"retrieved_after_restart": False, "error_code": "ACTIVE_DOCUMENT_MISSING"})
            all_ok = False
            results.append(entry)
            continue
        persisted = repo.count_chunks(report_id)
        expected = EXPECTED_CHUNKS.get(report_id)
        queries = QUERIES_BANK if doc.symbol == "000001" else QUERIES_DEFAULT
        retrievals = []
        for q in queries:
            res = retriever.retrieve(report_id=report_id, question=q, symbol=doc.symbol, report_year=doc.report_year)
            chunks = res.get("chunks") or []
            top_page = chunks[0].get("page_start") if chunks else None
            retrievals.append(
                {
                    "query": q,
                    "evidence_found": bool(chunks),
                    "retrieved": len(chunks),
                    "top_page": top_page,
                    "citation_valid": bool(chunks) and 1 <= int(top_page or 0) <= doc.page_count,
                    "report_isolation": all(int(c.get("report_id", report_id)) == report_id for c in chunks),
                    "cross_report_leakage_detected": bool(res.get("cross_report_leakage_detected")),
                }
            )
        entry.update(
            {
                "rag_document_id": doc.id,
                "symbol": doc.symbol,
                "generation": doc.index_generation,
                "persisted_chunk_count": persisted,
                "expected_chunk_count": expected,
                "chunk_count_match": expected is None or persisted == expected,
                "retrieved_after_restart": True,
                "symbol_isolation": all(r["report_isolation"] for r in retrievals),
                "retrievals": retrievals,
            }
        )
        if not entry["chunk_count_match"] or not all(r["evidence_found"] and r["citation_valid"] for r in retrievals):
            all_ok = False
        results.append(entry)

    payload = {
        "ok": all_ok,
        "repository_backend": status["repository_backend"],
        "persistent": status["persistent"],
        "results": results,
        "total_persisted_chunks": sum(r.get("persisted_chunk_count") or 0 for r in results),
    }
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("ok", "repository_backend", "persistent", "total_persisted_chunks")}))
    for r in results:
        print(
            r["report_id"],
            r.get("symbol"),
            "doc=", r.get("rag_document_id"),
            "gen=", r.get("generation"),
            "chunks=", r.get("persisted_chunk_count"), "/", r.get("expected_chunk_count"),
            "restart_read=", r.get("retrieved_after_restart"),
            "evidence=", sum(1 for x in r.get("retrievals", []) if x["evidence_found"]), "/", len(r.get("retrievals", [])),
        )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
