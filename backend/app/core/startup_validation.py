"""
app/core/startup_validation.py — Fail-fast production config checks.

Called at application startup (lifespan). Raises ValueError if the running
environment is staging or production and mandatory security settings are missing
or misconfigured. Development / test environments are NOT affected.

Validation rules when app_env in {"staging", "production"}:
  Email verification:
    1. EMAIL_VERIFICATION_HMAC_SECRET must be set and at least 32 bytes long.
    2. EMAIL_VERIFICATION_REQUIRED must be True.
    3. EMAIL_PROVIDER must not be "fake".
    4. When EMAIL_PROVIDER in {"resend", "sendgrid"}:
         EMAIL_API_KEY must be set (non-empty).
         EMAIL_FROM must be set (non-empty).

  Invite code hashing:
    5. INVITE_CODE_HMAC_SECRET must be set and at least 32 bytes.
    6. INVITE_CODE_HMAC_SECRET must not equal SECRET_KEY.
    7. INVITE_CODE_HMAC_SECRET must not equal EMAIL_VERIFICATION_HMAC_SECRET.

These checks are deliberately conservative — a misconfigured production deploy
should refuse to start rather than silently degrade security.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_PRODUCTION_ENVS = frozenset({"staging", "production"})


def validate_startup_config(settings) -> None:  # type: ignore[type-arg]
    """Raise ValueError if a production-required setting is missing or insecure.

    Designed to be called in the FastAPI lifespan startup hook.
    Takes a Settings instance (avoids circular import with config module).
    """
    env = getattr(settings, "app_env", "development").lower()
    if env not in _PRODUCTION_ENVS:
        return  # no enforcement in development / test

    errors: list[str] = []

    # ── Rule 1: Email HMAC secret ─────────────────────────────────────────────
    email_hmac = getattr(settings, "email_verification_hmac_secret", "")
    if not email_hmac:
        errors.append(
            "EMAIL_VERIFICATION_HMAC_SECRET is not set. "
            "Generate a random 32+ byte value and set it as an environment variable."
        )
    elif len(email_hmac.encode("utf-8")) < 32:
        errors.append(
            f"EMAIL_VERIFICATION_HMAC_SECRET is too short "
            f"({len(email_hmac.encode())} bytes; minimum 32 required)."
        )

    # ── Rule 2: Verification required ─────────────────────────────────────────
    email_required = getattr(settings, "email_verification_required", False)
    if not email_required:
        errors.append(
            "EMAIL_VERIFICATION_REQUIRED must be True in staging/production. "
            "Set EMAIL_VERIFICATION_REQUIRED=true in your environment."
        )

    # ── Rule 3: No fake provider ──────────────────────────────────────────────
    provider = getattr(settings, "email_provider", "fake").lower()
    if provider == "fake":
        errors.append(
            "EMAIL_PROVIDER=fake is not allowed in staging/production. "
            "Set EMAIL_PROVIDER=resend or EMAIL_PROVIDER=sendgrid."
        )

    # ── Rule 4: Real provider credentials ────────────────────────────────────
    if provider in ("resend", "sendgrid"):
        api_key = getattr(settings, "email_api_key", None)
        if not api_key:
            errors.append(f"EMAIL_API_KEY must be set when EMAIL_PROVIDER={provider}.")
        email_from = getattr(settings, "email_from", "")
        if not email_from:
            errors.append(f"EMAIL_FROM must be set when EMAIL_PROVIDER={provider}.")

    # ── Rule 5: Invite code HMAC secret ──────────────────────────────────────
    invite_hmac = getattr(settings, "invite_code_hmac_secret", "")
    if not invite_hmac:
        errors.append(
            "INVITE_CODE_HMAC_SECRET is not set. "
            "Generate a random 32+ byte value (distinct from all other secrets)."
        )
    elif len(invite_hmac.encode("utf-8")) < 32:
        errors.append(
            f"INVITE_CODE_HMAC_SECRET is too short "
            f"({len(invite_hmac.encode())} bytes; minimum 32 required)."
        )
    else:
        # ── Rule 6: Must not equal SECRET_KEY ────────────────────────────────
        jwt_secret = getattr(settings, "secret_key", "")
        if invite_hmac == jwt_secret:
            errors.append(
                "INVITE_CODE_HMAC_SECRET must not equal SECRET_KEY. "
                "Each secret must be independently random."
            )

        # ── Rule 7: Must not equal EMAIL_VERIFICATION_HMAC_SECRET ────────────
        if invite_hmac == email_hmac and email_hmac:
            errors.append(
                "INVITE_CODE_HMAC_SECRET must not equal EMAIL_VERIFICATION_HMAC_SECRET. "
                "Each secret must be independently random."
            )

    if errors:
        msg = (
            f"[startup_validation] Configuration errors for environment '{env}':\n"
            + "\n".join(f"  • {e}" for e in errors)
        )
        log.critical(msg)
        raise ValueError(msg)

    log.info(
        "[startup_validation] Production config OK (email_provider=%s, env=%s)",
        provider, env,
    )
