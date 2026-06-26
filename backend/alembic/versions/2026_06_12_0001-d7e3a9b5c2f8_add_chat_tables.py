"""add chat_sessions and chat_messages tables

Revision ID: d7e3a9b5c2f8
Revises: c5e9f12a3b87
Create Date: 2026-06-12 00:01:00

"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7e3a9b5c2f8'
down_revision: Union[str, None] = 'c5e9f12a3b87'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── chat_sessions ─────────────────────────────────────────────────────────
    op.create_table(
        'chat_sessions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            UUID(as_uuid=True),
            sa.ForeignKey('app_users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('title', sa.String(100), nullable=True),
        sa.Column(
            'status', sa.String(16), nullable=False, server_default='active'
        ),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('session_metadata', JSONB, nullable=False, server_default='{}'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'idx_chat_sessions_user_created',
        'chat_sessions',
        ['user_id', 'created_at'],
    )
    op.create_index(
        'idx_chat_sessions_user_id',
        'chat_sessions',
        ['user_id'],
    )

    # ── chat_messages ─────────────────────────────────────────────────────────
    op.create_table(
        'chat_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'session_id',
            UUID(as_uuid=True),
            sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            UUID(as_uuid=True),
            sa.ForeignKey('app_users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column(
            'message_type', sa.String(32), nullable=False, server_default='text'
        ),
        sa.Column('tool_events', JSONB, nullable=False, server_default='[]'),
        sa.Column('cards', JSONB, nullable=False, server_default='[]'),
        sa.Column('confirmation', JSONB, nullable=True),
        sa.Column('msg_metadata', JSONB, nullable=False, server_default='{}'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_index(
        'idx_chat_messages_session_created',
        'chat_messages',
        ['session_id', 'created_at'],
    )
    op.create_index(
        'idx_chat_messages_user',
        'chat_messages',
        ['user_id'],
    )


def downgrade() -> None:
    op.drop_index('idx_chat_messages_user', table_name='chat_messages')
    op.drop_index('idx_chat_messages_session_created', table_name='chat_messages')
    op.drop_table('chat_messages')

    op.drop_index('idx_chat_sessions_user_id', table_name='chat_sessions')
    op.drop_index('idx_chat_sessions_user_created', table_name='chat_sessions')
    op.drop_table('chat_sessions')
