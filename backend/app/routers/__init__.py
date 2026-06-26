from fastapi import APIRouter
from app.routers import analysis, auth, chat, health, industry, llm, reports, stocks, watchlist

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(llm.router)
router.include_router(stocks.router)
router.include_router(analysis.router)
router.include_router(reports.router)
router.include_router(industry.router)
router.include_router(watchlist.router)
router.include_router(chat.router)
