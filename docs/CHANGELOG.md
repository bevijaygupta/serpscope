# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- One-click **public-evidence audit** for real domains: `POST /api/v1/audits/projects/{project_id}/public-audit/start`, `GET .../public-audit`, `.../export`, `.../reports` and the read-only `GET /api/v1/public/case-studies/{project_id}`. Findings carry sources, confidence and limitations, plus a six-month roadmap and six explicit missing-data statements.
- Editable PPTX export via `python-pptx`, alongside CSV/JSON/XLSX/PDF for public audits.
- Source-tracked robots.txt and sitemap-index evidence: 12 named AI/search agent rules, sitemap documents, `in_sitemap` provenance and AEO page evidence (question headings, answer paragraph, FAQ/Organization schema).
- Public SEO landing page and static assets (`robots.txt`, `sitemap.xml`, `llms.txt`, `manifest.webmanifest`, `favicon.svg`, `og-preview.svg`), plus Overview and Crawler entry points for the public audit.
- Regression tests for audit route registration, PPTX generation and the SQLite crawl-progress path.
- Honest foundation: stored audit history with before/after comparison and a labelled SERPScope-derived health score; verified AI-observation CSV/JSON import; scheduled `public_audit` workflow step; anonymous, non-PII case-study view analytics; and explicit vendor "Not supplied"/"Supplied"/"Synthetic" status explanations.
- GTM container `GTM-NZ3DFL7C` with a `gtag()`/`dataLayer` shim and privacy-safe `serpscope_*` events for page views, landing search, audit lifecycle, exports, AI imports, case-study views, module tabs and login. Events carry only route paths and fixed labels, never audited domains, emails, search-box values or user identity; DNT/local opt-out suppresses them.
- Anonymous on-site presence endpoints (`POST /api/v1/presence/ping`, `GET /api/v1/presence/count`) and a live visitor badge in the public and workspace headers. The backend stores only a SHA-256 hash of a random per-tab token for 60 seconds; no IP, cookie, referrer or Google identifier is used, and counts reset on API restart. This is explicitly not GA4 Realtime.
- **Google Search Overview** as the single Search Console interpretation surface in the authenticated Overview and published case studies. Workspace mode reads only `supplied-signals` and `supplied-records?signal=gsc`, shows verbatim labelled cells, and stays `Not supplied` without rows; public mode uses only the sanitised case-study payload and says **Private data excluded**. No client-side totals, averages, CTR, rankings, forecasts or trends are calculated.
- `ALLOW_SELF_REGISTRATION` configuration switch: self-registration is dev/local by default and returns `403` in production unless explicitly opted in. Registered accounts use validated email/password, role `viewer`, no organisation membership and a dedicated 5/600 s rate bucket.

### Changed

- Real end-to-end audit of `https://www.techmagnate.com/` recorded in the documentation: 303 discovered URLs, 60 fetched from a deliberately narrow sample, 0 failures, 60 sitemap entries from 9 documents, 6 finding groups and a 6-month roadmap. Demo metrics remain labelled synthetic; public-audit data is labelled as observed or derived public evidence.
- Hosted public audit completed on the same domain (job 17, report 2, crawl 1): 497 discovered, 219 fetched, 0 failed, 1 excluded, 12 finding groups and 6 roadmap months. Sitemap discovery timed out in the hosted run, so the hosted evidence states 0 sitemap entries; the local sample's 60 sitemap entries are kept separate rather than blended.
- Test counts updated to 80 fast / 81 full; hardening regressions now cover DNS SSRF, redirect hops, caller overrides, upload cleanup, export path confinement, cancellation-safe publication/imports/sitemap discovery, tenant/rate limits, demo bootstrap with pre-existing users and validated/disableable self-registration. Local 1k/10k/100k URL import/export benchmarks are recorded in `docs/TESTING.md`.

### Fixed

- Registered the audits router so authenticated audit and export endpoints no longer return 404.
- Roadmap builder no longer raises `KeyError` for sitemap counts.
- Sitemap evidence is committed before progress callbacks, preventing SQLite write locks during the one-click job.
- Audit view no longer fails before the first crawl, and the start endpoint accepts an optional body.
- Scheduled workflows no longer crash with "can't subtract offset-naive and offset-aware datetimes"; the scheduler now ticks in both the standalone worker and the inline API worker.
- The derived health score now returns "not enough evidence" below 10 fetched URLs, so a one-page smoke-test crawl is never shown as a misleading 0/100 site-wide score.
- Caller-supplied export names are collapsed to a safe filename stem and suffix, so `kind` query values cannot escape `EXPORT_DIR` or alter the download filename.
- Cancellation is checked before sitemap discovery and at each sitemap/page request, so a cancelled crawl no longer performs robots/sitemap fetches.
- URL and keyword import handlers stop before persisting rows, data sources or supplied metrics when their job has been cancelled.
- Demo owner bootstrap no longer depends on an empty `users` table, so a self-registered account cannot suppress the deterministic demo login needed by the one-field landing flow.

### Added (documentation set)

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
- Database-backed job queue with an inline API worker and a standalone `python -m app.workers.runner` worker, plus REST job status and cancellation and a one-second polling WebSocket; no REST retry endpoint exists.
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
