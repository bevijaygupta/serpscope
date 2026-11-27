"""Share mutating-route rate limits through the application database.

Revision ID: 0006_shared_rate_limits
Revises: 0005_user_token_version
Create Date: 2026-11-27

Only HMAC-digest keys, window start times and counts are stored. The socket
peer, headers, user identity and request contents are never persisted.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_shared_rate_limits"
down_revision = "0005_user_token_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the table only when create_all has not already done so."""
    if "rate_limit_windows" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "rate_limit_windows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("window_key", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.Float(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index(
        "ix_rate_limit_windows_window_key", "rate_limit_windows", ["window_key"], unique=True
    )
    op.create_index("ix_rate_limit_windows_window_start", "rate_limit_windows", ["window_start"])


def downgrade() -> None:
    if "rate_limit_windows" not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_index("ix_rate_limit_windows_window_start", table_name="rate_limit_windows")
    op.drop_index("ix_rate_limit_windows_window_key", table_name="rate_limit_windows")
    op.drop_table("rate_limit_windows")
