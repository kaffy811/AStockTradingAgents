from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.security import decode_token
from app.core.runtime_reliability import AuthPrincipal, load_auth_principal

bearer_scheme = HTTPBearer()
# auto_error=False so that public endpoints can call get_optional_user
# without raising 403 when no Authorization header is present
_optional_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Any = None,
) -> AuthPrincipal:
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not an access token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token subject")
    return await load_auth_principal(user_id, token_exp=payload.get("exp"))


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_bearer),
    db: Any = None,
) -> Optional[AuthPrincipal]:
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
    if not user_id:
        return None
    return await load_auth_principal(user_id, token_exp=payload.get("exp"))
