"""
Provider audit trail — Phase 6V-P1.31.

Records real provider call outcomes to pi_real_provider_audit table.
All fields are hashed or non-sensitive — no raw API keys, no raw prompts.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from .models import ProviderCallOutcome


@dataclass
class AuditRecord:
    """An audit record for a single provider call attempt."""
    call_id: str
    phase: str
    outcome: ProviderCallOutcome
    model_id: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int
    usage_complete: bool
    estimated_cost_cny: str  # Decimal as string
    duration_ms: int
    error_type: str
    trigger: str  # what initiated the call
    config_version: int
    # Hash-only fields (no raw content)
    request_hash: str  # sha256 of prompt content
    response_hash: str  # sha256 of response content
    epoch: float


def _sha256_prefix(value: str, length: int = 16) -> str:
    """Return first `length` hex chars of sha256."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


class ProviderAuditLogger:
    """
    Writes audit records to the pi_real_provider_audit DB table.

    In P1.31, all calls are NOT_EXECUTED or fake — no real records generated.
    This class is implemented for P1.32+ real activation.
    """

    def __init__(self, db_session: Any | None = None) -> None:
        self._db = db_session

    def log_call(
        self,
        *,
        call_id: str,
        phase: str,
        outcome: ProviderCallOutcome,
        model_id: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        usage_complete: bool = False,
        estimated_cost_cny: str = "0",
        duration_ms: int = 0,
        error_type: str = "",
        trigger: str = "",
        config_version: int = 12,
        prompt_content: str = "",
        response_content: str = "",
    ) -> AuditRecord:
        record = AuditRecord(
            call_id=call_id,
            phase=phase,
            outcome=outcome,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
            usage_complete=usage_complete,
            estimated_cost_cny=estimated_cost_cny,
            duration_ms=duration_ms,
            error_type=error_type,
            trigger=trigger,
            config_version=config_version,
            request_hash=_sha256_prefix(prompt_content),
            response_hash=_sha256_prefix(response_content),
            epoch=time.time(),
        )
        # In P1.31, DB session is None (no real calls) — record is returned but not persisted
        # P1.32+ will wire this to the Alembic-migrated pi_real_provider_audit table
        return record

    def log_not_executed(self, *, call_id: str, phase: str, reason: str) -> AuditRecord:
        """Log a NOT_EXECUTED outcome (no real call made)."""
        return self.log_call(
            call_id=call_id,
            phase=phase,
            outcome=ProviderCallOutcome.NOT_EXECUTED,
            error_type=f"NOT_EXECUTED: {reason}",
            trigger="phase_gate_blocked",
        )
