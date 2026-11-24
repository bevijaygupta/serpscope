"""Add verbatim user-supplied vendor metrics.

Revision ID: 0002_supplied_metrics
Revises: 0001_initial
Create Date: 2026-11-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_supplied_metrics"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return table in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    """Create the supplied-metrics store unless create_all already did."""
    if _has_table("supplied_metrics"):
        return
    op.create_table(
        "supplied_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=60), nullable=False),
        sa.Column("signal", sa.String(length=40), nullable=False),
        sa.Column("data_kind", sa.String(length=40), nullable=False, server_default="imported"),
        sa.Column("dimension", sa.Text(), nullable=False),
        sa.Column("period_start", sa.String(length=20), nullable=True),
        sa.Column("period_end", sa.String(length=20), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("meta_info", sa.JSON(), nullable=False),
        sa.Column("data_source_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
    )
    op.create_index("ix_supplied_metrics_project_id", "supplied_metrics", ["project_id"])
    op.create_index("ix_supplied_metrics_source", "supplied_metrics", ["source"])
    op.create_index("ix_supplied_metrics_signal", "supplied_metrics", ["signal"])
    op.create_index("ix_supplied_metrics_data_kind", "supplied_metrics", ["data_kind"])
    op.create_index("ix_supplied_metrics_dimension", "supplied_metrics", ["dimension"])
    op.create_index("ix_supplied_metrics_data_source_id", "supplied_metrics", ["data_source_id"])


def downgrade() -> None:
    """Drop only this table; it contains user-supplied data, so use with care."""
    if not _has_table("supplied_metrics"):
        return
    for name in (
        "ix_supplied_metrics_data_source_id",
        "ix_supplied_metrics_dimension",
        "ix_supplied_metrics_data_kind",
        "ix_supplied_metrics_signal",
        "ix_supplied_metrics_source",
        "ix_supplied_metrics_project_id",
    ):
        op.drop_index(name, table_name="supplied_metrics")
    op.drop_table("supplied_metrics")
