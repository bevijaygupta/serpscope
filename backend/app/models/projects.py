"""Projects, domains, data sources and jobs."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin


class Project(Base, IdMixin, TimestampMixin):
    __tablename__ = "projects"
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    domain: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active")
    description: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class ProjectMember(Base, IdMixin, TimestampMixin):
    __tablename__ = "project_members"
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(30), default="editor")


class DataSource(Base, IdMixin, TimestampMixin):
    __tablename__ = "data_sources"
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(60), index=True)
    name: Mapped[str] = mapped_column(String(200))
    file_name: Mapped[str] = mapped_column(String(255), default="")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="ready")
    data_kind: Mapped[str] = mapped_column(String(40), default="imported")
    meta_info: Mapped[dict] = mapped_column(JSON, default=dict)
    job_id: Mapped[int | None] = mapped_column(index=True)


class Job(Base, IdMixin, TimestampMixin):
    __tablename__ = "jobs"
    organization_id: Mapped[int | None] = mapped_column(index=True)
    project_id: Mapped[int | None] = mapped_column(index=True)
    job_type: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str] = mapped_column(String(500), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(index=True)
    started_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))
    cancel_requested: Mapped[bool] = mapped_column(default=False)


class Task(Base, IdMixin, TimestampMixin):
    __tablename__ = "tasks"
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    assignee_id: Mapped[int | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="P2")
    due_date: Mapped[str | None] = mapped_column(String(20))
    issue_id: Mapped[int | None] = mapped_column(index=True)
    approval_status: Mapped[str] = mapped_column(String(30), default="not_required")


class MeetingNote(Base, IdMixin, TimestampMixin):
    __tablename__ = "meeting_notes"
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str] = mapped_column(Text, default="")
    meeting_date: Mapped[str | None] = mapped_column(String(20))


Index("ix_jobs_status_created", Job.status, Job.created_at)
Index("ix_sources_project_type", DataSource.project_id, DataSource.source_type)
