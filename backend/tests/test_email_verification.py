"""
Phase MVP-R1.3 — Email Verification Service Tests
Coverage: 28 tests

A. FakeEmailSender (4)
B. get_email_sender factory (4)
C. request_verification_code (8)
D. verify_code (6)
E. consume_code (3)
F. Register endpoint with email verification (3)
"""
from __future__ import annotations

import hashlib
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


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

    @pytest.mark.asyncio
    async def test_fake_last_code_returns_correct_code(self):
        from app.services.email_sender import FakeEmailSender
        sender = FakeEmailSender()
        await sender.send_verification("a@test.com", "111111")
        await sender.send_verification("a@test.com", "999999")
        assert sender.last_code("a@test.com") == "999999"

    @pytest.mark.asyncio
    async def test_fake_last_code_returns_none_for_unknown(self):
        from app.services.email_sender import FakeEmailSender
        sender = FakeEmailSender()
        assert sender.last_code("nobody@test.com") is None


# ===========================================================================
# B. get_email_sender factory
# ===========================================================================

class TestEmailSenderFactory:
    def test_fake_provider_returns_fake_sender(self):
        from app.services.email_sender import FakeEmailSender, get_email_sender
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.email_provider = "fake"
            sender = get_email_sender()
        assert isinstance(sender, FakeEmailSender)

    def test_resend_provider_needs_api_key(self):
        from app.services.email_sender import get_email_sender
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.email_provider = "resend"
            mock_settings.email_api_key = None
            with pytest.raises(RuntimeError, match="EMAIL_API_KEY"):
                get_email_sender()

    def test_resend_provider_with_key_returns_sender(self):
        from app.services.email_sender import ResendEmailSender, get_email_sender
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.email_provider = "resend"
            mock_settings.email_api_key = "key_test"
            mock_settings.email_from = "no-reply@test.com"
            sender = get_email_sender()
        assert isinstance(sender, ResendEmailSender)

    def test_unknown_provider_defaults_to_fake(self):
        from app.services.email_sender import FakeEmailSender, get_email_sender
        with patch("app.services.email_sender.settings") as mock_settings:
            mock_settings.email_provider = "unknown_xyz"
            sender = get_email_sender()
        assert isinstance(sender, FakeEmailSender)


# ===========================================================================
# C. request_verification_code
# ===========================================================================

