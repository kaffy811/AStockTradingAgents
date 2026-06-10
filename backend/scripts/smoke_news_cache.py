"""
smoke_news_cache.py — NewsDataService Redis 缓存 smoke 验证脚本（Phase R3）。

用途：
  验证 NewsDataService Redis L1 缓存是否真实命中，
  以及 Redis 不可用时业务是否能正常降级到内存缓存。

使用方式：
  # 基础测试（Redis 未启动 or 启动均可运行）
  uv run python scripts/smoke_news_cache.py --market CN --symbol 600519

  # 清除缓存后重测（验证 cache miss → 上游调用 → Redis write → Redis HIT）
  uv run python scripts/smoke_news_cache.py --market CN --symbol 600519 --clear

  # 自定义时间窗口和条数
  uv run python scripts/smoke_news_cache.py --market CN --symbol 000001 --hours-back 48 --limit 5

  # 禁用详细字段输出
  uv run python scripts/smoke_news_cache.py --market CN --symbol 600519 --quiet

  # HK 测试
  uv run python scripts/smoke_news_cache.py --market HK --symbol 700

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

# ── 日志配置：只显示 WARNING 以上，避免 AkShare 刷屏 ─────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# 开放 cache_service 和 news_data_service 的 INFO，便于观察缓存命中日志
logging.getLogger("app.services.cache_service").setLevel(logging.INFO)
logging.getLogger("app.services.news_data_service").setLevel(logging.INFO)

# ── 延迟导入（需先设置 sys.path）─────────────────────────────────────────────────
from app.core.config import settings  # noqa: E402
from app.core.database import connect_redis, close_redis, get_redis  # noqa: E402
from app.services.cache_service import cache_service, set_event_loop, _full_key  # noqa: E402
from app.services.news_data_service import news_data_service, _cache_key  # noqa: E402


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _hr(char: str = "─", width: int = 60) -> str:
    return char * width


def _fmt_result(result: dict, quiet: bool) -> None:
    dq = result.get("data_quality", {})
    print(f"  count         : {result.get('count')}")
    print(f"  provider      : {dq.get('provider')}")
    print(f"  cached        : {dq.get('cached')}")
    print(f"  message       : {dq.get('message')}")
    if not quiet and result.get("items"):
        first = result["items"][0]
        print(f"  items[0].title: {str(first.get('title', ''))[:60]}")
        print(f"  items[0].time : {first.get('publish_time')}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

async def run(
    market:     str,
    symbol:     str,
    hours_back: int,
    limit:      int,
    clear:      bool,
    quiet:      bool,
) -> None:
    print(_hr("═"))
    print(f"  smoke_news_cache.py  —  {market}/{symbol}")
    print(f"  env: {settings.app_env}  |  redis_url: {settings.redis_url}")
    print(f"  hours_back={hours_back}  limit={limit}")
    print(_hr("═"))

    # ── Redis 连接 ────────────────────────────────────────────────────────────
    await connect_redis()
    redis = get_redis()

    if redis is None:
        print("\n[Redis]  ⚠  unavailable（连接失败，业务将走内存缓存 / stale fallback）")
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
    cache_key      = _cache_key(market, symbol, hours_back, limit)
    full_redis_key = _full_key(cache_key)
    print(f"\n[Key]    cache key  = '{cache_key}'")
    print(f"[Key]    Redis key  = '{full_redis_key}'")

    # ── 可选：清除旧缓存 ──────────────────────────────────────────────────────
    if clear:
        deleted = await cache_service.delete(cache_key)
        if deleted:
            print("[Clear]  ✓  Redis key 已删除，测试将从 cache miss 开始")
        else:
            print("[Clear]  -  key 不存在或 Redis 不可用，无需删除")

    # ── 检查 Redis key 是否存在（调用前）────────────────────────────────────────
    before_exists = await cache_service.exists(cache_key)
    print(f"\n[Pre]    Redis key exists before call 1: {before_exists}")

    # ── 第一次调用 ────────────────────────────────────────────────────────────
    print(_hr())
    print(f"[Call 1] 调用 news_data_service.get_stock_news({market}, {symbol}, "
          f"hours_back={hours_back}, limit={limit}) ...")

    t0 = time.perf_counter()
    result1 = await asyncio.to_thread(
        news_data_service.get_stock_news,
        market, symbol, hours_back, limit,
    )
    t1 = time.perf_counter()
    elapsed1 = t1 - t0

    print(f"[Call 1] 完成  耗时: {elapsed1:.3f}s")
    _fmt_result(result1, quiet)

    # ── 检查 Redis key 写入状态 ───────────────────────────────────────────────
    after1_exists = await cache_service.exists(cache_key)
    print(f"\n[Post1]  Redis key exists after call 1: {after1_exists}")
    if redis_ok and not after1_exists:
        print("         ⚠  key 未写入 Redis（可能是 provider 失败且无 stale，不写 Redis）")
    elif redis_ok and after1_exists:
        try:
            raw = await redis.get(full_redis_key)
            size_bytes = len(raw.encode("utf-8")) if raw else 0
            ttl_sec    = await redis.ttl(full_redis_key)
            print(f"[Post1]  value size: {size_bytes:,} bytes  |  TTL remaining: {ttl_sec}s")
        except Exception as exc:
            print(f"[Post1]  无法读取 key 详情: {exc}")

    # ── 第二次调用 ────────────────────────────────────────────────────────────
    print(_hr())
    print("[Call 2] 第二次调用同一标的（预期命中 Redis）...")

    t2 = time.perf_counter()
    result2 = await asyncio.to_thread(
        news_data_service.get_stock_news,
        market, symbol, hours_back, limit,
    )
    t3 = time.perf_counter()
    elapsed2 = t3 - t2

    print(f"[Call 2] 完成  耗时: {elapsed2:.3f}s")
    _fmt_result(result2, quiet)

    # ── 汇总判断 ──────────────────────────────────────────────────────────────
    print(_hr())
    speedup = elapsed1 / elapsed2 if elapsed2 > 0 else float("inf")

    cached2 = result2.get("data_quality", {}).get("cached", False)

    if redis_ok and after1_exists and cached2:
        if elapsed2 < elapsed1 * 0.3:
            verdict = "✓  Redis 命中成功（第二次 cached=True，耗时显著下降）"
        else:
            verdict = "~  命中了内存缓存（cached=True，但 Redis 耗时差不明显）"
    elif redis_ok and after1_exists and not cached2:
        verdict = "?  Redis key 存在但 cached=False（检查 sync_get_json 是否正常）"
    elif not redis_ok:
        verdict = "⚠  Redis 不可用，业务通过内存缓存正常降级"
    else:
        verdict = "✗  Redis key 不存在，未命中"

    print(f"\n[Result] 第一次耗时  : {elapsed1:.3f}s  (cached={result1['data_quality'].get('cached')})")
    print(f"[Result] 第二次耗时  : {elapsed2:.3f}s  (cached={result2['data_quality'].get('cached')})")
    print(f"[Result] 速度比      : {speedup:.1f}x")
    print(f"[Result] 判断        : {verdict}")

    # ── 数据一致性验证 ────────────────────────────────────────────────────────
    count1 = result1.get("count", -1)
    count2 = result2.get("count", -1)
    if count1 == count2:
        print(f"[Result] 数据一致性  : ✓  两次 count 相同 ({count1})")
    else:
        print(f"[Result] 数据一致性  : ⚠  count 不同（{count1} vs {count2}），可能有竞争条件")

    # ── Redis 不可用时的降级说明 ──────────────────────────────────────────────
    if not redis_ok:
        print("\n[Fallback] Redis 不可用时的降级链：")
        print("  L1 Redis     → 不可用（sync_get_json 返回 None）")
        print("  L2 内存 _cache → 按 TTL 命中或 miss")
        print("  L3 上游 EastmoneyNewsProvider.get_stock_news()")
        print("  L4 内存 _stale_cache（永久保留最近一次成功数据）")
        print("  → 以上任一层成功即返回，不会崩溃，HTTP 200 不受影响")

    print(_hr("═"))
    print("[Done]   smoke test 完成")
    print(_hr("═"))

    await close_redis()


# ── CLI 入口 ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="NewsDataService Redis 缓存 smoke 验证脚本 — Phase R3",
    )
    parser.add_argument("--market",     default="CN",   help="市场代码（默认 CN）")
    parser.add_argument("--symbol",     default="600519", help="股票代码（默认 600519）")
    parser.add_argument("--hours-back", type=int, default=72,
                        help="新闻时间窗口（小时，默认 72）")
    parser.add_argument("--limit",      type=int, default=10,
                        help="最大条数（默认 10）")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="运行前先删除 Redis 中该 key（强制 cache miss）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="不打印详细新闻内容，只显示耗时和判断",
    )
    args = parser.parse_args()

    asyncio.run(run(
        market=args.market.upper(),
        symbol=args.symbol.strip(),
        hours_back=args.hours_back,
        limit=args.limit,
        clear=args.clear,
        quiet=args.quiet,
    ))


if __name__ == "__main__":
    main()
