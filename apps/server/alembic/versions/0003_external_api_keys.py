"""Add external API client, key, and usage event tables.

Revision ID: 0003_external_api_keys
Revises: 0002_add_usage_fields
Create Date: 2026-06-02
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_external_api_keys"
down_revision: Union[str, None] = "0002_add_usage_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_clients",
        sa.Column("id", sa.String(21), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.execute(
        "CREATE TRIGGER trg_api_clients_updated_at BEFORE UPDATE ON api_clients "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("idx_api_clients_status", "api_clients", ["status"])

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(21), primary_key=True),
        sa.Column("client_id", sa.String(21), nullable=False),
        sa.Column("public_id", sa.String(21), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("key_last4", sa.String(4), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False, server_default="live"),
        sa.Column("scopes", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("allowed_model_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("allowed_prompt_ids", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("allowed_ips", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("allowed_origins", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["client_id"], ["api_clients.id"], ondelete="CASCADE"),
    )
    op.execute(
        "CREATE TRIGGER trg_api_keys_updated_at BEFORE UPDATE ON api_keys "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.create_index("idx_api_keys_client_id", "api_keys", ["client_id"])
    op.create_index("idx_api_keys_public_id", "api_keys", ["public_id"], unique=True)
    op.create_index("idx_api_keys_status", "api_keys", ["status"])

    op.create_table(
        "api_usage_events",
        sa.Column("id", sa.String(21), primary_key=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(21), nullable=False),
        sa.Column("api_key_id", sa.String(21), nullable=False),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("model_id", sa.String(255), nullable=True),
        sa.Column("prompt_id", sa.String(21), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_latency_ms", sa.Integer(), nullable=True),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("request_bytes", sa.Integer(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.execute("CREATE INDEX idx_usage_client_created ON api_usage_events (client_id, created_at DESC)")
    op.execute("CREATE INDEX idx_usage_key_created ON api_usage_events (api_key_id, created_at DESC)")
    op.execute("CREATE INDEX idx_usage_model_created ON api_usage_events (model_id, created_at DESC)")
    op.create_index("idx_usage_trace_id", "api_usage_events", ["trace_id"])


def downgrade() -> None:
    op.drop_index("idx_usage_trace_id", table_name="api_usage_events")
    op.drop_index("idx_usage_model_created", table_name="api_usage_events")
    op.drop_index("idx_usage_key_created", table_name="api_usage_events")
    op.drop_index("idx_usage_client_created", table_name="api_usage_events")
    op.drop_table("api_usage_events")

    op.drop_index("idx_api_keys_status", table_name="api_keys")
    op.drop_index("idx_api_keys_public_id", table_name="api_keys")
    op.drop_index("idx_api_keys_client_id", table_name="api_keys")
    op.execute("DROP TRIGGER IF EXISTS trg_api_keys_updated_at ON api_keys")
    op.drop_table("api_keys")

    op.drop_index("idx_api_clients_status", table_name="api_clients")
    op.execute("DROP TRIGGER IF EXISTS trg_api_clients_updated_at ON api_clients")
    op.drop_table("api_clients")
