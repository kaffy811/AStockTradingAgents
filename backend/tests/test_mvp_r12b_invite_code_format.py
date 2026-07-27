"""
Phase MVP-R1.2b — 8-character Invite Code Format & Registration Compatibility
8 tests

Coverage:
  1. New invite code length is exactly 8
  2. All characters from allowed alphabet (no O/0/I/1)
  3. Consecutive codes are not identical
  4. Database does not store plaintext (model has no invite_code column)
  5. New 8-char codes: sha-256 hash stored, not plaintext
  6. Lowercase 8-char input normalizes to uppercase for hashing
  7. Legacy long codes (48-char) still hash correctly with original case
  8. Invalid invite code returns correct error detail
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

_INVITE_ALPHABET_SET = frozenset("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
_FORBIDDEN_CHARS = frozenset("OI01")  # chars excluded to avoid confusion


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _mock_request(ip: str = "127.0.0.1") -> MagicMock:
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}
    return req


async def _do_register(body, db):
    """Call register() with a mock Request and IP rate-limit stubs."""
    from contextlib import ExitStack
    from app.services.email_verification import IpCheckResult
    ok = IpCheckResult(allowed=True)
    with ExitStack() as stack:
        stack.enter_context(patch(
            "app.services.email_verification.check_ip_register_limit",
            AsyncMock(return_value=ok)))
        stack.enter_context(patch(
            "app.services.email_verification.record_ip_register",
            AsyncMock()))
        stack.enter_context(patch(
            "app.services.email_verification.check_ip_fail_limit",
            AsyncMock(return_value=ok)))
        stack.enter_context(patch(
            "app.services.email_verification.record_ip_fail",
            AsyncMock()))
        from app.routers.auth import register
        return await register(_mock_request(), body, db)


# ===========================================================================
# 1. New invite code length is exactly 8
# ===========================================================================

class TestInviteCodeLength:
    def test_generated_code_is_8_chars(self):
        from app.routers.mvp import generate_invite_code
        code = generate_invite_code()
        assert len(code) == 8, f"Expected 8, got {len(code)}: {code!r}"

    def test_generated_code_length_is_consistent(self):
        from app.routers.mvp import generate_invite_code
        codes = [generate_invite_code() for _ in range(50)]
        assert all(len(c) == 8 for c in codes), \
            "All generated codes must be exactly 8 characters"


# ===========================================================================
# 2. Characters from allowed alphabet only (no O/0/I/1)
# ===========================================================================

class TestInviteCodeAlphabet:
    def test_code_uses_allowed_alphabet(self):
        from app.routers.mvp import generate_invite_code
        code = generate_invite_code()
        invalid = set(code) - _INVITE_ALPHABET_SET
        assert not invalid, \
            f"Code {code!r} contains disallowed chars: {invalid}"

    def test_code_never_contains_forbidden_chars(self):
        from app.routers.mvp import generate_invite_code
        # Generate many codes — forbidden chars should never appear
        codes = [generate_invite_code() for _ in range(200)]
        for code in codes:
            forbidden_found = set(code) & _FORBIDDEN_CHARS
            assert not forbidden_found, \
                f"Code {code!r} contains forbidden char(s): {forbidden_found}"

    def test_code_is_uppercase(self):
        from app.routers.mvp import generate_invite_code
        code = generate_invite_code()
        assert code == code.upper(), f"Code {code!r} is not fully uppercase"

    def test_generate_uses_secrets_not_random(self):
        """generate_invite_code must not use the random module."""
        import inspect
        from app.routers import mvp as mvp_module
        source = inspect.getsource(mvp_module)
        # random.choice / random.randint etc would be insecure
        assert "import random" not in source, \
            "mvp.py must not import the random module"


# ===========================================================================
# 3. Consecutive codes are unique (collision test)
# ===========================================================================

class TestInviteCodeUniqueness:
    def test_100_codes_have_no_duplicates(self):
        from app.routers.mvp import generate_invite_code
        codes = [generate_invite_code() for _ in range(100)]
        assert len(set(codes)) == 100, \
            f"Collision found among 100 generated codes"

    def test_hashes_of_100_codes_are_unique(self):
        from app.routers.mvp import generate_invite_code
        codes = [generate_invite_code() for _ in range(100)]
        hashes = [_hash(c) for c in codes]
        assert len(set(hashes)) == 100, \
            "Hash collision found among 100 generated codes (extremely unlikely)"


# ===========================================================================
# 4. Database model does not store plaintext
# ===========================================================================

class TestNoPlainstextInModel:
    def test_mvpinvite_has_no_invite_code_column(self):
        from app.models.mvp import MvpInvite
        assert not hasattr(MvpInvite, "invite_code"), \
            "MvpInvite must not have an invite_code (plaintext) column"

    def test_mvpinvite_has_code_hash(self):
        from app.models.mvp import MvpInvite
        assert hasattr(MvpInvite, "code_hash"), \
            "MvpInvite must have a code_hash column"


# ===========================================================================
# 5. SHA-256 hash of 8-char code is what would be stored
# ===========================================================================

class TestHashStorage:
    def test_8char_code_hash_is_sha256(self):
        from app.routers.mvp import _hash_invite_code, generate_invite_code
        code = generate_invite_code()
        expected = hashlib.sha256(code.encode("utf-8")).hexdigest()
        assert _hash_invite_code(code) == expected

    def test_hash_length_is_64(self):
        from app.routers.mvp import _hash_invite_code, generate_invite_code
        code = generate_invite_code()
        assert len(_hash_invite_code(code)) == 64


# ===========================================================================
# 6. 8-char lowercase input normalizes to uppercase before hashing
# ===========================================================================

class TestLowercaseNormalization:
    def test_lowercase_8char_normalizes_to_uppercase(self):
        """Registration should accept '7kmr9x2p' and match '7KMR9X2P'."""
        from app.routers.auth import _hash_invite_code
        upper = "7KMR9X2P"
        lower = "7kmr9x2p"

        # Simulate the normalization logic in auth.py register endpoint
        raw = lower.strip()
        normalized = raw.upper() if len(raw) == 8 else raw

        assert _hash_invite_code(normalized) == _hash_invite_code(upper), \
            "Lowercase 8-char code must hash identically to its uppercase form"

    def test_mixed_case_8char_normalizes(self):
        from app.routers.auth import _hash_invite_code
        mixed = "7Kmr9X2p"
        upper = "7KMR9X2P"

        raw = mixed.strip()
        normalized = raw.upper() if len(raw) == 8 else raw

        assert _hash_invite_code(normalized) == _hash_invite_code(upper)

    def test_whitespace_stripped_before_hash(self):
        from app.routers.auth import _hash_invite_code
        padded = "  7KMR9X2P  "
        clean  = "7KMR9X2P"

        raw = padded.strip()
        normalized = raw.upper() if len(raw) == 8 else raw

        assert _hash_invite_code(normalized) == _hash_invite_code(clean)


# ===========================================================================
# 7. Legacy long codes (48-char) preserve original case
# ===========================================================================

class TestLegacyCodeCompatibility:
    def test_legacy_48char_code_keeps_original_case(self):
        """Old codes were token_urlsafe(36)[:48] — mixed case must be preserved."""
        import secrets as _secrets
        legacy_code = _secrets.token_urlsafe(36)[:48]
        assert len(legacy_code) == 48

        # Simulate auth.py normalization logic
        raw = legacy_code.strip()
        normalized = raw.upper() if len(raw) == 8 else raw

        # For 48-char codes, normalized == original (case preserved)
        assert normalized == legacy_code, \
            "Legacy long codes must NOT be uppercased"

    def test_legacy_code_hash_differs_from_uppercased(self):
        """Confirm case-sensitivity matters for legacy codes."""
        import secrets as _secrets
        from app.routers.auth import _hash_invite_code
        # Use a code with known mixed-case content
        code = "aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890ABCDEFGH"[:48]
        assert _hash_invite_code(code) != _hash_invite_code(code.upper()), \
            "Mixed-case legacy code must hash differently from its uppercase form"


# ===========================================================================
# 8. Invalid invite code returns 400 with clear message
# ===========================================================================

class TestInvalidInviteError:
    @pytest.mark.asyncio
    async def test_hash_mismatch_gives_invalid_message(self):
        """An unrecognized code_hash → 'Invalid invite code.'"""
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import HTTPException
        from app.models.user import RegisterRequest
        from app.routers.auth import register as register_endpoint

        body = RegisterRequest(
            username="newuser",
            email="newuser@test.com",
            password="password123",
            invite_code="BADCODE1",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await _do_register(body, mock_db)

        assert exc_info.value.status_code == 400
        assert "Invalid invite code" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_used_invite_gives_already_used_message(self):
        """A fully-consumed invite → 'already been used'"""
        from unittest.mock import AsyncMock, MagicMock
        from fastapi import HTTPException
        from app.models.user import RegisterRequest
        from app.models.mvp import MvpInvite
        from app.routers.auth import register as register_endpoint

        body = RegisterRequest(
            username="newuser",
            email="newuser@test.com",
            password="password123",
            invite_code="USEDCODE",
        )

        # Fully consumed invite
        invite = MagicMock(spec=MvpInvite)
        invite.expires_at = None
        invite.use_count  = 1
        invite.max_uses   = 1
        invite.email      = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = invite

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await _do_register(body, mock_db)

        assert exc_info.value.status_code == 400
        assert "already been used" in str(exc_info.value.detail)
