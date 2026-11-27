# Database Schema

This document is derived directly from the SQLAlchemy models under `backend/app/models/`. A fresh schema is created with `Base.metadata.create_all()` in `app/db/session.py::init_db()`. An Alembic baseline revision (`backend/migrations/versions/0001_initial_schema.py`) uses the same `create_all()` call to stamp existing deployments; future changes require explicit incremental revisions.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how these tables are used and [DEPLOYMENT.md](DEPLOYMENT.md) for environment setup.

## 1. Conventions

| Convention | Implementation |
| --- | --- |
| Base | Every model inherits `app.db.base.Base` (a SQLAlchemy 2 `DeclarativeBase`) |
| Primary key | `app.db.base.IdMixin` adds `id: Integer, primary_key=True, autoincrement=True` |
| Timestamps | `app.db.base.TimestampMixin` adds `created_at` and `updated_at` (`DateTime`, Python default `utcnow_naive()`, server default `CURRENT_TIMESTAMP`) |
| Time storage | "Naive UTC" `DateTime` for mixin columns; most event fields (`started_at`, `observed_at`, `collected_at`, …) are `String(40)` ISO strings produced by `app.core.timeutil.iso()` |
| Flexible data | `JSON` columns for lists/dicts (sources, evidence, config, results, recommendations) |
| Types | SQLite by default (`sqlite:///./data/serpscope.db`), PostgreSQL URL supported by configuration; no database-specific column types in models |
| SQLite PRAGMAs | `journal_mode=WAL`, `foreign_keys=ON`, `synchronous=NORMAL` applied on every connection |

> **Caution:** `create_all()` only creates missing tables. It does not add columns or change types on an existing database. For schema evolution, ship and run an explicit idempotent Alembic revision; revisions `0002_supplied_metrics`, `0003_honest_foundation`, `0004_token_revocation`, `0005_user_token_version` and `0006_shared_rate_limits` cover the changes added after the baseline.

There are **45 tables** across seven model modules.

## 2. Identity and access (`app/models/auth.py`)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `organizations` | Tenant / client organisation | `id`, `name`, `slug` (unique, indexed), `plan` (default `demo`), `is_demo`, `retention_days` (default 365), `created_at`, `updated_at` |
| `users` | Local accounts | `id`, `email` (unique, indexed), `full_name`, `hashed_password` (PBKDF2 string), `global_role` (default `viewer`), `is_active`, `is_demo`, `token_version` (default `0`; bumped by `POST /auth/logout-all`), timestamps |
| `memberships` | User ↔ organisation role assignment | `id`, `user_id` → `users.id` (CASCADE, indexed), `organization_id` → `organizations.id` (CASCADE, indexed), `role` (default `viewer`), timestamps |
| `audit_logs` | Action trail | `id`, `organization_id` → `organizations.id` (SET NULL, indexed), `user_id` → `users.id` (SET NULL, indexed), `project_id` (indexed, no FK), `action` (indexed), `target`, `details` (JSON), timestamps |
| `revoked_tokens` | Logout denylist | `id`, `token_digest` (unique, indexed; HMAC-SHA256 of the bearer token, never the raw token), `expires_at` (indexed, original JWT expiry), timestamps |
| `rate_limit_windows` | Shared mutating-route counters | `id`, `window_key` (unique, indexed; HMAC-SHA256 of UTC day, route bucket and socket peer, never the raw peer), `window_start` (indexed, epoch seconds), `count`, timestamps |

