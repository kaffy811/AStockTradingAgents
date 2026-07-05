#!/usr/bin/env python
"""
scripts/run_fundamental_etl.py — 基本面 ETL CLI（Phase 2B）

用法：

  python scripts/run_fundamental_etl.py stock_basic
      加载全市场 A 股基本信息到 etl_stock_basic。

  python scripts/run_fundamental_etl.py daily_basic --trade-date 20260705
      加载指定交易日的全市场日频估值到 etl_daily_basic。

  python scripts/run_fundamental_etl.py fina_indicator --end-date 20251231
      加载指定报告期的全市场财务指标到 etl_fina_indicator。

  python scripts/run_fundamental_etl.py industry_rank --trade-date 20260705 --end-date 20251231
      基于已导入的 ETL 数据，用 SQL 窗口函数计算行业排名，写入 industry_rank_snapshot。

前置条件：
  - TUSHARE_TOKEN、DATABASE_URL、SECRET_KEY 已在 .env 中配置
  - alembic upgrade head 已执行（ETL 表已创建）
  - ETL_ENABLED=true（默认为 true）

注意：
  ❌ 本脚本不按 ts_code 循环拉取 Tushare（避免触发速率限制）。
  ✅ 按 trade_date / end_date 一次性批量拉取全市场数据。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import os

# 将项目根目录加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("etl_cli")


async def _main(args: argparse.Namespace) -> int:
    """异步主函数，返回 exit code（0=成功，1=失败）。"""

    # 初始化 Tushare（除 industry_rank 外都需要）
    from app.datasource.tushare_client import init_tushare_client
    if args.command != "industry_rank":
        await init_tushare_client()

    command = args.command

    if command == "stock_basic":
        from app.etl.loaders import load_stock_basic
        result = await load_stock_basic()

    elif command == "daily_basic":
        if not args.trade_date:
            log.error("daily_basic 需要 --trade-date 参数（格式 YYYYMMDD）")
            return 1
        from app.etl.loaders import load_daily_basic_by_trade_date
        result = await load_daily_basic_by_trade_date(args.trade_date)

    elif command == "fina_indicator":
        if not args.end_date and not args.ann_date:
            log.error("fina_indicator 需要 --end-date 或 --ann-date 参数")
            return 1
        from app.etl.loaders import load_fina_indicator_by_period_or_disclosure
        result = await load_fina_indicator_by_period_or_disclosure(
            end_date=args.end_date,
            ann_date=getattr(args, "ann_date", None),
        )

    elif command == "industry_rank":
        if not args.trade_date or not args.end_date:
            log.error("industry_rank 需要 --trade-date 和 --end-date 参数")
            return 1
        from app.etl.rankings import compute_industry_rank_snapshot
        result = await compute_industry_rank_snapshot(
            trade_date=args.trade_date,
            end_date=args.end_date,
        )
        _print_rank_result(result)
        return 0 if not result.get("errors") else 1

    else:
        log.error("未知命令: %s", command)
        return 1

    _print_load_result(command, result)
    return 0 if not result.get("errors") else 1


def _print_load_result(command: str, result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"ETL Command: {command}")
    print(f"  inserted : {result.get('inserted', 0)}")
    print(f"  updated  : {result.get('updated', 0)}")
    print(f"  skipped  : {result.get('skipped', 0)}")
    errors = result.get("errors", [])
    if errors:
        print(f"  errors   : {len(errors)}")
        for e in errors[:5]:
            print(f"    - {e}")
    else:
        print("  errors   : 0")
    print(f"{'='*60}\n")


def _print_rank_result(result: dict) -> None:
    print(f"\n{'='*60}")
    print(f"Industry Rank Snapshot")
    print(f"  trade_date : {result.get('trade_date')}")
    print(f"  end_date   : {result.get('end_date')}")
    metrics = result.get("metrics_computed", [])
    print(f"  metrics    : {len(metrics)} ({', '.join(metrics[:5])}{'...' if len(metrics) > 5 else ''})")
    print(f"  total_rows : {result.get('total_rows_inserted', 0)}")
    errors = result.get("errors", [])
    if errors:
        print(f"  errors     : {len(errors)}")
        for e in errors[:5]:
            print(f"    - {e}")
    else:
        print("  errors     : 0")
    print(f"{'='*60}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="TradingAgents Fundamental ETL CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["stock_basic", "daily_basic", "fina_indicator", "industry_rank"],
        help="ETL 命令",
    )
    parser.add_argument(
        "--trade-date",
        dest="trade_date",
        metavar="YYYYMMDD",
        help="交易日期（daily_basic / industry_rank 必填）",
    )
    parser.add_argument(
        "--end-date",
        dest="end_date",
        metavar="YYYYMMDD",
        help="报告期末日期（fina_indicator / industry_rank 必填）",
    )
    parser.add_argument(
        "--ann-date",
        dest="ann_date",
        metavar="YYYYMMDD",
        help="披露日期（fina_indicator 可选，与 --end-date 互斥使用）",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()
    exit_code = asyncio.run(_main(args))
    sys.exit(exit_code)
