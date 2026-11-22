# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Required project documentation set: `README.md`, `docs/INSTALLATION.md`, `docs/API_DOCUMENTATION.md`, `docs/INTEGRATIONS.md`, `docs/DEMO_GUIDE.md`, `docs/INTERVIEW_DEMONSTRATIONS.md`, `docs/ROADMAP.md` and `docs/CHANGELOG.md`.
- A roadmap that separates implemented, partial and planned work with explicit priorities.
- Hosted deployment assets: `vercel.json` for the React UI and `render.yaml` for the FastAPI API, inline worker and Postgres, with one-time synthetic demo seeding.

### Changed

- Product and repository branding renamed from SEO Automation Lab to **SERPScope**, including UI labels, package metadata, docs, demo login and environment defaults.

### Added

- XLSX and JSON import parsing for URL and keyword uploads; JSON accepts arrays of objects or `{rows: [...]}` payloads.
- Final implementation report with completed / partial / pending status and evidence paths.

### Fixed

- Corrected documentation that described `backend/alembic.ini`, `backend/migrations/`, `frontend/nginx.conf`, `docker-compose.yml` and the in-app documentation index as missing; all are present in the repository.
- Corrected the Demo Guide crawler caveat: the current frontend default body already uses `start_url`, `crawl_delay`, `respect_robots` and `follow_external`.
- The crawler now checks robots.txt permission **before** every request (including redirect hops) and fails closed when robots.txt cannot be fetched. Stored `robots_allowed` reflects the actual decision.
- Job progress WebSocket now validates the bearer token (or `token` query parameter) and project scope.
- Documentation now reflects Alembic, JSON/XLSX imports, WebSocket authentication, the current test count and the crawler compliance behaviour.
- Startup bootstrap reuses an existing demo organisation slug instead of failing on seeded databases with no users.
- Large URL imports now use Core-batched inserts and bulk updates, keeping the 100,000-URL acceptance test inside its 90-second budget while preserving deduplication and source merging.

## [1.0.0] - 2026-11-22

Initial portfolio reference release of SERPScope.

### Added

- Full-stack application: FastAPI backend, React 18 / TypeScript / Vite frontend, SQLAlchemy models and SQLite-by-default storage.
- 23-module interface covering command centre, discovery, intent and content, market intelligence, intelligence and automation workflows.
- Authentication and authorisation: demo account bootstrap, HMAC-SHA256 signed bearer tokens, PBKDF2 password hashing, organisation/project scoping and write-role checks.
- Database-backed job queue with an inline API worker and a standalone `python -m app.workers.runner` worker, plus REST job status, cancellation, retry and a one-second polling WebSocket.
- Deterministic synthetic dataset generation seeded with `random.Random(20261122)`, with record-level `synthetic` / `simulated` labels and planted technical, content, link and analytics issue classes.
- Twelve curated demo scenarios, including a full audit preset, with interview explanations and stated limitations.
- Technical issue detection, URL inventory, raw crawl observations, orphan reconciliation, internal-link suggestions and weighted priority explanations.
- Keyword import, clustering, page mapping, cannibalisation checks, content scoring, editable briefs and content-gap analysis.
- AI-search readiness rules and manually recorded visibility observations; no answer-engine sampling or outcome guarantee is included.
- Forecasting with editable assumptions, three scenarios and sensitivity analysis, labelled as estimates rather than predictions.
- Report generation, workflows, schedules, audit trails and CSV/JSON/XLSX/PDF exports with spreadsheet-injection escaping and provenance columns.
- File upload endpoints for CSV/TSV/TXT/XML, JSON and XLSX inputs, sitemap parsing, URL normalisation and bounded batch imports.
- Integration provider registry with encrypted-at-rest credential records; OAuth and API-key modes are declarations only and no live vendor API calls are implemented.
- Container assets: backend and frontend Dockerfiles, `backend/alembic.ini`, `backend/migrations/`, `frontend/nginx.conf` and a root `docker-compose.yml` defining API, worker and frontend services.
- Backend test suite covering auth/RBAC, WebSocket auth, bounded pagination, exports, imports, planted-issue detection, orphan classification, link suggestions, keyword clustering/mapping, priority scoring, crawler safety, idempotent demo bootstrap and the 100,000-URL inventory path. The fast suite reports `36 passed, 1 deselected`.

### Security

- Signed bearer tokens, hashed passwords, project-scoped data access, SSRF validation for crawler targets and formula-injection escaping in exports.
- Integration credentials are encrypted at rest using a key derived from the configured `SECRET_KEY`.

> **Scope note:** this release is an engineering and process demonstration. Demo metrics are synthetic, no live vendor integrations are called, no real client crawl results are included, and no AI-search outcome is promised. See [INTEGRATIONS.md](INTEGRATIONS.md), [DEMO_GUIDE.md](DEMO_GUIDE.md) and [ROADMAP.md](ROADMAP.md).
