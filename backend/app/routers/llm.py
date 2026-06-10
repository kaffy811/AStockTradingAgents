from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.dependencies import get_current_user
from app.llm.factory import get_llm_client
from app.models.user import User

router = APIRouter(prefix="/llm", tags=["llm"])


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    model: str
    reply: str


@router.post("/test", response_model=ChatResponse)
async def test_flash(
    body: ChatRequest,
    _: User = Depends(get_current_user),
):
    """Quick sanity-check using deepseek-v4-flash (default model)."""
    try:
        client = get_llm_client()
        reply = client.chat(
            messages=[{"role": "user", "content": body.message}],
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    return ChatResponse(model=settings.deepseek_default_model, reply=reply)


@router.post("/test-pro", response_model=ChatResponse)
async def test_pro(
    body: ChatRequest,
    _: User = Depends(get_current_user),
):
    """Sanity-check using deepseek-v4-pro (pro model for complex reasoning)."""
    try:
        client = get_llm_client()
        reply = client.chat(
            messages=[{"role": "user", "content": body.message}],
            model=settings.deepseek_pro_model,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

    return ChatResponse(model=settings.deepseek_pro_model, reply=reply)
