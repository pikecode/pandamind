"""Add usage tracking fields to conversations.

Revision ID: 0002_add_usage_fields
Revises: 0001_initial
Create Date: 2026-06-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_add_usage_fields"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("usage", postgresql.JSONB(), server_default="{}", nullable=False))
    op.add_column("conversations", sa.Column("provider_latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "provider_latency_ms")
    op.drop_column("conversations", "usage")
