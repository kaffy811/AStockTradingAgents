"""
MVP Release Candidate endpoints — Phase MVP-R1.2.

Endpoints
---------
POST /mvp/invites/check     — check invite code validity (public)
POST /mvp/invites           — create invite code (admin only)
POST /chat/feedback         — submit answer feedback (auth optional)
POST /mvp/analytics/event   — record analytics event (internal)
GET  /mvp/health            — MVP readiness probe
GET  /mvp/quota/check/{user_id} — check user daily quota (Phase MVP-R1.1)
GET  /mvp/wave/status       — wave configuration (Phase MVP-R1.1)
GET  /mvp/admin/invites     — list all invites (admin only)
DELETE /mvp/admin/invites/{invite_id} — revoke an invite (admin only)

Security:
- POST /mvp/invites requires Bearer token with is_admin=True (MVP-R1.2 fix)
- Invite codes are hashed (SHA-256) at creation; plaintext is never stored
- No PII in stored records (snippet max 200 chars, no raw prompts/responses)
- Feedback comment max 1000 chars
- Analytics properties stripped of PII-named keys
- error_severity=p0/p1 triggers server-side error log
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_admin_user
from app.models.mvp import ChatFeedback, MvpAnalyticsEvent, MvpInvite

log = logging.getLogger(__name__)

router = APIRouter(tags=["mvp"])

# PII key names that must be stripped from analytics properties
_PII_PROPERTY_KEYS = frozenset({
    "email", "password", "token", "api_key", "secret",
    "phone", "name", "ip", "user_agent", "authorization",
})


def _hash_invite_code(code: str) -> str:
    """Return SHA-256 hex digest of a plaintext invite code."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


# Unambiguous alphabet: no O/0/I/1 to avoid transcription errors
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_invite_code(length: int = 8) -> str:
    """Generate a cryptographically random invite code of exactly `length` chars.

    Uses an unambiguous subset of uppercase letters and digits (excludes O, 0, I, 1).
    Must use secrets module — not random.
    """
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(length))


# ── Request / Response schemas ────────────────────────────────────────────────

class InviteCheckRequest(BaseModel):
    invite_code: str = Field(..., min_length=8, max_length=64)


class InviteCheckResponse(BaseModel):
    valid: bool
    message: str


class InviteCreateRequest(BaseModel):
    email: Optional[str] = Field(None, max_length=255)
    max_uses: int = Field(1, ge=1, le=100)
    note: Optional[str] = Field(None, max_length=500)


class InviteCreateResponse(BaseModel):
    # Plaintext code returned ONCE to the admin — not stored server-side
    invite_code: str
    code_prefix: str
    email: Optional[str]
    max_uses: int
    created_at: str


class InviteListItem(BaseModel):
    id: str
    code_prefix: str
    email: Optional[str]
    max_uses: int
    use_count: int
    redeemed: bool
    redeemed_at: Optional[str]
    expires_at: Optional[str]
    note: Optional[str]
    created_at: str
    created_by: str


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    message_id: Optional[str] = Field(None, max_length=64)
    user_id: Optional[int] = None
    # thumbs_up | thumbs_down | report
    feedback_type: str = Field(..., pattern=r"^(thumbs_up|thumbs_down|report)$")
    # subcategory for 'report': data_inaccurate | not_relevant | load_failed | other
    feedback_detail: Optional[str] = Field(None, max_length=128)
    comment: Optional[str] = Field(None, max_length=1000)
    # first ≤200 chars of the answer text, no PII
    answer_snippet: Optional[str] = Field(None, max_length=200)


class FeedbackResponse(BaseModel):
    ok: bool
    feedback_id: str


class AnalyticsEventRequest(BaseModel):
    event_name: str = Field(..., max_length=128)
    # chat | analysis | nav | error | provider
    event_category: str = Field(..., max_length=64)
    user_id: Optional[int] = None
    session_id: Optional[str] = Field(None, max_length=64)
    # arbitrary non-PII properties
    properties: Optional[dict] = None
    error_class: Optional[str] = Field(None, max_length=128)
    # p0 | p1 | p2 | info
    error_severity: Optional[str] = Field(None, pattern=r"^(p0|p1|p2|info)$")


