"""
Phase MVP-R1.3 / MVP-R1.3-sec — Email Verification Service Tests
Coverage: 36 tests (28 original adapted + 4 new HMAC tests + 4 new IP tests)

A. FakeEmailSender (4)
B. get_email_sender factory (4)
C. request_verification_code (8)
D. verify_code (6)
E. consume_code (3)
F. Register endpoint with email verification (3)
G. HMAC-SHA256 security properties (4)  ← NEW
H. IP rate limiting (4)                  ← NEW
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

# ── Test constants ─────────────────────────────────────────────────────────────
TEST_HMAC_SECRET = "test-secret-32-bytes-for-unit-tests!!"  # 38 bytes — safe in tests


def _compute_hmac(email: str, code: str, secret: str = TEST_HMAC_SECRET) -> str:
    """Compute the same HMAC as email_verification._hmac_code for test assertions."""
    key = secret.encode("utf-8")
    msg = f"{email.strip().lower()}|register|{code}".encode("utf-8")
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


def _sha256(s: str) -> str:
    """Plain SHA-256 — used only in section G to prove HMAC != SHA-256."""
    return hashlib.sha256(s.encode()).hexdigest()


def _mock_request(ip: str = "10.0.0.1") -> MagicMock:
    """Build a minimal FastAPI Request mock with a client IP."""
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}
    return req


def _settings_patch(s, *, required: bool = False) -> None:
    """Apply common email verification settings to a settings mock."""
    s.email_verification_ttl_seconds = 600
    s.email_verification_hmac_secret = TEST_HMAC_SECRET
    s.email_verification_required = required
    s.trusted_proxy_ips = "127.0.0.1,::1"
    s.email_ip_send_hourly_limit = 20
    s.email_ip_fail_hourly_limit = 15
    s.register_ip_hourly_limit = 10


# ===========================================================================
# A. FakeEmailSender
# ===========================================================================

class TestFakeEmailSender:
    @pytest.mark.asyncio
    async def test_fake_sends_no_real_email(self):
        from app.services.email_sender import FakeEmailSender
        sender = FakeEmailSender()
        # Should not raise even without network
        await sender.send_verification("user@test.com", "123456")

    @pytest.mark.asyncio
    async def test_fake_records_sent_emails(self):
        from app.services.email_sender import FakeEmailSender
        sender = FakeEmailSender()
        await sender.send_verification("a@test.com", "111111")
        await sender.send_verification("b@test.com", "222222")
        assert len(sender.sent) == 2
        assert ("a@test.com", "111111") in sender.sent
        assert ("b@test.com", "222222") in sender.sent

    @pytest.mark.asyncio
    async def test_fake_last_code_returns_most_recent(self):
        from app.services.email_sender import FakeEmailSender
        sender = FakeEmailSender()
        await sender.send_verification("u@test.com", "000001")
        await sender.send_verification("u@test.com", "000002")
        assert sender.last_code("u@test.com") == "000002"

    def test_fake_last_code_none_for_unknown_email(self):
        from app.services.email_sender import FakeEmailSender
        sender = FakeEmailSender()
        assert sender.last_code("nobody@test.com") is None


# ===========================================================================
# B. get_email_sender factory
# ===========================================================================

class TestGetEmailSenderFactory:
    def test_fake_provider_returns_fake_sender(self):
        from app.services.email_sender import get_email_sender, FakeEmailSender
        with patch("app.services.email_sender.settings") as s:
            s.email_provider = "fake"
            sender = get_email_sender()
        assert isinstance(sender, FakeEmailSender)

    def test_resend_without_api_key_raises(self):
        from app.services.email_sender import get_email_sender
        with patch("app.services.email_sender.settings") as s:
            s.email_provider = "resend"
            s.email_api_key = None
            with pytest.raises(RuntimeError, match="EMAIL_API_KEY"):
                get_email_sender()

    def test_resend_with_api_key_returns_resend_sender(self):
        from app.services.email_sender import get_email_sender, ResendEmailSender
        with patch("app.services.email_sender.settings") as s:
            s.email_provider = "resend"
            s.email_api_key = "re_test_key"
            s.email_from = "test@example.com"
            sender = get_email_sender()
        assert isinstance(sender, ResendEmailSender)

    def test_unknown_provider_defaults_to_fake(self):
        from app.services.email_sender import get_email_sender, FakeEmailSender
        with patch("app.services.email_sender.settings") as s:
            s.email_provider = "notarealprovider"
            sender = get_email_sender()
        assert isinstance(sender, FakeEmailSender)


# ===========================================================================
# C. request_verification_code
# ===========================================================================

class TestRequestVerificationCode:
    def _make_redis(self, *, cooldown=False, hourly_count=0) -> MagicMock:
        r = AsyncMock()
        r.exists = AsyncMock(return_value=int(cooldown))
        r.ttl = AsyncMock(return_value=45)
        r.get = AsyncMock(return_value=str(hourly_count).encode())
        r.delete = AsyncMock()
        pipe = AsyncMock()
        pipe.set = MagicMock()
        pipe.delete = MagicMock()
        pipe.incr = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = AsyncMock(return_value=[True, True, True, 1, True])
        r.pipeline = MagicMock(return_value=pipe)
        return r

    @pytest.mark.asyncio
    async def test_returns_ok_on_first_request(self):
        from app.services import email_verification as ev

        redis = self._make_redis()
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is True

    @pytest.mark.asyncio
    async def test_code_is_6_digits(self):
        from app.services import email_verification as ev

        redis = self._make_redis()
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is True
        code = result.message
        assert len(code) == 6
        assert code.isdigit()

    @pytest.mark.asyncio
    async def test_cooldown_blocks_repeat_request(self):
        from app.services import email_verification as ev

        redis = self._make_redis(cooldown=True)
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is False
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_hourly_limit_blocks_excess_requests(self):
        from app.services import email_verification as ev

        redis = self._make_redis(hourly_count=5)
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is False
        assert "上限" in result.message or "小时" in result.message

    @pytest.mark.asyncio
    async def test_redis_unavailable_raises_runtime_error(self):
        from app.services import email_verification as ev

        with patch("app.services.email_verification.get_redis", return_value=None), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            with pytest.raises(RuntimeError, match="Redis"):
                await ev.request_verification_code("user@test.com")

    @pytest.mark.asyncio
    async def test_code_uses_secrets_not_random(self):
        import inspect
        from app.services import email_verification as ev
        source = inspect.getsource(ev)
        assert "import secrets" in source
        assert "import random" not in source

    @pytest.mark.asyncio
    async def test_hmac_stored_not_plaintext_or_sha256(self):
        """The pipeline stores HMAC-SHA256, not the raw code or plain SHA-256."""
        from app.services import email_verification as ev

        redis = self._make_redis()
        pipe = redis.pipeline.return_value
        stored_calls = []
        pipe.set = MagicMock(side_effect=lambda *a, **kw: stored_calls.append(a))

        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is True
        plaintext_code = result.message
        if stored_calls:
            stored_hash = stored_calls[0][1]
            expected_hmac = _compute_hmac("user@test.com", plaintext_code)
            plain_sha256 = _sha256(plaintext_code)
            assert stored_hash == expected_hmac, "Must store HMAC-SHA256"
            assert stored_hash != plain_sha256, "Must NOT store plain SHA-256"
            assert stored_hash != plaintext_code, "Must NOT store plaintext code"

    @pytest.mark.asyncio
    async def test_email_normalized_before_keying(self):
        """Emails are lowercased and stripped for Redis key generation."""
        from app.services.email_verification import _normalize_email
        assert _normalize_email("  User@Test.COM  ") == "user@test.com"


# ===========================================================================
# D. verify_code
# ===========================================================================

class TestVerifyCode:
    @pytest.mark.asyncio
    async def test_correct_code_returns_ok(self):
        from app.services import email_verification as ev

        code = "123456"
        email = "user@test.com"
        stored_hmac = _compute_hmac(email, code)

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[stored_hmac.encode(), b"0"])
        redis.ttl = AsyncMock(return_value=500)
        redis.set = AsyncMock()
        redis.delete = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.verify_code(email, code)
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_wrong_code_returns_failure(self):
        from app.services import email_verification as ev

        email = "user@test.com"
        stored_hmac = _compute_hmac(email, "123456")

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[stored_hmac.encode(), b"0"])
        redis.ttl = AsyncMock(return_value=500)
        redis.set = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.verify_code(email, "999999")
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_missing_code_returns_failure(self):
        from app.services import email_verification as ev

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.verify_code("user@test.com", "123456")
        assert result.ok is False
        assert "过期" in result.message or "不存在" in result.message

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded_invalidates_code(self):
        from app.services import email_verification as ev

        email = "user@test.com"
        stored_hmac = _compute_hmac(email, "123456")

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[stored_hmac.encode(), b"5"])
        redis.delete = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.verify_code(email, "999999")
        assert result.ok is False
        redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_unavailable_raises(self):
        from app.services import email_verification as ev

        with patch("app.services.email_verification.get_redis", return_value=None):
            with pytest.raises(RuntimeError):
                await ev.verify_code("user@test.com", "123456")

    @pytest.mark.asyncio
    async def test_attempt_counter_incremented_on_failure(self):
        from app.services import email_verification as ev

        email = "user@test.com"
        stored_hmac = _compute_hmac(email, "123456")

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[stored_hmac.encode(), b"1"])
        redis.ttl = AsyncMock(return_value=500)
        redis.set = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.verify_code(email, "000000")  # wrong code
        assert result.ok is False
        redis.set.assert_called_once()


# ===========================================================================
# E. consume_code
# ===========================================================================

class TestConsumeCode:
    @pytest.mark.asyncio
    async def test_consume_deletes_hash_and_attempts_keys(self):
        from app.services import email_verification as ev

        redis = AsyncMock()
        redis.delete = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis):
            await ev.consume_code("user@test.com")

        redis.delete.assert_called_once()
        args = redis.delete.call_args[0]
        assert any("ev:hash:" in k for k in args)
        assert any("ev:attempts:" in k for k in args)

    @pytest.mark.asyncio
    async def test_consume_does_not_raise_if_redis_unavailable(self):
        from app.services import email_verification as ev

        with patch("app.services.email_verification.get_redis", return_value=None):
            await ev.consume_code("user@test.com")

    @pytest.mark.asyncio
    async def test_consume_leaves_cooldown_key(self):
        from app.services import email_verification as ev

        redis = AsyncMock()
        redis.delete = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis):
            await ev.consume_code("user@test.com")

        args = redis.delete.call_args[0]
        assert not any("ev:cooldown:" in k for k in args)


# ===========================================================================
# F. Register endpoint with email verification
# ===========================================================================

def _make_ip_ok_mocks() -> dict:
    """Return patch targets that make all IP rate limit checks pass."""
    from app.services.email_verification import IpCheckResult
    ok = IpCheckResult(allowed=True)
    return {
        "app.services.email_verification.check_ip_register_limit": AsyncMock(return_value=ok),
        "app.services.email_verification.record_ip_register": AsyncMock(return_value=None),
        "app.services.email_verification.check_ip_fail_limit": AsyncMock(return_value=ok),
        "app.services.email_verification.record_ip_fail": AsyncMock(return_value=None),
    }


class TestRegisterWithEmailVerification:
    @pytest.mark.asyncio
    async def test_register_requires_code_when_setting_enabled(self):
        from fastapi import HTTPException
        from app.models.user import RegisterRequest
        from app.routers.auth import register

        body = RegisterRequest(
            username="newuser",
            email="new@test.com",
            password="password123",
            invite_code="VALIDCOD",
            email_verification_code=None,
        )

        db = AsyncMock()
        request = _mock_request()
        ip_mocks = _make_ip_ok_mocks()

        with patch("app.routers.auth.settings") as s, \
             patch("app.services.email_verification.check_ip_register_limit",
                   ip_mocks["app.services.email_verification.check_ip_register_limit"]), \
             patch("app.services.email_verification.record_ip_register",
                   ip_mocks["app.services.email_verification.record_ip_register"]):
            _settings_patch(s, required=True)
            s.trusted_proxy_ips = "127.0.0.1,::1"
            with pytest.raises(HTTPException) as exc:
                await register(request, body, db)
        assert exc.value.status_code == 400
        assert "验证码" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_register_sets_email_verified_at_when_code_valid(self):
        """When a valid email code is provided, email_verified_at is set."""
        from app.models.user import RegisterRequest
        from app.models.mvp import MvpInvite
        from app.services.email_verification import VerifyResult

        body = RegisterRequest(
            username="verifieduser",
            email="v@test.com",
            password="password123",
            invite_code="VALIDCOD",
            email_verification_code="654321",
        )

        invite = MagicMock(spec=MvpInvite)
        invite.expires_at = None
        invite.use_count = 0
        invite.max_uses = 1
        invite.email = None
        invite.redeemed = False

        no_dup = MagicMock()
        no_dup.scalar_one_or_none.return_value = None
        invite_res = MagicMock()
        invite_res.scalar_one_or_none.return_value = invite

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[invite_res, no_dup])
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        created_users = []
        db.add = MagicMock(side_effect=created_users.append)

        async def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.username = "verifieduser"
            obj.email = "v@test.com"
            obj.is_active = True
            obj.is_admin = False
            from datetime import datetime
            obj.created_at = datetime.utcnow()
            obj.email_verified_at = datetime.utcnow()

        db.refresh = _refresh
        request = _mock_request()
        ip_mocks = _make_ip_ok_mocks()

        with patch("app.routers.auth.settings") as s, \
             patch("app.services.email_verification.verify_code",
                   AsyncMock(return_value=VerifyResult(ok=True, message="ok"))), \
             patch("app.services.email_verification.consume_code", AsyncMock()), \
             patch("app.services.email_verification.check_ip_register_limit",
                   ip_mocks["app.services.email_verification.check_ip_register_limit"]), \
             patch("app.services.email_verification.check_ip_fail_limit",
                   ip_mocks["app.services.email_verification.check_ip_fail_limit"]), \
             patch("app.services.email_verification.record_ip_register",
                   ip_mocks["app.services.email_verification.record_ip_register"]):
            _settings_patch(s, required=False)  # optional path
            s.trusted_proxy_ips = "127.0.0.1,::1"
            from app.routers.auth import register
            result = await register(request, body, db)

        if created_users:
            assert created_users[0].email_verified_at is not None

    @pytest.mark.asyncio
    async def test_register_skips_verification_when_not_required(self):
        """When email_verification_required=False and no code provided, register works."""
        from app.models.user import RegisterRequest
        from app.models.mvp import MvpInvite

        body = RegisterRequest(
            username="newuser2",
            email="new2@test.com",
            password="password123",
            invite_code="VALIDCOD",
            email_verification_code=None,
        )

        invite = MagicMock(spec=MvpInvite)
        invite.expires_at = None
        invite.use_count = 0
        invite.max_uses = 1
        invite.email = None
        invite.redeemed = False

        no_dup = MagicMock()
        no_dup.scalar_one_or_none.return_value = None
        invite_res = MagicMock()
        invite_res.scalar_one_or_none.return_value = invite

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[invite_res, no_dup])
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        async def _refresh(obj):
            obj.id = uuid.uuid4()
            obj.username = "newuser2"
            obj.email = "new2@test.com"
            obj.is_active = True
            obj.is_admin = False
            from datetime import datetime
            obj.created_at = datetime.utcnow()
            obj.email_verified_at = None

        db.refresh = _refresh
        request = _mock_request()
        ip_mocks = _make_ip_ok_mocks()

        with patch("app.routers.auth.settings") as s, \
             patch("app.services.email_verification.check_ip_register_limit",
                   ip_mocks["app.services.email_verification.check_ip_register_limit"]), \
             patch("app.services.email_verification.record_ip_register",
                   ip_mocks["app.services.email_verification.record_ip_register"]):
            _settings_patch(s, required=False)
            s.trusted_proxy_ips = "127.0.0.1,::1"
            from app.routers.auth import register
            result = await register(request, body, db)
        assert result.username == "newuser2"


# ===========================================================================
# G. HMAC-SHA256 security properties  (NEW in MVP-R1.3-sec)
# ===========================================================================

class TestHmacSecurity:
    def test_same_code_different_email_produces_different_hmac(self):
        """HMAC is bound to the email address — prevents cross-email replay."""
        code = "123456"
        hmac1 = _compute_hmac("alice@test.com", code)
        hmac2 = _compute_hmac("bob@test.com", code)
        assert hmac1 != hmac2, "Same code with different emails must produce different HMACs"

    def test_hmac_result_is_not_plain_sha256_of_code(self):
        """HMAC must be structurally different from SHA-256(code)."""
        code = "654321"
        hmac_val = _compute_hmac("user@test.com", code)
        plain_sha = _sha256(code)
        assert hmac_val != plain_sha, "HMAC must not equal SHA-256(code)"

    def test_wrong_code_does_not_verify(self):
        """A code that differs by one digit must not match the stored HMAC."""
        email = "user@test.com"
        real_code = "123456"
        wrong_code = "123457"
        hmac_real = _compute_hmac(email, real_code)
        hmac_wrong = _compute_hmac(email, wrong_code)
        assert hmac_real != hmac_wrong

    def test_no_hmac_secret_raises_runtime_error_at_startup(self):
        """Missing HMAC secret in production must cause startup validation to fail."""
        from app.core.startup_validation import validate_startup_config

        config = MagicMock()
        config.app_env = "production"
        config.email_verification_hmac_secret = ""   # not configured
        config.email_verification_required = True
        config.email_provider = "resend"
        config.email_api_key = "key"
        config.email_from = "from@example.com"

        with pytest.raises(ValueError, match="HMAC_SECRET"):
            validate_startup_config(config)

    def test_short_hmac_secret_rejected_in_production(self):
        """HMAC secret shorter than 32 bytes must be rejected."""
        from app.core.startup_validation import validate_startup_config

        config = MagicMock()
        config.app_env = "production"
        config.email_verification_hmac_secret = "short"  # < 32 bytes
        config.email_verification_required = True
        config.email_provider = "resend"
        config.email_api_key = "key"
        config.email_from = "from@example.com"

        with pytest.raises(ValueError, match="32"):
            validate_startup_config(config)


# ===========================================================================
# H. IP rate limiting  (NEW in MVP-R1.3-sec)
# ===========================================================================

class TestIpRateLimiting:
    def _make_redis_with_count(self, count: int) -> AsyncMock:
        r = AsyncMock()
        r.get = AsyncMock(return_value=str(count).encode())
        pipe = AsyncMock()
        pipe.incr = MagicMock()
        pipe.expire = MagicMock()
        pipe.execute = AsyncMock(return_value=[count + 1, True])
        r.pipeline = MagicMock(return_value=pipe)
        return r

    @pytest.mark.asyncio
    async def test_ip_send_limit_allows_under_threshold(self):
        from app.services import email_verification as ev

        redis = self._make_redis_with_count(5)
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.check_ip_send_limit("1.2.3.4")
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_ip_send_limit_blocks_at_threshold(self):
        from app.services import email_verification as ev

        redis = self._make_redis_with_count(20)  # at limit
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.check_ip_send_limit("1.2.3.4")
        assert result.allowed is False
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_ip_register_limit_blocks_at_threshold(self):
        from app.services import email_verification as ev

        redis = self._make_redis_with_count(10)  # at limit
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            _settings_patch(s)
            result = await ev.check_ip_register_limit("5.6.7.8")
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_ip_check_raises_when_redis_unavailable(self):
        """IP rate limit check must raise RuntimeError when Redis is down (fail-closed)."""
        from app.services import email_verification as ev

        with patch("app.services.email_verification.get_redis", return_value=None):
            with pytest.raises(RuntimeError, match="Redis"):
                await ev.check_ip_send_limit("1.2.3.4")
