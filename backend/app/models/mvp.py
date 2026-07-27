"""
MVP Release Candidate models — Phase 6V-P1.32.

Tables:
  mvp_invite           — invite-only access control
  chat_feedback        — user answer feedback (thumbs up/down/report)
  mvp_analytics_event  — structured analytics events for launch monitoring
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MvpInvite(Base):
    """Invite-only access control for MVP launch.

    Plaintext invite codes are NEVER stored.
    Only the SHA-256 hex digest (code_hash) is persisted,
    plus a non-secret 8-char prefix (code_prefix) for admin display.
    """
    __tablename__ = "mvp_invite"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # SHA-256 of the plaintext invite code — unique, used for all lookups
    code_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    # First 8 chars of plaintext code for admin UI display only
    code_prefix: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Optional: email the code was bound to (validated at redemption)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="system"
    )
    redeemed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    redeemed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class ChatFeedback(Base):
    """User feedback on individual chat answers."""
    __tablename__ = "chat_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    message_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # feedback_type: thumbs_up | thumbs_down | report
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # feedback_detail: subcategory for 'report' (data_inaccurate, not_relevant, etc.)
    feedback_detail: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # answer_snippet: first 200 chars of the answer, no PII, no full prompt
    answer_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class MvpAnalyticsEvent(Base):
    """Structured analytics events for MVP launch monitoring and funnel tracking."""
    __tablename__ = "mvp_analytics_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # event_name: e.g. chat_answer_completed, fallback_triggered, feedback_submitted
    event_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    # event_category: chat | analysis | nav | error | provider
    event_category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # properties: arbitrary non-PII event metadata
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # error fields (for error-category events)
    error_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # error_severity: p0 | p1 | p2 | info
    error_severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
