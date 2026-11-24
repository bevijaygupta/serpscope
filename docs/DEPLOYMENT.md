# Deployment

This document covers local development and the intended container topology. The repository is FastAPI + SQLAlchemy on the backend and a React/Vite SPA on the frontend; the database-backed job queue is executed either by an inline worker thread in the API process or by a separate worker process.

> Docker assets are present (`backend/Dockerfile`, `frontend/Dockerfile`, `docker-compose.yml`). The hosted portfolio demo uses **Vercel for the React UI** and **Render for the FastAPI API, inline worker and Postgres**. No external broker (Redis/Celery) exists in the code.

See [ARCHITECTURE.md](ARCHITECTURE.md) for component relationships, [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for schema/bootstrap details, [SECURITY.md](SECURITY.md) for required hardening and [TESTING.md](TESTING.md) for verification commands.

## 1. Configuration reference

All settings are read from environment variables (or a `.env` file in the working directory) by `Settings` in `backend/app/core/config.py`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_NAME` | `SERPScope` | Application label |
| `ENVIRONMENT` | `development` | Reported by `/api/health` |
| `SECRET_KEY` | `dev-only-secret-change-before-deployment` | HMAC token signing **and** Fernet key derivation for integration credentials — override in every non-local environment |
| `DATABASE_URL` | `sqlite:///./data/serpscope.db` | SQLAlchemy URL; PostgreSQL URLs are supported by config (driver must be installed separately) |
| `UPLOAD_DIR` | `./data/uploads` | Uploaded imports, organised as `<project_id>/<timestamp>_<safe-name>` |
| `EXPORT_DIR` | `./data/exports` | Generated exports, served at `/api/v1/exports/files` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Bearer token lifetime (24 h) |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins (credentials enabled) |
| `JOB_POLL_SECONDS` | `0.5` | Worker idle poll interval |
| `RUN_JOBS_IN_API` | `true` | Start the inline worker daemon thread in the API process; set `false` when running the separate worker |
| `MAX_UPLOAD_MB` | `50` | Per-file upload limit |
| `LOG_LEVEL` | `INFO` | Root logging level used by `app.main` |

The frontend calls `/api/v1` by default, but `VITE_API_URL` can override it at build time (`frontend/src/lib/api.ts`). The hosted setup keeps the default and uses a Vercel rewrite to forward `/api` (including `/api/health` and `/api/v1/exports/files`) to the Render API, so the browser sees one origin and CORS is avoided.

## 2. Local development (two or three processes)

### Backend

```bash
cd backend
python -m venv .venv
# activate .venv (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

# Optional overrides for local development
# export SECRET_KEY="a-local-random-value"
# export RUN_JOBS_IN_API=true

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On startup the API:

1. Creates `UPLOAD_DIR` and `EXPORT_DIR`.
2. Runs `init_db()` → `Base.metadata.create_all()`, creating all 42 tables if absent.
3. If the `users` table is empty, creates the demo organisation `Demo Organisation` (`demo-organisation`) and owner `demo@serpscope.local` with password `demo1234`, plus an owner `Membership`.
4. Starts the inline worker thread if `RUN_JOBS_IN_API=true`.

Check with:

```bash
curl http://localhost:8000/api/health
# {"status":"ok","environment":"development","database":"sqlite"}
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # Vite on http://localhost:5173, host 0.0.0.0
```

The Vite dev server must proxy `/api` to the Uvicorn port so the default `CORS_ORIGINS` and relative axios paths work. Alternatively, enable CORS for the frontend origin and call the API host directly during development.

### Separate worker (recommended for realistic job testing)

```bash
cd backend
export RUN_JOBS_IN_API=false
python -m app.workers.runner
```

The worker calls `init_db()`, imports all `*_jobs` handler modules, enqueues a `scheduler_tick` job roughly every 60 seconds, then polls the shared `jobs` table. Only **one** execution strategy should be active: either the inline thread or the standalone worker (running both is safe because claims are conditional updates, but it doubles polling and makes local debugging confusing).

## 3. Hosted portfolio demo: Vercel + Render

The checked-in infrastructure files are:

| File | Purpose |
| --- | --- |
| `vercel.json` | Builds `frontend/` with Vite, publishes `frontend/dist`, rewrites `/api/:path*` to `https://serpscope-api.onrender.com/api/:path*`, and falls back to `index.html` so SPA deep links work. |
| `render.yaml` | Render Blueprint declaring `serpscope-db` (Postgres), `serpscope-api` (FastAPI + inline job worker) and the production environment variables. |

Deploy sequence from the GitHub repository:

1. Create a **Blueprint** in Render pointing at the repository. It provisions `serpscope-db` and `serpscope-api`.
2. Render generates `SECRET_KEY` automatically and injects the database connection string.
3. After the first successful API deploy, `initialDeployHook` runs `python scripts/seed_demo.py --size 1000 --keyword-count 1000`, so the public demo has the same deterministic synthetic dataset used in screenshots and interview scenarios.
4. Import the repository into Vercel. It uses `vercel.json`, so no manual build settings are required. The canonical production URL is `https://serpscopelive.vercel.app`; legacy aliases redirect there in `vercel.json`.
5. Confirm `https://serpscopelive.vercel.app/api/health` returns `{"status":"ok","environment":"production","database":"postgresql"}`. That proves the Vercel rewrite and Render API are connected and that no database credentials are exposed.
6. Log in with `demo@serpscope.local` / `demo1234`.
7. The Vercel project must allow public access to its production domain. In this deployment, Vercel Authentication (`ssoProtection`) was disabled on project `prj_096DxSK5ekfzYa4vHxEZ1YGbxwbb`; otherwise visitors see a `Protected by Vercel Authentication` page.

**Live deployment (verified 2026-11-22/24; canonical URL live):** UI and same-origin API are served from `https://serpscopelive.vercel.app`, API/database on Render (`https://serpscope-api.onrender.com`), source on `https://github.com/bevijaygupta/serpscope`. The Render Blueprint ID is `exs-dc1iqeks728c73cic3l0`, API service ID `srv-dc1iqt2vcj2c73en3v8g`. Vercel auto-deploys from `main`; Render is connected through a public repository URL, so code changes need **Manual Deploy → Deploy latest commit** on the `serpscope-api` service (and Blueprint sync when `render.yaml` changes, so the new `CORS_ORIGINS` value reaches the environment). `serpscope.vercel.app` belongs to another Vercel team and is not part of this deployment; `serpscopelive.vercel.app` is the single canonical URL.

**Latest verification (2026-11-24):** The one-field landing flow was driven end to end in the browser on the auto-deployed Vercel build: a bare domain was normalised, the demo login and project creation were automatic, the public-audit job completed, and the app navigated to `/overview` with the evidence ribbon and all 14 Techmagnate findings. The full JSON export is semantically identical to the published case-study payload. Root-host redirects from legacy Vercel aliases now return `308` (previously only asset paths redirected). The raw crawl-observation table needed `project_id` on its API call; that frontend fix is deployed and the table now loads 100 rows with no console errors.

**Frontend-only Gap Center upgrade (2026-11-24):** A second pass adds a derived public-evidence health score with a per-category breakdown and disclosed formula (explicitly not a vendor score), rule-based effort estimates with a quick-win filter for easy high-severity issues, copy-draft blocks with a one-click Copy action for title/meta/H1/schema findings, and an observed-host benchmark that ranks external hostnames by outbound links from the public crawl. The gap-pack export now includes `health_score` and `competitor_benchmark`. This is a frontend-only change: it reuses existing audit and API data, invents no private metrics and needs no Render deploy.

**Frontend upgrade live verification (2026-11-24):** Commits `2bab526` and `88a94f6` were auto-deployed by Vercel; the canonical overview now loads `assets/index-37EwmJBR.js` with no console errors. On the Techmagnate project the score panel reads **70/100** with nine category rows and the disclosed formula; the observed-host benchmark lists six external hosts led by `clutch.co` (747 observed outbound links). The effort filter's quick-win option narrows the queue to the easy high-severity `missing_title` fix, the Copy action reports `Copied` (with an `execCommand` fallback when clipboard permission is denied), and the exported gap pack is **380,203 bytes** containing `health_score` (score, nine categories, formula), `competitor_benchmark` (six hosts), 145 fix items and 112 copy drafts.

**Backend/Gap Center verification (2026-11-24):** Commit `c861e81` was manually deployed on Render (`Manual Deploy → Deploy latest commit`, deploy `dep-dc2jb1jrjlhs73ctjsag`) and succeeded. The Render Blueprint was then synced manually and the `CORS_ORIGINS` change was approved; the resulting Blueprint deploy also succeeded. A fresh public-audit job (job 28, verification project 4) returned `derived_competitors`, `derived_keywords`, `derived_keyword_gaps` and `derived_mappings` with no doubled keys, proving the backend fix is live. A request with `Origin: https://serpscopelive.vercel.app` returns `Access-Control-Allow-Origin: https://serpscopelive.vercel.app`. Vercel auto-deployed the same commit to the canonical URL (asset `index-BQ6KqZxB.js`). The Gap & Fix Center was verified on the live Techmagnate overview: 16 signal-coverage rows, 145 queued fixes (14 audit findings, 16 issue groups, 15 competitor topic gaps and mapped content opportunities), four evidence tables, two filters, working module links, a 15-row gap-only filter and a client-side JSON gap-pack export (357,852 bytes). No browser console errors were observed.

**User-supplied data verification (2026-11-24, final):** Commits `1b31579` (verbatim supplied-metric imports, Integrations UI, dynamic Gap Center statuses and JSON gap-pack field) and `7f7ec04` (live refresh of supplied-data fields on persisted audits) were pushed to `main`. Both required **Manual Deploy → Deploy latest commit** on `serpscope-api`; deploy `dep-dc2k8oe7bikc738ug10g` for `7f7ec04` succeeded. `render.yaml` was unchanged, so **no Blueprint sync was needed**. Locally the full backend suite passed (46 tests), a fresh Alembic upgrade ran through `0001_initial` → `0002_supplied_metrics`, and the frontend passed `npm run typecheck` and `npm run build`.

The canonical Vercel build now serves `assets/index-BEVZUqnE.js` and `assets/index-BzUPJh60.css`. On hosted project 4 (`Backend deploy verification · https://example.com/`), the clearly labelled synthetic export `serpscope_synthetic_gsc.csv` was uploaded with `source_type=gsc` and `data_kind=synthetic_verification`; job 29 stored 2 verbatim rows. The live Integrations page shows **1 of 12 signals supplied**, `Search Console · Supplied · 2 verbatim rows · latest 2026-11-24 · gsc`, the original query/click/impression/CTR/position/date columns, and the import record labelled `synthetic_verification`. The other 11 signals remain `Not supplied`. The Gap & Fix Center shows the same GSC row as `Supplied`, a **1/12 signals supplied** panel, `user-supplied: gsc` in the source registry, `user_supplied:gsc` in `data_kinds`, and removes only the GSC missing-data statement; the rank, backlink, performance, local, SERP and history gaps remain explicit. The client-side gap-pack export (`serpscope-gap-and-fix-4.json`, 27,942 bytes) includes `supplied_data`, 16 signal rows and the supplied GSC sample. No browser console errors were observed on `/integrations` or `/overview`.

**Auto-published case studies and honest AI visibility (2026-11-24, final):** Commit `1667236` was pushed to `main`. Locally all **48 backend tests** passed, `npm run typecheck` was clean and `npm run build` succeeded. Render required **Manual Deploy → Deploy latest commit** on `serpscope-api`; deploy `dep-dc2l67d9fdbs73819bbg` for `1667236` succeeded in `1m 8s`. `render.yaml` was unchanged, so **no Blueprint sync was needed**. Vercel auto-deployed the frontend to the canonical URL. Live checks passed: `/` and `/api/health` are `200 {"status":"ok",...}`, legacy alias `serpscope-six.vercel.app` returns `308` to `https://serpscopelive.vercel.app/`, and a request with the canonical `Origin` returns `Access-Control-Allow-Origin: https://serpscopelive.vercel.app`.

The one-field landing flow was driven live with `https://example.com`: it auto-signed in, selected the existing project 3, queued the public audit and navigated to `/overview` with zero console errors. On success the backend auto-published project 3 as a case study; `/api/v1/public/case-studies` now returns **2** items (project 3 `example.com` and project 2 Techmagnate), and `/api/v1/public/case-studies/sitemap.xml` lists both canonical case-study URLs. The public index, `/case-studies` and `/case-studies/{id}` all return `200`; each detail page sets its canonical, OG/Twitter metadata and Article JSON-LD, and strips user-supplied/private data with `publication_scope=public_evidence_only`. AI citations, Google AI Overview and brand mentions now report **`not_sampled`** for every engine when no verified observation exists, with the explicit notice “An empty observation log means 'not sampled', not 'not mentioned'.” The live Gap & Fix Center on `/overview` shows the same AI panel and wording with no console errors.

### 3.1 Publishing the real public audit on the hosted demo

The audit endpoints and case study are live. The steps below were used for the original publication; repeat them after backend changes or to regenerate the hosted evidence. For a backend-only change, push `main` and then deploy the latest commit in Render; Vercel auto-deploys the frontend from `main`.

1. In Render, open `serpscope-api` → **Manual Deploy → Deploy latest commit**; wait for the health check to pass. If `render.yaml` changed, also open the `serpscope` Blueprint → **Manual sync** and approve the plan.
2. Log in with `demo@serpscope.local` / `demo1234` and obtain a bearer token:
   ```bash
   curl -s -X POST https://serpscope-api.onrender.com/api/v1/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"email":"demo@serpscope.local","password":"demo1234"}'
   ```
3. Publish project 2 (`https://www.techmagnate.com/`) as a case study:
   ```bash
   curl -X PATCH https://serpscope-api.onrender.com/api/v1/projects/2 \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"settings":{"public_audit":true}}'
   ```
4. Queue the audit, poll `GET /api/v1/jobs/{job_id}` until `succeeded`, then check `GET /api/v1/audits/projects/2/public-audit`, all five export formats and `GET /api/v1/public/case-studies/2`.
5. Confirm the landing page at `https://serpscopelive.vercel.app`, `/robots.txt`, `/sitemap.xml`, `/llms.txt`, `/manifest.webmanifest`, `/favicon.svg`, `/og-preview.svg`, `/login` and `/overview`.

Local verification figures were 303 discovered URLs and 60 fetched from a deliberately narrow sample, with 60 sitemap entries from 9 documents and six finding groups. The completed hosted run (job 17, report 2, crawl 1) discovered 497 URLs, fetched 219, recorded 0 failures and 1 robots exclusion, and produced 12 finding groups plus a six-month roadmap. Its sitemap discovery timed out, so the hosted evidence states 0 sitemap entries rather than borrowing the local sample's 60. Neither figure is an exhaustive audit of the domain. The landing case study is available at `/api/v1/public/case-studies/2`, and the archived authoritative audit pack is in `evidence/techmagnate_public_audit_hosted_2026-11-23/`.

Notes:

- The worker runs **inside the API process** (`RUN_JOBS_IN_API=true`) because Render background workers have no free plan. This is correct for a single-instance demo; use the separate `worker` service for a paid, production-like deployment.
- Free Render web services sleep after inactivity, so the first request may take about a minute. Free Postgres expires after 30 days; upgrade the database before relying on a long-lived demo.
- Uploads and exports use `/tmp/serpscope/...` because the free web service has no persistent disk. Generated files are not retained across restarts.
- If Vercel assigns a different project name, update `CORS_ORIGINS` on Render and the rewrite destination in `vercel.json`.
- PostgreSQL compatibility: keyword cannibalisation grouping is done in Python instead of SQLite's `GROUP_CONCAT`, and report queries order by column position to avoid Postgres `GROUP BY` ambiguity. The backend test suite passes in both local SQLite and hosted PostgreSQL configurations.

## 4. Intended container topology

```mermaid
flowchart LR
    U["User browser"] --> FE["frontend service\nnginx serving built SPA\n(proxies /api to api service)"]
    FE -->|"/api/*"| API["api service\nUvicorn app.main:app\nRUN_JOBS_IN_API=false"]
    FE -.->|"/api/health"| API
    API --> DB[("shared database volume\nSQLite file or PostgreSQL")]
    WORKER["worker service\npython -m app.workers.runner\nRUN_JOBS_IN_API=false"] --> DB
    API --> VOL[("shared uploads + exports volume")]
    WORKER --> VOL
```

| Service | Process | Notes |
| --- | --- | --- |
| `api` | `uvicorn app.main:app --host 0.0.0.0` | Mounts `/api/v1/exports/files` from `EXPORT_DIR`; exposes `/api/health`; should have `RUN_JOBS_IN_API=false` when a worker service is present |
| `worker` | `python -m app.workers.runner` | Same image and environment as `api`; no inbound port; shares the database (and upload/export directories for file-based jobs) |
| `frontend` (nginx) | Static SPA + reverse proxy | Serves the Vite `dist/` build, proxies `/api` and `/api/health` to `api`, so the browser only needs one origin |

Shared-state requirements:

- `api` and `worker` **must** point at the same `DATABASE_URL`. With SQLite this means a shared, writable volume and a single writer host; PostgreSQL is the safer multi-process choice.
- Both processes need the same `SECRET_KEY` (token verification and credential encryption) and the same `UPLOAD_DIR` / `EXPORT_DIR` paths so file-based import and export jobs can find files created by the API.
- Bind uploaded/exported directories to persistent volumes; otherwise generated reports and imported files are lost on container recreation.
- Set `CORS_ORIGINS` to the public frontend origin. When nginx proxies `/api` on the same origin, CORS is largely moot, but the default list must still be changed if the SPA is served from a different host/port.

Example environment block for both backend services (values are illustrative — generate your own secret):

```dotenv
ENVIRONMENT=production
SECRET_KEY=<generate-a-long-random-value>
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>:5432/<db>
RUN_JOBS_IN_API=false
CORS_ORIGINS=https://serpscope.example.com
ACCESS_TOKEN_EXPIRE_MINUTES=60
LOG_LEVEL=INFO
MAX_UPLOAD_MB=50
```

> `psycopg2-binary` is included in `backend/requirements.txt`. `Settings.normalise_database_url` converts a provider-supplied `postgres://` URL to `postgresql+psycopg2://`. SQLite needs no extra driver.

## 5. First run and verification

1. Start the database/volumes, then `api`, then `worker`, then `frontend`.
2. Confirm `GET /api/health` returns `{"status":"ok", ...}` through the same public origin as the SPA.
3. Log in at `/login` with an account created through `/api/v1/auth/register` (local) or provisioned in the database. Remove/rotate the seeded demo account for real deployments.
4. Queue a small job from the UI (e.g. "Add keyword" is synchronous; "Detect issues" is queued) and verify the job panel transitions to `succeeded`.
5. Run the backend test suite as described in [TESTING.md](TESTING.md) against a deployed-equivalent configuration where practical.

## 6. Operational notes

- **Schema changes:** run `alembic upgrade head` from `backend/` on each deploy. The baseline revision and `init_db()` both call `create_all()` for fresh tables; neither alters columns of an existing database. Any future change must ship as an explicit incremental revision and be tested against a copy of production data.
- **Backups:** back up the database and the upload/export volumes together. Integration credentials are Fernet-encrypted with a key derived from `SECRET_KEY`, so **losing or rotating `SECRET_KEY` makes stored credentials unreadable and invalidates all tokens**.
- **Retention:** `organizations.retention_days` exists (default 365) but no automated purge job was found in the code; retention must be handled operationally.
- **Job failures:** failed jobs persist `status="failed"`, an `error` string and `finished_at`; the traceback is returned at runtime but not stored. Monitor `jobs` with `status='failed'` or long-lived `status='claimed'`/`running'` rows (there is no visibility timeout or automatic retry).
- **Worker scheduler:** the `scheduler_tick` job is enqueued by the worker roughly every 60 seconds; ensure only one worker is running if you rely on scheduled workflows.

## 7. Production hardening checklist

Before exposing the stack publicly, address the items in [SECURITY.md](SECURITY.md#10-known-limitations--production-hardening-still-needed), in particular:

- [ ] Replace the default `SECRET_KEY` and store it in a secrets manager; plan rotation for tokens and Fernet credentials.
- [ ] Disable open self-registration and add SSO/admin provisioning; remove the automatic demo-account bootstrap.
- [ ] Restrict `CORS_ORIGINS`; terminate TLS at the edge; add rate limiting and login backoff.
- [ ] Use PostgreSQL with a managed pool instead of default SQLite for multi-process/concurrent writes.
- [ ] Add a backup/restore runbook and test each incremental Alembic revision against production-like data.
- [ ] Add network egress controls for the crawler (the code's SSRF check is string-based, not DNS-aware).
- [ ] Keep uploads non-executable and non-web-served; patch openpyxl/lxml/httpx dependencies.
- [ ] Replace the 300-character raw-error response with a generic 500 response and centralised logging.
