"""Phase 6T-J1: checkpoint ok=true must NOT skip index when DB has no active doc."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path


def _load_prepare():
    path = Path(__file__).resolve().parents[2] / "scripts" / "company_v2_financial_fusion_stage2_prepare.py"
    name = "company_v2_financial_fusion_stage2_prepare_tj1"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module  # dataclass definitions need the module registered
    spec.loader.exec_module(module)
    return module


def _checkpoint(tmp_path: Path, ok: bool) -> Path:
    path = tmp_path / "cp.json"
    path.write_text(
        json.dumps(
            {
                "step": "index",
                "symbols": {"600519": {"index": {"ok": ok, "timeout": False, "report_id": 2, "symbol": "600519", "status": "indexed"}}},
            }
        ),
        encoding="utf-8",
    )
    return path


def _run(prepare, tmp_path: Path, monkeypatch, *, persisted: bool):
    calls: list[str] = []

    async def fake_run_symbol_step(symbol, step, timeout):
        calls.append(symbol)

        class R:
            def to_dict(self):
                return {"ok": True, "timeout": False, "symbol": symbol, "step": step, "report_id": 2, "status": "indexed"}

        return R()

    monkeypatch.setattr(prepare, "_run_symbol_step", fake_run_symbol_step)
    monkeypatch.setattr(
        prepare.company_v2_report_rag_index_service.repository.__class__,
        "get_document",
        lambda self, rid: object() if persisted else None,
    )
    # keep artifacts inside tmp_path
    monkeypatch.setattr(prepare, "STAGE2_JSON", tmp_path / "s.json")
    monkeypatch.setattr(prepare, "STAGE2_MD", tmp_path / "s.md")
    monkeypatch.setattr(prepare, "STAGE2_MULTI_JSON", tmp_path / "m.json")
    payload = asyncio.run(
        prepare.run_stage2_prepare("index", ["600519"], 30.0, _checkpoint(tmp_path, ok=True), resume=True)
    )
    return calls, payload


def test_checkpoint_ok_but_db_missing_forces_reindex(tmp_path, monkeypatch):
    prepare = _load_prepare()
    calls, payload = _run(prepare, tmp_path, monkeypatch, persisted=False)
    assert calls == ["600519"]  # re-indexed, not skipped
    assert payload["results"][0].get("resume_note") == "PERSISTENCE_MISSING_REINDEX_REQUIRED"


def test_checkpoint_ok_and_db_present_skips(tmp_path, monkeypatch):
    prepare = _load_prepare()
    calls, payload = _run(prepare, tmp_path, monkeypatch, persisted=True)
    assert calls == []  # persisted active document → checkpoint skip is safe
    assert payload["results"][0]["ok"] is True
