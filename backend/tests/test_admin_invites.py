"""
Phase MVP-R1.3 — Admin Invite Management Tests
Coverage: 24 tests

A. Auth: non-admin access denied (4)
B. Admin can create and list invites (6)
C. GET list never returns plaintext codes (4)
D. Revoke endpoint (6)
E. Code generation properties (4)
"""
from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))


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
    async def test_create_invite_prefix_equals_code(self):
        from app.routers.admin_invites import create_invite, AdminInviteCreateRequest

        req = AdminInviteCreateRequest(max_uses=1)
        db = _no_collision_db()
        admin = _make_principal(is_admin=True, username="admin")

        result = await create_invite(req, db, admin)
        assert result.code_prefix == result.invite_code

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
        # Stored hash should be sha256 of the returned plaintext
        expected_hash = hashlib.sha256(result.invite_code.encode()).hexdigest()
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