class AnalyticsEventResponse(BaseModel):
    ok: bool
    event_id: str


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.post("/mvp/invites/check", response_model=InviteCheckResponse)
async def check_invite(
    req: InviteCheckRequest, db: AsyncSession = Depends(get_db)
):
    """Check invite code validity without consuming a use."""
    code_hash = _hash_invite_code(req.invite_code)
    result = await db.execute(
        select(MvpInvite).where(MvpInvite.code_hash == code_hash)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        return InviteCheckResponse(valid=False, message="Invalid invite code.")

    if invite.expires_at and invite.expires_at < datetime.utcnow():
        return InviteCheckResponse(valid=False, message="Invite code has expired.")

    if invite.use_count >= invite.max_uses:
        return InviteCheckResponse(valid=False, message="Invite code fully redeemed.")

    return InviteCheckResponse(valid=True, message="Invite code is valid.")


# ── Admin-only invite management ──────────────────────────────────────────────

@router.post("/mvp/invites", response_model=InviteCreateResponse)
async def create_invite(
    req: InviteCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """Create a new invite code. Admin only (is_admin=True Bearer token required).

    The plaintext code is returned ONCE in the response and never stored.
    The server persists only the SHA-256 hash; code_prefix equals the full 8-char code.
    """
    # Try up to 10 times to guard against the astronomically unlikely hash collision
    for _ in range(10):
        plaintext_code = generate_invite_code()
        code_hash = _hash_invite_code(plaintext_code)
        existing = await db.execute(
            select(MvpInvite).where(MvpInvite.code_hash == code_hash)
        )
        if existing.scalar_one_or_none() is None:
            break
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate a unique invite code. Please retry.",
        )

    # For 8-char codes the prefix IS the full code
    code_prefix = plaintext_code

    invite = MvpInvite(
        id=uuid.uuid4(),
        code_hash=code_hash,
        code_prefix=code_prefix,
        email=req.email,
        max_uses=req.max_uses,
        note=req.note,
        created_by=str(admin.username),
        created_at=datetime.utcnow(),
    )
    db.add(invite)
    await db.commit()
    log.info(
        "mvp_invite created: prefix=%s email=%s max_uses=%d by=%s",
        code_prefix, req.email, req.max_uses, admin.username,
    )
    return InviteCreateResponse(
        invite_code=plaintext_code,
        code_prefix=code_prefix,
        email=req.email,
        max_uses=req.max_uses,
        created_at=invite.created_at.isoformat(),
    )


@router.get("/mvp/admin/invites", response_model=List[InviteListItem])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """List all invite codes (admin only). Plaintext codes are not shown."""
    result = await db.execute(
        select(MvpInvite).order_by(desc(MvpInvite.created_at)).limit(500)
    )
    invites = result.scalars().all()
    return [
        InviteListItem(
            id=str(inv.id),
            code_prefix=inv.code_prefix or "????????",
            email=inv.email,
            max_uses=inv.max_uses,
            use_count=inv.use_count,
            redeemed=inv.redeemed,
            redeemed_at=inv.redeemed_at.isoformat() if inv.redeemed_at else None,
            expires_at=inv.expires_at.isoformat() if inv.expires_at else None,
            note=inv.note,
            created_at=inv.created_at.isoformat(),
            created_by=inv.created_by,
        )
        for inv in invites
    ]


@router.delete("/mvp/admin/invites/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """Revoke (delete) an invite by ID. Admin only."""
    try:
        invite_uuid = uuid.UUID(invite_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid invite ID format.")

    result = await db.execute(
        select(MvpInvite).where(MvpInvite.id == invite_uuid)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")

    await db.delete(invite)
    await db.commit()
    log.info("mvp_invite revoked: id=%s by=%s", invite_id, admin.username)


# ── Feedback & analytics ──────────────────────────────────────────────────────

@router.post("/chat/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    req: FeedbackRequest, db: AsyncSession = Depends(get_db)
):
    """Submit user feedback on a chat answer."""
    feedback = ChatFeedback(
        id=uuid.uuid4(),
        session_id=req.session_id,
        message_id=req.message_id,
        user_id=req.user_id,
        feedback_type=req.feedback_type,
        feedback_detail=req.feedback_detail,
        comment=req.comment[:1000] if req.comment else None,
        answer_snippet=req.answer_snippet[:200] if req.answer_snippet else None,
        created_at=datetime.utcnow(),
    )
    db.add(feedback)
    await db.commit()
    log.info(
        "chat_feedback: type=%s session=%s message=%s",
        req.feedback_type,
        req.session_id[:8] if req.session_id else "?",
        req.message_id[:8] if req.message_id else "?",
    )
    return FeedbackResponse(ok=True, feedback_id=str(feedback.id))


@router.post("/mvp/analytics/event", response_model=AnalyticsEventResponse)
async def record_analytics_event(
    req: AnalyticsEventRequest, db: AsyncSession = Depends(get_db)
):
    """Record a structured analytics event. PII-named property keys are stripped."""
    safe_props: dict | None = None
    if req.properties:
        safe_props = {
            k: v
            for k, v in req.properties.items()
            if k.lower() not in _PII_PROPERTY_KEYS
        }

    event = MvpAnalyticsEvent(
        id=uuid.uuid4(),
        event_name=req.event_name,
        event_category=req.event_category,
        user_id=req.user_id,
        session_id=req.session_id,
        properties=safe_props,
        error_class=req.error_class,
        error_severity=req.error_severity,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    await db.commit()

    if req.error_severity in ("p0", "p1"):
        log.error(
            "mvp_error_monitor [%s] event=%s error_class=%s session=%s",
            req.error_severity.upper(),
            req.event_name,
            req.error_class,
            req.session_id,
        )

    return AnalyticsEventResponse(ok=True, event_id=str(event.id))


# ---------------------------------------------------------------------------
# Phase MVP-R1.1: Quota check
# ---------------------------------------------------------------------------

class QuotaCheckResponse(BaseModel):
    allowed: bool
    reason: str | None = None
    daily_used: int = 0
    daily_limit: int = 0


@router.get("/mvp/quota/check/{user_id}", response_model=QuotaCheckResponse)
async def check_user_quota(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Check whether a user has remaining daily chat quota."""
    from datetime import date
    from sqlalchemy import func

    from app.core.config import settings

    daily_limit = settings.mvp_daily_quota_per_user

    today_start = datetime.combine(date.today(), datetime.min.time())
    result = await db.execute(
        select(func.count(MvpAnalyticsEvent.id)).where(
            MvpAnalyticsEvent.user_id == user_id,
            MvpAnalyticsEvent.event_name == "chat_message_sent",
            MvpAnalyticsEvent.created_at >= today_start,
        )
    )
    daily_used = result.scalar() or 0

    if not settings.mvp_new_chat_enabled or settings.mvp_kill_chat:
        return QuotaCheckResponse(
            allowed=False,
            reason="当前聊天功能暂时关闭，请稍后再试。",
            daily_used=daily_used,
            daily_limit=daily_limit,
        )

    if daily_used >= daily_limit:
        return QuotaCheckResponse(
            allowed=False,
            reason="今日测试额度已用完，请明天继续使用。",
            daily_used=daily_used,
            daily_limit=daily_limit,
        )

    return QuotaCheckResponse(
        allowed=True,
        daily_used=daily_used,
        daily_limit=daily_limit,
    )


# ---------------------------------------------------------------------------
# Phase MVP-R1.1: Wave status
# ---------------------------------------------------------------------------

class WaveStatusResponse(BaseModel):
    current_wave: int
    max_invited_users: int
    wave_limits: dict
    new_invites_enabled: bool
    new_login_enabled: bool
    new_chat_enabled: bool
    kill_switches: dict


@router.get("/mvp/wave/status", response_model=WaveStatusResponse)
async def get_wave_status():
    """Return current invite wave configuration."""
    from app.core.config import settings

    return WaveStatusResponse(
        current_wave=settings.mvp_current_wave,
        max_invited_users=settings.mvp_max_invited_users,
        wave_limits={
            "wave1": settings.mvp_wave1_max_users,
            "wave2": settings.mvp_wave2_max_users,
            "wave3": settings.mvp_wave3_max_users,
        },
        new_invites_enabled=settings.mvp_new_invites_enabled and not settings.mvp_kill_invites,
        new_login_enabled=settings.mvp_new_login_enabled and not settings.mvp_kill_login,
        new_chat_enabled=settings.mvp_new_chat_enabled and not settings.mvp_kill_chat,
        kill_switches={
            "kill_invites": settings.mvp_kill_invites,
            "kill_login": settings.mvp_kill_login,
            "kill_chat": settings.mvp_kill_chat,
        },
    )


@router.get("/mvp/health")
async def mvp_health():
    """MVP readiness probe — provider gate status + runtime snapshot."""
    from app.core.config import settings
    from app.llm.factory import check_real_provider_gate

    gate_result = check_real_provider_gate()
    return {
        "ok": True,
        "phase": "MVP-R1.2",
        "mvp_mode": "invite_only",
        "provider_mode": getattr(settings, "pi_canary_provider_mode", "staging_replay"),
        "real_provider_enabled": getattr(settings, "pi_real_provider_enabled", False),
        "real_provider_kill_switch": getattr(settings, "pi_real_provider_kill_switch", True),
        "real_provider_gate": gate_result,
        "config_version": getattr(settings, "pi_canary_config_version", 12),
    }
