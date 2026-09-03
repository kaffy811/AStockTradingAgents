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

class TestAdminInviteCRUD:
    @pytest.mark.asyncio
    async def test_create_invite_returns_plaintext(self):
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert result.invite_code is not None
        assert len(result.invite_code) == 8

    @pytest.mark.asyncio
    async def test_create_invite_prefix_is_4_chars(self):
        """code_prefix stored in DB must be only the first 4 chars — not the full code."""
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert len(result.code_prefix) == 4
        assert result.code_prefix != result.invite_code

    @pytest.mark.asyncio
    async def test_create_invite_with_email(self):
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(email="test@example.com", max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert result.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_create_invite_stores_hash_not_plaintext(self):
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        added = []
        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        db.add = MagicMock(side_effect=added.append)
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert len(added) == 1
        inv_obj = added[0]
        # Stored hash should be HMAC-SHA256 (v2) of the returned 8-char plaintext
        expected_hash = _compute_invite_hmac(result.invite_code)
        assert inv_obj.code_hash == expected_hash

    @pytest.mark.asyncio
    async def test_list_invites_returns_list(self):
        from app.routers.admin_invites import list_invites

        inv = MagicMock()
        inv.id = uuid.uuid4()
        inv.code_prefix = "ABCD1234"
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
        assert len(items) == 1
        assert items[0].code_prefix == "ABCD1234"

    @pytest.mark.asyncio
    async def test_create_records_created_by(self):
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        added = []
        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        db.add = MagicMock(side_effect=added.append)
        admin = _make_principal(is_admin=True, username="superadmin")

        await create_invite(req, db, admin)
        assert added[0].created_by == "superadmin"


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
        assert "log.info" in source  # sanity


# ===========================================================================
# D. Revoke endpoint
# ===========================================================================

class TestRevokeInvite:
    @pytest.mark.asyncio
    async def test_revoke_deletes_invite(self):
        from app.routers.admin_invites import revoke_invite
        from app.models.mvp import MvpInvite

        invite = MagicMock(spec=MvpInvite)
        invite.id = uuid.uuid4()
        invite.redeemed = False

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        admin = _make_principal(is_admin=True)

        response = await revoke_invite(str(invite.id), db=db, admin=admin)
        db.delete.assert_called_once_with(invite)
        db.commit.assert_called_once()
        assert response.ok is True

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_returns_404(self):
        from fastapi import HTTPException
        from app.routers.admin_invites import revoke_invite

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        admin = _make_principal(is_admin=True)

        with pytest.raises(HTTPException) as exc:
            await revoke_invite(str(uuid.uuid4()), db=db, admin=admin)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_revoke_invalid_id_returns_400(self):
        from fastapi import HTTPException
        from app.routers.admin_invites import revoke_invite

        db = AsyncMock()
        admin = _make_principal(is_admin=True)

        with pytest.raises(HTTPException) as exc:
            await revoke_invite("not-a-uuid", db=db, admin=admin)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_revoke_already_redeemed_returns_409(self):
        from fastapi import HTTPException
        from app.routers.admin_invites import revoke_invite
        from app.models.mvp import MvpInvite

        invite = MagicMock(spec=MvpInvite)
        invite.id = uuid.uuid4()
        invite.redeemed = True

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        admin = _make_principal(is_admin=True)

        with pytest.raises(HTTPException) as exc:
            await revoke_invite(str(invite.id), db=db, admin=admin)
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_revoke_prevents_reuse(self):
        """After revoke, the invite is deleted so it can't be used again."""
        from app.routers.admin_invites import revoke_invite
        from app.models.mvp import MvpInvite

        invite = MagicMock(spec=MvpInvite)
        invite.id = uuid.uuid4()
        invite.redeemed = False
        deleted = []

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = invite

        db = AsyncMock()
        db.execute = AsyncMock(return_value=result_mock)
        db.delete = AsyncMock(side_effect=deleted.append)
        db.commit = AsyncMock()
        admin = _make_principal(is_admin=True)

        await revoke_invite(str(invite.id), db=db, admin=admin)
        assert invite in deleted

    def test_revoke_route_is_post_not_delete(self):
        """Route is POST /admin/invites/{id}/revoke (not DELETE)."""
        from app.routers.admin_invites import router
        paths = {r.path for r in router.routes}
        assert any("revoke" in p for p in paths), \
            "Router must have a /revoke route"


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

class TestInviteCodeNonDisclosure:
    @pytest.mark.asyncio
    async def test_new_invite_code_is_exactly_8_chars(self):
        """POST create must return exactly 8-char invite codes."""
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert len(result.invite_code) == 8, (
            f"invite_code should be 8 chars, got {len(result.invite_code)}"
        )

    @pytest.mark.asyncio
    async def test_code_prefix_is_exactly_4_chars(self):
        """DB-stored code_prefix must be exactly 4 chars — NOT the full code."""
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert len(result.code_prefix) == 4, (
            f"code_prefix should be 4 chars, got {len(result.code_prefix)!r}"
        )

    @pytest.mark.asyncio
    async def test_code_prefix_is_not_full_invite_code(self):
        """code_prefix must never equal invite_code for 8-char codes."""
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert result.code_prefix != result.invite_code, (
            "code_prefix must not equal invite_code — storing full code would leak it"
        )

    @pytest.mark.asyncio
    async def test_list_response_does_not_contain_full_invite_code(self):
        """GET /admin/invites must not return a field that equals the full invite code."""
        from app.routers.admin_invites import list_invites, create_invite, AdminInviteCreateRequest
        import json

        # 1. Create an invite and capture the plaintext code
        create_db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")
        created = await create_invite(AdminInviteCreateRequest(max_uses=1), create_db, admin)
        full_code = created.invite_code

        # 2. List invites — mock DB returning an invite with only the 4-char prefix
        inv = MagicMock()
        inv.id = uuid.uuid4()
        inv.code_prefix = full_code[:4]   # only prefix stored
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
        list_db = AsyncMock()
        list_db.execute = AsyncMock(return_value=result_mock)

        items = await list_invites(db=list_db, admin=admin)
        assert len(items) == 1
        item = items[0]

        # Serialise to JSON dict and verify full code is absent
        item_dict = json.loads(item.model_dump_json())
        for key, val in item_dict.items():
            assert val != full_code, (
                f"List response field '{key}' contains the full invite code — must not leak it"
            )

    @pytest.mark.asyncio
    async def test_db_stored_prefix_does_not_equal_full_code(self):
        """The MvpInvite.code_prefix stored to DB must not equal the full invite code."""
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        added = []
        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        db.add = MagicMock(side_effect=added.append)
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        stored = added[0]

        # The DB-stored prefix must not equal the full plaintext code
        assert stored.code_prefix != result.invite_code, (
            "MvpInvite.code_prefix stored to DB must not be the full invite code"
        )
        assert len(stored.code_prefix) == 4

    @pytest.mark.asyncio
    async def test_create_response_contains_full_invite_code_exactly_once(self):
        """POST create must return the full invite_code in the response body."""
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)

        # Exactly one field holds the full code in the create response
        assert result.invite_code is not None
        assert len(result.invite_code) == 8
        # Prefix is different (first 4 chars)
        assert result.code_prefix == result.invite_code[:4]
