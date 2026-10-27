"""Verify Google ID tokens with pinned JWKS URL and RS256 only."""
import asyncio
import time

import httpx
from fastapi import HTTPException
from jose import JWTError, jwt
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import settings

_keys: dict = {}
_expires = 0.0
_lock = asyncio.Lock()


async def verify_google_token(credential: str, nonce: str) -> dict:
    global _keys, _expires
    if not settings.google_client_id:
        raise HTTPException(503, "Google 登录尚未配置。")
    try:
        if not isinstance(nonce, str) or not nonce:
            raise ValueError("Missing nonce")
        header = jwt.get_unverified_header(credential)
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise ValueError("Invalid signing header")
        async with _lock:
            if time.monotonic() >= _expires:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.get("https://www.googleapis.com/oauth2/v3/certs")
                    response.raise_for_status()
                    _keys = {key["kid"]: key for key in response.json()["keys"]}
                _expires = time.monotonic() + 300
        key = _keys.get(header["kid"])
        if key is None:
            raise ValueError("Unknown signing key")
        claims = jwt.decode(
            credential, key, algorithms=["RS256"], audience=settings.google_client_id,
            options={"require_exp": True, "require_sub": True, "require_iat": True,
                     "require_aud": True},
        )
        if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError("Invalid issuer")
        if claims.get("nonce") != nonce or claims.get("email_verified") is not True:
            raise ValueError("Invalid identity")
        sub = claims.get("sub")
        email = claims.get("email")
        if (not isinstance(sub, str) or not sub or len(sub) > 255
                or not isinstance(email, str) or not email.strip() or len(email) > 254
                or '@' not in email or claims['iat'] > time.time() + 60
                or (claims.get('azp') and claims['azp'] != settings.google_client_id)):
            raise ValueError("Missing identity")
        TypeAdapter(EmailStr).validate_python(email)
        return claims
    except httpx.HTTPError:
        raise HTTPException(503, "暂时无法连接 Google，请稍后重试。")
    except (JWTError, ValueError, KeyError, TypeError, ValidationError):
        raise HTTPException(401, "Google 登录凭证无效或已过期，请重试。")
