"""Persist revoked bearer-token digests in the shared database.

Revision ID: 0004_token_revocation
Revises: 0003_honest_foundation
Create Date: 2026-11-27

A logout must survive a worker restart and apply to every API process. Only an
HMAC digest of the token is stored, never the token itself.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_token_revocation"
down_revision = "0003_honest_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the table only when create_all has not already done so."""
    if "revoked_tokens" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index(
        "ix_revoked_tokens_token_digest", "revoked_tokens", ["token_digest"], unique=True
    )
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])


def downgrade() -> None:
    if "revoked_tokens" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_index("ix_revoked_tokens_token_digest", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
