"""Add a per-user token version for account-wide sign-out.

Revision ID: 0005_user_token_version
Revises: 0004_token_revocation
Create Date: 2026-11-27

Every new access token carries the user's current ``ver``. Incrementing the
column invalidates all previously issued tokens for that account, while older
tokens without the claim remain valid at version 0 until the next sign-out.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_user_token_version"
down_revision = "0004_token_revocation"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names() and column in {
        c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)
    }


def upgrade() -> None:
    """Add the column only when create_all has not already done so."""
    if _has_column("users", "token_version"):
        return
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    if not _has_column("users", "token_version"):
        return
    op.drop_column("users", "token_version")
