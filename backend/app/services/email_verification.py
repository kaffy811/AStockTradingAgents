"""
app/services/email_verification.py — Email verification code service.

Phase MVP-R1.3: Used by POST /auth/email-verification/request and register.

Redis key schema (all keyed to normalized email):
  ev:hash:{email}          SHA-256 of the 6-digit code        TTL: verification_ttl
  ev:cooldown:{email}      sentinel for 60s resend throttle   TTL: 60s
  ev:hourly:{email}:{hour} send count for this clock-hour     TTL: 3601s
  ev:attempts:{email}      failed verification attempt count  TTL: verification_ttl

Policy:
  - Min resend interval: 60 seconds
  - Max sends per hour: 5
  - Code TTL: EMAIL_VERIFICATION_TTL_SECONDS (default 600 = 10 min)
  - Max failed verification attempts before lockout: 5
  - On success: delete code hash + attempts keys

Redis unavailable → raise RuntimeError (fail-closed for security, unlike analytics).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass

from app.core.config import settings
from app.core.database import get_redis

log = logging.getLogger(__name__)

_COOLDOWN_TTL = 60       # seconds between sends for same email
_HOURLY_LIMIT = 5        # max verification emails per email per hour
_MAX_ATTEMPTS = 5        # failed attempts before code is invalidated


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hour_window() -> int:
    return int(time.time()) // 3600


def _redis_keys(email: str) -> tuple[str, str, str, str]:
    """Return (hash_key, cooldown_key, hourly_key, attempts_key)."""
    norm = _normalize_email(email)
    hour = _hour_window()
    return (
        f"ev:hash:{norm}",
        f"ev:cooldown:{norm}",
        f"ev:hourly:{norm}:{hour}",
        f"ev:attempts:{norm}",
    )


@dataclass
class SendResult:
    ok: bool
    message: str
    # seconds remaining on cooldown (0 if not in cooldown)
    retry_after: int = 0


@dataclass
class VerifyResult:
    ok: bool
    message: str


async def request_verification_code(email: str) -> SendResult:
    """Generate and store a 6-digit code; return generic success/failure.

    Does NOT send the email — caller must call email_sender.send_verification().

    Returns (ok=True, code=...) on success; caller must send the email and
    NOT log the code at any level other than DEBUG.

    Raises RuntimeError if Redis is unavailable.
    """
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot issue verification codes.")

    ttl = getattr(settings, "email_verification_ttl_seconds", 600)

    hash_key, cooldown_key, hourly_key, attempts_key = _redis_keys(email)

    # ── Rate limit: cooldown ──────────────────────────────────────────────────
    if await redis.exists(cooldown_key):
        remaining = await redis.ttl(cooldown_key)
        return SendResult(ok=False, message="发送过于频繁，请稍后再试。", retry_after=max(remaining, 1))

    # ── Rate limit: hourly ────────────────────────────────────────────────────
    hourly_count = int(await redis.get(hourly_key) or 0)
    if hourly_count >= _HOURLY_LIMIT:
        return SendResult(
            ok=False,
            message="本小时发送次数已达上限，请 1 小时后再试。",
            retry_after=3600 - (int(time.time()) % 3600),
        )

    # ── Generate code ─────────────────────────────────────────────────────────
    code = "".join(str(secrets.randbelow(10)) for _ in range(6))
    code_hash = _hash_code(code)

    pipe = redis.pipeline()
    # Store hashed code
    pipe.set(hash_key, code_hash, ex=ttl)
    # Reset attempt counter
    pipe.delete(attempts_key)
    # Set cooldown
    pipe.set(cooldown_key, "1", ex=_COOLDOWN_TTL)
    # Increment hourly counter (keep for slightly over an hour)
    pipe.incr(hourly_key)
    pipe.expire(hourly_key, 3601)
    await pipe.execute()

    log.debug("Verification code generated for %s (hash stored in Redis)", _normalize_email(email))

    # Return code so the caller can send it via email_sender
    return SendResult(ok=True, message=code)   # message carries the plaintext code


async def verify_code(email: str, code: str) -> VerifyResult:
    """Check that `code` matches the stored hash for `email`.

    Does NOT consume the code — call consume_code() after successful registration.
    Increments the attempt counter; returns VerifyResult(ok=False) after 5 failures.
    """
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot verify code.")

    hash_key, _, _, attempts_key = _redis_keys(email)

    stored_hash = await redis.get(hash_key)
    if stored_hash is None:
        return VerifyResult(ok=False, message="验证码不存在或已过期，请重新发送。")

    # Check attempt count
    attempts = int(await redis.get(attempts_key) or 0)
    if attempts >= _MAX_ATTEMPTS:
        # Invalidate the code
        await redis.delete(hash_key, attempts_key)
        return VerifyResult(ok=False, message="验证失败次数过多，验证码已失效，请重新发送。")

    expected_hash = _hash_code(code)
    # Redis may return bytes or str depending on decode_responses setting
    stored_str = stored_hash if isinstance(stored_hash, str) else stored_hash.decode()

    if expected_hash != stored_str:
        # Increment attempt counter with same TTL as the code
        ttl = await redis.ttl(hash_key)
        await redis.set(attempts_key, attempts + 1, ex=max(ttl, 1))
        remaining = _MAX_ATTEMPTS - attempts - 1
        return VerifyResult(
            ok=False,
            message=f"验证码错误，还可尝试 {remaining} 次。",
        )

    return VerifyResult(ok=True, message="验证码正确。")


async def consume_code(email: str) -> None:
    """Delete all verification keys for `email` after successful registration."""
    redis = get_redis()
    if redis is None:
        log.warning("Redis unavailable; could not clean up verification keys for %s", email)
        return

    hash_key, cooldown_key, _, attempts_key = _redis_keys(email)
    await redis.delete(hash_key, attempts_key)
    # Leave cooldown key in place so re-registration isn't trivial immediately
    log.debug("Verification keys consumed for %s", _normalize_email(email))
