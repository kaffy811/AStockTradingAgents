"""
Phase MVP-R1.3-sec — Invite Code Hasher Unit Tests
12 tests

Coverage:
  1.  normalize_invite_code: 8-char input is uppercased
  2.  normalize_invite_code: 8-char input is stripped
  3.  normalize_invite_code: legacy (non-8-char) preserves case
  4.  normalize_invite_code: legacy code is stripped but NOT uppercased
  5.  hash_invite_code: 8-char code returns HMAC-SHA256 (v2), not SHA-256
  6.  hash_invite_code: 8-char HMAC output is 64-char hex
  7.  hash_invite_code: same 8-char code always produces same HMAC
  8.  hash_invite_code: different HMAC secrets → different hashes (key sensitivity)
  9.  hash_invite_code: legacy (non-8-char) code returns SHA-256 (v1)
  10. hash_invite_code: 8-char code with missing secret raises RuntimeError
  11. hash_invite_code: lowercase 8-char input hashes identically to uppercase
  12. startup_validation rejects missing INVITE_CODE_HMAC_SECRET in staging
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

_SECRET_A = "secret-A-for-invite-hmac-32bytes!!"   # 35 bytes
_SECRET_B = "secret-B-for-invite-hmac-32bytes!!"   # 35 bytes


def _make_settings(secret: str = _SECRET_A) -> MagicMock:
    s = MagicMock()
    s.invite_code_hmac_secret = secret
    return s


def _expected_hmac(code_upper8: str, secret: str = _SECRET_A) -> str:
    key = secret.encode("utf-8")
    msg = f"invite|v2|{code_upper8}".encode("utf-8")
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


# ===========================================================================
# 1. normalize_invite_code: 8-char input is uppercased
# ===========================================================================

class TestNormalizeInviteCode:
    def test_8char_is_uppercased(self):
        from app.services.invite_hasher import normalize_invite_code
        assert normalize_invite_code("abcd1234") == "ABCD1234"

    def test_8char_is_stripped(self):
        from app.services.invite_hasher import normalize_invite_code
        assert normalize_invite_code("  ABCD1234  ") == "ABCD1234"

    def test_legacy_preserves_case(self):
        """Non-8-char codes must NOT be uppercased."""
        from app.services.invite_hasher import normalize_invite_code
        code = "aBcDeFgHiJkLmNoP"  # 16 chars
        assert normalize_invite_code(code) == code

    def test_legacy_is_stripped_but_not_uppercased(self):
        from app.services.invite_hasher import normalize_invite_code
        code = "  MixedCaseToken  "
        assert normalize_invite_code(code) == "MixedCaseToken"


# ===========================================================================
# 5-8. hash_invite_code for 8-char codes (HMAC-SHA256 v2)
# ===========================================================================

class TestHashInviteCode8Char:
    def test_8char_uses_hmac_not_sha256(self):
        """8-char code must return HMAC, not plain SHA-256."""
        from app.services.invite_hasher import hash_invite_code
        settings = _make_settings()
        code = "ABCD1234"
        result = hash_invite_code(code, settings)
        plain = hashlib.sha256(code.encode()).hexdigest()
        assert result != plain, "Must use HMAC, not plain SHA-256"
        assert result == _expected_hmac(code)

    def test_8char_hmac_output_is_64_hex(self):
        from app.services.invite_hasher import hash_invite_code
        settings = _make_settings()
        result = hash_invite_code("WXYZ5678", settings)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_8char_hmac_is_deterministic(self):
        from app.services.invite_hasher import hash_invite_code
        settings = _make_settings()
        code = "EFGH2345"
        assert hash_invite_code(code, settings) == hash_invite_code(code, settings)

    def test_different_secrets_produce_different_hashes(self):
        """HMAC must be key-sensitive — different secrets → different digests."""
        from app.services.invite_hasher import hash_invite_code
        code = "MNPQ6789"
        h_a = hash_invite_code(code, _make_settings(_SECRET_A))
        h_b = hash_invite_code(code, _make_settings(_SECRET_B))
        assert h_a != h_b, "Different HMAC secrets must produce different hashes"


# ===========================================================================
# 9. hash_invite_code for legacy (non-8-char) codes (SHA-256 v1)
# ===========================================================================

class TestHashInviteCodeLegacy:
    def test_legacy_code_uses_sha256(self):
        """Non-8-char codes use plain SHA-256 for backwards compatibility."""
        from app.services.invite_hasher import hash_invite_code
        code = "aBcDeFgHiJkLmNoPqRsTuVwXyZ123456789012"  # 39 chars
        settings = _make_settings()
        expected = hashlib.sha256(code.encode()).hexdigest()
        assert hash_invite_code(code, settings) == expected

    def test_legacy_code_no_secret_needed(self):
        """Legacy codes must not require INVITE_CODE_HMAC_SECRET."""
        from app.services.invite_hasher import hash_invite_code
        settings = _make_settings(secret="")  # empty secret
        code = "SomeLegacyTokenWithLotsOfChars"  # 30 chars
        # Should not raise RuntimeError
        result = hash_invite_code(code, settings)
        assert len(result) == 64


# ===========================================================================
# 10. Missing secret raises RuntimeError for 8-char codes
# ===========================================================================

class TestMissingSecret:
    def test_8char_without_secret_raises(self):
        """An 8-char code with empty INVITE_CODE_HMAC_SECRET must raise RuntimeError."""
        from app.services.invite_hasher import hash_invite_code
        settings = _make_settings(secret="")
        with pytest.raises(RuntimeError, match="INVITE_CODE_HMAC_SECRET"):
            hash_invite_code("ABCD1234", settings)


# ===========================================================================
# 11. Lowercase 8-char input normalizes to same hash as uppercase
# ===========================================================================

class TestLowercaseNormalization:
    def test_lowercase_8char_hashes_identically_to_uppercase(self):
        from app.services.invite_hasher import hash_invite_code
        settings = _make_settings()
        assert hash_invite_code("abcd1234", settings) == hash_invite_code("ABCD1234", settings)


# ===========================================================================
# 12. startup_validation rejects missing INVITE_CODE_HMAC_SECRET in staging
# ===========================================================================

class TestStartupValidationInviteHmac:
    def _make_settings_stub(self, **kwargs):
        """Build a minimal settings stub for startup_validation tests."""
        base = {
            "app_env": "staging",
            "email_verification_hmac_secret": "a" * 32,
            "email_verification_required": True,
            "email_provider": "resend",
            "email_api_key": "key",
            "email_from": "no-reply@example.com",
            "invite_code_hmac_secret": "",
            "secret_key": "jwt-secret-" + "x" * 32,
        }
        base.update(kwargs)
        s = MagicMock()
        for k, v in base.items():
            setattr(s, k, v)
        return s

    def test_missing_invite_hmac_raises(self):
        from app.core.startup_validation import validate_startup_config
        s = self._make_settings_stub(invite_code_hmac_secret="")
        with pytest.raises(ValueError, match="INVITE_CODE_HMAC_SECRET"):
            validate_startup_config(s)

    def test_short_invite_hmac_raises(self):
        from app.core.startup_validation import validate_startup_config
        s = self._make_settings_stub(invite_code_hmac_secret="short")
        with pytest.raises(ValueError, match="too short"):
            validate_startup_config(s)

    def test_invite_hmac_equal_to_jwt_secret_raises(self):
        from app.core.startup_validation import validate_startup_config
        shared = "a" * 32
        s = self._make_settings_stub(invite_code_hmac_secret=shared, secret_key=shared)
        with pytest.raises(ValueError, match="SECRET_KEY"):
            validate_startup_config(s)

    def test_invite_hmac_equal_to_email_hmac_raises(self):
        from app.core.startup_validation import validate_startup_config
        shared = "a" * 32
        s = self._make_settings_stub(
            invite_code_hmac_secret=shared,
            email_verification_hmac_secret=shared,
        )
        with pytest.raises(ValueError, match="EMAIL_VERIFICATION_HMAC_SECRET"):
            validate_startup_config(s)

    def test_valid_invite_hmac_passes(self):
        from app.core.startup_validation import validate_startup_config
        s = self._make_settings_stub(
            invite_code_hmac_secret="b" * 32,
            secret_key="c" * 32,
            email_verification_hmac_secret="d" * 32,
        )
        # Should not raise
        validate_startup_config(s)