## 3. Projects, sources and jobs (`app/models/projects.py`)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `projects` | A client website / engagement | `id`, `organization_id` → `organizations.id` (CASCADE, indexed), `name`, `domain` (indexed), `status` (default `active`), `description`, `is_demo`, `settings` (JSON), timestamps |
| `project_members` | Optional project-level role | `id`, `project_id` → `projects.id` (CASCADE, indexed), `user_id` → `users.id` (CASCADE, indexed), `role` (default `editor`), timestamps |
| `data_sources` | Import provenance record | `id`, `project_id` → `projects.id` (CASCADE, indexed), `source_type` (indexed), `name`, `file_name`, `row_count`, `rejected_count`, `status`, `data_kind` (default `imported`), `meta_info` (JSON), `job_id` (indexed, no FK), timestamps |
| `jobs` | The database-backed job queue | `id`, `organization_id` (indexed, nullable), `project_id` (indexed, nullable), `job_type` (indexed), `name`, `status` (default `queued`, indexed), `progress`, `total`, `message`, `payload` (JSON), `result` (JSON), `error` (Text), `created_by` (indexed, nullable), `started_at`, `finished_at`, `cancel_requested`, timestamps |
| `tasks` | Delivery task list | `id`, `project_id` → `projects.id` (CASCADE, indexed), `title`, `description`, `assignee_id` (indexed, no FK), `status` (indexed), `priority`, `due_date`, `issue_id` (indexed, no FK), `approval_status`, timestamps |
| `meeting_notes` | Client meeting notes | `id`, `project_id` → `projects.id` (CASCADE, indexed), `title`, `notes`, `meeting_date`, timestamps |

Explicit indexes in this module: `ix_jobs_status_created` on `(jobs.status, jobs.created_at)` and `ix_sources_project_type` on `(data_sources.project_id, data_sources.source_type)`.

## 4. URL inventory, links and crawl evidence (`app/models/inventory.py`)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `url_records` | Shared, interpreted URL inventory | `id`, `project_id` (indexed), `url` (Text), `url_hash` (indexed), `normalized_url` (indexed), `hostname` (indexed), `path`, provenance (`sources` JSON, `data_kind` indexed, `first_seen`, `last_seen`), crawl summary (`crawled` indexed, `crawled_at`, `http_status` indexed, `content_type`, `response_time_ms`, `content_size`), on-page fields (`title`, `meta_description`, `h1`/`h2` JSON, `canonical`, `meta_robots`, `x_robots_tag`, `robots_allowed`, `indexable` indexed, `word_count`, link/image counts, `schema_types`, `og`, `hreflang`, `pagination`, `redirect_chain`, `redirected_to`, `crawl_depth` indexed, `javascript_rendered`), classification/business fields (`page_type` indexed, `template` indexed, `importance`, `in_sitemap`, `is_orphan`, `has_traffic`, `clicks`, `impressions`, `sessions`, `conversions`, `revenue`, `referring_domains`, `notes`), timestamps |
| `link_edges` | Observed internal/external links | `id`, `project_id` (indexed), `source_url` (indexed), `target_url` (indexed), `anchor`, `link_type` (indexed), `is_broken` (indexed), `observed_at`, `crawl_id` (indexed, no FK), timestamps |
| `sitemap_entries` | Raw sitemap `<loc>` entries | `id`, `project_id` (indexed), `source`, `loc` (indexed), `lastmod`, `changefreq`, `priority`, `observed_at`, timestamps |
| `crawls` | Crawl run header / counters | `id`, `project_id` (indexed), `job_id` (indexed, no FK), `name`, `config` (JSON), `status` (indexed), `discovered`, `crawled`, `failed`, `excluded`, `started_at`, `finished_at`, `summary` (JSON), `data_kind` (default `live`), timestamps |
| `crawl_observations` | Raw, uninterpreted fetch evidence | `id`, `crawl_id` → `crawls.id` (CASCADE, indexed), `project_id` (indexed), `requested_url`, `final_url`, `status_code` (indexed), `headers` (JSON), `redirect_chain` (JSON), `body_excerpt`, `response_time_ms`, `content_size`, `extracted` (JSON), `error`, `observed_at`, timestamps |

