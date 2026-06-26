"""
行业热门股快照刷新脚本
======================
拉取全市场行情 → 按行业成分股过滤 → 计算 Hot Score → 写入 DB。

运行方式：
    uv run python scripts/refresh_industry_hot_stocks.py --market CN
    uv run python scripts/refresh_industry_hot_stocks.py --market CN --industry-code 801120
    uv run python scripts/refresh_industry_hot_stocks.py --market CN --dry-run
    uv run python scripts/refresh_industry_hot_stocks.py --market CN --top-n 5

可重复运行（幂等）：同 market+industry_code+trade_date+score_version 先删再插。
单个行业失败不影响其他行业。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import akshare as ak
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base
from app.models.industry import StockIndustryMap
from app.models.industry_hot_stock import IndustryHotStockSnapshot  # noqa: F401
from app.services.hot_score_calculator import SCORE_VERSION, calculate_hot_scores

# ── 引擎 ──────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
    echo=False,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# ── 工具 ──────────────────────────────────────────────────────────────────────

def _norm_code(raw: str) -> str:
    """
    将 AkShare 返回的股票代码归一化为 6 位纯数字。

    sh600519 → 600519
    sz000001 → 000001
    bj920000 → 920000
    600519   → 600519（已是纯数字）
    """
    raw = str(raw).strip()
    for prefix in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if raw.lower().startswith(prefix.lower()):
            return raw[2:]
    return raw


def _parse_trade_date(ts_str: str | None) -> date:
    """
    解析行情时间戳为 date。失败则使用今日本地日期。
    stock_zh_a_spot 的时间戳列格式可能是 "15:30:02" 或 "2026-05-26 15:30:02"。
    遇到仅时间格式时，使用今日日期。
    """
    if not ts_str:
        return datetime.now().date()
    ts = str(ts_str).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%H:%M:%S"):
        try:
            dt = datetime.strptime(ts, fmt)
            if fmt == "%H:%M:%S":
                return datetime.now().date()
            return dt.date()
        except ValueError:
            continue
    return datetime.now().date()


def _load_spot(retries: int = 3) -> tuple[dict[str, dict], date]:
    """
    调用 ak.stock_zh_a_spot() 并返回：
        (symbol_map: {symbol_6: row_dict}, trade_date)

    返回列：代码 名称 最新价 涨跌额 涨跌幅 买入 卖出 昨收 今开 最高 最低 成交量 成交额 时间戳
    """
    import time as _time
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            print(f"  [行情] 拉取 ak.stock_zh_a_spot()... (attempt {attempt}/{retries})")
            df = ak.stock_zh_a_spot()
            break
        except Exception as e:
            last_exc = e
            if attempt < retries:
                print(f"  [行情] 失败: {e}，等待 3s 重试...")
                _time.sleep(3)
    else:
        raise RuntimeError(f"stock_zh_a_spot 失败（{retries} 次）: {last_exc}") from last_exc
    print(f"  [行情] 返回 {len(df)} 条，列: {list(df.columns)}")

    # 自动识别关键列（对应申万 spot 字段）
    cols = list(df.columns)
    code_col   = next((c for c in cols if "代码" in c), None)
    name_col   = next((c for c in cols if "名称" in c), None)
    amount_col = next((c for c in cols if "成交额" in c), None)
    pct_col    = next((c for c in cols if "涨跌幅" in c), None)
    ts_col     = next((c for c in cols if "时间" in c or "时间戳" in c), None)

    if not all([code_col, amount_col, pct_col]):
        raise RuntimeError(
            f"stock_zh_a_spot 缺少必要列: code={code_col} amount={amount_col} pct={pct_col}"
        )

    # 取第一行的时间戳确定交易日期
    sample_ts = df[ts_col].iloc[0] if ts_col and len(df) > 0 else None
    trade_date = _parse_trade_date(str(sample_ts) if sample_ts is not None else None)
    print(f"  [行情] trade_date={trade_date}")

    symbol_map: dict[str, dict] = {}
    for _, row in df.iterrows():
        sym6 = _norm_code(str(row[code_col]))
        try:
            amount_v = float(row[amount_col]) if row[amount_col] is not None else None
            pct_v    = float(row[pct_col])    if row[pct_col]    is not None else None
        except (TypeError, ValueError):
            amount_v = None
            pct_v    = None

        symbol_map[sym6] = {
            "symbol":     sym6,
            "stock_name": str(row[name_col]) if name_col else None,
            "amount":     amount_v,
            "change_pct": pct_v,
        }

    return symbol_map, trade_date


async def _load_industry_map(
    db: AsyncSession,
    market: str,
    industry_code: str | None,
) -> dict[str, dict]:
    """
    从 stock_industry_map 读取行业→成分股映射。
    返回: {industry_code: {"industry_name": ..., "symbols": [...]}}
    """
    stmt = select(StockIndustryMap).where(StockIndustryMap.market == market)
    if industry_code:
        stmt = stmt.where(StockIndustryMap.industry_code == industry_code)

    rows = (await db.execute(stmt)).scalars().all()

    result: dict[str, dict] = {}
    for r in rows:
        if r.industry_code not in result:
            result[r.industry_code] = {"industry_name": r.industry_name, "symbols": []}
        result[r.industry_code]["symbols"].append(r.symbol)

    return result


async def _upsert_snapshots(
    db: AsyncSession,
    market: str,
    industry_code: str,
    industry_name: str,
    trade_date: date,
    scored: list[dict],
    dry_run: bool,
) -> int:
    """
    先删除同 (market, industry_code, trade_date, score_version) 的旧记录，
    再批量插入新记录。返回插入数量。
    """
    if dry_run:
        return len(scored)

    # 删除旧快照
    del_stmt = delete(IndustryHotStockSnapshot).where(
        IndustryHotStockSnapshot.market        == market,
        IndustryHotStockSnapshot.industry_code == industry_code,
        IndustryHotStockSnapshot.trade_date    == trade_date,
        IndustryHotStockSnapshot.score_version == SCORE_VERSION,
    )
    await db.execute(del_stmt)

    # 批量插入
    for item in scored:
        db.add(IndustryHotStockSnapshot(
            id              = uuid.uuid4(),
            market          = market,
            industry_code   = industry_code,
            industry_name   = industry_name,
            trade_date      = trade_date,
            rank            = item["rank"],
            symbol          = item["symbol"],
            stock_name      = item.get("stock_name"),
            hot_score       = item["hot_score"],
            amount          = item.get("amount"),
            change_pct      = item.get("change_pct"),
            amount_norm     = item.get("amount_norm"),
            change_abs_norm = item.get("change_abs_norm"),
            score_version   = SCORE_VERSION,
            data_source     = item.get("data_source", "akshare_stock_zh_a_spot"),
            score_factors   = item.get("score_factors"),
        ))

    await db.commit()
    return len(scored)


# ── 主逻辑 ────────────────────────────────────────────────────────────────────

async def run(
    market:        str,
    industry_code: str | None,
    top_n:         int,
    dry_run:       bool,
) -> None:
    market = market.upper()
    print(f"\n行业热门股快照刷新")
    print(f"  market={market}  industry_code={industry_code or '全部'}  top_n={top_n}  dry_run={dry_run}")
    print("-" * 60)

    # ── 建表 ──────────────────────────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── 拉取全市场行情 ────────────────────────────────────────────────────────
    try:
        spot_map, trade_date = _load_spot()
    except Exception as e:
        print(f"[ERR] 行情拉取失败: {e}")
        return

    # ── 读取行业成分股映射 ────────────────────────────────────────────────────
    async with SessionLocal() as db:
        industry_map = await _load_industry_map(db, market, industry_code)

    if not industry_map:
        msg = f"DB 中无 market={market}"
        if industry_code:
            msg += f" industry_code={industry_code}"
        msg += " 的成分股数据，请先运行 import_industry_map.py"
        print(f"[ERR] {msg}")
        return

    print(f"  [DB]  读取 {len(industry_map)} 个行业的成分股")

    # ── 逐行业计算 Hot Score ─────────────────────────────────────────────────
    stats = {
        "industry_count":    len(industry_map),
        "stocks_loaded":     len(spot_map),
        "snapshot_inserted": 0,
        "skipped_industries": [],
        "failed_industries":  [],
    }

    for ind_code, ind_info in industry_map.items():
            ind_name = ind_info["industry_name"]
            symbols  = ind_info["symbols"]

            # 将行业成分股与行情快照 join（对同一 symbol 去重，避免 UniqueViolation）
            seen_syms: set[str] = set()
            candidates = []
            for sym in symbols:
                if sym in spot_map and sym not in seen_syms:
                    seen_syms.add(sym)
                    candidates.append(spot_map[sym])

            if not candidates:
                stats["skipped_industries"].append(
                    f"{ind_name}({ind_code}): 0 只有行情数据"
                )
                continue

            # 计算
            try:
                scored = calculate_hot_scores(candidates, top_n=top_n)
            except Exception as e:
                stats["failed_industries"].append(f"{ind_name}({ind_code}): {e}")
                continue

            if not scored:
                stats["skipped_industries"].append(
                    f"{ind_name}({ind_code}): 过滤后无有效股票"
                )
                continue

            if len(scored) < top_n:
                print(f"  [WARN] {ind_name}: 有效候选 {len(scored)} < top_n={top_n}")

            # dry-run 输出
            if dry_run:
                print(f"\n  [DRY-RUN] {ind_name}({ind_code}) Top{len(scored)}:")
                for item in scored:
                    print(
                        f"    rank={item['rank']}  {item['symbol']} {item.get('stock_name','')}  "
                        f"amount={item['amount']:.0f}  chg%={item['change_pct']:+.2f}  "
                        f"score={item['hot_score']:.4f}"
                    )
            else:
                # 每行业使用独立 session，防止跨行业 session 状态污染导致 UniqueViolation
                async with SessionLocal() as db:
                    try:
                        n = await _upsert_snapshots(
                            db, market, ind_code, ind_name, trade_date, scored, dry_run
                        )
                        stats["snapshot_inserted"] += n
                    except Exception as e:
                        stats["failed_industries"].append(f"{ind_name}({ind_code}): {e}")
                        await db.rollback()

    # ── 统计输出 ──────────────────────────────────────────────────────────────
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}刷新完成：")
    print(f"  market           = {market}")
    print(f"  trade_date       = {trade_date}")
    print(f"  industry_count   = {stats['industry_count']}")
    print(f"  stocks_loaded    = {stats['stocks_loaded']}")
    print(f"  snapshot_inserted= {stats['snapshot_inserted']}")
    if stats["skipped_industries"]:
        print(f"  skipped ({len(stats['skipped_industries'])}):")
        for s in stats["skipped_industries"]:
            print(f"    - {s}")
    if stats["failed_industries"]:
        print(f"  failed ({len(stats['failed_industries'])}):")
        for f in stats["failed_industries"]:
            print(f"    - {f}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="行业热门股快照刷新脚本")
    parser.add_argument("--market",        default="CN",  help="市场代码，如 CN")
    parser.add_argument("--industry-code", default=None,  help="只刷新指定行业，如 801120")
    parser.add_argument("--top-n",         type=int, default=5, help="Top N，默认 5")
    parser.add_argument("--dry-run",       action="store_true",  help="只打印结果，不写 DB")
    args = parser.parse_args()

    asyncio.run(run(
        market        = args.market,
        industry_code = args.industry_code,
        top_n         = args.top_n,
        dry_run       = args.dry_run,
    ))


if __name__ == "__main__":
    main()
