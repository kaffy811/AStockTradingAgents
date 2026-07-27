"""
Admin Invite management — Phase MVP-R1.3.

Routes (all require Bearer token with is_admin=True):
  POST   /api/v1/admin/invites               — create invite code
  GET    /api/v1/admin/invites               — list all invites (prefix only)
  POST   /api/v1/admin/invites/{id}/revoke   — revoke (mark used / delete)

Security:
  - All endpoints require get_admin_user dependency (403 for non-admin)
  - GET never returns plaintext invite codes — only code_prefix
  - POST returns the plaintext code ONCE and never stores it

The legacy /mvp/invites endpoints remain functional for backwards compatibility
but are superseded by this router for frontend usage.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.dependencies import get_admin_user
from app.models.mvp import MvpInvite

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/invites", tags=["admin"])

_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _hash_invite_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_invite_code(length: int = 8) -> str:
    return "".join(secrets.choice(_INVITE_ALPHABET) for _ in range(length))


# ── Schemas ───────────────────────────────────────────────────────────────────

class AdminInviteCreateRequest(BaseModel):
    email: Optional[str] = Field(None, max_length=255)
    max_uses: int = Field(1, ge=1, le=100)
    note: Optional[str] = Field(None, max_length=500)
    expires_at: Optional[datetime] = None


class AdminInviteCreateResponse(BaseModel):
    invite_code: str        # plaintext — returned ONCE, never stored
    code_prefix: str
    email: Optional[str]
    max_uses: int
    created_at: str
    expires_at: Optional[str]


class AdminInviteListItem(BaseModel):
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


class RevokeResponse(BaseModel):
    ok: bool
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=AdminInviteCreateResponse, status_code=201)
async def create_invite(
    req: AdminInviteCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """Create a new 8-char invite code. Plaintext returned once; DB stores only hash."""
    for _ in range(10):
        plaintext_code = _generate_invite_code()
        code_hash = _hash_invite_code(plaintext_code)
        existing = await db.execute(
            select(MvpInvite).where(MvpInvite.code_hash == code_hash)
        )
        if existing.scalar_one_or_none() is None:
            break
    else:
        raise HTTPException(
            status_code=500,
            detail="生成唯一邀请码失败，请重试。",
        )

    # Store only first 4 chars as prefix — never the full 8-char code in DB.
    code_prefix = plaintext_code[:4]

    invite = MvpInvite(
        id=uuid.uuid4(),
        code_hash=code_hash,
        code_prefix=code_prefix,
        email=req.email,
        max_uses=req.max_uses,
        note=req.note,
        expires_at=req.expires_at,
        created_by=str(admin.username),
        created_at=datetime.utcnow(),
    )
    db.add(invite)
    await db.commit()
    log.info(
        "admin_invite created: prefix=%s email=%s max_uses=%d by=%s",
        code_prefix, req.email, req.max_uses, admin.username,
    )
    return AdminInviteCreateResponse(
        invite_code=plaintext_code,   # plaintext returned ONCE — never stored
        code_prefix=code_prefix,
        email=req.email,
        max_uses=req.max_uses,
        created_at=invite.created_at.isoformat(),
        expires_at=req.expires_at.isoformat() if req.expires_at else None,
    )


@router.get("", response_model=List[AdminInviteListItem])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """List all invite codes — returns code_prefix only, never plaintext."""
    result = await db.execute(
        select(MvpInvite).order_by(desc(MvpInvite.created_at)).limit(500)
    )
    invites = result.scalars().all()
    return [
        AdminInviteListItem(
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


@router.post("/{invite_id}/revoke", response_model=RevokeResponse)
async def revoke_invite(
    invite_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """Revoke an invite code by ID. Revoked codes can no longer be used."""
    try:
        invite_uuid = uuid.UUID(invite_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的邀请码 ID。")

    result = await db.execute(
        select(MvpInvite).where(MvpInvite.id == invite_uuid)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail="邀请码不存在。")
    if invite.redeemed:
        raise HTTPException(status_code=409, detail="邀请码已被使用，无法撤销。")

    await db.delete(invite)
    await db.commit()
    log.info("admin_invite revoked: id=%s by=%s", invite_id, admin.username)
    return RevokeResponse(ok=True, message="邀请码已撤销。")
