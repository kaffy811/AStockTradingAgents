"""
行业分类 CSV 导入脚本
=====================
将 sw_industry_map_sample.csv（或任意符合格式的 CSV）导入
industry_master 和 stock_industry_map 两张表。

运行方式：
    uv run python scripts/import_industry_map.py --csv data/industry/sw_industry_map_sample.csv

可重复运行；已存在的行按 UniqueConstraint 做 upsert（先查再更新，不存在则插入）。

CSV 必需列：
    market, symbol, stock_name, industry_code, industry_name,
    industry_level, source, is_primary
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# 确保 backend/ 在 sys.path，使 app.* 可导入
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base
from app.models.industry import IndustryMaster, StockIndustryMap  # noqa: F401 — populates Base.metadata


# ── 数据库引擎（与主应用相同配置）────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
    echo=False,
)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def parse_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")


def normalize_row(row: dict) -> dict:
    return {
        "market":         row["market"].strip().upper(),
        "symbol":         row["symbol"].strip(),
        "stock_name":     row.get("stock_name", "").strip() or None,
        "industry_code":  row["industry_code"].strip(),
        "industry_name":  row["industry_name"].strip(),
        "industry_level": int(row.get("industry_level", 1)),
        "source":         row.get("source", "sw_static_csv").strip(),
        "is_primary":     parse_bool(row.get("is_primary", "true")),
    }


# ── 批量 upsert（PostgreSQL ON CONFLICT）──────────────────────────────────────

INDUSTRY_UPSERT_SQL = text("""
INSERT INTO industry_master
    (id, market, industry_code, industry_name, industry_level, source)
VALUES
    (:id, :market, :industry_code, :industry_name, :industry_level, :source)
ON CONFLICT (market, industry_code, source) DO UPDATE SET
    industry_name  = EXCLUDED.industry_name,
    industry_level = EXCLUDED.industry_level,
    updated_at     = now()
""")

STOCK_MAP_UPSERT_SQL = text("""
INSERT INTO stock_industry_map
    (id, market, symbol, stock_name, industry_code, industry_name,
     industry_level, source, is_primary)
VALUES
    (:id, :market, :symbol, :stock_name, :industry_code, :industry_name,
     :industry_level, :source, :is_primary)
ON CONFLICT (market, symbol, industry_code, source) DO UPDATE SET
    stock_name     = EXCLUDED.stock_name,
    industry_name  = EXCLUDED.industry_name,
    industry_level = EXCLUDED.industry_level,
    is_primary     = EXCLUDED.is_primary,
    updated_at     = now()
""")


# ── 主逻辑 ───────────────────────────────────────────────────────────────────

BATCH_SIZE = 500   # rows per transaction for stock_industry_map


async def run(csv_path: Path) -> None:
    print(f"\n行业分类导入脚本")
    print(f"CSV 文件: {csv_path.resolve()}")
    print("-" * 50)

    if not csv_path.exists():
        print(f"[ERR] CSV 文件不存在: {csv_path}")
        sys.exit(1)

    # ── 建表（create_all 若表已存在则跳过，安全） ────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[OK]  数据库表已确认（create_all）")

    # ── 读取 CSV ─────────────────────────────────────────────────────────────
    raw_rows: list[dict] = []
    with csv_path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                raw_rows.append(normalize_row(row))
            except Exception as e:
                print(f"[WARN] 第 {i} 行解析失败，跳过: {e} | 原始: {dict(row)}")

    print(f"[OK]  读取 {len(raw_rows)} 行数据")

    # ── 1. 行业主表：去重后批量 upsert（一次事务）───────────────────────────
    seen: set[tuple] = set()
    ind_params: list[dict] = []
    for r in raw_rows:
        key = (r["market"], r["industry_code"], r["source"])
        if key in seen:
            continue
        seen.add(key)
        ind_params.append({
            "id":             str(uuid.uuid4()),
            "market":         r["market"],
            "industry_code":  r["industry_code"],
            "industry_name":  r["industry_name"],
            "industry_level": r["industry_level"],
            "source":         r["source"],
        })

    async with engine.begin() as conn:
        await conn.execute(INDUSTRY_UPSERT_SQL, ind_params)
    print(f"[OK]  行业主表 upsert {len(ind_params)} 条")

    # ── 2. 股票映射表：分批 upsert（每批 BATCH_SIZE 行）────────────────────
    map_params = [
        {
            "id":             str(uuid.uuid4()),
            "market":         r["market"],
            "symbol":         r["symbol"],
            "stock_name":     r["stock_name"],
            "industry_code":  r["industry_code"],
            "industry_name":  r["industry_name"],
            "industry_level": r["industry_level"],
            "source":         r["source"],
            "is_primary":     r["is_primary"],
        }
        for r in raw_rows
    ]

    total = len(map_params)
    errors = 0
    written = 0
    for start in range(0, total, BATCH_SIZE):
        batch = map_params[start : start + BATCH_SIZE]
        try:
            async with engine.begin() as conn:
                await conn.execute(STOCK_MAP_UPSERT_SQL, batch)
            written += len(batch)
            print(f"  ... {written}/{total} 股票映射已提交")
        except Exception as e:
            errors += len(batch)
            print(f"[WARN] 批次 {start}–{start+len(batch)} 写入失败: {e}")

    # ── 输出统计 ─────────────────────────────────────────────────────────────
    print(f"\n导入完成：")
    print(f"  行业主表   upsert={len(ind_params)}")
    print(f"  股票映射   upsert={written}  errors={errors}")
    print(f"  CSV 总行数: {len(raw_rows)}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="行业分类 CSV 导入脚本")
    parser.add_argument(
        "--csv",
        required=True,
        help="CSV 文件路径（相对于当前目录或绝对路径）",
    )
    args = parser.parse_args()
    csv_path = Path(args.csv)
    asyncio.run(run(csv_path))


if __name__ == "__main__":
    main()
