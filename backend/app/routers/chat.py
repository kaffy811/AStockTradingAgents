"""
Chat Router — Phase C9 Skill Discovery.

路由：
  POST   /chat/sessions                               创建 session
  GET    /chat/sessions                               列出当前用户 sessions
  GET    /chat/sessions/{session_id}                  获取 session 详情（含 messages）
  POST   /chat/sessions/{session_id}/messages         发送消息（real tool orchestrator）
  POST   /chat/sessions/{session_id}/confirm          确认 / 取消 pending action
  DELETE /chat/sessions/{session_id}                  软删除 session
  GET    /chat/sessions/{session_id}/memory           获取 session 结构化记忆（C8）
  POST   /chat/sessions/{session_id}/memory/clear     清空 session 记忆（不删消息）（C8）
  GET    /chat/skills                                 列出可用 Agent 技能（C9）

所有接口需要 Bearer token 鉴权。
user_id 严格从 JWT 读取，不接受请求体传入。
用户只能访问自己的 session（返回 404 而非 403 避免枚举）。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_confirmation import is_expired
from app.agents.chat_orchestrator import get_skills_list, process_confirm, process_message
import app.agents.chat_memory as _mem
from app.core.database import AsyncSessionLocal, get_db
from app.dependencies import get_current_user
from app.models.chat import (
    ChatConfirmRequest,
    ChatConfirmResponse,
    ChatMessageSendRequest,
    ChatMessageSendResponse,
    ChatSessionCreateRequest,
    ChatSessionCreateResponse,
    ChatSessionDetailResponse,
    ChatSessionListResponse,
    ChatSessionSearchResponse,
)
from app.models.user import User
from app.services import chat_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ── POST /chat/sessions ────────────────────────────────────────────────────────

@router.post(
    "/sessions",
    response_model=ChatSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新的 Chat Session",
)
async def create_chat_session(
    body: ChatSessionCreateRequest,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ChatSessionCreateResponse:
    return await chat_service.create_session(db, user.id, body.title)


# ── GET /chat/sessions ─────────────────────────────────────────────────────────

@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    summary="列出当前用户的 Chat Sessions",
)
async def list_chat_sessions(
    limit:  int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ChatSessionListResponse:
    items, total = await chat_service.list_sessions(db, user.id, limit, offset)
    return ChatSessionListResponse(items=items, total=total)


# ── GET /chat/sessions/search ─────────────────────────────────────────────────
# NOTE: this route MUST be declared before /{session_id} so FastAPI doesn't
# treat "search" as a session UUID.

@router.get(
    "/sessions/search",
    response_model=ChatSessionSearchResponse,
    summary="C32.4: 搜索 Chat Sessions（关键词 + 时间筛选）",
)
async def search_chat_sessions(
    q:           str | None       = Query(default=None, max_length=200, description="关键词"),
    date_ranges: list[str] | None = Query(default=None, description="today/yesterday/7days/30days/month"),
    start_date:  datetime | None  = Query(default=None, description="自定义起始时间 (ISO)"),
    end_date:    datetime | None  = Query(default=None, description="自定义结束时间 (ISO)"),
    limit:  int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ChatSessionSearchResponse:
    # Validate date_ranges values
    _VALID_RANGES = {"today", "yesterday", "7days", "30days", "month"}
    if date_ranges:
        invalid = [r for r in date_ranges if r not in _VALID_RANGES]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"无效的 date_ranges 值：{invalid}。支持：{sorted(_VALID_RANGES)}",
            )
    items, total = await chat_service.search_sessions(
        db,
        user.id,
        q           = q,
        date_from   = start_date,
        date_to     = end_date,
        date_ranges = date_ranges,
        limit       = limit,
        offset      = offset,
    )
    return ChatSessionSearchResponse(items=items, total=total)


# ── GET /chat/sessions/{session_id} ───────────────────────────────────────────

@router.get(
    "/sessions/{session_id}",
    response_model=ChatSessionDetailResponse,
    summary="获取 Session 详情（含历史消息）",
)
async def get_chat_session(
    session_id: uuid.UUID,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ChatSessionDetailResponse:
    session, messages = await chat_service.get_session_with_messages(
        db, session_id, user.id
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session '{session_id}' not found",
        )
    return ChatSessionDetailResponse(
        session_id=session.id,
        title=session.title,
        status=session.status,
        messages=messages,
    )


# ── POST /chat/sessions/{session_id}/messages ──────────────────────────────────

@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageSendResponse,
    summary="发送消息（Real Tool Orchestrator 同步响应）",
)
async def send_chat_message(
    session_id: uuid.UUID,
    body: ChatMessageSendRequest,
    request: Request = None,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ChatMessageSendResponse:
    # Acceptance-only shadow correlation (no-op unless shadow executor mode).
    from app.agent_runtime.shadow_correlation import (  # noqa: PLC0415
        SHADOW_CORRELATION_HEADER,
        set_correlation_from_header,
    )

    set_correlation_from_header(
        request.headers.get(SHADOW_CORRELATION_HEADER) if request is not None else None
    )
    # Verify session belongs to user
    session = await chat_service.get_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session '{session_id}' not found",
        )

    # 1. Save user message
    user_msg = await chat_service.save_user_message(
        db, session_id, user.id, body.content, body.output_language
    )

    # 2. Run orchestrator with real tools (C8: pass session_id for memory writes)
    result = await process_message(body.content, db, user.id, body.output_language, session_id=session_id)

    # 3. Save assistant message
    asst_msg = await chat_service.save_assistant_message(
        db=db,
        session_id=session_id,
        user_id=user.id,
        answer=result.answer,
        tool_events=result.tool_events,
        cards=result.cards,
        confirmation=result.confirmation,
        output_language=body.output_language,
        extra_metadata=result.metadata,  # C6: skill audit trail
    )

    # 4. Update session timestamps and commit
    await chat_service.update_session_last_message(db, session_id)
    await db.commit()

    public_meta = {
        key: value
        for key, value in {
            "response_kind": (result.metadata or {}).get("response_kind"),
            "clarification": (result.metadata or {}).get("clarification"),
        }.items()
        if value
    }
    return ChatMessageSendResponse(
        message_id=user_msg.id,
        assistant_message_id=asst_msg.id,
        status="completed",
        answer=result.answer,
        tool_events=result.tool_events,
        cards=result.cards,
        confirmation=result.confirmation,
        metadata=public_meta or None,
    )


# ── POST /chat/sessions/{session_id}/messages/stream ──────────────────────────

@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="发送消息（SSE 流式响应 — C13-a）",
)
async def send_chat_message_stream(
    session_id: uuid.UUID,
    body: ChatMessageSendRequest,
    request: Request,
    user: User         = Depends(get_current_user),
) -> StreamingResponse:
    """
    SSE streaming version of send_chat_message.

    Returns text/event-stream.  Each event is a JSON-encoded ChatStreamEvent:
      { event_type, sequence, message_id, payload, created_at }

    Event types (in order):
      user_message_saved, agent_started, assistant_placeholder_created,
      intent_detected, skill_started, skill_completed, tool_completed,
      confirmation_required, cards_delta, answer_delta, agent_completed,
      agent_error, keepalive

    The synchronous POST /messages endpoint remains unchanged as fallback.

    Security:
      - Requires Bearer token (same as all other chat endpoints).
      - User can only stream to their own sessions (404 on mismatch).
      - answer_delta carries only the final answer text — no private CoT.
      - tool_completed carries tool_name / status / summary only.
    """
    from app.agents.chat_streaming import stream_chat_message
    from app.agent_runtime.shadow_correlation import (  # noqa: PLC0415
        SHADOW_CORRELATION_HEADER,
        set_correlation_from_header,
    )

    # Acceptance-only shadow correlation (no-op unless shadow executor mode).
    set_correlation_from_header(request.headers.get(SHADOW_CORRELATION_HEADER))

    # Verify session belongs to user in a short transaction.  Do not keep a
    # request-scoped AsyncSession alive for the StreamingResponse lifetime.
    try:
        async with AsyncSessionLocal() as verify_db:
            session = await asyncio.wait_for(
                chat_service.get_session(verify_db, session_id, user.id),
                timeout=10.0,
            )
            await asyncio.wait_for(verify_db.rollback(), timeout=3.0)
    except (
        asyncio.TimeoutError,
        TimeoutError,
        SQLAlchemyTimeoutError,
        OperationalError,
        DBAPIError,
        SQLAlchemyError,
        OSError,
    ) as exc:
        log.warning(
            "chat_stream_session_verification_failed session=%s error_class=%s connection_invalidated=%s raised_at=app.routers.chat:send_chat_message_stream",
            session_id,
            type(exc).__name__,
            bool(getattr(exc, "connection_invalidated", False)),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "failed",
                "error_code": "CHAT_SESSION_VERIFICATION_DATABASE_UNAVAILABLE",
                "message": "会话验证服务暂时不可用，请稍后重试。",
                "retryable": True,
            },
        ) from None
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session '{session_id}' not found",
        )

    output_language = body.output_language

    async def event_generator():
        async for chunk in stream_chat_message(
            session_id=session_id,
            user_id=user.id,
            content=body.content,
            output_language=output_language,
        ):
            # Stop if client disconnected
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ── POST /chat/sessions/{session_id}/confirm ───────────────────────────────────

@router.post(
    "/sessions/{session_id}/confirm",
    response_model=ChatConfirmResponse,
    summary="确认或取消 Pending Action（C5 Real Execution）",
)
async def confirm_chat_action(
    session_id: uuid.UUID,
    body: ChatConfirmRequest,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> ChatConfirmResponse:
    # Verify session belongs to user
    session = await chat_service.get_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session '{session_id}' not found",
        )

    # Find the assistant message with the matching confirmation
    pending_msg = await chat_service.find_pending_confirmation(
        db, session_id, user.id, body.confirmation_id
    )
    if pending_msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"confirmation '{body.confirmation_id}' not found in session",
        )

    conf = pending_msg.confirmation or {}

    # Guard: reject non-pending confirmations (idempotency)
    if conf.get("status") != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"confirmation '{body.confirmation_id}' already processed (status={conf.get('status')})",
        )

    # Guard: reject expired confirmations
    if is_expired(conf):
        await chat_service.update_confirmation_status(
            db, pending_msg.id, "expired",
            extra={"error": "操作已超时，请重新发起请求。"},
        )
        await db.commit()
        return ChatConfirmResponse(
            status="expired",
            answer="",
            tool_events=[],
            cards=[],
        )

    if not body.confirmed:
        # User cancelled — mark as cancelled in DB
        await chat_service.update_confirmation_status(
            db, pending_msg.id, "cancelled",
        )
        await db.commit()
        return ChatConfirmResponse(
            status="cancelled",
            answer="",
            tool_events=[],
            cards=[],
        )

    # Mark as confirmed + executing
    now_iso = datetime.now(timezone.utc).isoformat()
    await chat_service.update_confirmation_status(
        db, pending_msg.id, "executing",
        extra={"confirmed_at": now_iso},
    )
    await db.flush()

    # Resolve output_language from originating message metadata
    output_language = (pending_msg.msg_metadata or {}).get("output_language", "zh-CN")

    # Execute real action
    result = await process_confirm(
        confirmation_type=conf.get("type", ""),
        params=conf.get("params", {}),
        db=db,
        user_id=user.id,
        output_language=output_language,
    )

    # Mark confirmation as executed or failed
    executed_iso = datetime.now(timezone.utc).isoformat()
    await chat_service.update_confirmation_status(
        db, pending_msg.id, "executed",
        extra={"executed_at": executed_iso},
    )

    # Save follow-up assistant message
    await chat_service.save_assistant_message(
        db=db,
        session_id=session_id,
        user_id=user.id,
        answer=result.answer,
        tool_events=result.tool_events,
        cards=result.cards,
        confirmation=None,
        output_language=output_language,
    )
    await chat_service.update_session_last_message(db, session_id)
    await db.commit()

    return ChatConfirmResponse(
        status="confirmed",
        answer=result.answer,
        tool_events=result.tool_events,
        cards=result.cards,
    )


# ── DELETE /chat/sessions/{session_id} ────────────────────────────────────────

@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="软删除 Session",
)
async def delete_chat_session(
    session_id: uuid.UUID,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> None:
    found = await chat_service.soft_delete_session(db, session_id, user.id)
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session '{session_id}' not found",
        )


# ── GET /chat/sessions/{session_id}/memory ────────────────────────────────────

@router.get(
    "/sessions/{session_id}/memory",
    summary="获取 Session 结构化记忆（C8）",
)
async def get_session_memory(
    session_id: uuid.UUID,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """
    Return the structured memory for a chat session.
    Only accessible by the session owner.
    Used for debugging, demo, and frontend context panel.
    """
    session = await chat_service.get_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session '{session_id}' not found",
        )
    memory = await _mem.get_memory(db, session_id, user.id)
    return {"session_id": str(session_id), "memory": memory}


# ── POST /chat/sessions/{session_id}/memory/clear ─────────────────────────────

@router.post(
    "/sessions/{session_id}/memory/clear",
    status_code=status.HTTP_200_OK,
    summary="清空 Session 记忆（不删消息）（C8）",
)
async def clear_session_memory(
    session_id: uuid.UUID,
    user: User         = Depends(get_current_user),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """
    Reset the structured memory of a session to empty.
    Messages are preserved. Only the memory_v1 key in session_metadata is cleared.
    """
    session = await chat_service.get_session(db, session_id, user.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"session '{session_id}' not found",
        )
    cleared = await _mem.clear_memory(db, session_id, user.id)
    return {"session_id": str(session_id), "cleared": cleared}


# ── GET /chat/skills ──────────────────────────────────────────────────────────

@router.get(
    "/skills",
    status_code=status.HTTP_200_OK,
    summary="列出当前 Agent 可用技能（C9 Skill Discovery）",
)
async def list_chat_skills(
    user: User = Depends(get_current_user),
) -> dict:
    """
    Return the list of registered financial research skills and their spec metadata.

    - Requires auth (Bearer token).
    - Returns only public metadata: name, display_name, description, enabled, available,
      required_tools, safety_rules.
    - Does NOT expose internal prompts or implementation details.
    - Frontend uses this for the ChatContextPanel "Agent Skills" section.
    """
    items = get_skills_list()
    return {"items": items}
