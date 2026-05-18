from fastapi import APIRouter
from app.routers import health, auth

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
