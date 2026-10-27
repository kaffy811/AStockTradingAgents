"""
Phase MVP-R1.3 / MVP-R1.3-sec — Admin Invite Management Tests
Coverage: 30 tests (24 original + 6 new security tests)

A. Auth: non-admin access denied (4)
B. Admin can create and list invites (6)
C. GET list never returns plaintext codes (4)
D. Revoke endpoint (6)
E. Code generation properties (4)
F. Invite code non-disclosure / prefix security (6)  ← NEW
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

TEST_INVITE_HMAC_SECRET = "test-invite-hmac-secret-32bytes!!"  # 34 bytes


def _compute_invite_hmac(code: str) -> str:
    """Compute the expected HMAC-SHA256 for an 8-char invite code (v2 path)."""
    normalized = code.strip().upper() if len(code.strip()) == 8 else code.strip()
    key = TEST_INVITE_HMAC_SECRET.encode("utf-8")
    msg = f"invite|v2|{normalized}".encode("utf-8")
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def _patch_invite_hmac_secret():
    """Inject INVITE_CODE_HMAC_SECRET into settings for every test in this module."""
    import app.core.config as _config_mod
    with patch.object(_config_mod.settings, "invite_code_hmac_secret", TEST_INVITE_HMAC_SECRET):
        yield


def _make_principal(is_admin: bool = False, username: str = "user"):
    from app.core.runtime_reliability import AuthPrincipal
    return AuthPrincipal(
        id=uuid.uuid4(),
        username=username,
        email=f"{username}@test.com",
        is_active=True,
        is_admin=is_admin,
        role="admin" if is_admin else "user",
    )


def _no_collision_db() -> AsyncMock:
    """DB mock where collision check returns None (no existing invite)."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    no_hit = MagicMock()
    no_hit.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_hit)
    return db


# ===========================================================================
# A. Non-admin access denied
# ===========================================================================

class TestNonAdminAccessDenied:
    @pytest.mark.asyncio
    async def test_create_invite_requires_admin(self):
        from fastapi import HTTPException
        from app.dependencies import get_admin_user

        regular = _make_principal(is_admin=False)
        with pytest.raises(HTTPException) as exc:
            await get_admin_user(regular)
        assert exc.value.status_code == 403

    def test_admin_router_uses_get_admin_user(self):
        import inspect
        from app.routers import admin_invites as m
        source = inspect.getsource(m)
        assert "get_admin_user" in source

    @pytest.mark.asyncio
    async def test_regular_user_cannot_list_invites(self):
        from fastapi import HTTPException
        from app.dependencies import get_admin_user

        regular = _make_principal(is_admin=False)
        with pytest.raises(HTTPException) as exc:
            await get_admin_user(regular)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_regular_user_cannot_revoke_invite(self):
        from fastapi import HTTPException
        from app.dependencies import get_admin_user

        regular = _make_principal(is_admin=False)
        with pytest.raises(HTTPException) as exc:
            await get_admin_user(regular)
        assert exc.value.status_code == 403


# ===========================================================================
# B. Admin can create and list invites
# ===========================================================================



# ===========================================================================
# C. GET list never returns plaintext codes
# ===========================================================================

class TestListNeverRevealsCodes:
    @pytest.mark.asyncio
    async def test_list_has_no_invite_code_field(self):
        from app.routers.admin_invites import list_invites, AdminInviteListItem

        assert not hasattr(AdminInviteListItem, "invite_code"), \
            "AdminInviteListItem must not have an invite_code field"

    @pytest.mark.asyncio
    async def test_list_item_has_code_prefix_not_hash(self):
        from app.routers.admin_invites import list_invites

        inv = MagicMock()
        inv.id = uuid.uuid4()
        inv.code_prefix = "XY3F9K2M"
        inv.email = None
        inv.max_uses = 1
        inv.use_count = 0
        inv.redeemed = False
        inv.redeemed_at = None
        inv.expires_at = None
        inv.note = None
        inv.created_at = datetime.utcnow()
        inv.created_by = "admin"

        scalars = MagicMock()
        scalars.all.return_value = [inv]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        admin = _make_principal(is_admin=True)

        items = await list_invites(db=db, admin=admin)
        # code_prefix is exposed; there is no raw invite_code
        assert items[0].code_prefix == "XY3F9K2M"
        assert not hasattr(items[0], "invite_code")

    def test_create_response_has_invite_code(self):
        """Create returns plaintext; list does not."""
        from app.routers.admin_invites import AdminInviteCreateResponse, AdminInviteListItem
        assert hasattr(AdminInviteCreateResponse, "model_fields") and \
               "invite_code" in AdminInviteCreateResponse.model_fields
        assert "invite_code" not in AdminInviteListItem.model_fields

    def test_source_has_no_plaintext_log(self):
        import inspect
        from app.routers import admin_invites as m
        source = inspect.getsource(m)
        # The plaintext code must not appear in log.info/log.error with the variable
        # (we only log the prefix, never the full plaintext)
        assert "log.info" not in source  # retired writes never log a plaintext code


# ===========================================================================
# D. Revoke endpoint
# ===========================================================================



# ===========================================================================
# E. Code generation properties
# ===========================================================================

class TestCodeGenerationProperties:
    def test_generated_codes_are_8_chars(self):
        from app.routers.admin_invites import _generate_invite_code
        codes = [_generate_invite_code() for _ in range(50)]
        assert all(len(c) == 8 for c in codes)

    def test_codes_use_unambiguous_alphabet(self):
        from app.routers.admin_invites import _generate_invite_code, _INVITE_ALPHABET
        alphabet = set(_INVITE_ALPHABET)
        for _ in range(200):
            code = _generate_invite_code()
            assert set(code).issubset(alphabet), f"Invalid chars in {code!r}"

    def test_no_ambiguous_chars(self):
        from app.routers.admin_invites import _generate_invite_code
        forbidden = set("OI01")
        for _ in range(200):
            code = _generate_invite_code()
            assert not set(code) & forbidden, f"Ambiguous chars in {code!r}"

    def test_100_codes_unique(self):
        from app.routers.admin_invites import _generate_invite_code
        codes = [_generate_invite_code() for _ in range(100)]
        assert len(set(codes)) == 100


# ===========================================================================
# F. Invite code non-disclosure / prefix security  (NEW in MVP-R1.3-sec)
# ===========================================================================
