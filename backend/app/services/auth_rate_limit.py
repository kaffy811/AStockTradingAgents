"""Atomic, shared authentication limits. Redis failure must not disable admission limits."""
import hashlib

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.database import get_redis

# Increment + expiry are one operation, including the first concurrent request.
_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""


def client_ip(request: Request) -> str:
    trusted = {ip.strip() for ip in settings.trusted_proxy_ips.split(',') if ip.strip()}
    direct = request.client.host if request.client else 'unknown'
    if direct not in trusted:
        return direct
    for ip in reversed(request.headers.get('X-Forwarded-For', '').split(',')):
        if ip.strip() and ip.strip() not in trusted:
            return ip.strip()
    return direct


def auth_error(status: int, code: str, message: str, *, headers=None) -> HTTPException:
    return HTTPException(status, {'error_code': code, 'message': message}, headers=headers)


def disabled_auth_method() -> None:
    raise auth_error(410, 'AUTH_METHOD_DISABLED', '此账户入口已停用，请使用 Google 登录。')


async def enforce_auth_limit(scope: str, identity: str, limit: int, seconds: int = 60) -> None:
    # No raw IP addresses, emails, subjects or credentials in Redis keys/logs.
    digest = hashlib.sha256(identity.encode()).hexdigest()
    key = f'ta:{settings.app_env}:auth:limit:{scope}:{digest}'
    try:
        redis = get_redis()
        if redis is None:
            raise RuntimeError('Redis unavailable')
        count, ttl = await redis.eval(_LIMIT_SCRIPT, 1, key, seconds)
        count, ttl = int(count), max(1, int(ttl))
    except Exception:
        raise auth_error(503, 'AUTH_SERVICE_UNAVAILABLE', '登录服务暂不可用，请稍后重试。') from None
    if count > limit:
        raise auth_error(429, 'AUTH_RATE_LIMITED', '登录请求过于频繁，请稍后重试。',
                         headers={'Retry-After': str(ttl)})
