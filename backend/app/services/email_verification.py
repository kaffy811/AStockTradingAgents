"""
app/services/email_verification.py — Email verification code service.

Phase MVP-R1.3-sec: HMAC-SHA256 code storage + IP rate limiting.

Redis key schema (all keyed to normalized email):
  ev:hash:{email}             HMAC-SHA256 of the 6-digit code     TTL: verification_ttl
  ev:cooldown:{email}         sentinel for 60s resend throttle    TTL: 60s
  ev:hourly:{email}:{hour}    send count for this clock-hour      TTL: 3601s
  ev:attempts:{email}         failed verification attempt count   TTL: verification_ttl

IP-level keys:
  ev:ip:send:{ip}:{hour}      verification sends per IP per hour  TTL: 3601s
  ev:ip:fail:{ip}:{hour}      verification failures per IP/hour   TTL: 3601s
  reg:ip:{ip}:{hour}          registration attempts per IP/hour   TTL: 3601s

Policy:
  - Min resend interval: 60 seconds
  - Max sends per hour per email: 5
  - Max sends per hour per IP: settings.email_ip_send_hourly_limit (default 20)
  - Max fails per hour per IP: settings.email_ip_fail_hourly_limit (default 15)
  - Code TTL: EMAIL_VERIFICATION_TTL_SECONDS (default 600 = 10 min)
  - Max failed verification attempts before code lockout: 5
  - On success: delete code hash + attempts keys

HMAC scheme:
  HMAC-SHA256(EMAIL_VERIFICATION_HMAC_SECRET, "{normalized_email}|register|{code}")
  Stored in Redis; compared with hmac.compare_digest — not plain string equality.

Redis unavailable → raise RuntimeError (fail-closed for security).
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
import secrets
import time
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.database import get_redis

log = logging.getLogger(__name__)

_COOLDOWN_TTL = 60       # seconds between sends for same email
_HOURLY_LIMIT = 5        # max verification emails per email per hour
_MAX_ATTEMPTS = 5        # failed attempts before code is invalidated


# ── HMAC helpers ──────────────────────────────────────────────────────────────

def _hmac_code(email: str, code: str) -> str:
    """Compute HMAC-SHA256(secret, '{normalized_email}|register|{code}').

    Raises RuntimeError if EMAIL_VERIFICATION_HMAC_SECRET is not configured.
    """
    secret = settings.email_verification_hmac_secret
    if not secret:
        raise RuntimeError(
            "EMAIL_VERIFICATION_HMAC_SECRET is not configured. "
            "Set a random 32+ byte value in your environment."
        )
    key = secret.encode("utf-8")
    msg = f"{_normalize_email(email)}|register|{code}".encode("utf-8")
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


def _constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return _hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ── General helpers ───────────────────────────────────────────────────────────

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


def _ip_send_key(ip: str) -> str:
    return f"ev:ip:send:{ip}:{_hour_window()}"


def _ip_fail_key(ip: str) -> str:
    return f"ev:ip:fail:{ip}:{_hour_window()}"


def _ip_register_key(ip: str) -> str:
    return f"reg:ip:{ip}:{_hour_window()}"


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SendResult:
    ok: bool
    message: str
    retry_after: int = 0


@dataclass
class VerifyResult:
    ok: bool
    message: str


@dataclass
class IpCheckResult:
    allowed: bool
    message: str = ""
    retry_after: int = 0


# ── IP rate limiting ──────────────────────────────────────────────────────────

async def check_ip_send_limit(ip: str) -> IpCheckResult:
    """Check whether this IP is allowed to request a verification code this hour.

    Raises RuntimeError if Redis is unavailable (fail-closed).
    """
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot check IP rate limit.")
    limit = getattr(settings, "email_ip_send_hourly_limit", 20)
    key = _ip_send_key(ip)
    count = int(await redis.get(key) or 0)
    if count >= limit:
        remaining = 3600 - (int(time.time()) % 3600)
        return IpCheckResult(allowed=False, message="IP 发送次数已达上限，请稍后再试。", retry_after=remaining)
    return IpCheckResult(allowed=True)


async def record_ip_send(ip: str) -> None:
    """Increment IP hourly send counter."""
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot record IP send.")
    key = _ip_send_key(ip)
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 3601)
    await pipe.execute()


async def check_ip_fail_limit(ip: str) -> IpCheckResult:
    """Check whether this IP has exceeded the hourly verification failure limit.

    Raises RuntimeError if Redis is unavailable (fail-closed).
    """
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot check IP fail limit.")
    limit = getattr(settings, "email_ip_fail_hourly_limit", 15)
    key = _ip_fail_key(ip)
    count = int(await redis.get(key) or 0)
    if count >= limit:
        remaining = 3600 - (int(time.time()) % 3600)
        return IpCheckResult(allowed=False, message="IP 验证失败次数过多，请稍后再试。", retry_after=remaining)
    return IpCheckResult(allowed=True)


async def record_ip_fail(ip: str) -> None:
    """Increment IP hourly failure counter."""
    redis = get_redis()
    if redis is None:
        return  # non-fatal: already fail-closed at check stage
    key = _ip_fail_key(ip)
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 3601)
    await pipe.execute()


async def check_ip_register_limit(ip: str) -> IpCheckResult:
    """Check whether this IP has exceeded the hourly registration limit.

    Raises RuntimeError if Redis is unavailable (fail-closed).
    """
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot check IP register limit.")
    limit = getattr(settings, "register_ip_hourly_limit", 10)
    key = _ip_register_key(ip)
    count = int(await redis.get(key) or 0)
    if count >= limit:
        remaining = 3600 - (int(time.time()) % 3600)
        return IpCheckResult(allowed=False, message="IP 注册次数已达上限，请稍后再试。", retry_after=remaining)
    return IpCheckResult(allowed=True)


async def record_ip_register(ip: str) -> None:
    """Increment IP hourly registration counter."""
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot record IP registration.")
    key = _ip_register_key(ip)
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, 3601)
    await pipe.execute()


# ── Core email verification logic ─────────────────────────────────────────────

async def request_verification_code(email: str) -> SendResult:
    """Generate and store a 6-digit code (HMAC-protected); return generic result.

    Does NOT send the email — caller must call email_sender.send_verification().
    Raises RuntimeError if Redis is unavailable or HMAC secret is not configured.

    Returns SendResult(ok=True, message=<plaintext_code>) on success.
    The plaintext code MUST NOT be logged by the caller.
    """
    # Eagerly validate HMAC secret before touching Redis
    _hmac_code(email, "000000")  # raises RuntimeError if secret is missing

    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot issue verification codes.")

    ttl = getattr(settings, "email_verification_ttl_seconds", 600)
    hash_key, cooldown_key, hourly_key, attempts_key = _redis_keys(email)

    # ── Rate limit: cooldown ──────────────────────────────────────────────────
    if await redis.exists(cooldown_key):
        remaining = await redis.ttl(cooldown_key)
        return SendResult(ok=False, message="发送过于频繁，请稍后再试。", retry_after=max(remaining, 1))

    # ── Rate limit: hourly per email ──────────────────────────────────────────
    hourly_count = int(await redis.get(hourly_key) or 0)
    if hourly_count >= _HOURLY_LIMIT:
        return SendResult(
            ok=False,
            message="本小时发送次数已达上限，请 1 小时后再试。",
            retry_after=3600 - (int(time.time()) % 3600),
        )

    # ── Generate code and compute HMAC ────────────────────────────────────────
    code = "".join(str(secrets.randbelow(10)) for _ in range(6))
    code_hmac = _hmac_code(email, code)

    pipe = redis.pipeline()
    pipe.set(hash_key, code_hmac, ex=ttl)
    pipe.delete(attempts_key)
    pipe.set(cooldown_key, "1", ex=_COOLDOWN_TTL)
    pipe.incr(hourly_key)
    pipe.expire(hourly_key, 3601)
    await pipe.execute()

    log.debug("Verification code generated for %s (HMAC stored in Redis)", _normalize_email(email))

    return SendResult(ok=True, message=code)   # plaintext carried to caller; NEVER log it


async def verify_code(email: str, code: str) -> VerifyResult:
    """Check that `code` matches the stored HMAC for `email`.

    Does NOT consume the code — call consume_code() after successful registration.
    Increments the attempt counter; invalidates after _MAX_ATTEMPTS failures.
    Raises RuntimeError if Redis is unavailable.
    """
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis is unavailable; cannot verify code.")

    hash_key, _, _, attempts_key = _redis_keys(email)

    stored_hmac = await redis.get(hash_key)
    if stored_hmac is None:
        return VerifyResult(ok=False, message="验证码不存在或已过期，请重新发送。")

    attempts = int(await redis.get(attempts_key) or 0)
    if attempts >= _MAX_ATTEMPTS:
        await redis.delete(hash_key, attempts_key)
        return VerifyResult(ok=False, message="验证失败次数过多，验证码已失效，请重新发送。")

    # Compute HMAC for submitted code
    try:
        computed_hmac = _hmac_code(email, code)
    except RuntimeError:
        return VerifyResult(ok=False, message="服务配置错误，无法验证。")

    stored_str = stored_hmac if isinstance(stored_hmac, str) else stored_hmac.decode()

    if not _constant_time_compare(computed_hmac, stored_str):
        ttl = await redis.ttl(hash_key)
        await redis.set(attempts_key, attempts + 1, ex=max(ttl, 1))
        remaining = _MAX_ATTEMPTS - attempts - 1
        return VerifyResult(ok=False, message=f"验证码错误，还可尝试 {remaining} 次。")

    return VerifyResult(ok=True, message="验证码正确。")


async def consume_code(email: str) -> None:
    """Delete all verification keys for `email` after successful registration."""
    redis = get_redis()
    if redis is None:
        log.warning("Redis unavailable; could not clean up verification keys for %s", _normalize_email(email))
        return

    hash_key, cooldown_key, _, attempts_key = _redis_keys(email)
    await redis.delete(hash_key, attempts_key)
    log.debug("Verification keys consumed for %s", _normalize_email(email))
