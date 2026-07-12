from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer()
# auto_error=False so that public endpoints can call get_optional_user
# without raising 403 when no Authorization header is present
_optional_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Like get_current_user but returns None instead of 401 when no token is supplied.
    Use for endpoints that are public but can optionally act on behalf of a logged-in user.
    """
    if credentials is None:
        return None
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        return None  # bad token → treat as anonymous

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
