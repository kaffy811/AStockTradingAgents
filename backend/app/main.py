from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import close_redis, connect_redis, init_db
from app.routers import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()       # Creates tables; raises clearly if Postgres is unreachable
    await connect_redis() # Best-effort; logs a warning if Redis is down
    yield
    await close_redis()


app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
