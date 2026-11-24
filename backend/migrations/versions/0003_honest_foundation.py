"""Add anonymous case-study views and AI observation provenance fields.

Revision ID: 0003_honest_foundation
Revises: 0002_supplied_metrics
Create Date: 2026-11-24

No live vendor or answer-engine connector is added by this migration. It only
stores evidence the user deliberately supplies and anonymous page-view counts.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_honest_foundation"
down_revision = "0002_supplied_metrics"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return _has_table(table) and column in {c["name"] for c in _inspector().get_columns(table)}


def upgrade() -> None:
    """Create only what create_all has not already created."""
    if _has_table("ai_visibility_records"):
        if not _has_column("ai_visibility_records", "answer_url"):
            op.add_column("ai_visibility_records", sa.Column("answer_url", sa.Text(), nullable=False, server_default=""))
        if not _has_column("ai_visibility_records", "locale"):
            op.add_column("ai_visibility_records", sa.Column("locale", sa.String(length=20), nullable=False, server_default=""))

    if not _has_table("case_study_views"):
        op.create_table(
            "case_study_views",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("report_id", sa.Integer(), nullable=True),
            sa.Column("path", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("source", sa.String(length=40), nullable=False, server_default="case_study_detail"),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        )
        for name, columns in (
            ("ix_case_study_views_project_id", ["project_id"]),
            ("ix_case_study_views_report_id", ["report_id"]),
        ):
            op.create_index(name, "case_study_views", columns)


def downgrade() -> None:
    """Remove this phase's columns and view table; earlier evidence is preserved."""
    if _has_table("case_study_views"):
        for name in ("ix_case_study_views_report_id", "ix_case_study_views_project_id"):
            op.drop_index(name, table_name="case_study_views")
        op.drop_table("case_study_views")
    if _has_table("ai_visibility_records"):
        if _has_column("ai_visibility_records", "locale"):
            op.drop_column("ai_visibility_records", "locale")
        if _has_column("ai_visibility_records", "answer_url"):
            op.drop_column("ai_visibility_records", "answer_url")
