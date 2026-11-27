# Installation

This page describes the **verified local source setup** for SERPScope. It is a portfolio project: the supported path is running the FastAPI backend and Vite frontend from source.

- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Backend](#backend)
- [Frontend](#frontend)
- [Job worker options](#job-worker-options)
- [First run](#first-run)
- [Testing](#testing)
- [Container files status](#container-files-status)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

| Requirement | Version used in this repository | Notes |
| --- | --- | --- |
| Python | 3.11 | `requirements.txt` pins FastAPI 0.115.6, SQLAlchemy 2.0.36, Pydantic 2.10.4, etc. |
| Node.js | 20+ | Frontend Dockerfile uses `node:20-alpine`; Vite 6 / React 18. |
| npm | bundled with Node | `npm ci` works from the committed `package-lock.json`. |
| Database | SQLite (default) | No server required. Set `DATABASE_URL` to another SQLAlchemy URL if needed. |
| Disk | writable `backend/data/` | Uploads and exports are created automatically at startup. |

No npm/pip install is performed by the application itself; you install dependencies once as shown below.

---

## Configuration

Copy the example file and edit it. Settings are read by `app/core/config.py` (Pydantic Settings) from environment variables and a `.env` file in the **current working directory** — so place it at `backend/.env` when running uvicorn from `backend/`.

```bash
cp ../.env.example .env        # from backend/ (Bash)
```

```powershell
Copy-Item ..\.env.example .env  # from backend/ (PowerShell)
```

Important variables (defaults shown):

| Variable | Default | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | `dev-only-secret-change-before-deployment` | Signs access tokens and derives the Fernet key for encrypted integration credentials. **Change in any shared deployment.** |
| `DATABASE_URL` | `sqlite:///./data/serpscope.db` | SQLAlchemy database URL. Tests override it with `data/test_serpscope.db`. |
| `UPLOAD_DIR` | `./data/uploads` | Staging area for uploaded CSV/XML files. |
| `EXPORT_DIR` | `./data/exports` | Generated CSV/JSON/XLSX/PDF downloads. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Bearer-token lifetime. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated browser origins. |
| `RUN_JOBS_IN_API` | `true` | Start the inline job thread inside the API process. Set `false` for a separate worker. |
| `JOB_POLL_SECONDS` | `0.5` | Worker poll interval. |
| `MAX_UPLOAD_MB` | `50` | Upload size cap enforced by `POST /api/v1/imports/upload`. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

> The demo login is ensured on every startup by `bootstrap()` in `backend/app/main.py`, even when other users already exist. Changing `DATABASE_URL` to a fresh file therefore recreates `demo@serpscope.local / demo1234`; existing demo rows are left untouched.

---

## Backend

### Bash

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### PowerShell

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify:

```bash
curl http://127.0.0.1:8000/api/health
# {"status":"ok","environment":"development","database":"sqlite"}
```

Interactive docs: `http://127.0.0.1:8000/docs` (OpenAPI JSON at `/openapi.json`, ReDoc at `/redoc`). These are FastAPI defaults; no custom auth is applied to them.

At startup the app calls `init_db()`, creates `data/uploads` and `data/exports`, verifies the database with a `SELECT 1` health probe, and — when `RUN_JOBS_IN_API=true` — starts a daemon thread that claims and runs queued jobs. Generated exports are streamed directly by the authenticated export endpoints; there is no public static mount.

---

## Frontend

### Bash

```bash
cd frontend
npm ci
npm run dev
```

### PowerShell

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. `vite.config.ts` proxies `/api` to `http://127.0.0.1:8000`; set `VITE_API_TARGET` to point elsewhere:

```bash
VITE_API_TARGET=http://127.0.0.1:9000 npm run dev
```

Other scripts: `npm run build` (`tsc -b && vite build`, output in `frontend/dist`), `npm run preview`, `npm run typecheck`.

The browser stores the bearer token in `localStorage` under `serpscope-token` and the active project id under `serpscope-project`. A `401` response clears the token and redirects to `/login`. The workspace **Sign out** button first calls `POST /api/v1/auth/logout` to revoke the token server-side (best-effort), then clears local state and returns to `/login`.

---

## Job worker options

By default the API process runs jobs inline. For a separate worker:

```bash
# backend/.env
RUN_JOBS_IN_API=false
```

Then, in a second terminal from `backend/`:

```bash
python -m app.workers.runner
```

The worker registers handlers by importing `crawl_jobs`, `analysis_jobs`, `demo_jobs`, `import_jobs`, `keyword_jobs` and `workflow_jobs`, polls `jobs` with an atomic `queued → claimed` update, and enqueues a `scheduler_tick` job about every 60 seconds. Both API and worker must point to the **same** `DATABASE_URL`.

Job states: `queued → claimed → running → succeeded | failed | cancelled`. Cancellation is requested through `POST /api/v1/jobs/{id}/cancel` and checked by handlers between batches. Progress can be observed through `GET /api/v1/jobs/{id}`, the jobs side panel, or the authenticated polling WebSocket `/api/v1/jobs/ws/{id}?token=<access-token>` (a `Bearer` header also works; the token must belong to a user who can access the job's project).

---

## First run

1. Sign in with `demo@serpscope.local` / `demo1234` (pre-filled on the login screen).
2. The seeded catalogue of 12 scenarios is available immediately at **Demo Centre**, but the dataset is empty.
3. Go to **Demo Centre → Generate synthetic dataset** and submit (default 1,000 URLs). Watch the job complete.
4. Select the new demo project under **Projects → Workspaces**, then open **Overview**.
5. Run **Detect technical issues**, **Detect orphan pages**, **Analyse internal links** and **Generate report** from Overview quick actions.
6. Open **Settings / Docs → Provenance / Methodologies / Exports** to see the labels and schemas used throughout.

See [DEMO_GUIDE.md](DEMO_GUIDE.md) for the full walkthrough and planted-issue inventory.

---

## Testing

From `backend/`:

```bash
# Fast suite: 77 passed; full suite: 78 passed including the slow 100k test
.venv/Scripts/python -m pytest -q -m "not slow"     # Windows
.venv/bin/python -m pytest -q -m "not slow"         # macOS/Linux

# Scale acceptance test (100,000 URLs; override with SEO_LAB_SCALE_URLS)
.venv/Scripts/python -m pytest -q -m slow
```

`pytest.ini` marks the large test as `slow`. `tests/conftest.py` deletes `backend/data/test_serpscope.db`, sets `RUN_JOBS_IN_API=false`, and clears every table before each test, so **do not point `DATABASE_URL` at a database you care about when running tests**.

From `frontend/`:

```bash
npm run typecheck
npm run build
```

Test areas: auth/RBAC and project scoping, WebSocket authentication, pagination and bounded responses, CSV/JSON/XLSX exports with filename confinement, CSV/JSON/XLSX/sitemap imports and URL normalisation with cancellation guards, planted issues and high-value 404s, orphan classification, link suggestions, keyword clustering/mapping/cannibalisation, priority scoring, URL utilities, crawler compliance/cancellation and the 100k inventory path.

---

## Container files status

The repository includes a container stack:

- `backend/Dockerfile` installs backend requirements, copies `alembic.ini`, `migrations/` and `app/`, and creates `data/uploads` and `data/exports`.
- `frontend/Dockerfile` is a multi-stage Node build followed by an `nginx:1.27-alpine` runtime; it copies `nginx.conf` and the built `dist/` output.
- Root `docker-compose.yml` defines `api`, `worker` and `frontend` services plus a named `seo-data` volume. The API and worker use a separate `python -m app.workers.runner` process.

All referenced files are present (`backend/alembic.ini`, `backend/migrations/`, `frontend/nginx.conf`, `.env.example`). The local source flow above is the verified path used for this documentation. The Compose stack is provided but has not been built in this environment; if you use it, first copy `.env.example` to `.env` at the repository root, review the settings, then start the services with `docker compose up --build`. See [ROADMAP.md](ROADMAP.md).

---

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `401 Authentication required` in the UI | Token expired or missing; sign in again. Check that `localStorage.serpscope-token` is set. |
| `403 Write permission required` | Your global role is `viewer`; owners/admins/editors can write. |
| `403 No access to this project` | Non-owner/admin users need an organisation membership for the selected project. |
| Jobs stay `queued` | `RUN_JOBS_IN_API=false` with no worker running, or the worker is pointed at a different database. |
| Demo generator reports success but Overview is empty | The new project is not the active one; select it under **Projects → Workspaces**. |
| Upload fails with "No URL-like column found" | The file must have a URL-ish header (see [INTEGRATIONS.md](INTEGRATIONS.md)). CSV/TSV/TXT, sitemap XML, XLSX and JSON arrays/objects with a URL-like key are parsed; check the column names and file encoding. |
| CORS error in browser | Add your frontend origin to `CORS_ORIGINS` and restart the API. |
