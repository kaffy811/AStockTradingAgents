"""Local-only Google admission regressions: no shared DB, Google or Redis calls."""
import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, select, func
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.routers import auth, admin_invites, mvp
from app.models.user import User
from app.dependencies import get_current_user
from app.core.security import decode_token, create_refresh_token
from app.services import auth_rate_limit, google_accounts


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.counts = {}
        self.expires = {}
        self.lock = asyncio.Lock()

    async def set(self, key, value, ex):
        self.values[key] = value
        self.expires[key] = time.monotonic() + ex
        return True

    async def getdel(self, key):
        async with self.lock:
            value = self.values.pop(key, None)
            return value if self.expires.get(key, 0) > time.monotonic() else None

    async def eval(self, script, number, key, seconds):
        async with self.lock:
            if self.expires.get(key, 0) <= time.monotonic():
                self.counts[key] = 0
                self.expires[key] = time.monotonic() + int(seconds)
            self.counts[key] = self.counts.get(key, 0) + 1
            return [self.counts[key], max(1, int(self.expires[key] - time.monotonic()))]


def result(value):
    obj = MagicMock()
    obj.scalar_one_or_none.return_value = value
    return obj


def user(**changes):
    values = dict(id=uuid.uuid4(), username='existing', email='person@example.com',
                  google_sub='stable-sub', is_active=True, is_admin=False,
                  hashed_password='unchanged', created_at=datetime.now(timezone.utc))
    return SimpleNamespace(**(values | changes))


def fake_db(*results):
    db = AsyncMock()
    db.add = MagicMock()
    db.execute.side_effect = [result(item) for item in results]
    return db


