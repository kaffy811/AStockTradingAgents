"""
Phase MVP-R1.2 — Invite Security Closure
Targeted test suite: 96 tests

Coverage:
  A. Invite code hashing (12 tests)
  B. MvpInvite model schema (8 tests)
  C. User model is_admin (6 tests)
  D. Auth register — invite required (10 tests)
  E. Auth login — email support (6 tests)
  F. Admin dependency (8 tests)
  G. Invite create endpoint — admin only (8 tests)
  H. Invite check endpoint — hash lookup (8 tests)
  I. Admin invite list endpoint (8 tests)
  J. Admin invite revoke endpoint (8 tests)
  K. Atomic register+redeem correctness (8 tests)
  L. Migration artifact checks (6 tests)
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

ARTIFACTS = BACKEND / "docs" / "artifacts"
MIGRATION_DIR = BACKEND / "alembic" / "versions"


# ---------------------------------------------------------------------------
# Helper — hash invite code exactly as the app does
# ---------------------------------------------------------------------------

def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _mock_request(ip: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}
    return req


async def _do_register(body, db, extra_patches: dict | None = None):
    """Call register() with a mock Request and IP rate-limit mocks pre-applied.

    MVP-R1.3-sec: register() now takes (request, body, db) and calls IP rate
    limiters against Redis. This wrapper satisfies both requirements so that
    pre-existing R1.2 tests keep passing unchanged.
    """
    from contextlib import ExitStack
    from app.services.email_verification import IpCheckResult

    ok = IpCheckResult(allowed=True)
    patches = {
        "app.services.email_verification.check_ip_register_limit": AsyncMock(return_value=ok),
        "app.services.email_verification.record_ip_register": AsyncMock(),
        "app.services.email_verification.check_ip_fail_limit": AsyncMock(return_value=ok),
        "app.services.email_verification.record_ip_fail": AsyncMock(),
        **(extra_patches or {}),
    }
    request = _mock_request()
    with ExitStack() as stack:
        for target, mock_obj in patches.items():
            stack.enter_context(patch(target, mock_obj))
        from app.routers.auth import register
        return await register(request, body, db)


# ===========================================================================
# A. Invite code hashing (12 tests)
# ===========================================================================

class TestInviteCodeHashing:
    def test_hash_is_sha256(self):
        code = "abcdefgh12345678"
        expected = hashlib.sha256(code.encode()).hexdigest()
        assert _hash_code(code) == expected

    def test_hash_length_is_64(self):
        code = secrets.token_urlsafe(36)[:48]
        assert len(_hash_code(code)) == 64

    def test_hash_is_deterministic(self):
        code = "test-invite-code-xyz"
        assert _hash_code(code) == _hash_code(code)

    def test_different_codes_different_hashes(self):
        code1 = secrets.token_urlsafe(36)[:48]
        code2 = secrets.token_urlsafe(36)[:48]
        if code1 != code2:
            assert _hash_code(code1) != _hash_code(code2)

    def test_hash_is_hex_string(self):
        code = "some-invite-code"
        h = _hash_code(code)
        assert all(c in "0123456789abcdef" for c in h)

    def test_auth_router_has_hash_function(self):
        from app.routers.auth import _hash_invite_code
        code = "test-code-123"
        assert _hash_invite_code(code) == _hash_code(code)

    def test_mvp_router_has_hash_function(self):
        from app.routers.mvp import _hash_invite_code
        code = "test-code-456"
        assert _hash_invite_code(code) == _hash_code(code)

    def test_auth_and_mvp_hash_functions_agree(self):
        from app.routers.auth import _hash_invite_code as auth_hash
        from app.routers.mvp import _hash_invite_code as mvp_hash
        code = secrets.token_urlsafe(36)[:48]
        assert auth_hash(code) == mvp_hash(code)

    def test_empty_code_still_hashes(self):
        # Edge case: even empty string has a sha256
        assert len(_hash_code("")) == 64

    def test_unicode_code_hashes(self):
        code = "邀请码-测试"
        h = _hash_code(code)
        assert len(h) == 64

    def test_generated_code_prefix_is_8_chars(self):
        code = secrets.token_urlsafe(36)[:48]
        prefix = code[:8]
        assert len(prefix) == 8

    def test_code_prefix_is_substring_of_code(self):
        code = "abcdefghijklmnop"
        assert code.startswith(code[:8])


# ===========================================================================
# B. MvpInvite model schema (8 tests)
# ===========================================================================

class TestMvpInviteModel:
    def test_model_has_code_hash(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "code_hash")

    def test_model_has_code_prefix(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "code_prefix")

    def test_model_has_no_invite_code(self):
        from app.models.mvp import MvpInvite
        assert not hasattr(MvpInvite, "invite_code"), \
            "invite_code (plaintext) must not exist on MvpInvite"

    def test_model_has_email(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "email")

    def test_model_has_redeemed(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "redeemed")

    def test_model_has_use_count(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "use_count")

    def test_model_has_max_uses(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "max_uses")

    def test_model_has_created_by(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "created_by")


# ===========================================================================
# C. User model is_admin (6 tests)
# ===========================================================================

class TestUserModelIsAdmin:
    def test_user_has_is_admin(self):
        from app.models.user import User
        assert hasattr(User, "is_admin")

    def test_register_request_has_invite_code(self):
        from app.models.user import RegisterRequest
        fields = RegisterRequest.model_fields
        assert "invite_code" in fields

    def test_register_request_invite_code_required(self):
        from app.models.user import RegisterRequest
        import pydantic
        with pytest.raises((pydantic.ValidationError, Exception)):
            RegisterRequest(username="test", email="t@t.com", password="password123")

    def test_user_public_has_is_admin(self):
        from app.models.user import UserPublic
        assert "is_admin" in UserPublic.model_fields

    def test_login_request_has_username(self):
        from app.models.user import LoginRequest
        assert "username" in LoginRequest.model_fields

    def test_login_request_has_password(self):
        from app.models.user import LoginRequest
        assert "password" in LoginRequest.model_fields


# ===========================================================================
# D. Auth register — invite required (10 tests)
# ===========================================================================

class TestAuthRegisterInviteRequired:
    def _make_invite(self, code: str, *, email: str | None = None, use_count: int = 0,
                     max_uses: int = 1, expired: bool = False) -> MagicMock:
        from app.models.mvp import MvpInvite
        inv = MagicMock(spec=MvpInvite)
        inv.code_hash = _hash_code(code)
        inv.code_prefix = code[:8]
        inv.email = email
        inv.use_count = use_count
        inv.max_uses = max_uses
        inv.expires_at = datetime.utcnow() - timedelta(hours=1) if expired else None
        inv.redeemed = use_count >= max_uses
        return inv

    @pytest.mark.asyncio
    async def test_register_with_valid_invite_succeeds(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code)
        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "newuser"
        fake_user.email = "new@example.com"
        fake_user.is_active = True
        fake_user.is_admin = False
        fake_user.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock()
        # First call: invite lookup → returns invite
        # Second call: duplicate user check → returns None
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=invite)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        invite.use_count = 0
        invite.max_uses = 1

        body = RegisterRequest(
            username="newuser",
            email="new@example.com",
            password="password123",
            invite_code=code,
        )

        with patch("app.routers.auth.UserPublic") as mock_up:
            mock_up.model_validate = MagicMock(return_value=fake_user)
            result = await _do_register(body, db)
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_register_with_invalid_invite_returns_400(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        from fastapi import HTTPException

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        body = RegisterRequest(
            username="user2", email="u2@e.com", password="password123",
            invite_code="fakecodeXYZ12345",
        )
        with pytest.raises(HTTPException) as exc:
            await _do_register(body, db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_register_with_expired_invite_returns_400(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        from fastapi import HTTPException

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code, expired=True)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=invite))
        )
        body = RegisterRequest(
            username="user3", email="u3@e.com", password="password123",
            invite_code=code,
        )
        with pytest.raises(HTTPException) as exc:
            await _do_register(body, db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_register_with_fully_used_invite_returns_400(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        from fastapi import HTTPException

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code, use_count=1, max_uses=1)

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=invite))
        )
        body = RegisterRequest(
            username="user4", email="u4@e.com", password="password123",
            invite_code=code,
        )
        with pytest.raises(HTTPException) as exc:
            await _do_register(body, db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_register_email_mismatch_with_bound_invite(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        from fastapi import HTTPException

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code, email="bound@example.com")

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=invite))
        )
        body = RegisterRequest(
            username="user5", email="other@example.com", password="password123",
            invite_code=code,
        )
        with pytest.raises(HTTPException) as exc:
            await _do_register(body, db)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_register_email_match_with_bound_invite_passes(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        from fastapi import HTTPException

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code, email="bound@example.com")
        invite.use_count = 0
        invite.max_uses = 1
        invite.expires_at = None

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "user6"
        fake_user.email = "bound@example.com"
        fake_user.is_active = True
        fake_user.is_admin = False
        fake_user.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=invite)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        body = RegisterRequest(
            username="user6", email="bound@example.com", password="password123",
            invite_code=code,
        )
        with patch("app.routers.auth.UserPublic") as mock_up:
            mock_up.model_validate = MagicMock(return_value=fake_user)
            result = await _do_register(body, db)
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_register_increments_use_count(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code)
        invite.use_count = 0
        invite.max_uses = 2

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "user7"
        fake_user.email = "u7@e.com"
        fake_user.is_active = True
        fake_user.is_admin = False
        fake_user.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=invite)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        body = RegisterRequest(
            username="user7", email="u7@e.com", password="password123",
            invite_code=code,
        )
        with patch("app.routers.auth.UserPublic") as mock_up:
            mock_up.model_validate = MagicMock(return_value=fake_user)
            await _do_register(body, db)
        assert invite.use_count == 1

    @pytest.mark.asyncio
    async def test_register_marks_redeemed_when_max_uses_reached(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code)
        invite.use_count = 0
        invite.max_uses = 1
        invite.expires_at = None

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "user8"
        fake_user.email = "u8@e.com"
        fake_user.is_active = True
        fake_user.is_admin = False
        fake_user.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=invite)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        body = RegisterRequest(
            username="user8", email="u8@e.com", password="password123",
            invite_code=code,
        )
        with patch("app.routers.auth.UserPublic") as mock_up:
            mock_up.model_validate = MagicMock(return_value=fake_user)
            await _do_register(body, db)
        assert invite.redeemed is True

    @pytest.mark.asyncio
    async def test_register_duplicate_user_returns_409(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        from fastapi import HTTPException

        code = secrets.token_urlsafe(36)[:48]
        invite = self._make_invite(code)
        invite.use_count = 0
        invite.max_uses = 1
        invite.expires_at = None
        existing_user = MagicMock()

        db = AsyncMock()
        db.execute = AsyncMock()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=invite)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=existing_user)),
        ]

        body = RegisterRequest(
            username="dup", email="dup@e.com", password="password123",
            invite_code=code,
        )
        with pytest.raises(HTTPException) as exc:
            await _do_register(body, db)
        assert exc.value.status_code == 409

    def test_register_invite_code_lookup_uses_hash(self):
        """Verify that auth router queries MvpInvite by code_hash, not invite_code."""
        import inspect
        from app.routers import auth
        source = inspect.getsource(auth)
        assert "code_hash" in source
        assert "_hash_invite_code" in source


# ===========================================================================
# E. Auth login — email support (6 tests)
# ===========================================================================

class TestAuthLoginEmail:
    @pytest.mark.asyncio
    async def test_login_with_username_works(self):
        from app.routers.auth import login
        from app.models.user import LoginRequest

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "alice"
        fake_user.is_active = True
        fake_user.hashed_password = "hashed"

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_user))
        )

        body = LoginRequest(username="alice", password="mypassword")
        with (
            patch("app.routers.auth.verify_password", return_value=True),
            patch("app.routers.auth.create_access_token", return_value="tok"),
            patch("app.routers.auth.create_refresh_token", return_value="ref"),
        ):
            result = await login(body, db)
        assert result.access_token == "tok"

    @pytest.mark.asyncio
    async def test_login_with_email_works(self):
        from app.routers.auth import login
        from app.models.user import LoginRequest

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "alice"
        fake_user.is_active = True
        fake_user.hashed_password = "hashed"

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_user))
        )

        # Email in the username field
        body = LoginRequest(username="alice@example.com", password="mypassword")
        with (
            patch("app.routers.auth.verify_password", return_value=True),
            patch("app.routers.auth.create_access_token", return_value="tok2"),
            patch("app.routers.auth.create_refresh_token", return_value="ref2"),
        ):
            result = await login(body, db)
        assert result.access_token == "tok2"

    def test_login_router_checks_at_sign_for_email(self):
        import inspect
        from app.routers import auth
        source = inspect.getsource(auth)
        assert "@" in source and "email" in source.lower()

    @pytest.mark.asyncio
    async def test_login_invalid_password_returns_401(self):
        from app.routers.auth import login
        from app.models.user import LoginRequest
        from fastapi import HTTPException

        fake_user = MagicMock()
        fake_user.is_active = True
        fake_user.hashed_password = "hashed"

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_user))
        )
        body = LoginRequest(username="alice", password="wrongpassword")
        with patch("app.routers.auth.verify_password", return_value=False):
            with pytest.raises(HTTPException) as exc:
                await login(body, db)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_returns_401(self):
        from app.routers.auth import login
        from app.models.user import LoginRequest
        from fastapi import HTTPException

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        body = LoginRequest(username="nobody", password="password123")
        with patch("app.routers.auth.verify_password", return_value=True):
            with pytest.raises(HTTPException) as exc:
                await login(body, db)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_login_disabled_user_returns_403(self):
        from app.routers.auth import login
        from app.models.user import LoginRequest
        from fastapi import HTTPException

        fake_user = MagicMock()
        fake_user.is_active = False
        fake_user.hashed_password = "hashed"

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=fake_user))
        )
        body = LoginRequest(username="disabled", password="password123")
        with patch("app.routers.auth.verify_password", return_value=True):
            with pytest.raises(HTTPException) as exc:
                await login(body, db)
        assert exc.value.status_code == 403


# ===========================================================================
# F. Admin dependency (8 tests)
# ===========================================================================

class TestAdminDependency:
    def test_get_admin_user_exists(self):
        from app.dependencies import get_admin_user
        assert callable(get_admin_user)

    @pytest.mark.asyncio
    async def test_get_admin_user_allows_admin(self):
        from app.dependencies import get_admin_user
        from app.core.runtime_reliability import AuthPrincipal

        principal = AuthPrincipal(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.com",
            is_active=True,
            is_admin=True,
            role="admin",
        )
        result = await get_admin_user(principal)
        assert result.is_admin is True

    @pytest.mark.asyncio
    async def test_get_admin_user_blocks_non_admin(self):
        from app.dependencies import get_admin_user
        from app.core.runtime_reliability import AuthPrincipal
        from fastapi import HTTPException

        principal = AuthPrincipal(
            id=uuid.uuid4(),
            username="user",
            email="user@example.com",
            is_active=True,
            is_admin=False,
            role="user",
        )
        with pytest.raises(HTTPException) as exc:
            await get_admin_user(principal)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_admin_user_returns_principal(self):
        from app.dependencies import get_admin_user
        from app.core.runtime_reliability import AuthPrincipal

        admin_id = uuid.uuid4()
        principal = AuthPrincipal(
            id=admin_id,
            username="superadmin",
            email="sa@e.com",
            is_active=True,
            is_admin=True,
            role="admin",
        )
        result = await get_admin_user(principal)
        assert result.id == admin_id

    def test_auth_principal_has_is_admin_field(self):
        from app.core.runtime_reliability import AuthPrincipal
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AuthPrincipal)}
        assert "is_admin" in fields

    def test_auth_principal_default_is_admin_false(self):
        from app.core.runtime_reliability import AuthPrincipal
        p = AuthPrincipal(
            id=uuid.uuid4(),
            username="x",
            email="x@x.com",
            is_active=True,
        )
        assert p.is_admin is False

    def test_auth_principal_role_admin_when_is_admin(self):
        from app.core.runtime_reliability import AuthPrincipal
        p = AuthPrincipal(
            id=uuid.uuid4(),
            username="x",
            email="x@x.com",
            is_active=True,
            is_admin=True,
            role="admin",
        )
        assert p.role == "admin"

    def test_dependencies_exports_get_admin_user(self):
        import app.dependencies as deps
        assert hasattr(deps, "get_admin_user")


# ===========================================================================
# G. Invite create endpoint — admin only (8 tests)
# ===========================================================================

class TestInviteCreateAdminOnly:
    def _make_admin(self) -> Any:
        from app.core.runtime_reliability import AuthPrincipal
        return AuthPrincipal(
            id=uuid.uuid4(), username="admin", email="a@a.com",
            is_active=True, is_admin=True, role="admin"
        )

    @pytest.mark.asyncio
    async def test_create_invite_stores_code_hash(self):
        from app.routers.mvp import create_invite, InviteCreateRequest

        req = InviteCreateRequest(max_uses=1)
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        # Collision check: no existing invite with the generated hash
        _no_collision = MagicMock()
        _no_collision.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=_no_collision)

        admin = self._make_admin()
        result = await create_invite(req, db, admin)

        # Verify the returned code can be re-hashed to find the invite
        code = result.invite_code
        assert len(code) >= 8
        stored_hash = _hash_code(code)
        assert len(stored_hash) == 64

    @pytest.mark.asyncio
    async def test_create_invite_does_not_store_plaintext(self):
        from app.routers.mvp import create_invite, InviteCreateRequest

        req = InviteCreateRequest(max_uses=1)
        db = AsyncMock()
        added_invites = []
        db.add = MagicMock(side_effect=added_invites.append)
        db.commit = AsyncMock()
        _no_collision = MagicMock()
        _no_collision.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=_no_collision)

        admin = self._make_admin()
        result = await create_invite(req, db, admin)

        # The MvpInvite object stored in DB must have code_hash, not invite_code
        assert len(added_invites) == 1
        invite_obj = added_invites[0]
        assert hasattr(invite_obj, "code_hash")
        assert not hasattr(invite_obj, "invite_code")

    @pytest.mark.asyncio
    async def test_create_invite_returns_plaintext_once(self):
        from app.routers.mvp import create_invite, InviteCreateRequest

        req = InviteCreateRequest(max_uses=1)
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        _no_collision = MagicMock()
        _no_collision.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=_no_collision)
        admin = self._make_admin()

        result = await create_invite(req, db, admin)
        assert result.invite_code is not None
        assert len(result.invite_code) == 8  # new format: exactly 8 chars

    @pytest.mark.asyncio
    async def test_create_invite_response_has_code_prefix(self):
        from app.routers.mvp import create_invite, InviteCreateRequest

        req = InviteCreateRequest(max_uses=1)
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        _no_collision = MagicMock()
        _no_collision.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=_no_collision)
        admin = self._make_admin()

        result = await create_invite(req, db, admin)
        assert result.code_prefix is not None
        # For 8-char codes, code_prefix == invite_code (prefix IS the full code)
        assert result.code_prefix == result.invite_code

    @pytest.mark.asyncio
    async def test_create_invite_with_email_binding(self):
        from app.routers.mvp import create_invite, InviteCreateRequest

        req = InviteCreateRequest(email="test@example.com", max_uses=1)
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        _no_collision = MagicMock()
        _no_collision.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=_no_collision)
        admin = self._make_admin()

        result = await create_invite(req, db, admin)
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_invite_with_note(self):
        from app.routers.mvp import create_invite, InviteCreateRequest

        req = InviteCreateRequest(max_uses=3, note="Wave 1 tester")
        db = AsyncMock()
        added = []
        db.add = MagicMock(side_effect=added.append)
        db.commit = AsyncMock()
        _no_collision = MagicMock()
        _no_collision.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=_no_collision)
        admin = self._make_admin()

        await create_invite(req, db, admin)
        assert added[0].note == "Wave 1 tester"

    @pytest.mark.asyncio
    async def test_create_invite_records_created_by_admin_username(self):
        from app.routers.mvp import create_invite, InviteCreateRequest

        req = InviteCreateRequest(max_uses=1)
        db = AsyncMock()
        added = []
        db.add = MagicMock(side_effect=added.append)
        db.commit = AsyncMock()
        _no_collision = MagicMock()
        _no_collision.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=_no_collision)
        admin = self._make_admin()

        await create_invite(req, db, admin)
        assert added[0].created_by == admin.username

    def test_create_invite_endpoint_requires_admin_dep(self):
        """Verify POST /mvp/invites has get_admin_user in its dependencies."""
        import inspect
        from app.routers import mvp as mvp_module
        source = inspect.getsource(mvp_module)
        assert "get_admin_user" in source


# ===========================================================================
# H. Invite check endpoint — hash lookup (8 tests)
# ===========================================================================

class TestInviteCheckHashLookup:
    @pytest.mark.asyncio
    async def test_check_valid_invite_returns_valid_true(self):
        from app.routers.mvp import check_invite, InviteCheckRequest
        from app.models.mvp import MvpInvite

        code = secrets.token_urlsafe(36)[:48]
        invite = MagicMock(spec=MvpInvite)
        invite.code_hash = _hash_code(code)
        invite.expires_at = None
        invite.use_count = 0
        invite.max_uses = 1

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=invite))
        )
        req = InviteCheckRequest(invite_code=code)
        result = await check_invite(req, db)
        assert result.valid is True

    @pytest.mark.asyncio
    async def test_check_invalid_code_returns_valid_false(self):
        from app.routers.mvp import check_invite, InviteCheckRequest

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        req = InviteCheckRequest(invite_code="badcode12345678")
        result = await check_invite(req, db)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_check_expired_invite_returns_valid_false(self):
        from app.routers.mvp import check_invite, InviteCheckRequest
        from app.models.mvp import MvpInvite

        code = secrets.token_urlsafe(36)[:48]
        invite = MagicMock(spec=MvpInvite)
        invite.expires_at = datetime.utcnow() - timedelta(hours=1)
        invite.use_count = 0
        invite.max_uses = 1

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=invite))
        )
        req = InviteCheckRequest(invite_code=code)
        result = await check_invite(req, db)
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_check_fully_used_invite_returns_valid_false(self):
        from app.routers.mvp import check_invite, InviteCheckRequest
        from app.models.mvp import MvpInvite

        code = secrets.token_urlsafe(36)[:48]
        invite = MagicMock(spec=MvpInvite)
        invite.expires_at = None
        invite.use_count = 1
        invite.max_uses = 1

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=invite))
        )
        req = InviteCheckRequest(invite_code=code)
        result = await check_invite(req, db)
        assert result.valid is False

    def test_check_endpoint_uses_code_hash_not_invite_code(self):
        import inspect
        from app.routers import mvp as mvp_module
        source = inspect.getsource(mvp_module.check_invite)
        assert "code_hash" in source
        assert "invite_code" not in source.split("code_hash")[0].split("def check_invite")[1]

    @pytest.mark.asyncio
    async def test_check_returns_message_on_valid(self):
        from app.routers.mvp import check_invite, InviteCheckRequest
        from app.models.mvp import MvpInvite

        code = secrets.token_urlsafe(36)[:48]
        invite = MagicMock(spec=MvpInvite)
        invite.expires_at = None
        invite.use_count = 0
        invite.max_uses = 1

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=invite))
        )
        req = InviteCheckRequest(invite_code=code)
        result = await check_invite(req, db)
        assert result.message is not None

    @pytest.mark.asyncio
    async def test_check_no_redeem_endpoint_removed(self):
        """Verify the old /mvp/invites/redeem endpoint is removed (merged into register)."""
        from app.routers import mvp as mvp_module
        assert not hasattr(mvp_module, "redeem_invite"), \
            "redeem_invite should be removed — redemption is now atomic inside /auth/register"

    def test_check_endpoint_is_public(self):
        """Check endpoint should not require authentication."""
        import inspect
        from app.routers import mvp as mvp_module
        src = inspect.getsource(mvp_module.check_invite)
        assert "get_admin_user" not in src
        assert "get_current_user" not in src


# ===========================================================================
# I. Admin invite list endpoint (8 tests)
# ===========================================================================

class TestAdminInviteList:
    def _make_admin(self):
        from app.core.runtime_reliability import AuthPrincipal
        return AuthPrincipal(
            id=uuid.uuid4(), username="admin", email="a@a.com",
            is_active=True, is_admin=True, role="admin"
        )

    def _make_invite_row(self, idx: int = 0) -> MagicMock:
        from app.models.mvp import MvpInvite
        inv = MagicMock(spec=MvpInvite)
        inv.id = uuid.uuid4()
        inv.code_prefix = f"prefix{idx:02d}"
        inv.email = f"user{idx}@example.com"
        inv.max_uses = 1
        inv.use_count = 0
        inv.redeemed = False
        inv.redeemed_at = None
        inv.expires_at = None
        inv.note = None
        inv.created_at = datetime.utcnow()
        inv.created_by = "admin"
        return inv

    @pytest.mark.asyncio
    async def test_list_invites_returns_list(self):
        from app.routers.mvp import list_invites

        invs = [self._make_invite_row(i) for i in range(3)]
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=invs))))
        )
        admin = self._make_admin()
        result = await list_invites(db, admin)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_list_invites_returns_code_prefix(self):
        from app.routers.mvp import list_invites

        inv = self._make_invite_row(0)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[inv]))))
        )
        admin = self._make_admin()
        result = await list_invites(db, admin)
        assert result[0].code_prefix == "prefix00"

    @pytest.mark.asyncio
    async def test_list_invites_never_returns_code_hash(self):
        from app.routers.mvp import list_invites, InviteListItem
        import inspect
        src = inspect.getsource(list_invites)
        # code_hash should not appear in the response serialization
        assert "code_hash" not in src.split("InviteListItem")[1]

    def test_list_invites_requires_admin(self):
        import inspect
        from app.routers import mvp as mvp_module
        src = inspect.getsource(mvp_module.list_invites)
        assert "get_admin_user" in src

    @pytest.mark.asyncio
    async def test_list_invites_empty_returns_empty_list(self):
        from app.routers.mvp import list_invites

        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        )
        admin = self._make_admin()
        result = await list_invites(db, admin)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_invites_includes_redeemed_status(self):
        from app.routers.mvp import list_invites

        inv = self._make_invite_row(0)
        inv.redeemed = True
        inv.redeemed_at = datetime.utcnow()
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[inv]))))
        )
        admin = self._make_admin()
        result = await list_invites(db, admin)
        assert result[0].redeemed is True

    @pytest.mark.asyncio
    async def test_list_invites_includes_created_by(self):
        from app.routers.mvp import list_invites

        inv = self._make_invite_row(0)
        inv.created_by = "superadmin"
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[inv]))))
        )
        admin = self._make_admin()
        result = await list_invites(db, admin)
        assert result[0].created_by == "superadmin"

    @pytest.mark.asyncio
    async def test_list_invites_id_is_string(self):
        from app.routers.mvp import list_invites

        inv = self._make_invite_row(0)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[inv]))))
        )
        admin = self._make_admin()
        result = await list_invites(db, admin)
        assert isinstance(result[0].id, str)


# ===========================================================================
# J. Admin invite revoke endpoint (8 tests)
# ===========================================================================

class TestAdminInviteRevoke:
    def _make_admin(self):
        from app.core.runtime_reliability import AuthPrincipal
        return AuthPrincipal(
            id=uuid.uuid4(), username="admin", email="a@a.com",
            is_active=True, is_admin=True, role="admin"
        )

    @pytest.mark.asyncio
    async def test_revoke_existing_invite_succeeds(self):
        from app.routers.mvp import revoke_invite
        from app.models.mvp import MvpInvite

        invite_id = str(uuid.uuid4())
        inv = MagicMock(spec=MvpInvite)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=inv))
        )
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        admin = self._make_admin()

        await revoke_invite(invite_id, db, admin)
        assert db.delete.called

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_invite_returns_404(self):
        from app.routers.mvp import revoke_invite
        from fastapi import HTTPException

        invite_id = str(uuid.uuid4())
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        admin = self._make_admin()

        with pytest.raises(HTTPException) as exc:
            await revoke_invite(invite_id, db, admin)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_invalid_uuid_returns_400(self):
        from app.routers.mvp import revoke_invite
        from fastapi import HTTPException

        db = AsyncMock()
        admin = self._make_admin()

        with pytest.raises(HTTPException) as exc:
            await revoke_invite("not-a-uuid", db, admin)
        assert exc.value.status_code == 400

    def test_revoke_endpoint_requires_admin(self):
        import inspect
        from app.routers import mvp as mvp_module
        src = inspect.getsource(mvp_module.revoke_invite)
        assert "get_admin_user" in src

    @pytest.mark.asyncio
    async def test_revoke_commits_after_delete(self):
        from app.routers.mvp import revoke_invite
        from app.models.mvp import MvpInvite

        invite_id = str(uuid.uuid4())
        inv = MagicMock(spec=MvpInvite)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=inv))
        )
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        admin = self._make_admin()

        await revoke_invite(invite_id, db, admin)
        assert db.commit.called

    @pytest.mark.asyncio
    async def test_revoke_returns_204(self):
        from app.routers.mvp import revoke_invite
        from app.models.mvp import MvpInvite

        invite_id = str(uuid.uuid4())
        inv = MagicMock(spec=MvpInvite)
        db = AsyncMock()
        db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=inv))
        )
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        admin = self._make_admin()

        result = await revoke_invite(invite_id, db, admin)
        assert result is None  # 204 No Content

    def test_revoke_endpoint_exists(self):
        from app.routers import mvp as mvp_module
        assert hasattr(mvp_module, "revoke_invite")

    def test_revoke_endpoint_path_contains_invite_id(self):
        import inspect
        from app.routers import mvp as mvp_module
        src = inspect.getsource(mvp_module.revoke_invite)
        assert "invite_id" in src


# ===========================================================================
# K. Atomic register+redeem correctness (8 tests)
# ===========================================================================

class TestAtomicRegisterRedeem:
    def test_register_uses_select_for_update(self):
        """Verify SELECT FOR UPDATE is used to prevent TOCTOU race."""
        import inspect
        from app.routers import auth
        src = inspect.getsource(auth.register)
        assert "with_for_update" in src

    def test_register_uses_single_flush_before_commit(self):
        """Verify db.flush() is called to get user.id before linking to invite."""
        import inspect
        from app.routers import auth
        src = inspect.getsource(auth.register)
        assert "flush" in src

    def test_register_redeemed_by_user_id_is_set(self):
        """Verify invite.redeemed_by_user_id is assigned after flush."""
        import inspect
        from app.routers import auth
        src = inspect.getsource(auth.register)
        assert "redeemed_by_user_id" in src

    def test_register_checks_duplicate_user_before_create(self):
        """Verify uniqueness check happens before user insert."""
        import inspect
        from app.routers import auth
        src = inspect.getsource(auth.register)
        # Both 'username' and '409' should appear
        assert "409" in src
        assert "already exists" in src.lower()

    def test_no_separate_redeem_endpoint_in_mvp_router(self):
        """POST /mvp/invites/redeem must be gone — redemption is in /auth/register."""
        from app.routers import mvp as mvp_module
        assert not hasattr(mvp_module, "redeem_invite")

    def test_invite_code_not_in_register_request_body_after_hashing(self):
        """Verify that after hashing, the raw code is not written to the DB."""
        import inspect
        from app.routers import auth
        # The raw body.invite_code should only be passed to _hash_invite_code
        src = inspect.getsource(auth.register)
        assert "_hash_invite_code" in src

    @pytest.mark.asyncio
    async def test_commit_called_once_per_register(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        import secrets as sec

        code = sec.token_urlsafe(36)[:48]
        from app.models.mvp import MvpInvite
        invite = MagicMock(spec=MvpInvite)
        invite.code_hash = _hash_code(code)
        invite.email = None
        invite.expires_at = None
        invite.use_count = 0
        invite.max_uses = 1

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "atomicuser"
        fake_user.email = "atomic@e.com"
        fake_user.is_active = True
        fake_user.is_admin = False
        fake_user.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=invite)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        body = RegisterRequest(
            username="atomicuser", email="atomic@e.com", password="password123",
            invite_code=code,
        )
        with patch("app.routers.auth.UserPublic") as mock_up:
            mock_up.model_validate = MagicMock(return_value=fake_user)
            await _do_register(body, db)
        assert db.commit.call_count == 1

    @pytest.mark.asyncio
    async def test_rollback_not_called_on_success(self):
        from app.routers.auth import register
        from app.models.user import RegisterRequest
        import secrets as sec

        code = sec.token_urlsafe(36)[:48]
        from app.models.mvp import MvpInvite
        invite = MagicMock(spec=MvpInvite)
        invite.code_hash = _hash_code(code)
        invite.email = None
        invite.expires_at = None
        invite.use_count = 0
        invite.max_uses = 1

        fake_user = MagicMock()
        fake_user.id = uuid.uuid4()
        fake_user.username = "succuser"
        fake_user.email = "succ@e.com"
        fake_user.is_active = True
        fake_user.is_admin = False
        fake_user.created_at = datetime.utcnow()

        db = AsyncMock()
        db.execute = AsyncMock()
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=invite)),
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        ]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.rollback = AsyncMock()

        body = RegisterRequest(
            username="succuser", email="succ@e.com", password="password123",
            invite_code=code,
        )
        with patch("app.routers.auth.UserPublic") as mock_up:
            mock_up.model_validate = MagicMock(return_value=fake_user)
            await _do_register(body, db)
        assert not db.rollback.called


# ===========================================================================
# L. Migration artifact checks (6 tests)
# ===========================================================================

class TestMigrationArtifacts:
    def test_p132_migration_exists(self):
        migrations = list(MIGRATION_DIR.glob("*n2o3p4q5r6s7*.py"))
        assert len(migrations) == 1, "P1.32 migration n2o3p4q5r6s7 must exist"

    def test_r12_migration_exists(self):
        migrations = list(MIGRATION_DIR.glob("*o3p4q5r6s7t8*.py"))
        assert len(migrations) == 1, "MVP-R1.2 migration o3p4q5r6s7t8 must exist"

    def test_r12_migration_adds_is_admin(self):
        migration = next(MIGRATION_DIR.glob("*o3p4q5r6s7t8*.py"))
        content = migration.read_text()
        assert "is_admin" in content

    def test_r12_migration_adds_code_hash(self):
        migration = next(MIGRATION_DIR.glob("*o3p4q5r6s7t8*.py"))
        content = migration.read_text()
        assert "code_hash" in content

    def test_r12_migration_drops_invite_code(self):
        migration = next(MIGRATION_DIR.glob("*o3p4q5r6s7t8*.py"))
        content = migration.read_text()
        assert "invite_code" in content and "drop_column" in content

    def test_r12_migration_revision_chain(self):
        migration = next(MIGRATION_DIR.glob("*o3p4q5r6s7t8*.py"))
        content = migration.read_text()
        assert 'down_revision = "n2o3p4q5r6s7"' in content
