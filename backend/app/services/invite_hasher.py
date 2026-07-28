"""
app/services/invite_hasher.py — Unified invite code hashing.

Phase MVP-R1.3-sec: Replaces ad-hoc SHA-256 calls scattered across routers
with a single, versioned implementation.

Hash scheme (version-dispatched on code length):

  v2  (len == 8, new-style): HMAC-SHA256(INVITE_CODE_HMAC_SECRET, "invite|v2|" + normalized)
  v1  (len != 8, legacy):    SHA-256(normalized)   — backwards-compatible for old token-urlsafe codes

Normalization:
  8-char codes  → strip + uppercase
  Legacy codes  → strip only (case-sensitive as originally stored)

Usage:
  from app.services.invite_hasher import hash_invite_code, normalize_invite_code

  normalized = normalize_invite_code(raw_input)
  digest      = hash_invite_code(raw_input, settings)

  # or call separately:
  h = hash_invite_code(already_normalized, settings)

Security notes:
  - INVITE_CODE_HMAC_SECRET must be at least 32 bytes in staging/production.
  - It must be different from SECRET_KEY and EMAIL_VERIFICATION_HMAC_SECRET.
  - With a secret the remaining 32-bit search space (32^4 after 4-char prefix
    leak) is protected against offline brute-force without the secret.
  - Legacy (v1) codes are already 48+ chars with 64-bit entropy — no HMAC needed.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import logging

log = logging.getLogger(__name__)


def normalize_invite_code(code: str) -> str:
    """Return the canonical form of an invite code for hashing.

    - Strip surrounding whitespace.
    - For exactly-8-char codes: uppercase (our unambiguous alphabet is all-caps).
    - For legacy codes (any other length): preserve original case.
    """
    stripped = code.strip()
    return stripped.upper() if len(stripped) == 8 else stripped


def hash_invite_code(code: str, settings) -> str:  # type: ignore[type-arg]
    """Hash a plaintext invite code for DB storage / lookup.

    Dispatches on code length after normalisation:
      - 8-char (new-style): HMAC-SHA256 with INVITE_CODE_HMAC_SECRET
      - other  (legacy):    plain SHA-256 for backwards compat

    Args:
        code:     Raw invite code (strip/uppercase applied internally).
        settings: Settings instance providing INVITE_CODE_HMAC_SECRET.

    Raises:
        RuntimeError: If the code is 8 chars and INVITE_CODE_HMAC_SECRET is not configured.
    """
    normalized = normalize_invite_code(code)

    if len(normalized) == 8:
        return _hash_v2(normalized, settings)
    else:
        return _hash_v1(normalized)


# ── Internal helpers (not part of the public API) ─────────────────────────────

def _hash_v2(normalized_8: str, settings) -> str:  # type: ignore[type-arg]
    """HMAC-SHA256 for new-style 8-char codes."""
    secret = getattr(settings, "invite_code_hmac_secret", "")
    if not secret:
        raise RuntimeError(
            "INVITE_CODE_HMAC_SECRET is not configured. "
            "Set a random 32+ byte value before using 8-char invite codes."
        )
    key = secret.encode("utf-8")
    msg = f"invite|v2|{normalized_8}".encode("utf-8")
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


def _hash_v1(normalized_code: str) -> str:
    """Plain SHA-256 for legacy (non-8-char) codes."""
    return hashlib.sha256(normalized_code.encode("utf-8")).hexdigest()
