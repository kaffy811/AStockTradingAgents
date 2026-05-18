from fastapi import APIRouter
from sqlalchemy import text

from app.core.database import async_engine, get_redis

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    return {"status": "ok"}


@router.get("/detailed")
async def health_detailed():
    results: dict = {"status": "ok", "services": {}}

    # PostgreSQL check
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        results["services"]["postgres"] = "ok"
    except Exception as e:
        results["services"]["postgres"] = str(e)
        results["status"] = "degraded"

    # Redis check (non-fatal)
    redis = get_redis()
    if redis is None:
        results["services"]["redis"] = "unavailable"
    else:
        try:
            await redis.ping()
            results["services"]["redis"] = "ok"
        except Exception as e:
            results["services"]["redis"] = str(e)

    return results
