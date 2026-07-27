"""
Auth router — MVP-R1.3.

Changes vs MVP-R1.2:
  POST /auth/email-verification/request — send 6-digit code (validates invite, rate-limited)
  POST /auth/register — optionally requires email_verification_code when
                        settings.email_verification_required=True
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.mvp import MvpInvite
from app.models.user import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    User,
    UserPublic,
)
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_invite_code(code: str) -> str:
    """Return SHA-256 hex digest of a plaintext invite code."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


# ── Email verification request schema ─────────────────────────────────────────

class EmailVerificationRequest(BaseModel):
    email: EmailStr
    invite_code: str = Field(min_length=8, max_length=64)


class EmailVerificationResponse(BaseModel):
    ok: bool
    message: str
    retry_after: int = 0   # seconds until next send is allowed


# ── Email verification request endpoint ───────────────────────────────────────

@router.post(
    "/email-verification/request",
    response_model=EmailVerificationResponse,
)
async def request_email_verification(
    body: EmailVerificationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a 6-digit verification code to the email address.

    - Validates that the invite code exists and is unused (does NOT consume it).
    - Rate limited: 60s cooldown, max 5 per hour per email.
    - Uses generic responses to avoid leaking whether email is registered.
    """
    # ── Validate invite code without consuming ────────────────────────────────
    raw_code = body.invite_code.strip()
    normalized_code = raw_code.upper() if len(raw_code) == 8 else raw_code
    code_hash = _hash_invite_code(normalized_code)

    result = await db.execute(
        select(MvpInvite).where(MvpInvite.code_hash == code_hash)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邀请码无效。")
    if invite.expires_at and invite.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邀请码已过期。")
    if invite.use_count >= invite.max_uses:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邀请码已被使用。")
    if invite.email and invite.email.lower() != str(body.email).lower():
        # Generic error — don't reveal email binding details
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "邀请码无效。")

    # ── Generate code and enforce rate limits ────────────────────────────────
    from app.services import email_verification as ev_service
    from app.services.email_sender import get_email_sender

    try:
        send_result = await ev_service.request_verification_code(str(body.email))
    except RuntimeError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))

    if not send_result.ok:
        return EmailVerificationResponse(
            ok=False,
            message=send_result.message,
            retry_after=send_result.retry_after,
        )

    # The plaintext code is in send_result.message — send it, never log it
    plaintext_code = send_result.message
    try:
        sender = get_email_sender()
        await sender.send_verification(str(body.email), plaintext_code)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Email send failed: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "邮件发送失败，请稍后再试。",
        )

    return EmailVerificationResponse(ok=True, message="验证码已发送，请查收邮件。")


# ── Register endpoint ─────────────────────────────────────────────────────────

@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user.  An unused, valid invite code is required.

    When settings.email_verification_required=True, a valid email_verification_code
    must also be provided and will be consumed atomically.

    Atomic transaction:
      [verify email code] → SELECT FOR UPDATE invite → validate → INSERT user
      → set email_verified_at → consume invite → COMMIT → [delete Redis code]
    """
    # ── Normalize invite code ─────────────────────────────────────────────────
    raw_code = body.invite_code.strip()
    normalized_code = raw_code.upper() if len(raw_code) == 8 else raw_code
    code_hash = _hash_invite_code(normalized_code)

    # ── Email verification check (when required) ──────────────────────────────
    email_verified_now = False
    if settings.email_verification_required:
        if not body.email_verification_code:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "邮箱验证码不能为空。",
            )
        from app.services import email_verification as ev_service
        try:
            vr = await ev_service.verify_code(str(body.email), body.email_verification_code)
        except RuntimeError as e:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))
        if not vr.ok:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, vr.message)
        email_verified_now = True
    elif body.email_verification_code:
        # Optional: if the user provides a code even when not required, verify it
        from app.services import email_verification as ev_service
        try:
            vr = await ev_service.verify_code(str(body.email), body.email_verification_code)
            email_verified_now = vr.ok
        except RuntimeError:
            pass  # Redis unavailable — treat as no verification

    # ── Lock and validate invite ──────────────────────────────────────────────
    result = await db.execute(
        select(MvpInvite)
        .where(MvpInvite.code_hash == code_hash)
        .with_for_update()
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid invite code.")

    if invite.expires_at and invite.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite code has expired.")

    if invite.use_count >= invite.max_uses:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite code has already been used.")

    if invite.email and invite.email.lower() != str(body.email).lower():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This invite code is bound to a different email address.",
        )

    # ── Check username/email uniqueness ───────────────────────────────────────
    dup = await db.execute(
        select(User).where(or_(User.username == body.username, User.email == str(body.email)))
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists.")

    # ── Create user + consume invite in single transaction ────────────────────
    user = User(
        username=body.username,
        email=str(body.email),
        hashed_password=hash_password(body.password),
        email_verified_at=datetime.now(timezone.utc) if email_verified_now else None,
    )
    db.add(user)
    await db.flush()

    invite.use_count += 1
    if invite.use_count >= invite.max_uses:
        invite.redeemed = True
        invite.redeemed_at = datetime.utcnow()
    invite.redeemed_by_user_id = user.id

    await db.commit()
    await db.refresh(user)

    # ── Post-commit: clean up Redis verification keys ─────────────────────────
    if email_verified_now:
        try:
            from app.services import email_verification as ev_service
            await ev_service.consume_code(str(body.email))
        except Exception:
            pass  # non-fatal: keys expire via TTL anyway

    return UserPublic.from_orm_user(user)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Login with username OR email.

    The `username` field accepts either a username or an email address.
    If the value contains '@' it is treated as an email lookup.
    """
    login_value = body.username.strip()

    if "@" in login_value:
        stmt = select(User).where(User.email == login_value)
    else:
        stmt = select(User).where(User.username == login_value)

    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account disabled")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not a refresh token")

    user_id = payload["sub"]
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.get("/me", response_model=UserPublic)
async def me(current_user=Depends(get_current_user)):
    # current_user is AuthPrincipal — reconstruct a minimal UserPublic
    return UserPublic(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        is_admin=getattr(current_user, "is_admin", False),
        email_verified=getattr(current_user, "email_verified", False),
        created_at=getattr(current_user, "created_at", None) or datetime.utcnow(),
    )
