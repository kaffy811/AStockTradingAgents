"""
smoke_redis_cache.py — Redis 缓存 smoke 验证脚本（Phase R1.5）。

用途：
  验证 FundamentalDataService Redis 缓存是否真实命中，
  以及 Redis 不可用时业务是否能正常降级。

使用方式：
  # 基础测试（Redis 未启动 or 启动均可运行）
  uv run python scripts/smoke_redis_cache.py --market CN --symbol 600519

  # 清除缓存后重测（验证 cache miss → 上游调用 → cache write）
  uv run python scripts/smoke_redis_cache.py --market CN --symbol 600519 --clear

  # 可选：禁用详细字段输出
  uv run python scripts/smoke_redis_cache.py --market CN --symbol 600519 --quiet

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

# ── 配置日志：只显示 WARNING 以上，避免 AkShare / SQLAlchemy DEBUG 刷屏 ─────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# 只开放 cache_service / fundamental_data_service 的 INFO，便于观察缓存命中
logging.getLogger("app.services.cache_service").setLevel(logging.INFO)
logging.getLogger("app.services.fundamental_data_service").setLevel(logging.INFO)

# ── 延迟导入（需先设置 sys.path）─────────────────────────────────────────────────
from app.core.config import settings  # noqa: E402
from app.core.database import connect_redis, close_redis, get_redis  # noqa: E402
from app.services.cache_service import cache_service, set_event_loop, _full_key  # noqa: E402
from app.services.fundamental_data_service import fundamental_data_service  # noqa: E402


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _hr(char: str = "─", width: int = 60) -> str:
    return char * width


def _fmt_fields(snapshot: dict) -> str:
    """格式化快照中关键字段，便于阅读。"""
    dq    = snapshot.get("data_quality", {})
    co    = snapshot.get("company", {})
    val   = snapshot.get("valuation", {})
    prof  = snapshot.get("profitability", {})
    lines = [
        f"  company.name          : {co.get('name')}",
        f"  valuation.pe          : {val.get('pe')}",
        f"  valuation.pb          : {val.get('pb')}",
        f"  valuation.market_cap  : {val.get('market_cap')}",
        f"  profitability.roe     : {prof.get('roe')}",
        f"  data_quality.stale    : {dq.get('stale')}",
        f"  data_quality.provider : {dq.get('provider')}",
        f"  latest_report_date    : {dq.get('latest_report_date')}",
        f"  missing_fields        : {dq.get('missing_fields', [])}",
    ]
    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────────────────────

async def run(market: str, symbol: str, clear: bool, quiet: bool) -> None:
    print(_hr("═"))
    print(f"  smoke_redis_cache.py  —  {market}/{symbol}")
    print(f"  env: {settings.app_env}  |  redis_url: {settings.redis_url}")
    print(_hr("═"))

    # ── Redis 连接 ────────────────────────────────────────────────────────────
    await connect_redis()
    redis = get_redis()

    if redis is None:
        print("\n[Redis]  ⚠  unavailable (连接失败，业务将走内存缓存 / stale fallback)")
        redis_ok = False
    else:
        try:
            pong = await redis.ping()
            print(f"\n[Redis]  ✓  ping → {pong}")
            redis_ok = True
        except Exception as exc:
            print(f"\n[Redis]  ⚠  ping 失败: {exc}")
            redis_ok = False

    # 注入 event loop 供 sync_* 桥接方法使用
    set_event_loop(asyncio.get_running_loop())

    # ── 构造并打印实际 Redis key ──────────────────────────────────────────────
    cache_key   = f"fundamental:{market}:{symbol}"
    full_redis_key = _full_key(cache_key)
    print(f"\n[Key]    Redis key = '{full_redis_key}'")

    # ── 可选：清除旧缓存 ──────────────────────────────────────────────────────
    if clear:
        deleted = await cache_service.delete(cache_key)
        if deleted:
            print("[Clear]  ✓  Redis key 已删除，测试将从 cache miss 开始")
        else:
            print("[Clear]  -  key 不存在或 Redis 不可用，无需删除")

    # ── 检查 Redis key 是否存在（调用前）────────────────────────────────────────
    before_exists = await cache_service.exists(cache_key)
    print(f"\n[Pre]    Redis key exists before call: {before_exists}")

    print(_hr())
    print("[Call 1] 第一次调用 fundamental_data_service.get_fundamentals() ...")

    t0 = time.perf_counter()
    result1 = await asyncio.to_thread(
        fundamental_data_service.get_fundamentals, market, symbol
    )
    t1 = time.perf_counter()
    elapsed1 = t1 - t0

    print(f"[Call 1] 完成  耗时: {elapsed1:.3f}s")
    if not quiet:
        print(_fmt_fields(result1))

    # ── 检查 Redis key 写入状态 ───────────────────────────────────────────────
    after_exists = await cache_service.exists(cache_key)
    print(f"\n[Post1]  Redis key exists after call 1: {after_exists}")
    if redis_ok and not after_exists:
        print("         ⚠  key 未写入 Redis（可能是上游数据全部失败，未触发缓存写入）")

    print(_hr())
    print("[Call 2] 第二次调用同一标的（预期命中 Redis）...")

    t2 = time.perf_counter()
    result2 = await asyncio.to_thread(
        fundamental_data_service.get_fundamentals, market, symbol
    )
    t3 = time.perf_counter()
    elapsed2 = t3 - t2

    print(f"[Call 2] 完成  耗时: {elapsed2:.3f}s")
    if not quiet:
        print(_fmt_fields(result2))

    # ── 命中判断 ──────────────────────────────────────────────────────────────
    print(_hr())
    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float("inf")

    if redis_ok and after_exists:
        if elapsed2 < elapsed1 * 0.3:
            verdict = "✓  Redis 命中成功（第二次耗时显著下降）"
        elif elapsed2 < elapsed1 * 0.7:
            verdict = "~  可能命中 Redis 或内存缓存（耗时有所下降）"
        else:
            verdict = "?  耗时未显著下降，可能命中了内存缓存（进程级 TTL）"
    elif not redis_ok:
        verdict = "⚠  Redis 不可用，业务通过内存缓存 / stale 正常降级"
    else:
        verdict = "✗  Redis key 不存在，未命中"

    print(f"\n[Result] 第一次耗时: {elapsed1:.3f}s")
    print(f"[Result] 第二次耗时: {elapsed2:.3f}s")
    print(f"[Result] 速度比:     {speedup:.1f}x")
    print(f"[Result] 判断:       {verdict}")

    # ── Redis 内存占用粗估 ────────────────────────────────────────────────────
    if redis_ok and after_exists:
        try:
            raw = await redis.get(full_redis_key)
            size_bytes = len(raw.encode("utf-8")) if raw else 0
            ttl_sec    = await redis.ttl(full_redis_key)
            print(f"\n[Key]    value size: {size_bytes:,} bytes  |  TTL remaining: {ttl_sec}s")
        except Exception as exc:
            print(f"\n[Key]    无法读取 key 详情: {exc}")

    # ── Negative cache 状态检查 ───────────────────────────────────────────────
    neg_akshare = f"negative:akshare_quote:CN:{symbol}"
    neg_yf      = f"negative:yfinance_quote:CN:{symbol}"
    neg_ak_exists = await cache_service.exists(neg_akshare)
    neg_yf_exists = await cache_service.exists(neg_yf)
    print(f"\n[Neg]    negative:akshare_quote:CN:{symbol} = {neg_ak_exists}")
    print(f"[Neg]    negative:yfinance_quote:CN:{symbol} = {neg_yf_exists}")
    if neg_ak_exists or neg_yf_exists:
        print("         ⚠  negative cache 存在，对应 provider 下次会被跳过")

    # ── 降级行为说明 ──────────────────────────────────────────────────────────
    if not redis_ok:
        print("\n[Fallback] Redis 不可用时的降级链：")
        print("  L1 Redis → 未命中（not available）")
        print("  L2 内存 _cache → 命中或 miss")
        print("  L3 上游数据源（AkShare / Sina / yfinance）")
        print("  L4 内存 _stale 永久缓存")
        print("  → 以上任一层成功即返回 HTTP 200，不会崩溃")

    print(_hr("═"))
    print("[Done]   smoke test 完成")
    print(_hr("═"))

    await close_redis()


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Redis 缓存 smoke 验证脚本 — Phase R1.5",
    )
    parser.add_argument("--market", required=True, help="市场代码，如 CN 或 HK")
    parser.add_argument("--symbol", required=True, help="股票代码，如 600519")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="运行前先删除 Redis 中该标的的 fundamental key（强制 cache miss）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不打印详细字段，只显示耗时和判断",
    )
    args = parser.parse_args()

    asyncio.run(run(
        market=args.market.upper(),
        symbol=args.symbol.strip(),
        clear=args.clear,
        quiet=args.quiet,
    ))


if __name__ == "__main__":
    main()
