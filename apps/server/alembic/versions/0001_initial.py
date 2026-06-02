"""Initial schema with updated_at triggers and GIN index on tags.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-01
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- updated_at trigger function (shared by all tables) ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
        $$ LANGUAGE plpgsql
        """
    )

    # --- models ---
    op.create_table(
        "models",
        sa.Column("id", sa.String(21), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("base_url", sa.Text, nullable=True),
        sa.Column("api_key_enc", sa.Text, nullable=True),
        sa.Column(
            "default_params", postgresql.JSONB, nullable=False, server_default="{}"
        ),
        sa.Column("aliases", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_models_updated_at BEFORE UPDATE ON models "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # --- prompts ---
    op.create_table(
        "prompts",
        sa.Column("id", sa.String(21), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("system", sa.Text, nullable=True),
        sa.Column("user_template", sa.Text, nullable=True),
        sa.Column("variables", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_prompts_updated_at BEFORE UPDATE ON prompts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("CREATE INDEX idx_prompts_tags ON prompts USING GIN (tags)")

    # --- prompt_versions (CASCADE on parent delete) ---
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("prompt_id", sa.String(21), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot", postgresql.JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["prompt_id"], ["prompts.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("prompt_id", "version", name="uq_prompt_versions_prompt_ver"),
    )

    # --- conversations (soft references, no FK on model_id/prompt_id) ---
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(21), primary_key=True),
        sa.Column("model_id", sa.String(21), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=True),
        sa.Column("prompt_id", sa.String(21), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("messages", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("meta", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.execute("CREATE INDEX idx_conversations_model ON conversations (model_id)")
    op.execute(
        "CREATE INDEX idx_conversations_created ON conversations (created_at DESC)"
    )
    op.execute(
        "CREATE TRIGGER trg_conversations_updated_at BEFORE UPDATE ON conversations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_conversations_updated_at ON conversations")
    op.execute("DROP TRIGGER IF EXISTS trg_prompts_updated_at ON prompts")
    op.execute("DROP TRIGGER IF EXISTS trg_models_updated_at ON models")
    op.drop_table("conversations")
    op.drop_table("prompt_versions")
    op.drop_table("prompts")
    op.drop_table("models")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
