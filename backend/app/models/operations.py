"""Analytics, reporting, forecasting, workflow automation and integrations."""
from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class AnalyticsRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "analytics_records"
    project_id: Mapped[int] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    data_kind: Mapped[str] = mapped_column(String(30), default="imported", index=True)
    dimension_type: Mapped[str] = mapped_column(String(40), default="page", index=True)
    dimension: Mapped[str] = mapped_column(Text, index=True)
    period_start: Mapped[str | None] = mapped_column(String(20), index=True)
    period_end: Mapped[str | None] = mapped_column(String(20))
    clicks: Mapped[float] = mapped_column(default=0.0)
    impressions: Mapped[float] = mapped_column(default=0.0)
    ctr: Mapped[float] = mapped_column(default=0.0)
    position: Mapped[float] = mapped_column(default=0.0)
    sessions: Mapped[float] = mapped_column(default=0.0)
    conversions: Mapped[float] = mapped_column(default=0.0)
    revenue: Mapped[float] = mapped_column(default=0.0)
    device: Mapped[str] = mapped_column(String(40), default="")
    country: Mapped[str] = mapped_column(String(40), default="")
    collected_at: Mapped[str | None] = mapped_column(String(40))


class CaseStudyView(Base, IdMixin, TimestampMixin):
    """Anonymous case-study page view. No IP, cookie or other PII is stored."""
    __tablename__ = "case_study_views"
    project_id: Mapped[int] = mapped_column(index=True)
    report_id: Mapped[int | None] = mapped_column(index=True)
    path: Mapped[str] = mapped_column(String(255), default="")
    source: Mapped[str] = mapped_column(String(40), default="case_study_detail")


class Report(Base, IdMixin, TimestampMixin):
    __tablename__ = "reports"
    project_id: Mapped[int] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(250))
    report_type: Mapped[str] = mapped_column(String(60), default="weekly", index=True)
    period_start: Mapped[str | None] = mapped_column(String(20))
    period_end: Mapped[str | None] = mapped_column(String(20))
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    missing_data: Mapped[list] = mapped_column(JSON, default=list)
    generated_by: Mapped[str] = mapped_column(String(60), default="system")
    file_path: Mapped[str] = mapped_column(Text, default="")


class Forecast(Base, IdMixin, TimestampMixin):
    __tablename__ = "forecasts"
    project_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    scenarios: Mapped[dict] = mapped_column(JSON, default=dict)
    formulas: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(index=True)


class Workflow(Base, IdMixin, TimestampMixin):
    __tablename__ = "workflows"
    project_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    trigger: Mapped[str] = mapped_column(String(40), default="manual", index=True)
    schedule: Mapped[str] = mapped_column(String(80), default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[str | None] = mapped_column(String(40))
    notification_email: Mapped[str] = mapped_column(String(255), default="")


class WorkflowRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "workflow_runs"
    workflow_id: Mapped[int] = mapped_column(index=True)
    project_id: Mapped[int] = mapped_column(index=True)
    job_id: Mapped[int | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    step_results: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))


class Integration(Base, IdMixin, TimestampMixin):
    __tablename__ = "integrations"
    project_id: Mapped[int | None] = mapped_column(index=True)
    organization_id: Mapped[int | None] = mapped_column(index=True)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(40), default="not_configured", index=True)
    mode: Mapped[str] = mapped_column(String(40), default="csv_import", index=True)
    credentials_encrypted: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    last_sync_at: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text, default="")


class SuppliedMetric(Base, IdMixin, TimestampMixin):
    """A user-supplied vendor row. Values are stored verbatim, never inferred.

    `signal` groups rows into auditable capabilities (gsc, ga4, rank, backlinks,
    performance, crux, serp, paid, local, historical, keywords). `metrics` keeps
    the original import columns so the UI can show exactly what was supplied.
    """
    __tablename__ = "supplied_metrics"
    project_id: Mapped[int] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    signal: Mapped[str] = mapped_column(String(40), index=True)
    data_kind: Mapped[str] = mapped_column(String(40), default="imported", index=True)
    dimension: Mapped[str] = mapped_column(Text, index=True)
    period_start: Mapped[str | None] = mapped_column(String(20))
    period_end: Mapped[str | None] = mapped_column(String(20))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    meta_info: Mapped[dict] = mapped_column(JSON, default=dict)
    data_source_id: Mapped[int | None] = mapped_column(index=True)


class DemoScenario(Base, IdMixin, TimestampMixin):
    __tablename__ = "demo_scenarios"
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(250))
    question: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(Text, default="")
    challenge: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSON, default=list)
    modules: Mapped[list] = mapped_column(JSON, default=list)
    expected_findings: Mapped[list] = mapped_column(JSON, default=list)
    interpretation: Mapped[str] = mapped_column(Text, default="")
    recommended_actions: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[str] = mapped_column(Text, default="")
    interview_explanation: Mapped[str] = mapped_column(Text, default="")
    dataset_info: Mapped[dict] = mapped_column(JSON, default=dict)
