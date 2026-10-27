"""Historical invite audit API. GET remains admin-only and never returns hashes.

Invite creation/revocation are retired (410) even for administrators. No invite
row is deleted or consumed by Google-only admission.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_rate_limit import disabled_auth_method
from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_admin_user
from app.models.mvp import MvpInvite
from app.services.invite_hasher import hash_invite_code as _hash_invite_code_impl

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/invites", tags=["admin"])

_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _hash_invite_code(code: str) -> str:
    return _hash_invite_code_impl(code, settings)


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

@router.post("", status_code=410, deprecated=True)
async def create_invite(admin=Depends(get_admin_user)):
    disabled_auth_method()


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


@router.post("/{invite_id}/revoke", status_code=410, deprecated=True)
async def revoke_invite(invite_id: str, admin=Depends(get_admin_user)):
    disabled_auth_method()
