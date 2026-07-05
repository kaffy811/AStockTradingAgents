"""
app/etl/db.py — ETL 数据库工具（Phase 2B）

设计原则：
  1. 复用项目现有 PostgreSQL（database_url），不引入独立 MYSQL_DSN。
  2. 提供 etl_available() 快速检查 ETL 是否可用（settings.etl_enabled）。
  3. 提供 get_etl_session() 获取 AsyncSession，供 loaders/rankings 使用。
  4. 如果 etl_enabled=False 或 DB 不可达，调用者通过 ETLDisabledError 感知。

注意：项目使用 PostgreSQL + asyncpg（非 MySQL）。SQL 排名逻辑使用标准窗口函数，
与 MySQL 8.x 的语法完全兼容，可无缝迁移。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


class ETLDisabledError(RuntimeError):
    """ETL 功能未启用或数据库不可达时抛出。"""


def etl_available() -> bool:
    """
    检查 ETL 底座是否可用。

    返回 False 的场景：
      - settings.etl_enabled = False（在 .env 中设置 ETL_ENABLED=false）
    """
    from app.core.config import settings
    return settings.etl_enabled


def require_etl() -> None:
    """
    断言 ETL 可用，否则抛出 ETLDisabledError（附带清晰说明）。
    在 ETL 相关功能入口调用。
    """
    if not etl_available():
        raise ETLDisabledError(
            "ETL 功能未启用（ETL_ENABLED=false）。"
            "如需行业排名功能，请在 .env 中设置 ETL_ENABLED=true 并执行："
            " python scripts/run_fundamental_etl.py industry_rank --trade-date YYYYMMDD --end-date YYYYMMDD"
        )


async def get_etl_session() -> AsyncSession:
    """
    获取用于 ETL 批量写入的 AsyncSession。

    使用方：
        async with await get_etl_session() as session:
            await session.execute(...)
            await session.commit()
    """
    require_etl()
    from app.core.database import AsyncSessionLocal
    return AsyncSessionLocal()


async def table_exists(session: AsyncSession, table_name: str) -> bool:
    """
    检查指定表是否已在 PostgreSQL 中创建。
    用于 industry_rank 工具的优雅降级判断。
    """
    result = await session.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.tables"
            "  WHERE table_schema = 'public'"
            "    AND table_name = :tname"
            ")"
        ),
        {"tname": table_name},
    )
    return bool(result.scalar())


async def count_rows(session: AsyncSession, table_name: str, where: str = "") -> int:
    """
    快速统计表行数（用于判断 ETL 数据是否就绪）。
    table_name 只允许字母/下划线，防止注入。
    """
    if not table_name.replace("_", "").isalnum():
        raise ValueError(f"非法 table_name: {table_name}")
    sql = f"SELECT COUNT(*) FROM {table_name}"
    if where:
        sql += f" WHERE {where}"
    result = await session.execute(text(sql))
    return int(result.scalar() or 0)


# ── Upsert helper ─────────────────────────────────────────────────────────────

def build_upsert_sql(
    table: str,
    rows: list[dict[str, Any]],
    conflict_cols: list[str],
    update_cols: list[str],
) -> tuple[str, list[dict]]:
    """
    构建 PostgreSQL INSERT ... ON CONFLICT DO UPDATE ... 批量 upsert SQL。

    参数：
        table         : 目标表名
        rows          : 数据行（list of dict，每行字段名相同）
        conflict_cols : 唯一约束列名列表（ON CONFLICT 子句使用）
        update_cols   : 冲突时需要更新的列名列表

    返回：
        (sql_template, rows) — 可用于 session.execute(text(sql), rows)

    注意：
        - table / 列名只允许字母+下划线，防止 SQL 注入
        - 此函数构建 SQL 字符串供 SQLAlchemy text() 使用，
          参数通过绑定变量传入，保证安全
    """
    if not rows:
        return "", []

    # 安全校验
    _safe = lambda s: s.replace("_", "").isalnum()  # noqa: E731
    assert _safe(table), f"非法 table name: {table}"
    all_cols = list(rows[0].keys())
    for c in all_cols + conflict_cols + update_cols:
        assert _safe(c), f"非法列名: {c}"

    col_names = ", ".join(all_cols)
    placeholders = ", ".join(f":{c}" for c in all_cols)
    conflict_clause = ", ".join(conflict_cols)
    update_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_cols)

    sql = (
        f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})\n"
        f"ON CONFLICT ({conflict_clause})\n"
        f"DO UPDATE SET {update_clause}, updated_at = now()"
    )
    return sql, rows
