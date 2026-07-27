"""
Auth router — MVP-R1.2.

Changes vs MVP-R1.1:
  POST /auth/register — requires invite_code; redeems it atomically in the same
                        DB transaction as user creation (no TOCTOU race).
  POST /auth/login    — accepts username OR email in the `username` field.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user.  An unused, valid invite code is required.

    Atomic transaction:
      SELECT FOR UPDATE invite → validate → INSERT user → consume invite → COMMIT
    """
    # Normalize invite code before hashing:
    # - Strip surrounding whitespace (copy-paste artifact)
    # - 8-char new-format codes: uppercase so "7kmr9x2p" == "7KMR9X2P"
    # - Longer legacy codes (48-char URL-safe): preserve original case
    raw_code = body.invite_code.strip()
    normalized_code = raw_code.upper() if len(raw_code) == 8 else raw_code
    code_hash = _hash_invite_code(normalized_code)

    # ── Lock and validate invite ───────────────────────────────────────────────
    # Use SELECT FOR UPDATE to prevent concurrent redemption of the same code.
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

    # If the invite was bound to a specific email, enforce that binding
    if invite.email and invite.email.lower() != body.email.lower():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "This invite code is bound to a different email address.",
        )

    # ── Check username/email uniqueness ────────────────────────────────────────
    dup = await db.execute(
        select(User).where(or_(User.username == body.username, User.email == body.email))
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists.")

    # ── Create user + consume invite in single transaction ────────────────────
    user = User(
        username=body.username,
        email=body.email,
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    # Flush to get user.id before we reference it in the invite
    await db.flush()

    invite.use_count += 1
    if invite.use_count >= invite.max_uses:
        invite.redeemed = True
        invite.redeemed_at = datetime.utcnow()
    invite.redeemed_by_user_id = user.id

    await db.commit()
    await db.refresh(user)
    return UserPublic.model_validate(user)


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
    from uuid import UUID
    return UserPublic(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        is_admin=getattr(current_user, "is_admin", False),
        created_at=current_user.created_at or datetime.utcnow(),
    )
