"""
app/services/email_sender.py — Abstract email sender + implementations.

Phase MVP-R1.3: email verification for invite-only registration.

Provider selection via EMAIL_PROVIDER env var:
  "fake"     — logs only, never sends real email (default; safe for tests/dev)
  "resend"   — https://resend.com transactional API
  "sendgrid" — SendGrid transactional API

Get the configured sender:
  from app.services.email_sender import get_email_sender
  sender = get_email_sender()
  await sender.send_verification(to_email="user@example.com", code="123456")

Never store API keys in code — they come from env/settings only.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from app.core.config import settings

log = logging.getLogger(__name__)


class EmailSender(ABC):
    """Abstract transactional email sender.

    Implementors must override `send_verification`.
    All methods are async to allow non-blocking HTTP calls.
    """

    @abstractmethod
    async def send_verification(self, to_email: str, code: str) -> None:
        """Send an email verification code to `to_email`.

        Args:
            to_email: recipient address (already normalized/validated)
            code:     6-digit verification code (plaintext)

        Raises:
            RuntimeError: if the underlying provider returns a non-2xx response
        """


# ---------------------------------------------------------------------------
# Fake sender — logs only; used in tests and local dev
# ---------------------------------------------------------------------------

class FakeEmailSender(EmailSender):
    """Never sends real email. Logs the code so manual testing is possible."""

    def __init__(self) -> None:
        self._sent: list[tuple[str, str]] = []   # (to_email, code)

    async def send_verification(self, to_email: str, code: str) -> None:
        self._sent.append((to_email, code))
        log.info(
            "[FakeEmailSender] verification code %s → %s (not sent)",
            code, to_email,
        )

    @property
    def sent(self) -> list[tuple[str, str]]:
        """All (to_email, code) pairs sent during this instance's lifetime."""
        return list(self._sent)

    def last_code(self, to_email: str) -> str | None:
        """Return the last code sent to `to_email`, or None."""
        for addr, code in reversed(self._sent):
            if addr == to_email:
                return code
        return None


# ---------------------------------------------------------------------------
# Resend provider — https://resend.com
# ---------------------------------------------------------------------------

class ResendEmailSender(EmailSender):
    def __init__(self, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from_address = from_address

    async def send_verification(self, to_email: str, code: str) -> None:
        import httpx  # optional dependency — only installed in production

        subject = "TradingAgents — 邮箱验证码"
        html = (
            f"<p>您的邮箱验证码为：</p>"
            f"<h2 style='letter-spacing:4px'>{code}</h2>"
            f"<p>验证码 10 分钟内有效，请勿泄露给他人。</p>"
        )
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self._from_address,
                    "to": [to_email],
                    "subject": subject,
                    "html": html,
                },
            )
        if res.status_code >= 300:
            raise RuntimeError(
                f"Resend API returned {res.status_code}: {res.text[:200]}"
            )
        log.info("Verification email sent via Resend to %s", to_email)


# ---------------------------------------------------------------------------
# SendGrid provider
# ---------------------------------------------------------------------------

class SendGridEmailSender(EmailSender):
    def __init__(self, api_key: str, from_address: str) -> None:
        self._api_key = api_key
        self._from_address = from_address

    async def send_verification(self, to_email: str, code: str) -> None:
        import httpx

        subject = "TradingAgents — 邮箱验证码"
        text = f"您的邮箱验证码为：{code}。验证码 10 分钟内有效，请勿泄露给他人。"
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": self._from_address},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": text}],
                },
            )
        if res.status_code >= 300:
            raise RuntimeError(
                f"SendGrid API returned {res.status_code}: {res.text[:200]}"
            )
        log.info("Verification email sent via SendGrid to %s", to_email)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_email_sender() -> EmailSender:
    """Return the configured EmailSender based on EMAIL_PROVIDER setting."""
    provider = getattr(settings, "email_provider", "fake").lower()

    if provider == "resend":
        api_key = getattr(settings, "email_api_key", None)
        from_addr = getattr(settings, "email_from", "noreply@tradingagents.ai")
        if not api_key:
            raise RuntimeError("EMAIL_API_KEY must be set when EMAIL_PROVIDER=resend")
        return ResendEmailSender(api_key=api_key, from_address=from_addr)

    if provider == "sendgrid":
        api_key = getattr(settings, "email_api_key", None)
        from_addr = getattr(settings, "email_from", "noreply@tradingagents.ai")
        if not api_key:
            raise RuntimeError("EMAIL_API_KEY must be set when EMAIL_PROVIDER=sendgrid")
        return SendGridEmailSender(api_key=api_key, from_address=from_addr)

    # Default: fake — safe for dev/test; never sends real email
    return FakeEmailSender()
