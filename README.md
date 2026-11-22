# SERPScope

**An evidence-first, 23-module enterprise SEO platform — built as a portfolio-grade reference implementation.**

SERPScope is a full-stack FastAPI + React application for crawling, diagnosing, mapping, forecasting and reporting on large websites. It ships with a deterministic synthetic dataset and 12 interview-ready scenarios so every workflow can be demonstrated end to end **without claiming real client results, live vendor data, or guaranteed AI-search outcomes**.

> **Live demo:** https://serpscope.vercel.app · **Source:** https://github.com/bevijaygupta/serpscope · [Deployment guide](docs/DEPLOYMENT.md#3-hosted-portfolio-demo-vercel--render)

> **Read this first:** all numbers in the demo are invented for rule testing. They are labelled `synthetic` / `simulated` at record level, in the UI and in exports. Nothing here is a real GSC/GA4 connection or a real crawl of a client site. See [Honesty, provenance and limitations](#honesty-provenance-and-limitations).

---

## What it is

| Layer | Implementation |
| --- | --- |
| Frontend | React 18, TypeScript, Vite 6, Tailwind CSS 3, Recharts, Axios |
| Backend | FastAPI 0.115, Pydantic 2, SQLAlchemy 2.0, SQLite by default (configurable via `DATABASE_URL`) |
| Jobs | Database-backed queue (`jobs` table) with an inline worker in the API by default, or a standalone worker (`app.workers.runner`) |
| Data | Shared URL inventory, raw crawl observations, issues, orphans, keyword mappings, analytics records, reports, forecasts, workflows |
| Exports | CSV, JSON, XLSX and text-based PDF, with spreadsheet-injection escaping |
| Auth | HMAC-SHA256 signed bearer tokens, PBKDF2 password hashing, organisation/project scoping and write-role checks |
| Demo | Deterministic generator seeded with `random.Random(20261122)`; 12 documented scenarios |

It is designed to answer interview questions such as *"How would you map keywords for 1,000 pages?"*, *"How would you find orphans on 100,000 URLs?"* and *"How do you report SEO to a board without overstating the data?"* — with a working UI and API rather than slideware.

---

## The 23 modules

Defined in `frontend/src/lib/modules.ts` and routed through `frontend/src/pages/ModulePage.tsx`.

### Command centre (2)

| Module | What it does |
| --- | --- |
| **Overview** | Database-backed portfolio pulse: inventory composition, issue pressure, opportunity volume, active jobs and quick automations. |
| **Projects** | Create and switch client workspaces; manage delivery tasks, meeting notes and the audit trail. |

### Discovery (4)

| Module | What it does |
| --- | --- |
| **Crawler** | Conservative, robots-aware HTTP crawling; raw observations stored separately from interpreted URL records. |
| **Technical Auditor** | Rule-based issue groups with evidence, weighted priority explanations and a Detected → Closed workflow. |
| **URL Intelligence** | Filterable, paginated, column-selectable URL inventory with provenance and exports. |
| **Orphans** | Source-union orphan reconciliation with classification, confidence and weighted priority. |

### Intent & content (4)

| Module | What it does |
| --- | --- |
| **Keywords** | Import, classify, cluster and map keywords with visible source and intent. |
| **Keyword Mapping** | One primary keyword per URL, reviewable reasoning and explicit cannibalisation conflicts. |
| **Content** | Content scoring and editable briefs; recommendations stay proposals until a human approves them. |
| **Internal Links** | Graph analysis, orphan/weakly-linked detection and reviewable anchor suggestions. |

### Market intelligence (5)

| Module | What it does |
| --- | --- |
| **Competitor / Gap** | Competitor domains and gap hypotheses derived from **imported** data only. |
| **International** | Market/language rollout plans and hreflang diagnostics derived from URL records. |
| **Local / GBP** | Bulk location inventory with NAP/duplicate heuristics; no Google Business Profile claims. |
| **E-commerce** | Product canonical, schema, identifier and availability diagnostics for large catalogues. |
| **Migration** | Redirect mapping and validation output; the tool never deploys redirects. |

### Intelligence (3)

| Module | What it does |
| --- | --- |
| **AI Search / AEO** | Answer-readiness audit rules plus manually recorded visibility observations. No synthesized citations. |
| **Analytics / Reporting** | Imports, summary metrics and reports that explicitly list missing data. |
| **Forecasting** | Editable assumptions with formulas, three scenarios and sensitivity analysis — labelled estimates, not guarantees. |

### Automation (5)

| Module | What it does |
| --- | --- |
| **Workflow Builder** | Composable, non-destructive step library, manual/scheduled workflows and run history. |
| **Client / Team** | Organisations, memberships and project permissions with write-role controls. |
| **Integrations** | Provider registry and connection records with encrypted-at-rest credentials; CSV import is the working mode. |
| **Demo Centre** | 12 scenario definitions plus generators for labelled synthetic datasets. |
| **Settings / Docs** | Provenance vocabulary, methodology summaries, export schemas and a documentation index. |

---

## Architecture at a glance

```
Browser (React @ http://localhost:5173)
   │  Axios, Bearer token in localStorage, /api/* proxied by Vite
   ▼
FastAPI app (http://127.0.0.1:8000)
   │  /api/health, /docs, /api/v1/<router>
   ├── Auth, RBAC, project scoping (app/api/deps.py)
   ├── 23 API routers (app/api/v1/*.py)
   ├── Services (app/services/*.py): rules, scoring, imports, reports
   └── SQLAlchemy models → SQLite / configured database
              ▲
              │ claim_next() / run_job()
        Job worker: inline thread in API (default)
        or `python -m app.workers.runner` (RUN_JOBS_IN_API=false)
```

Long-running work (imports, crawls, detection, clustering, reporting) is **enqueued as a database row** and never blocks the UI. The frontend polls `GET /api/v1/jobs/{id}` and can also watch `/api/v1/jobs/ws/{id}`. Cancellation is checked between batches. Every list endpoint is bounded; the 100k-scale acceptance test asserts a 50-row page is returned instead of the whole inventory.

---

## Quick start

Prerequisites: **Python 3.11**, **Node.js 20+ / npm**. No external database or message broker is required.

### Bash (macOS / Linux / Git Bash)

```bash
# 1. Backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
# 2. Frontend
cd frontend
npm ci
npm run dev
```

### PowerShell (Windows)

```powershell
# 1. Backend
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
# 2. Frontend
cd frontend
npm ci
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api` to `http://127.0.0.1:8000` (override with `VITE_API_TARGET`). Interactive API docs are served by FastAPI at **http://127.0.0.1:8000/docs**.

### Demo login

| Field | Value |
| --- | --- |
| Email | `demo@serpscope.local` |
| Password | `demo1234` |

The account is created automatically on first API startup if the `users` table is empty. The login form pre-fills these values.

**First move:** go to **Demo Centre → Generate dataset** (default 1,000 URLs), wait for the job to finish, then reopen **Overview**. A blank project has no data until you import or generate it. See [DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

> Container build files and `docker-compose.yml` are present. The verified setup path in this documentation is still local source; the Compose stack is provided as a convenience stack and requires a local `.env` copied from `.env.example`. See [INSTALLATION.md](docs/INSTALLATION.md#container-files-status).

---

## Honesty, provenance and limitations

This project is a **demonstration of engineering and SEO process**, not a production SEO data source.

1. **All demo metrics are synthetic.** `backend/app/services/demo.py` invents URLs, clicks, sessions, conversions, revenue, keywords, locations, products and AI observations. Records carry `data_kind = "synthetic"` and a `SYNTHETIC DEMONSTRATION RECORD` note.
2. **Planted issues are deterministic formulas**, e.g. `i % 137 == 17` creates a high-value 404. Exact counts for a 1,000-URL dataset are in [DEMO_GUIDE.md](docs/DEMO_GUIDE.md#planted-issue-inventory).
3. **No live vendor API calls are made.** The integration registry lists providers and modes, but only file import is implemented. OAuth/API-key modes are declarations, not working connections. See [INTEGRATIONS.md](docs/INTEGRATIONS.md).
4. **No real crawl is performed by the demo generator.** The crawler itself can fetch authorised public URLs with robots/delay/SSRF protections, but the default seed in the UI is the fictional `demo.example.com`.
5. **Forecasts are arithmetic on user-supplied assumptions** with a relative CTR curve. They are not ranking, traffic or revenue guarantees.
6. **AI-search readiness is rule-based; visibility is manual observation only.** No answer-engine sampling or provider API is called, and no inclusion outcome is promised.
7. **Exports retain provenance columns** (`data_kind`, `source`, `observed_at` where applicable) so a screenshot or CSV cannot quietly become "real data".

The API exposes the vocabulary at `GET /api/v1/meta/data-kinds`, methodologies at `GET /api/v1/meta/methodologies` and export schemas at `GET /api/v1/meta/export-columns`.

---

## Testing

From `backend/`:

```bash
# Fast suite (36 tests in the current tree)
.venv/Scripts/python -m pytest -q -m "not slow"     # Windows
# .venv/bin/python -m pytest -q -m "not slow"       # macOS/Linux

# Include the 100,000-URL acceptance check (marked slow)
.venv/Scripts/python -m pytest -q -m slow
```

From `frontend/`:

```bash
npm run typecheck
npm run build
```

Coverage includes authentication/RBAC, bounded pagination, CSV/XLSX/PDF exports, imports and normalisation, planted-issue detection, orphan classification, link suggestions, keyword clustering/mapping, priority scoring and the 100k inventory path. See [INSTALLATION.md](docs/INSTALLATION.md#testing).

---

## Documentation index

| File | Contents |
| --- | --- |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Local setup, configuration, jobs, testing, Docker Compose |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System boundaries, job lifecycle, storage and scale decisions |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Tables, indexes, provenance fields and relationships |
| [docs/CRAWLER_METHODOLOGY.md](docs/CRAWLER_METHODOLOGY.md) | Robots, delay, SSRF, cancellation, raw observations and issue rules |
| [docs/ORPHAN_DETECTION_METHODOLOGY.md](docs/ORPHAN_DETECTION_METHODOLOGY.md) | Source union, reachability classification and confidence |
| [docs/KEYWORD_MAPPING_METHODOLOGY.md](docs/KEYWORD_MAPPING_METHODOLOGY.md) | Clustering, cannibalisation, mapping and intent |
| [docs/PRIORITY_SCORING_METHODOLOGY.md](docs/PRIORITY_SCORING_METHODOLOGY.md) | Explainable component scores |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model, controls and known gaps |
| [docs/TESTING.md](docs/TESTING.md) | Test inventory, markers and commands |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production configuration, worker topology and migrations |
| [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Auth flow, conventions, pagination and the full route table |
| [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) | File imports, provider registry, encrypted credentials, what is *not* connected |
| [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | All 12 scenarios, planted-issue counts, regeneration and limits |
| [docs/INTERVIEW_DEMONSTRATIONS.md](docs/INTERVIEW_DEMONSTRATIONS.md) | 12 questions mapped to UI/API demos and talking points |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Completed / partial / pending work with priorities |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Keep a Changelog history |
| [docs/IMPLEMENTATION_REPORT.md](docs/IMPLEMENTATION_REPORT.md) | Final completed / partial / pending status with evidence paths |

The in-app **Settings / Docs → Docs** tab links to the same documents. `docs/IMPLEMENTATION_REPORT.md` is the final honest status report.

---

## Interview talking points

- **"Show me a hard problem."** Reconcile a 100k-URL source union into classified orphans, explain why an uncrawled URL is not automatically an orphan, and show the priority components.
- **"Do you invent data?"** No — I label it. Open **Settings → Provenance** and point at `data_kind` in an export.
- **"How do you avoid fake vendor claims?"** Open **Integrations → Providers**: CSV modes work, OAuth/API modes are explicitly unimplemented, and credentials are encrypted and never returned.
- **"How does the automation scale?"** Show a job moving `queued → claimed → running → succeeded`, then cancel one, then point to the separate worker option.
- **"How do you communicate risk?"** Generate a report via **Analytics / Reporting → Generate now** and read the **Data gaps** section before the charts.
- **"What is not proven?"** Live integrations, JS-rendered crawling, production RBAC hardening, distributed queues and any guarantee about answer-engine visibility.