Explicit indexes: `ix_url_project_status`, `ix_url_project_type`, **`ix_url_project_hash` (unique on `project_id`, `url_hash`)**, `ix_url_project_norm`, `ix_edge_project_target`, `ix_edge_project_source`, `ix_obs_crawl_status` on `(crawl_id, status_code)`.

## 5. Analysis (`app/models/analysis.py`)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `issues` | Technical issue groups | `id`, `project_id` (indexed), `code` (indexed), `name`, `category` (indexed), `severity` (indexed), `priority` (indexed), `priority_score`, `business_impact`, `affected_count`, `page_templates` (JSON), `evidence` (JSON), `priority_explanation`, `recommended_fix`, `owner`, `status` (indexed), `due_date`, `resolution_notes`, `validation_status`, `detected_at`, `source` (default `rule-engine`), `is_demo`, timestamps |
| `issue_urls` | URL-to-issue link with evidence | `id`, `issue_id` → `issues.id` (CASCADE, indexed), `project_id` (indexed), `url` (indexed), `evidence` (JSON), timestamps |
| `orphan_records` | Orphan reconciliation register | `id`, `project_id` (indexed), `url` (indexed), `normalized_url` (indexed), `classification` (indexed), `sources` (JSON), `internal_inlinks`, `crawled`, `indexable`, traffic/business columns (`clicks`, `impressions`, `sessions`, `conversions`, `revenue`, `referring_domains`), `importance`, `priority` (indexed), `priority_score`, `score_components` (JSON), `confidence`, `likely_cause`, `recommended_action`, `page_type`, `observed_at`, timestamps |
| `content_analyses` | Content scoring rows | `id`, `project_id` (indexed), `url` (indexed), `title`, `title_length`, `meta_length`, `h1_count`, `h2_count`, `word_count`, `intent_alignment`, `topic_gaps`/`entity_gaps` (JSON), `image_alt_issues`, `schema_recommendations` (JSON), `internal_link_suggestions` (JSON), `freshness_signal`, `decay_signal`, `score`, `findings` (JSON), `data_kind` (default `derived`), timestamps |
| `content_briefs` | Editable briefs (stay drafts) | `id`, `project_id` (indexed), `url` (indexed), `primary_keyword`, `secondary_keywords` (JSON), `intent`, `audience`, `page_purpose`, `suggested_title`, `suggested_h1`, `suggested_headings` (JSON), `questions` (JSON), `entities` (JSON), `internal_links` (JSON), `conversion_objective`, `recommended_schema` (JSON), `sources` (JSON), `approval_status` (default `draft`), timestamps |
| `link_suggestions` | Reviewable internal-link proposals | `id`, `project_id` (indexed), `source_url` (indexed), `target_url` (indexed), `anchor_text`, `relevance`, `target_importance`, `current_status`, `reason`, `status` (default `proposed`), `source` (default `graph-rule`), timestamps |

Explicit indexes: `ix_issue_project_priority` and `ix_orphan_project_priority`.

## 6. Keywords (`app/models/keywords.py`)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `keywords` | Keyword inventory | `id`, `project_id` (indexed), `keyword` (indexed), `normalized` (indexed), `intent` (indexed), `intent_source`, `intent_override`, `topic` (indexed), `parent_topic` (indexed), `country` (indexed), `language`, `volume` (nullable), `difficulty` (nullable), `cpc` (nullable), `competition`, `serp_features` (JSON), `source` (indexed), `collected_at`, `confidence`, `cluster_id` → `keyword_clusters.id` (SET NULL, indexed), `cluster_method`, `evidence` (JSON), timestamps |
| `keyword_clusters` | Cluster definitions | `id`, `project_id` (indexed), `name` (indexed), `parent_topic`, `intent`, `method`, `reasoning`, `primary_keyword`, `review_status` (default `auto`), `keywords` (JSON), timestamps |
| `keyword_mappings` | One primary keyword per URL | `id`, `project_id` (indexed), `url` (indexed), `url_id` (indexed, no FK), `primary_keyword` (indexed), `secondary_keywords`/`supporting_keywords` (JSON), `intent`, `cluster_name`, `page_type`, `funnel_stage`, `target_location`, `confidence`, `reasoning`, `recommended_changes` (JSON), `suggested_internal_links` (JSON), `status` (default `suggested`, indexed), `cannibalisation_risk`, `source` (default `rule-based`), timestamps |

