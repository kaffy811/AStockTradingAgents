"""Google subject is the only login identity. Email never grants ownership."""
import asyncio
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.config import settings
from app.models.user import User
from app.services.auth_rate_limit import auth_error, enforce_auth_limit


async def _by_subject(db: AsyncSession, sub: str):
    return (await db.execute(select(User).where(User.google_sub == sub).with_for_update())).scalar_one_or_none()


def _check_active(user: User) -> User:
    if not user.is_active:
        raise auth_error(403, 'ACCOUNT_DISABLED', '账户已停用，请联系管理员。')
    return user


async def resolve_google_account(db: AsyncSession, claims: dict, ip: str) -> User:
    sub = claims['sub']
    user = await _by_subject(db, sub)
    if user is not None:
        _check_active(user)
        await db.commit()
        return user

    # This query is a collision guard, never an identity lookup for login/linking.
    email = claims['email'].strip().lower()
    collision = (await db.execute(
        select(User.id).where(func.lower(User.email) == email).limit(1)
    )).scalar_one_or_none()
    if collision is not None:
        # The same subject may have committed between our first lookup and the
        # collision guard. Recheck sub, never adopt the email-matched row.
        winner = await _by_subject(db, sub)
        if winner is not None:
            _check_active(winner)
            await db.commit()
            return winner
        raise auth_error(409, 'ACCOUNT_MIGRATION_REQUIRED',
                         '无法自动关联该账户，请联系管理员核实身份并办理账户迁移。')
    await enforce_auth_limit('registration-ip', ip, settings.auth_google_register_ip_per_hour, 3600)
    # Keep NOT NULL + bcrypt compatibility for rollback. No usable password is
    # assigned or returned; password entry points are unconditionally disabled.
    password_hash = await asyncio.to_thread(hash_password, secrets.token_urlsafe(32))
    user = User(id=uuid.uuid4(), username='google_' + secrets.token_hex(12), email=email,
                google_sub=sub, hashed_password=password_hash, is_active=True, is_admin=False,
                email_verified_at=datetime.now(timezone.utc))
    try:
        db.add(user)
        await db.flush()
        await db.commit()
    except IntegrityError:
        # Two independently verified, one-time sessions may race for the first
        # login. Only the DB unique sub constraint chooses the winning account.
        await db.rollback()
        winner = await _by_subject(db, sub)
        if winner is None:
            raise auth_error(409, 'ACCOUNT_MIGRATION_REQUIRED',
                             '无法自动创建或关联账户，请联系管理员核实后重试。') from None
        _check_active(winner)
        await db.commit()
        return winner
    return user
