"""
Chat Session & Message models — Phase C3 Chat API MVP.

Tables:
  chat_sessions  — per-user conversation sessions
  chat_messages  — messages within a session (user + assistant)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── ORM Models ─────────────────────────────────────────────────────────────────

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    __table_args__ = (
        Index("idx_chat_sessions_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # active | archived | deleted
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    session_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    __table_args__ = (
        Index("idx_chat_messages_session_created", "session_id", "created_at"),
        Index("idx_chat_messages_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # user | assistant | system
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    # Empty string ("") for messages that only have a confirmation card
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # text | tool_trace | confirmation | result | error
    message_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="text", server_default="text"
    )
    tool_events: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    cards: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    # Stored when response contains a pending action requiring user confirmation
    confirmation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    msg_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Pydantic Schemas ───────────────────────────────────────────────────────────

_ALLOWED_LANGUAGES = {"zh-CN", "en-US", "zh-TW", "ja-JP", "ko-KR", "es-ES"}


class ChatSessionCreateRequest(BaseModel):
    title: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if len(v) > 100:
                raise ValueError("title 不能超过 100 字符")
            if not v:
                return None
        return v


class ChatSessionCreateResponse(BaseModel):
    session_id: uuid.UUID
    title: str | None
    status: str
    created_at: datetime


class ChatSessionListItem(BaseModel):
    session_id: uuid.UUID
    title: str | None
    status: str
    last_message_at: datetime | None
    preview: str


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionListItem]
    total: int


class ChatMessageItem(BaseModel):
    message_id: uuid.UUID
    role: str
    content: str
    message_type: str
    tool_events: list
    cards: list
    confirmation: dict | None
    created_at: datetime


class ChatSessionDetailResponse(BaseModel):
    session_id: uuid.UUID
    title: str | None
    status: str
    messages: list[ChatMessageItem]


class ChatMessageSendRequest(BaseModel):
    content: str
    output_language: str = "zh-CN"

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("消息内容不能为空")
        if len(v) > 4000:
            raise ValueError("消息内容不能超过 4000 字符")
        return v

    @field_validator("output_language")
    @classmethod
    def validate_output_language(cls, v: str) -> str:
        if v not in _ALLOWED_LANGUAGES:
            raise ValueError(f"output_language 不支持 '{v}'")
        return v


class ChatMessageSendResponse(BaseModel):
    message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    status: str
    answer: str
    tool_events: list
    cards: list
    confirmation: dict | None


class ChatConfirmRequest(BaseModel):
    confirmation_id: str
    confirmed: bool


class ChatConfirmResponse(BaseModel):
    status: str
    answer: str
    tool_events: list
    cards: list