Explicit indexes: `ix_kw_project_norm` and `ix_mapping_project_primary`.

## 7. Domain-specific enterprise tables (`app/models/enterprise.py`)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `competitors` | Competitor set | `id`, `project_id` (indexed), `domain` (indexed), `name`, `notes`, timestamps |
| `keyword_gaps` | Gap hypotheses | `id`, `project_id` (indexed), `competitor_id` (indexed, no FK), `keyword` (indexed), `intent`, `competitor_url`, `our_url`, `gap_type` (indexed), `priority`, `evidence` (JSON), `recommendation`, timestamps |
| `international_plans` | Market rollout plans | `id`, `project_id` (indexed), `market` (indexed), `language`, `url_structure`, `search_intent`, `service_pages`/`supporting_content`/`keyword_clusters`/`hreflang_recommendations`/`internal_link_architecture`/`roadmap` (JSON), `evidence` (JSON), timestamps |
| `hreflang_records` | Hreflang diagnostics | `id`, `project_id` (indexed), `url` (indexed), `lang`, `target`, `status` (indexed), `evidence`, timestamps |
| `locations` | Local/GBP location inventory | `id`, `project_id` (indexed), `name` (indexed), `brand` (indexed), `address`, `city` (indexed), `state` (indexed), `postal_code`, `country` (indexed), `phone`, `website`, `category`, `status` (indexed), `landing_page`, `local_keywords`/`issues` (JSON), `audit`/`performance` (JSON), `duplicate_group`, `data_kind`, timestamps |
| `products` | E-commerce product diagnostics | `id`, `project_id` (indexed), `url` (indexed), `product_id` (indexed), `title`, `description`, `category` (indexed), `price`, `availability`, `identifier`, `canonical`, `schema_types`/`diagnostics` (JSON), `status` (indexed), `priority`, `data_kind`, timestamps |
| `migration_mappings` | Redirect map with risk flags | `id`, `project_id` (indexed), `old_url` (indexed), `new_url` (indexed), `redirect_status` (indexed), `redirect_chain` (JSON), `http_status`, `old_canonical`, `new_canonical`, `old_indexable`, `new_indexable`, `in_old_sitemap`, `in_new_sitemap`, `clicks`, `revenue`, `risk` (indexed), `findings` (JSON), `recommendation`, timestamps |
| `migration_projects` | Migration programme header | `id`, `project_id` (indexed), `name`, `migration_type`, `old_domain`, `new_domain`, `phase`, `checklist` (JSON), `summary` (JSON), timestamps |
| `ai_visibility_records` | Manual AI/answer-engine observations | `id`, `project_id` (indexed), `question` (indexed), `answer_engine` (indexed), `observed_at`, `brand_mentioned`, `competitor_mentioned` (JSON), `cited_url`, `source`, `data_kind`, `notes`, timestamps |
| `ai_readiness_items` | Rule-derived AEO readiness | `id`, `project_id` (indexed), `url` (indexed), `dimension` (indexed), `status`, `evidence`, `recommendation`, `data_kind` (default `derived`), timestamps |

## 8. Operations (`app/models/operations.py`)

