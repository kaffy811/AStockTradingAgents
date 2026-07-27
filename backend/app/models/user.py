import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── ORM model ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
    # Phase MVP-R1.3: NULL = email not yet verified
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
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


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: EmailStr
    password: str = Field(min_length=8)
    invite_code: str = Field(min_length=8, max_length=64)
    # Phase MVP-R1.3: optional here; enforced server-side when
    # settings.email_verification_required is True
    email_verification_code: Optional[str] = Field(None, min_length=6, max_length=6)


class LoginRequest(BaseModel):
    # Accepts username OR email in this field
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserPublic(BaseModel):
    id: uuid.UUID
    username: str
    email: EmailStr
    is_active: bool
    is_admin: bool
    email_verified: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, user: "User") -> "UserPublic":
        return cls(
            id=user.id,
            username=user.username,
            email=user.email,
            is_active=user.is_active,
            is_admin=user.is_admin,
            email_verified=user.email_verified_at is not None,
            created_at=user.created_at,
        )
