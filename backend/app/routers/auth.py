"""Google-only admission. Legacy password/invite endpoints are permanently retired."""
from datetime import datetime, timezone
import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi import HTTPException
from jose import JWTError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db, get_redis
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.dependencies import get_current_user
from app.models.user import RefreshRequest, TokenResponse, User, UserPublic
from app.services.auth_rate_limit import (
    auth_error, client_ip as _get_client_ip, disabled_auth_method, enforce_auth_limit,
)
from app.services.google_accounts import resolve_google_account
from app.services.google_identity import verify_google_token


class SafeAuthRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            try:
                return await original(request)
            except RequestValidationError:
                # FastAPI's default validation body includes rejected input,
                # which may contain the entire Google credential/refresh token.
                raise auth_error(422, 'INVALID_AUTH_REQUEST', '登录请求格式无效，请重新尝试。') from None
            except SQLAlchemyError as exc:
                logging.getLogger(__name__).warning('Authentication database failure (%s)', type(exc).__name__)
                raise auth_error(503, 'AUTH_DATABASE_UNAVAILABLE', '暂时无法验证账户，请稍后重试。') from None
            except HTTPException:
                raise
            except Exception as exc:
                # Authentication must stay safe even under accidental debug
                # configuration; never echo a provider exception or its input.
                logging.getLogger(__name__).warning('Authentication service failure (%s)', type(exc).__name__)
                raise auth_error(503, 'AUTH_SERVICE_UNAVAILABLE', '登录服务暂不可用，请稍后重试。') from None
        return handler


router = APIRouter(prefix='/auth', tags=['auth'], route_class=SafeAuthRoute)
_NONCE_COOKIE = 'ta_google_nonce'
_NONCE_PATH = '/api/v1/auth/google'


@router.post('/login', status_code=410, deprecated=True)
async def login():
    disabled_auth_method()


@router.post('/register', status_code=410, deprecated=True)
async def register():
    disabled_auth_method()


@router.post('/email-verification/request', status_code=410, deprecated=True)
async def request_email_verification():
    disabled_auth_method()


def _tokens(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(str(user.id)),
                         refresh_token=create_refresh_token(str(user.id)))


@router.post('/refresh', response_model=TokenResponse)
async def refresh(request: Request, body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    await enforce_auth_limit('refresh-ip', _get_client_ip(request), settings.auth_refresh_ip_per_minute)
    try:
        payload = decode_token(body.refresh_token)
        user_id = uuid.UUID(payload.get('sub', ''))
        if payload.get('type') != 'refresh':
            raise ValueError()
    except (JWTError, ValueError, TypeError, AttributeError):
        raise auth_error(401, 'AUTH_REQUIRED', '登录已过期，请重新登录。') from None
    await enforce_auth_limit('refresh-user', str(user_id), settings.auth_refresh_user_per_minute)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise auth_error(401, 'AUTH_REQUIRED', '登录已过期，请重新登录。')
    if not user.is_active:
        raise auth_error(403, 'ACCOUNT_DISABLED', '账户已停用，请联系管理员。')
    return _tokens(user)


@router.get('/me', response_model=UserPublic)
async def me(current_user=Depends(get_current_user)):
    return UserPublic(id=current_user.id, username=current_user.username, email=current_user.email,
                      is_active=current_user.is_active, is_admin=getattr(current_user, 'is_admin', False),
                      email_verified=getattr(current_user, 'email_verified', False),
                      created_at=getattr(current_user, 'created_at', None) or datetime.now(timezone.utc))


class GoogleLoginRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    credential: str = Field(min_length=1, max_length=16384, repr=False)


@router.get('/google/config')
async def google_config(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    if not settings.google_client_id:
        return {'enabled': False}
    await enforce_auth_limit('nonce-ip', _get_client_ip(request), settings.auth_google_nonce_per_minute)
    nonce = secrets.token_urlsafe(32)
    try:
        redis = get_redis()
        if redis is None:
            raise RuntimeError()
        await redis.set(f'auth:google:nonce:{nonce}', '1', ex=300)
    except Exception:
        raise auth_error(503, 'AUTH_SERVICE_UNAVAILABLE', '登录服务暂不可用，请稍后重试。') from None
    response.set_cookie(_NONCE_COOKIE, nonce, max_age=300, httponly=True,
                        secure=settings.app_env not in {'development', 'dev', 'local', 'test'},
                        samesite='lax', path=_NONCE_PATH)
    return {'enabled': True, 'client_id': settings.google_client_id, 'nonce': nonce}


@router.post('/google', response_model=TokenResponse)
async def google_login(request: Request, body: GoogleLoginRequest, response: Response,
                       db: AsyncSession = Depends(get_db)):
    await enforce_auth_limit('login-ip', _get_client_ip(request), settings.auth_google_login_ip_per_minute)
    nonce = request.cookies.get(_NONCE_COOKIE)
    if not nonce or len(nonce) > 128:
        raise auth_error(401, 'GOOGLE_SESSION_EXPIRED', '登录会话已过期，请重新尝试。')
    claims = await verify_google_token(body.credential, nonce)
    try:
        redis = get_redis()
        if redis is None:
            raise RuntimeError()
        valid = await redis.getdel(f'auth:google:nonce:{nonce}')
    except Exception:
        raise auth_error(503, 'AUTH_SERVICE_UNAVAILABLE', '登录服务暂不可用，请稍后重试。') from None
    if not valid:
        raise auth_error(401, 'GOOGLE_SESSION_USED', '登录会话已使用或过期，请重新尝试。')
    await enforce_auth_limit('login-sub', claims['sub'], settings.auth_google_login_sub_per_minute)
    user = await resolve_google_account(db, claims, _get_client_ip(request))
    response.delete_cookie(_NONCE_COOKIE, path=_NONCE_PATH)
    response.headers['Cache-Control'] = 'no-store'
    return _tokens(user)
