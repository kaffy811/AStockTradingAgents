#!/usr/bin/env python3
"""
scripts/debug_free_mode_data_sources.py — Free Mode 全数据源诊断脚本（Phase 6N）

对指定股票逐项测试数据源，而不是只看前端结果。
覆盖：BaoStock 登录 + 6 张财务表、AkShare 3 接口、PDF 发现、DB 状态、
      前端可渲染性评分。

输出：
  docs/artifacts/free_mode_data_source_debug.json   — 全量结构化结果
  docs/artifacts/free_mode_data_source_debug.csv    — 便于 Excel/Sheets 浏览

用法：
    uv run python scripts/debug_free_mode_data_sources.py --symbols 600519,000725,601686
    uv run python scripts/debug_free_mode_data_sources.py --symbols 600519 --years 2025,2024,2023
    uv run python scripts/debug_free_mode_data_sources.py --symbols 600519 --dry-run
    uv run python scripts/debug_free_mode_data_sources.py --symbols 600519 --out-dir /tmp/debug
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# ── 添加 backend/ 到 sys.path ─────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ── 常量 ─────────────────────────────────────────────────────────────────────

# BaoStock 财务方法列表 (module_key, method_name, description)
_BAOSTOCK_FINANCIAL_PROBES: list[tuple[str, str, str]] = [
    ("profit",     "get_profit_data",     "盈利能力（ROE/净利率/毛利率）"),
    ("growth",     "get_growth_data",     "成长能力（YOY净利/营收/净资产）"),
    ("balance",    "get_balance_data",    "偿债能力（流动比率/速动比率）"),
    ("operation",  "get_operation_data",  "营运能力（应收账款/存货周转）"),
    ("cash_flow",  "get_cash_flow_data",  "现金流量（CFO/净利润/营收比）"),
    ("dupont",     "get_dupont_data",     "杜邦分析（ROE分解）"),
]

# 每个 BaoStock module 的关键可渲染字段（至少有 1 个非 None 才算可渲染）
_BAOSTOCK_RENDERABLE_FIELDS: dict[str, list[str]] = {
    "profit":    ["roe_avg", "net_margin", "gross_margin"],
    "growth":    ["yoy_ni", "yoy_equity"],
    "balance":   ["current_ratio", "quick_ratio", "liability_to_asset"],
    "operation": ["nr_turn_ratio", "inv_turn_ratio", "asset_turn_ratio"],
    "cash_flow": ["cfo_to_or", "cfo_to_np"],
    "dupont":    ["dupont_roe", "dupont_at", "dupont_am"],
}

# AkShare 探针
_AKSHARE_PROBES: list[tuple[str, str]] = [
    ("financial_abstract", "同花顺财务摘要"),
    ("cash_flow",          "同花顺现金流"),
    ("real_time_quote",    "实时行情快照"),
]

# PDF 发现来源域名（用于 DNS 检查）
_PDF_DOMAINS: list[str] = [
    "static.cninfo.com.cn",
    "www.sse.com.cn",
    "disclosure.szse.cn",
]


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _to_ts_code(symbol: str) -> str:
    """将纯 6 位代码转为 ts_code 格式（600519 → 600519.SH）。"""
    symbol = symbol.strip()
    if "." in symbol:
        return symbol
    if symbol.startswith(("6", "5", "9")):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _to_6digit(symbol: str) -> str:
    """将 ts_code 转为 6 位纯代码（600519.SH → 600519）。"""
    if "." in symbol:
        return symbol.split(".")[0]
    return symbol


def _non_null_fields(row: dict, skip: set[str] | None = None) -> list[str]:
    """返回 row 中值非 None 的字段名。"""
    skip = skip or {"ts_code", "pub_date", "stat_date"}
    return [k for k, v in row.items() if v is not None and k not in skip]


def _renderable(rows: list[dict], key_fields: list[str]) -> bool:
    """至少 1 行中有至少 1 个 key_field 非 None。"""
    for row in rows:
        if any(row.get(f) is not None for f in key_fields):
            return True
    return False


# ── BaoStock 探针 ─────────────────────────────────────────────────────────────

async def _probe_baostock_login() -> dict:
    """测试 BaoStock 登录是否成功。"""
    t0 = time.time()
    try:
        import baostock as bs
        import io

        def _do():
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
            try:
                lg = bs.login()
                code = lg.error_code
                bs.logout()
                return code
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

        error_code = await asyncio.to_thread(_do)
        ok = error_code == "0"
        return {
            "probe":      "baostock_login",
            "status":     "ok" if ok else "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      None if ok else f"error_code={error_code}",
            "detail":     {},
        }
    except ImportError:
        return {
            "probe":      "baostock_login",
            "status":     "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      "baostock 未安装（pip install baostock）",
            "detail":     {},
        }
    except Exception as exc:
        return {
            "probe":      "baostock_login",
            "status":     "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"{type(exc).__name__}: {exc}",
            "detail":     {},
        }


async def _probe_baostock_table(
    ts_code: str,
    module_key: str,
    method_name: str,
) -> dict:
    """测试单张 BaoStock 财务表。"""
    t0 = time.time()
    try:
        from app.datasource.baostock_client import BaoStockClient
        client = BaoStockClient()
        method = getattr(client, method_name)
        rows: list[dict] = await method(ts_code=ts_code)
        elapsed_ms = round((time.time() - t0) * 1000)

        rows_count = len(rows) if rows else 0
        first_row_fields = _non_null_fields(rows[0]) if rows else []
        key_fields = _BAOSTOCK_RENDERABLE_FIELDS.get(module_key, [])
        renderable = _renderable(rows, key_fields) if rows else False

        # 检查字段覆盖率：期望字段 vs 实际非 null 字段
        missing_key_fields = [f for f in key_fields if not any(
            r.get(f) is not None for r in rows
        )] if rows else key_fields

        return {
            "probe":              f"baostock_{module_key}",
            "status":             "ok" if rows_count > 0 else "empty",
            "latency_ms":         elapsed_ms,
            "error":              None,
            "detail": {
                "rows_count":         rows_count,
                "non_null_fields":    first_row_fields[:8],
                "renderable":         renderable,
                "missing_key_fields": missing_key_fields,
                "provider":           "baostock",
            },
        }
    except Exception as exc:
        return {
            "probe":      f"baostock_{module_key}",
            "status":     "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"{type(exc).__name__}: {exc}",
            "detail":     {"rows_count": 0, "renderable": False, "provider": "baostock"},
        }


def _timeout_probe(probe_name: str, timeout_seconds: float, provider: str) -> dict:
    return {
        "probe": probe_name,
        "status": "timeout",
        "latency_ms": int(timeout_seconds * 1000),
        "error": f"PROVIDER_TIMEOUT: exceeded {timeout_seconds:g}s",
        "detail": {"rows_count": 0, "renderable": False, "provider": provider},
    }


async def _run_probe_with_progress(
    symbol_6: str,
    provider: str,
    probe_name: str,
    description: str,
    timeout_seconds: float,
    coro_factory,
) -> dict:
    print(f"[PROVIDER] {symbol_6} {provider} {description} start timeout={timeout_seconds:g}s", flush=True)
    t0 = time.time()
    try:
        result = await asyncio.wait_for(coro_factory(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        result = _timeout_probe(probe_name, timeout_seconds, provider)
    except Exception as exc:
        result = {
            "probe": probe_name,
            "status": "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error": f"{type(exc).__name__}: {exc}",
            "detail": {"rows_count": 0, "renderable": False, "provider": provider},
        }

    latency_ms = result.get("latency_ms", round((time.time() - t0) * 1000))
    detail = result.get("detail") or {}
    rows_count = detail.get("rows_count", detail.get("count", detail.get("chunk_count", detail.get("candidates", 0))))
    status = result.get("status", "failed")
    tag = {
        "ok": "OK",
        "empty": "EMPTY",
        "timeout": "TIMEOUT",
        "failed": "ERROR",
        "disabled": "ERROR",
    }.get(status, "ERROR")
    print(f"[{tag}] {symbol_6} {provider} {probe_name} rows_count={rows_count} latency_ms={latency_ms}", flush=True)
    if result.get("error"):
        print(f"  ERR: {result['error']}", flush=True)
    return result


# ── AkShare 探针 ──────────────────────────────────────────────────────────────

async def _probe_akshare_financial_abstract(symbol_6: str) -> dict:
    """测试 AkShare 同花顺财务摘要接口。"""
    t0 = time.time()
    try:
        from app.datasource.akshare_client import akshare_fs_client, AkShareDisabledError
        result = await akshare_fs_client.get_financial_abstract(symbol=symbol_6)
        elapsed_ms = round((time.time() - t0) * 1000)
        rows_count = 0
        if isinstance(result, dict):
            data = result.get("data") or result
            for field in ("rows", "series", "periods", "records"):
                v = data.get(field) if isinstance(data, dict) else None
                if isinstance(v, list):
                    rows_count = len(v)
                    break
        return {
            "probe":      "akshare_financial_abstract",
            "status":     "ok" if rows_count > 0 else "empty",
            "latency_ms": elapsed_ms,
            "error":      None,
            "detail":     {"rows_count": rows_count, "provider": "akshare"},
        }
    except Exception as exc:
        status = "disabled" if "disabled" in str(exc).lower() or "禁用" in str(exc) else "failed"
        return {
            "probe":      "akshare_financial_abstract",
            "status":     status,
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"{type(exc).__name__}: {exc}",
            "detail":     {"rows_count": 0, "provider": "akshare"},
        }


async def _probe_akshare_cash_flow(symbol_6: str) -> dict:
    """测试 AkShare 同花顺现金流接口。"""
    t0 = time.time()
    try:
        from app.datasource.akshare_client import akshare_fs_client
        result = await akshare_fs_client.get_cash_flow(symbol=symbol_6)
        elapsed_ms = round((time.time() - t0) * 1000)
        rows_count = 0
        if isinstance(result, dict):
            data = result.get("data") or result
            for field in ("rows", "series", "periods", "records"):
                v = data.get(field) if isinstance(data, dict) else None
                if isinstance(v, list):
                    rows_count = len(v)
                    break
        return {
            "probe":      "akshare_cash_flow",
            "status":     "ok" if rows_count > 0 else "empty",
            "latency_ms": elapsed_ms,
            "error":      None,
            "detail":     {"rows_count": rows_count, "provider": "akshare"},
        }
    except Exception as exc:
        status = "disabled" if "disabled" in str(exc).lower() or "禁用" in str(exc) else "failed"
        return {
            "probe":      "akshare_cash_flow",
            "status":     status,
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"{type(exc).__name__}: {exc}",
            "detail":     {"rows_count": 0, "provider": "akshare"},
        }


async def _probe_akshare_quote(symbol_6: str) -> dict:
    """测试 AkShare 实时行情接口。"""
    t0 = time.time()
    try:
        from app.datasource.akshare_client import akshare_fs_client
        result = await akshare_fs_client.get_real_time_quote(symbol=symbol_6, market="CN")
        elapsed_ms = round((time.time() - t0) * 1000)
        close = result.get("close") if isinstance(result, dict) else None
        return {
            "probe":      "akshare_real_time_quote",
            "status":     "ok" if close is not None else "empty",
            "latency_ms": elapsed_ms,
            "error":      None,
            "detail":     {
                "close":    close,
                "provider": result.get("source", "akshare") if isinstance(result, dict) else "akshare",
            },
        }
    except Exception as exc:
        status = "disabled" if "disabled" in str(exc).lower() or "禁用" in str(exc) else "failed"
        return {
            "probe":      "akshare_real_time_quote",
            "status":     status,
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"{type(exc).__name__}: {exc}",
            "detail":     {"close": None, "provider": "akshare"},
        }


# ── PDF 探针 ──────────────────────────────────────────────────────────────────

def _probe_dns(domain: str) -> dict:
    """测试 DNS 解析（不发起 HTTP 请求）。"""
    import socket
    t0 = time.time()
    try:
        ip = socket.gethostbyname(domain)
        return {
            "probe":      f"dns_{domain}",
            "status":     "ok",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      None,
            "detail":     {"ip": ip},
        }
    except socket.gaierror as exc:
        return {
            "probe":      f"dns_{domain}",
            "status":     "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"DNS failed: {exc}",
            "detail":     {},
        }


async def _probe_pdf_discovery(ts_code: str, years: list[int]) -> list[dict]:
    """
    对每个年份测试 PDF 年报发现（调用 report_discovery_agent）。
    返回每年一个 probe result。
    """
    results = []
    try:
        from app.agents.report_discovery_agent import report_discovery_agent
    except Exception as exc:
        for yr in years:
            results.append({
                "probe":      f"pdf_discovery_{yr}",
                "status":     "failed",
                "latency_ms": 0,
                "error":      f"import failed: {exc}",
                "detail":     {"year": yr, "candidates": 0},
            })
        return results

    symbol_6 = _to_6digit(ts_code)
    company_name = symbol_6  # 发现代理接受 symbol 作为公司名 fallback

    for yr in years:
        t0 = time.time()
        try:
            res = await asyncio.wait_for(
                report_discovery_agent.discover_latest(
                    stock_code=ts_code,
                    company_name=company_name,
                    report_year=yr,
                ),
                timeout=15.0,
            )
            elapsed_ms = round((time.time() - t0) * 1000)
            candidates = res.get("candidates") or []
            total = res.get("total_found") or len(candidates)
            errors = res.get("errors") or []
            sources = res.get("sources_searched") or []
            results.append({
                "probe":      f"pdf_discovery_{yr}",
                "status":     "ok" if total > 0 else "empty",
                "latency_ms": elapsed_ms,
                "error":      "; ".join(errors) if errors else None,
                "detail": {
                    "year":            yr,
                    "candidates":      total,
                    "sources_tried":   sources,
                    "top_title":       candidates[0].get("title") if candidates else None,
                    "top_confidence":  candidates[0].get("confidence") if candidates else None,
                },
            })
        except asyncio.TimeoutError:
            results.append({
                "probe":      f"pdf_discovery_{yr}",
                "status":     "failed",
                "latency_ms": 15000,
                "error":      "timeout (15s)",
                "detail":     {"year": yr, "candidates": 0},
            })
        except Exception as exc:
            results.append({
                "probe":      f"pdf_discovery_{yr}",
                "status":     "failed",
                "latency_ms": round((time.time() - t0) * 1000),
                "error":      f"{type(exc).__name__}: {exc}",
                "detail":     {"year": yr, "candidates": 0},
            })

    return results


# ── DB 探针 ───────────────────────────────────────────────────────────────────

async def _probe_db_report_documents(ts_code: str) -> dict:
    """检查 DB 中是否有该股票的 report_documents 记录。"""
    t0 = time.time()
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy import text
        from app.core.config import settings

        engine = create_async_engine(str(settings.database_url), echo=False)
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text("SELECT COUNT(*), MAX(created_at) FROM report_documents WHERE ts_code = :ts_code"),
                {"ts_code": ts_code},
            )
            row = result.one()
            count = row[0] or 0
            latest_at = str(row[1]) if row[1] else None

        await engine.dispose()
        return {
            "probe":      "db_report_documents",
            "status":     "ok" if count > 0 else "empty",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      None,
            "detail":     {"count": count, "latest_discovered_at": latest_at},
        }
    except Exception as exc:
        return {
            "probe":      "db_report_documents",
            "status":     "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"{type(exc).__name__}: {exc}",
            "detail":     {"count": 0, "latest_discovered_at": None},
        }


async def _probe_db_report_chunks(ts_code: str) -> dict:
    """检查 DB 中是否有该股票的 report_chunks（RAG 索引状态）。"""
    t0 = time.time()
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy import text
        from app.core.config import settings

        engine = create_async_engine(str(settings.database_url), echo=False)
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text("""
                    SELECT COUNT(rc.id), COUNT(DISTINCT rd.ts_code)
                    FROM report_chunks rc
                    JOIN report_documents rd ON rc.report_id = rd.id
                    WHERE rd.ts_code = :ts_code
                """),
                {"ts_code": ts_code},
            )
            row = result.one()
            chunk_count = row[0] or 0
            doc_count = row[1] or 0

        await engine.dispose()
        return {
            "probe":      "db_report_chunks",
            "status":     "ok" if chunk_count > 0 else "empty",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      None,
            "detail":     {"chunk_count": chunk_count, "indexed_docs": doc_count},
        }
    except Exception as exc:
        return {
            "probe":      "db_report_chunks",
            "status":     "failed",
            "latency_ms": round((time.time() - t0) * 1000),
            "error":      f"{type(exc).__name__}: {exc}",
            "detail":     {"chunk_count": 0, "indexed_docs": 0},
        }


# ── 渲染能力评分 ──────────────────────────────────────────────────────────────

def _compute_renderability(probes: list[dict]) -> dict:
    """
    根据探针结果计算前端渲染能力评分。

    返回：
      renderable_modules  : 可渲染 BaoStock 模块数（0-6）
      total_bs_modules    : 探针的 BaoStock 模块总数
      akshare_ok          : AkShare quote 是否成功
      pdf_any_year_found  : 是否任意年份找到 PDF
      rag_ready           : DB chunks > 0
      score               : 综合评分 0–100
    """
    bs_probes = [p for p in probes if p["probe"].startswith("baostock_") and p["probe"] != "baostock_login"]
    bs_renderable = sum(
        1 for p in bs_probes
        if p["status"] == "ok" and p["detail"].get("renderable", False)
    )
    bs_total = len(bs_probes)

    akshare_quote = next((p for p in probes if p["probe"] == "akshare_real_time_quote"), None)
    akshare_ok = akshare_quote is not None and akshare_quote["status"] == "ok"

    pdf_probes = [p for p in probes if p["probe"].startswith("pdf_discovery_")]
    pdf_found = any(p["status"] == "ok" for p in pdf_probes)

    rag_probe = next((p for p in probes if p["probe"] == "db_report_chunks"), None)
    rag_ready = rag_probe is not None and rag_probe["status"] == "ok"

    # 评分公式（满分 100）：
    #   BaoStock 财务覆盖   40%（每个 module 约 6.7 分）
    #   AkShare 实时行情    20%
    #   PDF 发现可用        25%
    #   RAG 索引就绪        15%
    score = 0.0
    if bs_total > 0:
        score += 40.0 * bs_renderable / bs_total
    if akshare_ok:
        score += 20.0
    if pdf_found:
        score += 25.0
    if rag_ready:
        score += 15.0

    return {
        "renderable_bs_modules": bs_renderable,
        "total_bs_modules":      bs_total,
        "akshare_quote_ok":      akshare_ok,
        "pdf_any_year_found":    pdf_found,
        "rag_ready":             rag_ready,
        "score":                 round(score, 1),
    }


# ── 每只股票的完整诊断 ────────────────────────────────────────────────────────

async def _run_symbol(ts_code: str, years: list[int], provider_timeout: float, symbol_timeout: float) -> dict:
    """对单只股票运行全部数据源探针。"""
    symbol_6 = _to_6digit(ts_code)
    print(f"\n[START] {symbol_6} years={','.join(str(y) for y in years)}", flush=True)

    probes: list[dict] = []
    deadline = time.monotonic() + symbol_timeout

    def _remaining() -> float:
        return max(0.1, min(provider_timeout, deadline - time.monotonic()))

    def _symbol_timeout_reached() -> bool:
        return time.monotonic() >= deadline

    # 1. BaoStock 登录
    bs_login = await _run_probe_with_progress(
        symbol_6, "baostock", "baostock_login", "login", _remaining(), _probe_baostock_login,
    )
    probes.append(bs_login)

    # 2. BaoStock 财务表（逐 provider 输出，避免 gather 卡死后长时间无日志）
    for mk, method, description in _BAOSTOCK_FINANCIAL_PROBES:
        if _symbol_timeout_reached():
            probes.append(_timeout_probe(f"baostock_{mk}", 0, "baostock"))
            break
        p = await _run_probe_with_progress(
            symbol_6,
            "baostock",
            f"baostock_{mk}",
            description,
            _remaining(),
            lambda mk=mk, method=method: _probe_baostock_table(ts_code, mk, method),
        )
        probes.append(p)

    # 3. AkShare 探针
    ak_probe_defs = [
        ("akshare_financial_abstract", "financial_abstract", lambda: _probe_akshare_financial_abstract(symbol_6)),
        ("akshare_cash_flow", "cash_flow", lambda: _probe_akshare_cash_flow(symbol_6)),
        ("akshare_real_time_quote", "real_time_quote", lambda: _probe_akshare_quote(symbol_6)),
    ]
    for probe_name, description, factory in ak_probe_defs:
        if _symbol_timeout_reached():
            probes.append(_timeout_probe(probe_name, 0, "akshare"))
            break
        p = await _run_probe_with_progress(
            symbol_6, "akshare", probe_name, description, _remaining(), factory,
        )
        probes.append(p)

    # 4. PDF 域名 DNS 检查（同步，快速）
    for domain in _PDF_DOMAINS:
        if _symbol_timeout_reached():
            probes.append(_timeout_probe(f"dns_{domain}", 0, "dns"))
            break
        p = await _run_probe_with_progress(
            symbol_6,
            "dns",
            f"dns_{domain}",
            domain,
            min(3.0, _remaining()),
            lambda domain=domain: asyncio.to_thread(_probe_dns, domain),
        )
        probes.append(p)

    # 5. PDF 年报发现（串行，每年独立请求）
    for yr in years:
        if _symbol_timeout_reached():
            probes.append(_timeout_probe(f"pdf_discovery_{yr}", 0, "pdf"))
            break
        async def _one_pdf_year(year=yr):
            results = await _probe_pdf_discovery(ts_code, [year])
            return results[0]
        p = await _run_probe_with_progress(
            symbol_6, "pdf", f"pdf_discovery_{yr}", f"annual_{yr}", _remaining(), _one_pdf_year,
        )
        probes.append(p)

    # 6. DB 探针
    db_probe_defs = [
        ("db_report_documents", "report_documents", lambda: _probe_db_report_documents(ts_code)),
        ("db_report_chunks", "report_chunks", lambda: _probe_db_report_chunks(ts_code)),
    ]
    for probe_name, description, factory in db_probe_defs:
        if _symbol_timeout_reached():
            probes.append(_timeout_probe(probe_name, 0, "db"))
            break
        p = await _run_probe_with_progress(
            symbol_6, "db", probe_name, description, min(8.0, _remaining()), factory,
        )
        probes.append(p)

    # 7. 渲染能力评分
    renderability = _compute_renderability(probes)

    # 汇总统计
    status_counts: dict[str, int] = {"ok": 0, "empty": 0, "failed": 0, "disabled": 0, "timeout": 0}
    for p in probes:
        s = p["status"]
        if s in status_counts:
            status_counts[s] += 1

    print(
        f"  → score={renderability['score']:.1f}/100  "
        f"ok={status_counts['ok']} empty={status_counts['empty']} "
        f"failed={status_counts['failed']} disabled={status_counts['disabled']}",
        flush=True,
    )

    return {
        "ts_code":       ts_code,
        "symbol_6":      symbol_6,
        "probed_at":     datetime.utcnow().isoformat() + "Z",
        "partial":       _symbol_timeout_reached() or any(p.get("status") == "timeout" for p in probes),
        "probes":        probes,
        "renderability": renderability,
        "summary":       status_counts,
    }


def _print_probe(p: dict) -> None:
    icon = {"ok": "✓", "empty": "○", "failed": "✗", "disabled": "—"}.get(p["status"], "?")
    detail = p.get("detail") or {}
    extra = ""
    if "rows_count" in detail:
        extra = f" rows={detail['rows_count']}"
    if "close" in detail and detail["close"] is not None:
        extra = f" close={detail['close']}"
    if "candidates" in detail:
        extra = f" candidates={detail['candidates']}"
    if "count" in detail:
        extra = f" count={detail['count']}"
    if "chunk_count" in detail:
        extra = f" chunks={detail['chunk_count']}"
    print(
        f"  {icon} {p['probe']:40s} {p['latency_ms']:5d}ms{extra}"
        + (f"  ERR: {p['error']}" if p.get("error") else ""),
        flush=True,
    )


# ── 输出写入 ──────────────────────────────────────────────────────────────────

def _write_json(all_results: list[dict], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {"generated_at": datetime.utcnow().isoformat() + "Z", "stocks": all_results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return out_path


def _write_csv(all_results: list[dict], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for stock in all_results:
        ts_code = stock["ts_code"]
        score = stock["renderability"]["score"]
        for p in stock["probes"]:
            detail = p.get("detail") or {}
            rows.append({
                "ts_code":      ts_code,
                "probe":        p["probe"],
                "status":       p["status"],
                "latency_ms":   p["latency_ms"],
                "rows_count":   detail.get("rows_count", detail.get("chunk_count", detail.get("count", ""))),
                "renderable":   detail.get("renderable", ""),
                "error":        p.get("error") or "",
                "score":        score,
            })

    if not rows:
        return out_path

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out_path


# ── 主函数 ────────────────────────────────────────────────────────────────────

async def _run(
    symbols: list[str],
    years: list[int],
    out_dir: Path,
    out_json: Path | None,
    out_csv: Path | None,
    dry_run: bool,
    provider_timeout: float,
    symbol_timeout: float,
) -> int:
    all_results: list[dict] = []

    for raw_symbol in symbols:
        ts_code = _to_ts_code(raw_symbol.strip())
        result = await _run_symbol(ts_code, years, provider_timeout, symbol_timeout)
        all_results.append(result)
        if not dry_run:
            _write_json(all_results, out_json or (out_dir / "free_mode_data_source_debug.json"))
            _write_csv(all_results, out_csv or (out_dir / "free_mode_data_source_debug.csv"))

    if not dry_run and all_results:
        json_path = _write_json(all_results, out_json or (out_dir / "free_mode_data_source_debug.json"))
        csv_path = _write_csv(all_results, out_csv or (out_dir / "free_mode_data_source_debug.csv"))
        print(f"\n[output] JSON → {json_path}")
        print(f"[output] CSV  → {csv_path}")
    elif dry_run:
        print("\n[dry-run] 不写入文件。")

    any_ok = any(
        p["status"] == "ok"
        for stock in all_results
        for p in stock["probes"]
    )
    return 0 if any_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Free Mode 全数据源诊断脚本（BaoStock + AkShare + PDF + DB）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--symbols",
        required=True,
        help="逗号分隔的股票代码列表，例：600519,000725,601686",
    )
    parser.add_argument(
        "--years",
        default="2025,2024,2023",
        help="逗号分隔的年份列表（PDF 发现年份），默认：2025,2024,2023",
    )
    parser.add_argument(
        "--out-dir",
        default="docs/artifacts",
        help="输出目录（默认：docs/artifacts）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅运行诊断并打印结果，不写入文件",
    )
    parser.add_argument("--provider-timeout", type=float, default=12.0, help="单 provider timeout 秒数")
    parser.add_argument("--symbol-timeout", type=float, default=None, help="单股票总 timeout 秒数")
    parser.add_argument("--out-json", default=None, help="输出 JSON 文件路径")
    parser.add_argument("--out-csv", default=None, help="输出 CSV 文件路径")

    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    out_dir = Path(args.out_dir)
    out_json = Path(args.out_json) if args.out_json else None
    out_csv = Path(args.out_csv) if args.out_csv else None
    symbol_timeout = args.symbol_timeout
    if symbol_timeout is None:
        try:
            from app.core.config import settings
            symbol_timeout = float(getattr(settings, "company_v2_debug_script_symbol_timeout_seconds", 90.0))
        except Exception:
            symbol_timeout = 90.0

    if not symbols:
        print("错误：--symbols 不能为空", file=sys.stderr)
        sys.exit(1)

    exit_code = asyncio.run(_run(
        symbols=symbols,
        years=years,
        out_dir=out_dir,
        out_json=out_json,
        out_csv=out_csv,
        dry_run=args.dry_run,
        provider_timeout=args.provider_timeout,
        symbol_timeout=symbol_timeout,
    ))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
