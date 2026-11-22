"""Initial baseline schema for SERPScope.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-22
"""
from __future__ import annotations

from alembic import op

from app.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create every table defined by the current SQLAlchemy metadata."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Drop the baseline schema. Destructive; use only in disposable databases."""
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