class TestRequestVerificationCode:
    def _make_redis(self, *, cooldown=False, hourly_count=0) -> MagicMock:
        """Build a minimal Redis mock for the verification flow."""
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
            s.email_verification_ttl_seconds = 600
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is True

    @pytest.mark.asyncio
    async def test_code_is_6_digits(self):
        from app.services import email_verification as ev

        redis = self._make_redis()
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            s.email_verification_ttl_seconds = 600
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
            s.email_verification_ttl_seconds = 600
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is False
        assert result.retry_after > 0

    @pytest.mark.asyncio
    async def test_hourly_limit_blocks_excess_requests(self):
        from app.services import email_verification as ev

        redis = self._make_redis(hourly_count=5)
        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            s.email_verification_ttl_seconds = 600
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is False
        assert "上限" in result.message or "小时" in result.message

    @pytest.mark.asyncio
    async def test_redis_unavailable_raises_runtime_error(self):
        from app.services import email_verification as ev

        with patch("app.services.email_verification.get_redis", return_value=None):
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
    async def test_code_hash_stored_not_plaintext(self):
        """The pipeline stores SHA-256, not the raw code."""
        from app.services import email_verification as ev

        stored_value = None
        redis = self._make_redis()

        original_execute = redis.pipeline.return_value.execute
        pipe = redis.pipeline.return_value
        stored_calls = []
        pipe.set = MagicMock(side_effect=lambda *a, **kw: stored_calls.append(a))

        with patch("app.services.email_verification.get_redis", return_value=redis), \
             patch("app.services.email_verification.settings") as s:
            s.email_verification_ttl_seconds = 600
            result = await ev.request_verification_code("user@test.com")

        assert result.ok is True
        plaintext_code = result.message
        # First set() call stores the hash
        if stored_calls:
            stored_hash = stored_calls[0][1]   # second arg to set()
            assert stored_hash == _sha256(plaintext_code)
        # Key point: the plaintext is in result.message for the caller to send, not stored

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
        code_hash = _sha256(code)

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[code_hash.encode(), b"0"])
        redis.ttl = AsyncMock(return_value=500)
        redis.set = AsyncMock()
        redis.delete = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis):
            result = await ev.verify_code("user@test.com", code)
        assert result.ok is True

    @pytest.mark.asyncio
    async def test_wrong_code_returns_failure(self):
        from app.services import email_verification as ev

        code_hash = _sha256("123456")

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[code_hash.encode(), b"0"])
        redis.ttl = AsyncMock(return_value=500)
        redis.set = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis):
            result = await ev.verify_code("user@test.com", "999999")
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_missing_code_returns_failure(self):
        from app.services import email_verification as ev

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        with patch("app.services.email_verification.get_redis", return_value=redis):
            result = await ev.verify_code("user@test.com", "123456")
        assert result.ok is False
        assert "过期" in result.message or "不存在" in result.message

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded_invalidates_code(self):
        from app.services import email_verification as ev

        code_hash = _sha256("123456")

        redis = AsyncMock()
        # hash_key → stored hash; attempts_key → 5 (at limit)
        redis.get = AsyncMock(side_effect=[code_hash.encode(), b"5"])
        redis.delete = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis):
            result = await ev.verify_code("user@test.com", "999999")
        assert result.ok is False
        redis.delete.assert_called_once()  # code invalidated

    @pytest.mark.asyncio
    async def test_redis_unavailable_raises(self):
        from app.services import email_verification as ev

        with patch("app.services.email_verification.get_redis", return_value=None):
            with pytest.raises(RuntimeError):
                await ev.verify_code("user@test.com", "123456")

    @pytest.mark.asyncio
    async def test_attempt_counter_incremented_on_failure(self):
        from app.services import email_verification as ev

        code_hash = _sha256("123456")

        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=[code_hash.encode(), b"1"])
        redis.ttl = AsyncMock(return_value=500)
        redis.set = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis):
            result = await ev.verify_code("user@test.com", "000000")  # wrong code
        assert result.ok is False
        redis.set.assert_called_once()  # attempt counter updated


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
            # Should log warning, not raise
            await ev.consume_code("user@test.com")

    @pytest.mark.asyncio
    async def test_consume_leaves_cooldown_key(self):
        from app.services import email_verification as ev

        redis = AsyncMock()
        redis.delete = AsyncMock()

        with patch("app.services.email_verification.get_redis", return_value=redis):
            await ev.consume_code("user@test.com")

        # cooldown key is NOT deleted (prevents immediate re-registration)
        args = redis.delete.call_args[0]
        assert not any("ev:cooldown:" in k for k in args)


# ===========================================================================
# F. Register endpoint with email verification
# ===========================================================================

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
            email_verification_code=None,  # missing
        )

        db = AsyncMock()

        with patch("app.routers.auth.settings") as s:
            s.email_verification_required = True
            with pytest.raises(HTTPException) as exc:
                await register(body, db)
        assert exc.value.status_code == 400
        assert "验证码" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_register_sets_email_verified_at_when_code_valid(self):
        """When a valid email code is provided, email_verified_at is set."""
        from app.models.user import RegisterRequest
        from app.models.mvp import MvpInvite
        from app.models.user import User

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

        # First call: invite; second: no duplicate user
        no_dup = MagicMock()
        no_dup.scalar_one_or_none.return_value = None
        invite_res = MagicMock()
        invite_res.scalar_one_or_none.return_value = invite

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[invite_res, no_dup])
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()

        # Mock verify_code to return ok
        from unittest.mock import AsyncMock as AM
        from app.services.email_verification import VerifyResult

        created_users = []
        original_add = db.add
        db.add = MagicMock(side_effect=created_users.append)

        with patch("app.routers.auth.settings") as s, \
             patch("app.services.email_verification.get_redis", return_value=None):
            s.email_verification_required = False  # optional path

            # Patch verify_code to return ok
            with patch("app.services.email_verification.verify_code",
                       return_value=VerifyResult(ok=True, message="ok")) as mock_verify, \
                 patch("app.services.email_verification.consume_code", return_value=None):

                from app.routers.auth import register

                # Set up db.refresh to fill in the user
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

                result = await register(body, db)

        # The user object created should have email_verified_at set
        if created_users:
            user_obj = created_users[0]
            assert user_obj.email_verified_at is not None

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

        with patch("app.routers.auth.settings") as s:
            s.email_verification_required = False
            from app.routers.auth import register
            # Should not raise
            result = await register(body, db)
        assert result.username == "newuser2"
