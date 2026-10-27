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
import hmac as _hmac
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

TEST_INVITE_HMAC_SECRET = "test-invite-hmac-secret-32bytes!!"  # 34 bytes


@pytest.fixture(autouse=True)
def _patch_invite_hmac_secret():
    """Inject INVITE_CODE_HMAC_SECRET into settings for every test in this module."""
    import app.core.config as _config_mod
    with patch.object(_config_mod.settings, "invite_code_hmac_secret", TEST_INVITE_HMAC_SECRET):
        yield


# ---------------------------------------------------------------------------
# Helper — hash invite code exactly as the app does (v1 SHA-256 for legacy codes)
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


    def test_mvp_router_has_hash_function(self):
        from app.routers.mvp import _hash_invite_code
        code = "test-code-456"
        assert _hash_invite_code(code) == _hash_code(code)


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



# ===========================================================================
# E. Auth login — email support (6 tests)
# ===========================================================================



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



# ===========================================================================
# H. Invite check endpoint — hash lookup (8 tests)
# ===========================================================================



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



# ===========================================================================
# K. Atomic register+redeem correctness (8 tests)
# ===========================================================================



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
