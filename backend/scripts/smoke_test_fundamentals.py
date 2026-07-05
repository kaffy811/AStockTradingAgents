#!/usr/bin/env python3
"""
scripts/smoke_test_fundamentals.py — 基本面数据服务真实接口冒烟测试

使用方式：
    uv run python scripts/smoke_test_fundamentals.py --market CN --symbol 600519
    uv run python scripts/smoke_test_fundamentals.py --symbol 600519.SH
    uv run python scripts/smoke_test_fundamentals.py --market HK --symbol 700

前提：
    1. 在 .env 中配置 TUSHARE_TOKEN
    2. 不要求 CI 环境中运行（CI 无真实 Token）

输出：
    每个模块的 OK/FAIL 状态、missing_fields、nullable_fields
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 确保能 import app 模块
sys.path.insert(0, str(Path(__file__).parent.parent))


def _parse_code(code: str) -> tuple[str, str]:
    """与 fundamentals_compat._parse_code 逻辑一致。"""
    code = code.strip()
    if "." in code:
        parts = code.rsplit(".", 1)
        symbol_part = parts[0]
        suffix = parts[1].upper()
        if suffix in ("SH", "SZ", "BJ"):
            return "CN", symbol_part
        elif suffix == "HK":
            digits = symbol_part.lstrip("0") or "0"
            return "HK", digits.zfill(5)
        else:
            return "US", symbol_part
    elif code.isdigit():
        if len(code) == 6:
            return "CN", code
        return "HK", code.zfill(5)
    return "US", code


async def _smoke_module(aggregator, market: str, symbol: str, module_key: str) -> dict:
    """测试单个模块，返回结果 summary。"""
    result = {
        "module":         module_key,
        "status":         "FAIL",
        "missing_fields": [],
        "nullable_fields": [],
        "error":          None,
        "stale":          False,
        "source":         None,
    }
    try:
        envelope = await aggregator.fetch_module(
            market=market, symbol=symbol, module_key=module_key
        )
        if not envelope["ok"]:
            result["error"] = envelope["reason"]
            return result

        result["status"] = "OK"
        result["stale"] = envelope["stale"]
        data = envelope["data"] or {}

        # 统计哪些字段为 None（nullable_fields）
        if isinstance(data, dict):
            result["nullable_fields"] = [k for k, v in data.items() if v is None and not k.startswith("_")]
        elif isinstance(data, list) and data:
            first = data[0] if isinstance(data[0], dict) else {}
            result["nullable_fields"] = [k for k, v in first.items() if v is None]

        if envelope["partial_errors"]:
            result["missing_fields"] = envelope["partial_errors"]

    except Exception as exc:
        result["error"] = str(exc)

    return result


def _print_result(r: dict) -> None:
    status_icon = "✅" if r["status"] == "OK" else "❌"
    stale_mark = " [stale]" if r.get("stale") else ""
    print(f"\n{status_icon} [{r['module']}]{stale_mark}")
    if r["error"]:
        print(f"   ERROR: {r['error']}")
    if r["missing_fields"]:
        print(f"   missing_fields: {r['missing_fields']}")
    if r["nullable_fields"]:
        preview = r["nullable_fields"][:8]
        suffix = "..." if len(r["nullable_fields"]) > 8 else ""
        print(f"   nullable_fields ({len(r['nullable_fields'])}): {preview}{suffix}")


async def main(market: str, symbol: str) -> None:
    # 设置环境（需要真实 TUSHARE_TOKEN）
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        # 尝试从 .env 读取
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("TUSHARE_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not token:
        print("⚠️  TUSHARE_TOKEN 未配置 — 将测试无 Token 降级行为（所有模块应返回 FAIL/err_envelope）")
    else:
        print(f"✓ TUSHARE_TOKEN: {token[:6]}***（已加载）")

    # 初始化
    from app.core.config import settings
    from app.datasource.tushare_client import tushare_client, init_tushare_client
    from app.aggregator.fundamentals_aggregator import get_aggregator

    if token:
        await init_tushare_client()

    aggregator = get_aggregator()

    print(f"\n{'='*60}")
    print(f"冒烟测试: market={market}  symbol={symbol}")
    print(f"{'='*60}")

    # 测试模块列表
    test_modules = [
        "snapshot",
        "financial_summary",
        "valuation",
        "dupont",
        "cashflow_quality",
    ]

    results = []
    for module_key in test_modules:
        print(f"  → 测试 {module_key}...", end="", flush=True)
        r = await _smoke_module(aggregator, market, symbol, module_key)
        results.append(r)
        print(f" {'OK' if r['status'] == 'OK' else 'FAIL'}")

    print(f"\n{'='*60}")
    print("详细结果：")
    for r in results:
        _print_result(r)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    fail_count = len(results) - ok_count
    print(f"\n{'='*60}")
    print(f"汇总: {ok_count}/{len(results)} OK | {fail_count} FAIL")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fundamental Service 冒烟测试")
    parser.add_argument("--market", default="", help="市场代码 CN/HK/US（可省略，从 symbol 推断）")
    parser.add_argument("--symbol", default="600519", help="股票代码（支持 600519 / 600519.SH / AAPL）")
    args = parser.parse_args()

    if args.market:
        market, symbol = args.market.upper(), args.symbol
    else:
        market, symbol = _parse_code(args.symbol)

    asyncio.run(main(market, symbol))
