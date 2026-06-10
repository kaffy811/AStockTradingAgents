"""
smoke_stock_cache.py — Redis quote/kline 缓存 smoke 验证脚本（Phase R2）。

用途：
  验证 StockCacheService Redis L1 缓存是否真实命中，
  以及 Redis 不可用时业务是否正常降级。

使用方式：
  # 基础验证（Redis 启动 or 未启动均可运行）
  uv run python scripts/smoke_stock_cache.py --market CN --symbol 600519

  # 清除缓存后重测（验证完整 miss → write → hit 流程）
  uv run python scripts/smoke_stock_cache.py --market CN --symbol 600519 --clear

  # 只看 kline（跳过 quote 测试）
  uv run python scripts/smoke_stock_cache.py --market CN --symbol 600519 --kline-only

  # 精简输出
  uv run python scripts/smoke_stock_cache.py --market CN --symbol 600519 --quiet

运行环境：
  须在 backend 目录下运行（或确保 PYTHONPATH 包含 backend）。
  Redis 未启动时脚本不崩溃，仅提示 Redis unavailable 后继续验证 fallback 行为。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# ── 确保 backend 目录在路径中 ──────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

# ── 日志配置：屏蔽低级 debug，只显示缓存相关 INFO ─────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("app.services.stock_cache_service").setLevel(logging.INFO)
logging.getLogger("app.services.cache_service").setLevel(logging.INFO)

# ── 延迟导入（需先设置 sys.path）─────────────────────────────────────────────────
from app.core.config import settings                                          # noqa: E402
from app.core.database import connect_redis, close_redis, get_redis          # noqa: E402
from app.services.cache_service import cache_service, set_event_loop, _full_key  # noqa: E402
from app.services.stock_data_service import stock_data_service               # noqa: E402
from app.services import stock_cache_service as scs                          # noqa: E402


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _hr(char: str = "─", width: int = 64) -> str:
    return char * width


def _fmt_quote(result) -> str:
    d = result.data
    lines = [
        f"  provider  : {result.provider}",
        f"  cached    : {result.cached}",
        f"  stale     : {result.stale}",
        f"  name      : {d.get('name')}",
        f"  price     : {d.get('price')}",
        f"  trade_date: {d.get('trade_date')}",
    ]
    return "\n".join(lines)


def _fmt_kline(result) -> str:
    bars = result.bars
    last = bars[-1] if bars else {}
    lines = [
        f"  provider  : {result.provider}",
        f"  cached    : {result.cached}",
        f"  stale     : {result.stale}",
        f"  bars      : {len(bars)}",
        f"  last date : {last.get('date')}",
        f"  last close: {last.get('close')}",
    ]
    return "\n".join(lines)


async def _check_key(key: str, label: str, quiet: bool) -> None:
    exists = await cache_service.exists(key)
    full   = _full_key(key)
    if not quiet:
        print(f"[Key]    {full}")
    if exists:
        redis = get_redis()
        if redis:
            try:
                raw = await redis.get(full)
                ttl = await redis.ttl(full)
                size = len(raw.encode("utf-8")) if raw else 0
                print(f"[{label}] Redis key ✓  size={size:,}B  TTL={ttl}s")
            except Exception:
                print(f"[{label}] Redis key ✓")
        else:
            print(f"[{label}] Redis key ✓")
    else:
        print(f"[{label}] Redis key ✗  (不存在)")


# ── Quote 测试 ────────────────────────────────────────────────────────────────

async def test_quote(
    market: str, symbol: str, clear: bool, quiet: bool
) -> None:
    quote_key = f"quote:{market}:{symbol}"

    if clear:
        deleted = await cache_service.delete(quote_key)
        scs._store.pop(quote_key, None)
        print(f"[Clear]  quote key {'已删除' if deleted else '不存在'}")

    before = await cache_service.exists(quote_key)
    print(f"[Pre]    quote Redis key exists: {before}")
    print(_hr())
    print(f"[Quote1] 第一次获取 quote [{market}/{symbol}] ...")

    t0 = time.perf_counter()
    r1 = await asyncio.to_thread(stock_data_service.get_quote, market, symbol)
    t1 = time.perf_counter()
    print(f"[Quote1] 完成  耗时: {t1-t0:.3f}s  http_status={r1.http_status}")
    if not quiet:
        print(_fmt_quote(r1))

    await _check_key(quote_key, "Quote1", quiet)
    print(_hr())
    print(f"[Quote2] 第二次获取 quote（预期 Redis HIT）...")

    t2 = time.perf_counter()
    r2 = await asyncio.to_thread(stock_data_service.get_quote, market, symbol)
    t3 = time.perf_counter()
    elapsed2 = t3 - t2
    elapsed1 = t1 - t0
    print(f"[Quote2] 完成  耗时: {elapsed2:.3f}s  http_status={r2.http_status}")
    if not quiet:
        print(_fmt_quote(r2))

    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float("inf")
    if elapsed2 < elapsed1 * 0.3:
        verdict = "✓  Redis 命中（耗时显著下降）"
    elif r2.cached:
        verdict = "~  命中缓存（内存或 Redis）"
    else:
        verdict = "?  未明显命中缓存"
    print(f"[Quote]  {elapsed1:.3f}s → {elapsed2:.3f}s  {speedup:.0f}x  {verdict}")


# ── Kline 测试 ────────────────────────────────────────────────────────────────

async def test_kline(
    market: str, symbol: str, period: str, adjust: str, limit: int,
    clear: bool, quiet: bool,
) -> None:
    kline_key = f"kline:{market}:{symbol}:{period}:{adjust}:{limit}"

    if clear:
        deleted = await cache_service.delete(kline_key)
        scs._store.pop(kline_key, None)
        print(f"[Clear]  kline key {'已删除' if deleted else '不存在'}")

    before = await cache_service.exists(kline_key)
    print(f"[Pre]    kline Redis key exists: {before}")
    print(_hr())
    print(f"[Kline1] 第一次获取 kline [{market}/{symbol} {period}/{adjust} limit={limit}] ...")

    t0 = time.perf_counter()
    r1 = await asyncio.to_thread(stock_data_service.get_kline, market, symbol, period, adjust, limit)
    t1 = time.perf_counter()
    print(f"[Kline1] 完成  耗时: {t1-t0:.3f}s  http_status={r1.http_status}")
    if not quiet:
        print(_fmt_kline(r1))

    await _check_key(kline_key, "Kline1", quiet)
    print(_hr())
    print(f"[Kline2] 第二次获取 kline（预期 Redis HIT）...")

    t2 = time.perf_counter()
    r2 = await asyncio.to_thread(stock_data_service.get_kline, market, symbol, period, adjust, limit)
    t3 = time.perf_counter()
    elapsed2 = t3 - t2
    elapsed1 = t1 - t0
    print(f"[Kline2] 完成  耗时: {elapsed2:.3f}s  http_status={r2.http_status}")
    if not quiet:
        print(_fmt_kline(r2))

    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float("inf")
    if elapsed2 < elapsed1 * 0.3:
        verdict = "✓  Redis 命中（耗时显著下降）"
    elif r2.cached:
        verdict = "~  命中缓存（内存或 Redis）"
    else:
        verdict = "?  未明显命中缓存"
    print(f"[Kline]  {elapsed1:.3f}s → {elapsed2:.3f}s  {speedup:.0f}x  {verdict}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

async def run(
    market: str, symbol: str, clear: bool, quiet: bool,
    kline_only: bool, quote_only: bool,
    period: str, adjust: str, limit: int,
) -> None:
    print(_hr("═"))
    print(f"  smoke_stock_cache.py  —  {market}/{symbol}")
    print(f"  env: {settings.app_env}  |  redis_url: {settings.redis_url}")
    print(_hr("═"))

    # ── Redis 连接 ────────────────────────────────────────────────────────────
    await connect_redis()
    redis = get_redis()

    if redis is None:
        print("\n[Redis]  ⚠  unavailable（业务将走内存缓存 / stale fallback）")
        redis_ok = False
    else:
        try:
            pong = await redis.ping()
            print(f"\n[Redis]  ✓  ping → {pong}")
            redis_ok = True  # noqa: F841
        except Exception as exc:
            print(f"\n[Redis]  ⚠  ping 失败: {exc}")

    set_event_loop(asyncio.get_running_loop())

    print()
    if not kline_only:
        await test_quote(market, symbol, clear, quiet)
        print()

    if not quote_only:
        await test_kline(market, symbol, period, adjust, limit, clear, quiet)
        print()

    print(_hr("═"))
    print("[Done]   smoke test 完成")
    print(_hr("═"))

    await close_redis()


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Redis quote/kline 缓存 smoke 验证脚本 — Phase R2",
    )
    parser.add_argument("--market",  required=True, help="市场代码，如 CN 或 HK")
    parser.add_argument("--symbol",  required=True, help="股票代码，如 600519")
    parser.add_argument("--clear",   action="store_true",
                        help="运行前先删除 Redis 中 quote/kline key（强制 cache miss）")
    parser.add_argument("--quiet",   action="store_true",
                        help="不打印详细字段，只显示耗时和判断")
    parser.add_argument("--kline-only", action="store_true",
                        help="只测试 kline，跳过 quote")
    parser.add_argument("--quote-only", action="store_true",
                        help="只测试 quote，跳过 kline")
    parser.add_argument("--period",  default="daily",
                        help="K线周期，默认 daily")
    parser.add_argument("--adjust",  default="qfq",
                        help="复权方式，默认 qfq（前复权）")
    parser.add_argument("--limit",   type=int, default=120,
                        help="K线条数，默认 120")
    args = parser.parse_args()

    asyncio.run(run(
        market     = args.market.upper(),
        symbol     = args.symbol.strip(),
        clear      = args.clear,
        quiet      = args.quiet,
        kline_only = args.kline_only,
        quote_only = args.quote_only,
        period     = args.period,
        adjust     = args.adjust,
        limit      = args.limit,
    ))


if __name__ == "__main__":
    main()
