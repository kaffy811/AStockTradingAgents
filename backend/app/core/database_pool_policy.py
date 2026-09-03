from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool


@dataclass(frozen=True)
class DatabasePoolPolicy:
    dialect: str
    connection_mode: str
    strategy: str
    pool_class: type
    pool_kwargs: dict[str, Any]
    connect_args: dict[str, Any]


def resolve_database_pool_policy(
    database_url: str,
    configured_strategy: str | None,
    *,
    connection_mode: str | None = None,
    pool_pre_ping: bool = True,
    command_timeout_seconds: float = 45.0,
    pool_size: int = 2,
    max_overflow: int = 0,
    direct_pool_size: int = 5,
    direct_max_overflow: int = 10,
    pool_recycle_seconds: int = 1800,
    pool_timeout_seconds: float = 10.0,
) -> DatabasePoolPolicy:
    """Resolve SQLAlchemy pool settings without constructing an engine."""

    url = make_url(database_url)
    dialect = url.drivername.split("+", 1)[0]
    mode = (connection_mode or "transaction_pooler").strip().lower()
    strategy = (configured_strategy or "small_queue_pool").strip().lower()
    is_postgres = url.drivername.startswith("postgresql")

    if not is_postgres:
        pool_class = NullPool
    elif mode == "transaction_pooler" and strategy == "null_pool":
        pool_class = NullPool
    elif strategy in {"small_queue_pool", "queue_pool", "null_pool"}:
        pool_class = AsyncAdaptedQueuePool
    else:
        raise ValueError(f"unsupported database transaction pool strategy: {strategy}")

    connect_args: dict[str, Any] = {}
    if is_postgres:
        connect_args = {
            "statement_cache_size": 0,
            "command_timeout": command_timeout_seconds,
        }

    pool_kwargs: dict[str, Any] = {
        "poolclass": pool_class,
        "pool_pre_ping": pool_pre_ping,
    }
    if connect_args:
        pool_kwargs["connect_args"] = connect_args
    if pool_class is AsyncAdaptedQueuePool:
        selected_pool_size = pool_size
        selected_max_overflow = max_overflow
        if mode in {"direct", "session_pooler"}:
            selected_pool_size = direct_pool_size
            selected_max_overflow = direct_max_overflow
        pool_kwargs.update(
            {
                "pool_size": selected_pool_size,
                "max_overflow": selected_max_overflow,
                "pool_recycle": pool_recycle_seconds,
                "pool_timeout": pool_timeout_seconds,
            }
        )

    return DatabasePoolPolicy(
        dialect=dialect,
        connection_mode=mode,
        strategy=strategy,
        pool_class=pool_class,
        pool_kwargs=pool_kwargs,
        connect_args=connect_args,
    )