@pytest.fixture
def setup(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(auth, 'get_redis', lambda: redis)
    monkeypatch.setattr(auth_rate_limit, 'get_redis', lambda: redis)
    monkeypatch.setattr(auth.settings, 'google_client_id', 'test.apps.googleusercontent.com')
    monkeypatch.setattr(auth.settings, 'app_env', 'test')
    monkeypatch.setattr(auth, 'verify_google_token', AsyncMock(return_value={
        'sub': 'stable-sub', 'email': 'person@example.com', 'email_verified': True}))
    # Keep account tests quick; signed identity and real DB uniqueness are tested separately.
    monkeypatch.setattr(google_accounts, 'hash_password', lambda _: 'unusable-test-hash')
    return redis


@asynccontextmanager
async def client_for(db, principal=None, *, debug=False):
    app = FastAPI(debug=debug)
    app.include_router(auth.router, prefix='/api/v1')
    app.include_router(admin_invites.router, prefix='/api/v1')
    app.include_router(mvp.router)
    async def get_test_db():
        yield db
    app.dependency_overrides[auth.get_db] = get_test_db
    if principal is not None:
        app.dependency_overrides[get_current_user] = lambda: principal
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield client


async def challenge(client):
    response = await client.get('/api/v1/auth/google/config')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    return response.json()['nonce']


async def google_login(client):
    await challenge(client)
    return await client.post('/api/v1/auth/google', json={'credential': 'signed-test-credential'})


async def test_new_google_user_needs_no_invite_password_and_is_ordinary(setup):
    db = fake_db(None, None)
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 200
    created = db.add.call_args.args[0]
    assert created.google_sub == 'stable-sub' and created.email == 'person@example.com'
    assert created.is_admin is False and created.is_active is True
    assert created.hashed_password and len(created.hashed_password) <= 255
    assert len(created.username) <= 32 and created.email_verified_at is not None
    assert decode_token(response.json()['access_token'])['sub'] == str(created.id)
    assert decode_token(response.json()['refresh_token'])['type'] == 'refresh'
    assert db.execute.await_count == 2  # subject + email guard; no invite table
    assert 'ta_google_nonce=""' in response.headers['set-cookie']
    db.commit.assert_awaited_once()


async def test_bound_subject_keeps_account_ownership_even_if_email_changes(setup):
    existing = user(email='old-address@example.com', is_admin=True)
    db = fake_db(existing)
    async with client_for(db) as client:
        first = await google_login(client)
        db.execute.side_effect = [result(existing)]
        second = await google_login(client)
    assert first.status_code == second.status_code == 200
    assert decode_token(first.json()['access_token'])['sub'] == str(existing.id)
    assert decode_token(second.json()['access_token'])['sub'] == str(existing.id)
    assert existing.email == 'old-address@example.com' and existing.is_admin is True
    db.add.assert_not_called()
    # Reports/watchlists continue to reference exactly the same immutable UUID.


@pytest.mark.parametrize('legacy_admin', [False, True])
async def test_legacy_email_is_never_linked_or_taken_over(setup, legacy_admin):
    old = user(google_sub=None, is_admin=legacy_admin)
    db = fake_db(None, old.id, None)
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 409
    assert response.json()['detail']['error_code'] == 'ACCOUNT_MIGRATION_REQUIRED'
    assert '联系管理员' in response.json()['detail']['message']
    assert old.google_sub is None and old.is_admin == legacy_admin
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


async def test_same_email_bound_to_other_google_sub_is_not_adopted(setup):
    db = fake_db(None, uuid.uuid4(), None)
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 409
    db.add.assert_not_called()


async def test_inactive_bound_account_cannot_login(setup):
    db = fake_db(user(is_active=False))
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 403
    assert response.json()['detail']['error_code'] == 'ACCOUNT_DISABLED'
    db.commit.assert_not_awaited()


async def test_one_time_session_rejects_replay_and_expiry(setup):
    db = fake_db(user())
    async with client_for(db) as client:
        nonce = await challenge(client)
        response = await client.post('/api/v1/auth/google', json={'credential': 'same-credential'})
        assert response.status_code == 200
        # Replay the consumed browser session even after the server cleared the cookie.
        client.cookies.set('ta_google_nonce', nonce, path='/api/v1/auth/google')
        response = await client.post('/api/v1/auth/google', json={'credential': 'same-credential'})
        assert response.status_code == 401
        nonce = await challenge(client)
        setup.expires['auth:google:nonce:' + nonce] = 0
        response = await client.post('/api/v1/auth/google', json={'credential': 'same-credential'})
        assert response.status_code == 401
    assert db.execute.await_count == 1


async def test_duplicate_requests_only_issue_one_session(setup):
    db = fake_db(user())
    async with client_for(db) as client:
        await challenge(client)
        responses = await asyncio.gather(*[
            client.post('/api/v1/auth/google', json={'credential': 'same-credential'}) for _ in range(2)])
    assert sorted(r.status_code for r in responses) == [200, 401]
    db.commit.assert_awaited_once()


async def test_missing_nonce_is_rejected_before_database(setup):
    db = fake_db()
    async with client_for(db) as client:
        response = await client.post('/api/v1/auth/google', json={'credential': 'fake'})
    assert response.status_code == 401
    db.execute.assert_not_awaited()


async def test_invalid_identity_never_consumes_account_or_issues_session(setup, monkeypatch):
    monkeypatch.setattr(auth, 'verify_google_token', AsyncMock(side_effect=HTTPException(401, '无效凭证')))
    db = fake_db()
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 401
    db.execute.assert_not_awaited()


async def test_flush_unique_violation_recovers_same_subject_only(setup):
    winner = user()
    db = fake_db(None, None, winner)
    db.flush.side_effect = IntegrityError('insert', {}, Exception('unique violation'))
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 200
    assert decode_token(response.json()['access_token'])['sub'] == str(winner.id)
    db.rollback.assert_awaited_once()


async def test_subject_appearing_during_email_guard_is_rechecked_safely(setup):
    winner = user()
    db = fake_db(None, winner.id, winner)
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 200
    assert decode_token(response.json()['access_token'])['sub'] == str(winner.id)
    db.add.assert_not_called()


async def test_conflicting_unique_email_never_logs_into_email_owner(setup):
    db = fake_db(None, None, None)
    db.flush.side_effect = IntegrityError('insert', {}, Exception('private SQL'))
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 409 and 'private SQL' not in response.text
    db.rollback.assert_awaited_once()


async def test_database_and_validation_errors_do_not_disclose_credential(setup):
    db = fake_db()
    db.execute.side_effect = OperationalError('secret-db-query', {}, Exception('private connection string'))
    async with client_for(db) as client:
        response = await google_login(client)
        assert response.status_code == 503
        for payload in [{'credential': 'credential-secret', 'password': 'password-secret'},
                        {'credential': 'credential-secret', 'is_admin': True},
                        {'credential': 'private-' * 3000}]:
            invalid = await client.post('/api/v1/auth/google', json=payload)
            assert invalid.status_code == 422
            assert 'credential-secret' not in invalid.text and 'private-' not in invalid.text
    assert 'secret-db-query' not in response.text and 'private connection' not in response.text


async def test_google_and_registration_limits_fail_closed(setup, monkeypatch):
    for _ in range(5):
        await auth_rate_limit.enforce_auth_limit('registration-ip', 'test-ip', 5, 3600)
    with pytest.raises(HTTPException) as exc:
        await auth_rate_limit.enforce_auth_limit('registration-ip', 'test-ip', 5, 3600)
    assert exc.value.status_code == 429 and int(exc.value.headers['Retry-After']) > 0
    monkeypatch.setattr(auth_rate_limit, 'get_redis', lambda: None)
    db = fake_db()
    async with client_for(db) as client:
        response = await client.post('/api/v1/auth/google', json={'credential': 'fake'})
    assert response.status_code == 503
    db.execute.assert_not_awaited()


async def test_atomic_rate_limit_does_not_over_admit_concurrent_callers(setup):
    results = await asyncio.gather(*[
        auth_rate_limit.enforce_auth_limit('test', 'same', 3) for _ in range(10)], return_exceptions=True)
    assert sum(item is None for item in results) == 3
    assert sum(isinstance(item, HTTPException) and item.status_code == 429 for item in results) == 7


async def test_untrusted_forwarded_ip_cannot_bypass_rate_limits(setup):
    from starlette.requests import Request
    request = Request({'type': 'http', 'client': ('198.51.100.8', 1),
                       'headers': [(b'x-forwarded-for', b'1.1.1.1')]})
    assert auth._get_client_ip(request) == '198.51.100.8'


@pytest.mark.parametrize('path', ['/api/v1/auth/register', '/api/v1/auth/login',
                                  '/api/v1/auth/email-verification/request', '/mvp/invites/check'])
async def test_legacy_public_endpoints_are_unconditionally_gone(setup, path):
    db = fake_db()
    async with client_for(db) as client:
        for body in [{}, {'username': 'old', 'password': 'secret', 'invite_code': 'VALIDCODE'}]:
            response = await client.post(path, json=body)
            assert response.status_code == 410
            assert response.json()['detail']['error_code'] == 'AUTH_METHOD_DISABLED'
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.parametrize('method,path', [
    ('post', '/api/v1/admin/invites'), ('post', '/mvp/invites'),
    ('post', '/api/v1/admin/invites/old/revoke'), ('delete', '/mvp/admin/invites/old')])
async def test_invite_writes_are_disabled_even_for_admin(setup, method, path):
    db = fake_db()
    async with client_for(db, principal=user(is_admin=True)) as client:
        response = await getattr(client, method)(path)
    assert response.status_code == 410
    db.execute.assert_not_awaited()
    db.commit.assert_not_awaited()
    db.delete.assert_not_awaited()


async def test_admin_authorization_still_blocks_ordinary_users(setup):
    db = fake_db()
    async with client_for(db, principal=user(is_admin=False)) as client:
        response = await client.get('/api/v1/admin/invites')
    assert response.status_code == 403
    db.execute.assert_not_awaited()


async def test_me_keeps_current_user_identity_and_admin_flag(setup):
    existing = user(is_admin=True)
    async with client_for(fake_db(), principal=existing) as client:
        response = await client.get('/api/v1/auth/me')
    assert response.status_code == 200
    assert response.json()['id'] == str(existing.id) and response.json()['is_admin'] is True


@pytest.mark.parametrize('active', [True, False])
async def test_refresh_rechecks_existing_account_state(setup, active):
    existing = user(is_active=active)
    db = fake_db(existing)
    async with client_for(db) as client:
        response = await client.post('/api/v1/auth/refresh', json={
            'refresh_token': create_refresh_token(str(existing.id))})
    assert response.status_code == (200 if active else 403)
    if active:
        assert decode_token(response.json()['access_token'])['sub'] == str(existing.id)


async def test_concurrent_first_logins_share_one_real_unique_account(setup, tmp_path):
    """Real local SQL transactions/unique constraints; never touches configured DB."""
    engine = create_engine('sqlite:///' + str(tmp_path / 'accounts.sqlite'),
                           connect_args={'check_same_thread': False, 'timeout': 5})
    User.__table__.create(engine)
    barrier = asyncio.Event()
    arrivals = 0
    class LocalSession:
        def __init__(self):
            self.session = Session(engine, expire_on_commit=False)
            self.first = True
        async def execute(self, statement):
            nonlocal arrivals
            value = await asyncio.to_thread(self.session.execute, statement)
            if self.first:
                self.first = False
                arrivals += 1
                if arrivals == 2:
                    barrier.set()
                await asyncio.wait_for(barrier.wait(), 2)
            return value
        def add(self, value):
            self.session.add(value)
        async def flush(self):
            await asyncio.to_thread(self.session.flush)
        async def commit(self):
            await asyncio.to_thread(self.session.commit)
        async def rollback(self):
            await asyncio.to_thread(self.session.rollback)
    sessions = [LocalSession(), LocalSession()]
    try:
        accounts = await asyncio.gather(*[
            google_accounts.resolve_google_account(db, {'sub': 'concurrent-sub', 'email': 'new@example.com'}, 'test-ip')
            for db in sessions])
        assert accounts[0].id == accounts[1].id
        with Session(engine) as verify:
            assert verify.scalar(select(func.count()).select_from(User)) == 1
            stored = verify.scalar(select(User))
            assert stored.google_sub == 'concurrent-sub' and stored.is_admin is False
    finally:
        for db in sessions:
            db.session.close()
        engine.dispose()


async def test_real_password_hash_satisfies_legacy_not_null_constraint(setup, monkeypatch):
    from app.core.security import hash_password, pwd_context
    monkeypatch.setattr(google_accounts, 'hash_password', hash_password)
    db = fake_db(None, None)
    async with client_for(db) as client:
        response = await google_login(client)
    assert response.status_code == 200
    stored = db.add.call_args.args[0].hashed_password
    assert pwd_context.identify(stored) == 'bcrypt'
    assert 'stored' not in response.json()


async def test_session_issue_limit_is_enforced_across_independent_nonces(setup):
    existing = user()
    db = fake_db(*[existing] * 11)
    async with client_for(db) as client:
        for _ in range(10):
            assert (await google_login(client)).status_code == 200
        blocked = await google_login(client)
    assert blocked.status_code == 429
    assert 'Retry-After' in blocked.headers
    assert db.commit.await_count == 10


@pytest.mark.parametrize('exists', [True, False])
async def test_refresh_invalid_or_deleted_account_is_rejected(setup, exists):
    db = fake_db(None)
    async with client_for(db) as client:
        token = 'invalid-refresh' if exists else create_refresh_token(str(uuid.uuid4()))
        response = await client.post('/api/v1/auth/refresh', json={'refresh_token': token})
    assert response.status_code == 401


async def test_disabling_legacy_flags_does_not_reenable_password_routes(setup, monkeypatch):
    monkeypatch.setattr(auth.settings, 'email_verification_required', False)
    monkeypatch.setattr(auth.settings, 'mvp_public_registration_enabled', True)
    monkeypatch.setattr(auth.settings, 'mvp_new_invites_enabled', True)
    db = fake_db()
    async with client_for(db) as client:
        for path in ['login', 'register', 'email-verification/request']:
            response = await client.post('/api/v1/auth/' + path, json={})
            assert response.status_code == 410
        status = await client.get('/mvp/wave/status')
        assert status.json()['new_invites_enabled'] is False
    db.execute.assert_not_awaited()


async def test_real_signed_credential_cannot_be_reused_with_a_fresh_browser_nonce(setup, monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jose import jwt
    from app.services import google_identity
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(google_identity, '_keys', {'test-key': key.public_key()})
    monkeypatch.setattr(google_identity, '_expires', time.monotonic() + 300)
    monkeypatch.setattr(auth, 'verify_google_token', google_identity.verify_google_token)
    db = fake_db(user())
    async with client_for(db) as client:
        nonce = await challenge(client)
        claims = {'iss': 'https://accounts.google.com', 'sub': 'stable-sub',
                  'aud': auth.settings.google_client_id, 'email': 'person@example.com',
                  'email_verified': True, 'nonce': nonce, 'iat': int(time.time()), 'exp': int(time.time()) + 300}
        token = jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})
        assert (await client.post('/api/v1/auth/google', json={'credential': token})).status_code == 200
        client.cookies.set('ta_google_nonce', nonce, path='/api/v1/auth/google')
        assert (await client.post('/api/v1/auth/google', json={'credential': token})).status_code == 401
        fresh = await challenge(client)
        assert fresh != nonce
        assert (await client.post('/api/v1/auth/google', json={'credential': token})).status_code == 401
    db.commit.assert_awaited_once()


async def test_challenge_cookie_retains_production_security_flags(setup, monkeypatch):
    monkeypatch.setattr(auth.settings, 'app_env', 'production')
    async with client_for(fake_db()) as client:
        response = await client.get('/api/v1/auth/google/config')
    cookie = response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
    assert 'Path=/api/v1/auth/google' in cookie


async def test_unconfigured_development_signin_does_not_offer_legacy_fallback(setup, monkeypatch):
    monkeypatch.setattr(auth.settings, 'google_client_id', '')
    async with client_for(fake_db()) as client:
        response = await client.get('/api/v1/auth/google/config')
    assert response.json() == {'enabled': False}
    assert 'set-cookie' not in response.headers


async def test_unexpected_auth_error_is_safe_even_when_debug_enabled(setup, monkeypatch):
    monkeypatch.setattr(auth, 'verify_google_token', AsyncMock(side_effect=RuntimeError('credential-secret private-stack')))
    async with client_for(fake_db(), debug=True) as client:
        response = await google_login(client)
    assert response.status_code == 503
    assert 'credential-secret' not in response.text and 'private-stack' not in response.text