| Table | Purpose | Key columns |
| --- | --- | --- |
| `analytics_records` | Imported analytics metrics | `id`, `project_id` (indexed), `source` (indexed), `data_kind` (indexed), `dimension_type` (indexed), `dimension` (indexed), `period_start` (indexed), `period_end`, `clicks`, `impressions`, `ctr`, `position`, `sessions`, `conversions`, `revenue`, `device`, `country`, `collected_at`, timestamps |
| `reports` | Generated report records | `id`, `project_id` (indexed), `title`, `report_type` (indexed), `period_start`, `period_end`, `content` (JSON), `missing_data` (JSON), `generated_by`, `file_path`, timestamps |
| `forecasts` | Editable scenarios | `id`, `project_id` (indexed), `name`, `inputs` (JSON), `scenarios` (JSON), `formulas` (JSON), `created_by` (indexed, nullable), timestamps |
| `workflows` | Workflow definitions | `id`, `project_id` (indexed), `name`, `description`, `trigger` (indexed), `schedule`, `steps` (JSON), `enabled`, `last_run_at`, `notification_email`, timestamps |
| `workflow_runs` | Workflow execution history | `id`, `workflow_id` (indexed, no FK), `project_id` (indexed), `job_id` (indexed, no FK), `status` (indexed), `step_results` (JSON), `error`, `started_at`, `finished_at`, timestamps |
| `integrations` | Provider connections with encrypted credentials | `id`, `project_id` (indexed, nullable), `organization_id` (indexed, nullable), `provider` (indexed), `display_name`, `status` (indexed), `mode` (indexed, default `csv_import`), `credentials_encrypted` (Text — Fernet token), `config` (JSON), `last_sync_at`, `notes`, timestamps |
| `supplied_metrics` | Verbatim user-supplied vendor/private rows | `id`, `project_id` (indexed), `source` (indexed), `signal` (indexed), `data_kind` (indexed), `dimension` (indexed), `period_start`, `period_end`, `metrics` (JSON — original import columns), `meta_info` (JSON), `data_source_id` (indexed), timestamps |
| `demo_scenarios` | Interview-ready demo content | `id`, `key` (unique, indexed), `title`, `question`, `context`, `challenge`, `steps`/`modules`/`expected_findings` (JSON), `interpretation`, `recommended_actions` (JSON), `limitations`, `interview_explanation`, `dataset_info` (JSON), timestamps |
| `case_study_views` | Anonymous case-study view | `id`, `project_id` (indexed), `report_id` (indexed), `path`, `source`, timestamps |

## 9. Foreign keys and cascade behaviour

| Child column | Parent | On delete |
| --- | --- | --- |
| `memberships.user_id` | `users.id` | CASCADE |
| `memberships.organization_id` | `organizations.id` | CASCADE |
| `audit_logs.user_id` / `audit_logs.organization_id` | `users.id` / `organizations.id` | SET NULL |
| `projects.organization_id` | `organizations.id` | CASCADE |
| `project_members.project_id` / `.user_id` | `projects.id` / `users.id` | CASCADE |
| `data_sources.project_id` | `projects.id` | CASCADE |
| `tasks.project_id` / `meeting_notes.project_id` | `projects.id` | CASCADE |
| `crawl_observations.crawl_id` | `crawls.id` | CASCADE |
| `issues.id` ← `issue_urls.issue_id` | `issues.id` | CASCADE |
| `keywords.cluster_id` | `keyword_clusters.id` | SET NULL |

Most other `project_id`, `job_id`, `crawl_id`, `workflow_id` and `*_id` columns are **plain indexed integers without a foreign key constraint** (for example `jobs.project_id`, `url_records.project_id`, `workflow_runs.job_id`). Application code, not the database, enforces those relationships. SQLite foreign key enforcement is enabled via PRAGMA; PostgreSQL deployments get the declared constraints only where a `ForeignKey` exists.

## 10. Growth and retention notes

- The unique `(project_id, url_hash)` index on `url_records` plus paginated reads is what supports the 100,000-URL acceptance test in [TESTING.md](TESTING.md).
- `Organization.retention_days` exists as a configuration column (default 365); no automatic purge job was found in the code, so retention must be handled operationally.
- `DemoScenario` rows and `is_demo`/`data_kind` flags label synthetic data; demo data is never mixed with live observations without a source label.
