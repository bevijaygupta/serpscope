# API Documentation

Base URL for the REST API: **`http://127.0.0.1:8000/api/v1`**

| Resource | URL |
| --- | --- |
| Health check | `GET http://127.0.0.1:8000/api/health` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |
| OpenAPI schema | `http://127.0.0.1:8000/openapi.json` |

FastAPI serves the interactive docs by default; no custom authentication is applied to `/docs` or `/openapi.json`. The frontend talks to the API through a Vite proxy: browser requests to `/api/*` on `http://localhost:5173` are forwarded to `http://127.0.0.1:8000`.

The route table below was derived from introspecting `app.main.app` (all feature routers registered with the `/api/v1` prefix, including the two audit routers), not from memory. The current schema exposes 119 paths / 134 operations; the five added paths are the public-audit endpoints.

---

## Authentication flow

Authentication is **bearer-token based**, not OAuth. Tokens are HMAC-SHA256 signed JSON payloads created in `backend/app/core/security.py` (`create_access_token`) and verified by `current_user` in `backend/app/api/deps.py`. Passwords are PBKDF2-SHA256 hashed with 210,000 rounds.

```bash
# 1. Log in (public)
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@serpscope.local","password":"demo1234"}'
# {"access_token":"<token>","token_type":"bearer"}

# 2. Call any protected endpoint
curl http://127.0.0.1:8000/api/v1/auth/me \
  -H 'Authorization: Bearer <token>'
```

Flow details:

1. `POST /auth/login` lowercases/trims the email, verifies the password, rejects inactive users (`403`) and returns `{ "access_token": str, "token_type": "bearer" }`.
2. The browser stores the token in `localStorage` (`serpscope-token`) and Axios adds `Authorization: Bearer <token>` to every request (`frontend/src/lib/api.ts`).
3. `current_user` returns `401` for a missing, malformed, expired or invalid token, and for inactive users. A `401` response in the frontend clears the token and redirects to `/login`.
4. Project-scoped endpoints use `ProjectDep` (`get_project`): owners/admins may access any project; other roles require an `Organization` membership matching the project. Non-owners get `403` otherwise.
5. Write endpoints call `check_write`: global role must be `owner`, `admin` or `editor`. `viewer` is read-only.
6. `POST /auth/register` creates a local-development account with global role `viewer`. It is not an invitation/SSO flow.
7. Token lifetime defaults to 1,440 minutes (`ACCESS_TOKEN_EXPIRE_MINUTES`). There is no refresh-token endpoint; log in again after expiry.

**Public endpoints:** `POST /auth/login`, `POST /auth/register`, all `/meta/*` endpoints, `GET /api/health`, `POST /presence/ping`, `GET /presence/count`, the docs/OpenAPI routes, the static export mount and `GET /public/case-studies/{project_id}` (only when the project has `settings.public_audit=true`). Everything else expects a bearer token. The progress WebSocket `/api/v1/jobs/ws/{job_id}` also requires authentication via a `Bearer` header or a `token` query parameter, and applies the same project-scope check as REST job endpoints (close codes `4401`/`4403`/`4404` for unauthenticated, forbidden and missing jobs).

---

## Common conventions

### Pagination

List endpoints built with `paged()` in `backend/app/api/v1/_helpers.py` use **offset/limit request parameters** and return this response shape:

```json
{
  "items": [ { "id": 1, "url": "https://demo.example.com/" } ],
  "total": 200,
  "page": 1,
  "page_size": 50,
  "has_more": true
}
```

- `page = offset // max(1, limit) + 1` (1-based, derived from `offset`).
- `page_size` echoes `limit`.
- `has_more = offset + limit < total`.
- Typical bounds: `limit >= 1`, `limit <= 500` for `/inventory/urls` (a `501` is rejected with `422`); most other lists default to `limit=100` without an explicit upper bound in the route signature.
- `offset`/`limit` are the request parameters — there is no `page` request parameter on these endpoints.

Some endpoints intentionally return only `{ "items": [...] }` (e.g. `/projects`, `/meta/data-kinds`, `/demo/scenarios`, `/analytics/summary`) or a plain summary object. The frontend's `unwrapList()` in `frontend/src/lib/api.ts` normalises both shapes.

### Other conventions

| Convention | Detail |
| --- | --- |
| Project identification | Most domain endpoints take `project_id` as a **query parameter** (e.g. `/technical/issues?project_id=1`). `ProjectDep` resolves and authorises it. Some endpoints instead use a path segment (`/projects/{project_id}/tasks`). |
| IDs | Integers. Path parameters named `{project_id}`, `{job_id}`, `{issue_id}`, `{url_id}`, etc. |
| Serialisation | `_helpers.serialize(row, columns)` returns only declared columns; missing values are `null`. |
| Timestamps | ISO-8601 strings from `app.core.timeutil.iso()` / `utcnow()`. |
| Provenance | Records include `data_kind` and often `source` / `sources` / `observed_at`. Values follow `/meta/data-kinds`. |
| Errors | HTTP errors use FastAPI's `{ "detail": "..." }`; the global handler logs the traceback server-side and returns only `{ "detail": "Internal server error" }` with status 500. |
| Writes | `POST` usually returns `201` and an id or `{ "success": true }`; job-triggering `POST`s return `202` with `{ "job_id": ..., "status": "queued" }`. |
| Exports | `GET .../export?format=csv\|json\|xlsx` (reports support `pdf`; public audits also support `pptx`) returns a `FileResponse` with an attachment header. Column selection uses `columns=a,b,c` where supported. Cells are escaped against spreadsheet formula injection. |
| Booleans in filters | `indexable` and `in_sitemap` on `/inventory/urls` are `0`/`1` integers constrained to `[0,1]`. `orphan` is a real boolean. |
| Job progress | `GET /jobs/{id}`; `POST /jobs/{id}/cancel`; WebSocket `/jobs/ws/{id}` polls the database once per second. |
| Async semantics | `202` means the work is queued, **not complete**. Track the returned `job_id`. `POST /analytics/reports/generate-now` is the deliberate synchronous exception for small demo datasets. |

---

## Route table

`Auth` column: **Bearer** = token required; **Bearer + project** = token plus authorised `project_id`; **Public** = no token; **None today** = no check implemented (development-only).

### Meta & health

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/health` | Public | Liveness, environment and database driver. |
| GET | `/api/v1/meta/data-kinds` | Public | Provenance vocabulary (`live_crawl`, `imported`, `simulated`, `synthetic`, `derived`, `estimated`, `model_suggestion`). |
| GET | `/api/v1/meta/export-columns` | Public | Declared columns per export type. |
| GET | `/api/v1/meta/methodologies` | Public | Crawler, orphans, keyword mapping, priority and forecast summaries. |

### Presence (`presence.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/presence/ping` | Public | Refresh one anonymous browser-tab session with `{ "session_id": "<random per-tab token>" }` and return `{ active, ttl_seconds, note }`. The server stores only a SHA-256 hash of the token for 60 seconds. Invalid tokens return 400. |
| GET | `/api/v1/presence/count` | Public | Read the current anonymous active-session count, TTL and no-PII note. |

This is an in-process, single-instance **on-site presence counter**, not GA4 Realtime. It stores no IP address, cookie, referrer, user identity or Google identifier, and the count resets when the API restarts or redeploys.

### Auth (`auth.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | Public | Email + password → bearer token. |
| GET | `/api/v1/auth/me` | Bearer | Current user profile. |
| POST | `/api/v1/auth/register` | Public | Local dev account creation (role `viewer`). |
| GET | `/api/v1/auth/users` | Bearer | List users (up to 1,000). |

### Projects (`projects.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/projects` | Bearer | List accessible projects. |
| POST | `/api/v1/projects` | Bearer | Create a project (201). |
| GET | `/api/v1/projects/{project_id}` | Bearer + project | Project detail. |
| PATCH | `/api/v1/projects/{project_id}` | Bearer (write) | Update name/domain/status/description/settings. |
| GET | `/api/v1/projects/{project_id}/overview` | Bearer + project | Dashboard cards, latest crawl, data composition, provenance note. |
| GET | `/api/v1/projects/{project_id}/tasks` | Bearer + project | Paged tasks. |
| POST | `/api/v1/projects/{project_id}/tasks` | Bearer (write) | Create task. |
| PATCH | `/api/v1/projects/{project_id}/tasks/{task_id}` | Bearer (write) | Update task. |
| GET | `/api/v1/projects/{project_id}/meeting-notes` | Bearer + project | Notes (up to 200). |
| POST | `/api/v1/projects/{project_id}/meeting-notes` | Bearer (write) | Add note. |
| GET | `/api/v1/projects/{project_id}/audit-log` | Bearer + project | Paged audit trail. |

### Clients (`clients.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/clients/organizations` | Bearer | List organisations (scoped for non owner/admin). |
| POST | `/api/v1/clients/organizations` | Bearer (write) | Create organisation + owner membership. |
| GET | `/api/v1/clients/organizations/{org_id}/projects` | Bearer | Projects in an organisation. |
| GET | `/api/v1/clients/organizations/{org_id}/members` | Bearer | Organisation members. |
| POST | `/api/v1/clients/organizations/{org_id}/members` | Bearer (write) | Add/invite-by-creating a member. |
| GET | `/api/v1/clients/projects/{project_id}/permissions` | Bearer | Project permission list. |
| POST | `/api/v1/clients/projects/{project_id}/permissions` | Bearer (write) | Set a project role. |

### Imports (`imports.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/imports/upload` | Bearer (write) | Multipart upload → 202 + `job_id`. Allowed: `.csv .tsv .txt .xml .json .xlsx`; max `MAX_UPLOAD_MB`. |
| POST | `/api/v1/imports/url-list` | Bearer (write) | Inline list of up to 10,000 URLs (201). |
| GET | `/api/v1/imports/sources` | Bearer + project | Imported data sources. |
| GET | `/api/v1/imports/sources/{source_id}` | Bearer | One source with column mapping/errors. |

### Jobs (`jobs.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/jobs` | Bearer | Paged jobs; filters `project_id`, `status_filter`. |
| GET | `/api/v1/jobs/{job_id}` | Bearer | Job detail including `result`, `payload`, `cancel_requested`. |
| POST | `/api/v1/jobs/{job_id}/cancel` | Bearer (write) | Request cancellation. |
| WS | `/api/v1/jobs/ws/{job_id}` | None today | 1-second polling progress stream. |

### Inventory (`inventory.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/inventory/urls` | Bearer + project | Paged/filtered URLs; `q,status,page_type,indexable,orphan,data_kind,min_clicks,min_revenue,in_sitemap,columns,offset,limit`. |
| GET | `/api/v1/inventory/urls/{url_id}` | Bearer + project | URL detail + recent raw crawl observations. |
| PATCH | `/api/v1/inventory/urls/{url_id}` | Bearer (write) | Edit page type, importance, notes, supplied metrics. |
| GET | `/api/v1/inventory/export` | Bearer + project | Export URL inventory. |
| GET | `/api/v1/inventory/summary` | Bearer + project | Counts by status, page type and data kind. |

### Crawler (`crawler.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/crawler/config-defaults` | Bearer | Conservative defaults (auth headers removed). |
| POST | `/api/v1/crawler/start` | Bearer (write) | Validate seeds and enqueue a crawl (202). |
| GET | `/api/v1/crawler/runs` | Bearer + project | Paged crawl runs. |
| GET | `/api/v1/crawler/runs/{crawl_id}` | Bearer + project | Run configuration and counters. |
| GET | `/api/v1/crawler/runs/{crawl_id}/observations` | Bearer + project | Paged raw observations. |
| GET | `/api/v1/crawler/runs/{crawl_id}/export` | Bearer + project | Export raw observations. |

### Technical (`technical.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/technical/detect` | Bearer (write) | Queue rule-based issue detection (202). |
| GET | `/api/v1/technical/issues` | Bearer + project | Paged issue groups; filters `priority,status,category,q`. |
| GET | `/api/v1/technical/issues/{issue_id}` | Bearer + project | Issue detail + affected URLs. |
| PATCH | `/api/v1/technical/issues/{issue_id}` | Bearer (write) | Update status/owner/due date/priority/validation. |
| GET | `/api/v1/technical/high-value-404s` | Bearer + project | Business-evidence-ranked 404s with explanation. |
| GET | `/api/v1/technical/export` | Bearer + project | Export issue groups. |

Valid issue statuses: `Detected, Reviewed, Approved, Assigned, Implemented, Validated, Closed, Resolved`.

### Orphans (`orphans.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/orphans/detect` | Bearer (write) | Queue orphan detection (202). |
| GET | `/api/v1/orphans` | Bearer + project | Paged orphan register; filters `classification,priority,q`. |
| GET | `/api/v1/orphans/summary` | Bearer + project | Counts/revenue/clicks by classification. |
| GET | `/api/v1/orphans/export` | Bearer + project | Export orphan register. |

### Keywords (`keywords.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/keywords/import` | Bearer (write) | Multipart keyword CSV/TSV/XLSX upload → 202. |
| POST | `/api/v1/keywords/inline` | Bearer (write) | Add up to 10,000 keywords/objects inline (201). |
| GET | `/api/v1/keywords` | Bearer + project | Paged keyword inventory. |
| GET | `/api/v1/keywords/summary` | Bearer + project | Totals by intent/source, cluster count. |
| POST | `/api/v1/keywords/cluster` | Bearer (write) | Queue clustering (202). |
| GET | `/api/v1/keywords/clusters` | Bearer + project | Paged clusters. |
| PATCH | `/api/v1/keywords/clusters/{cluster_id}` | Bearer (write) | Edit cluster or split keywords out. |
| POST | `/api/v1/keywords/map` | Bearer (write) | Queue keyword → URL mapping (202). |
| GET | `/api/v1/keywords/mappings` | Bearer + project | Paged mappings; filter `q`, `risk`. |
| GET | `/api/v1/keywords/cannibalisation` | Bearer + project | Duplicate primary keywords across URLs. |
| POST | `/api/v1/keywords/bulk-workflow` | Bearer (write) | Queue the 1,000-page demo workflow (202). |
| GET | `/api/v1/keywords/export` | Bearer + project | Export `kind=mapping\|clusters\|keywords`. |

Clustering methods advertised by the API: `exact, normalized, token, semantic, intent, serp_overlap`. Fresh third-party research is not performed; the bulk workflow processes imported data.

### Content (`content.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/content/analyse` | Bearer (write) | Queue content analysis (202). |
| POST | `/api/v1/content/briefs/generate` | Bearer (write) | Queue brief generation (202). |
| GET | `/api/v1/content/analyses` | Bearer + project | Paged analyses. |
| GET | `/api/v1/content/briefs` | Bearer + project | Paged briefs. |
| PATCH | `/api/v1/content/briefs/{brief_id}` | Bearer (write) | Approve/edit a brief. |
| GET | `/api/v1/content/export` | Bearer + project | Export `kind=analyses\|briefs`. |

### Internal links (`links.py`, prefix `/internal-links`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/internal-links/analyse` | Bearer (write) | Queue graph analysis (202). |
| GET | `/api/v1/internal-links/graph-summary` | Bearer + project | Edge/orphan/excess-link counts. |
| GET | `/api/v1/internal-links/suggestions` | Bearer + project | Paged suggestions. |
| PATCH | `/api/v1/internal-links/suggestions/{suggestion_id}` | Bearer (write) | Set `proposed\|approved\|rejected\|implemented`. |
| GET | `/api/v1/internal-links/export` | Bearer + project | Export suggestions. |

### Competitors (`competitor.py`, prefix `/competitors`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/competitors` | Bearer + project | Competitor set. |
| POST | `/api/v1/competitors` | Bearer (write) | Add competitor (201). |
| POST | `/api/v1/competitors/analyse` | Bearer (write) | Queue gap analysis from **imported data only** (202). |
| GET | `/api/v1/competitors/gaps` | Bearer + project | Paged gap hypotheses. |
| GET | `/api/v1/competitors/export` | Bearer + project | Export gaps. |

### International (`international.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/international/plan` | Bearer (write) | Queue market plan (202). |
| GET | `/api/v1/international/plans` | Bearer + project | Recent plans (up to 50). |
| GET | `/api/v1/international/hreflang` | Bearer + project | Hreflang records; filter `status`. |
| GET | `/api/v1/international/export` | Bearer + project | Export `kind=plan\|hreflang`. |

### Local (`local.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/local/locations/bulk` | Bearer (write) | Bulk insert up to 10,000 locations (201). |
| GET | `/api/v1/local/locations` | Bearer + project | Paged locations; filters `city,country,status,issue,q`. |
| POST | `/api/v1/local/audit` | Bearer (write) | Queue NAP/duplicate audit (202). |
| GET | `/api/v1/local/export` | Bearer + project | Export location audit. |

### E-commerce (`ecommerce.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/ecommerce/products/bulk` | Bearer (write) | Bulk insert up to 50,000 products (201). |
| GET | `/api/v1/ecommerce/products` | Bearer + project | Paged diagnostics; filters `issue,priority,category,q`. |
| POST | `/api/v1/ecommerce/audit` | Bearer (write) | Queue catalogue audit (202). |
| GET | `/api/v1/ecommerce/export` | Bearer + project | Export merchant diagnostics. |

### Migration (`migration.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/migration/projects` | Bearer + project | Migration projects. |
| POST | `/api/v1/migration/projects` | Bearer (write) | Create migration project (201). |
| POST | `/api/v1/migration/mappings/bulk` | Bearer (write) | Bulk insert up to 100,000 mappings (201). |
| GET | `/api/v1/migration/mappings` | Bearer + project | Paged redirect map; filters `risk,q`. |
| POST | `/api/v1/migration/validate` | Bearer (write) | Queue validation (202). No redirect is deployed. |
| GET | `/api/v1/migration/export` | Bearer + project | Export redirect map. |

### AI search (`ai.py`, prefix `/ai-search`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/ai-search/observations` | Bearer (write) | Record a manual observation (201). Accepts `answer_url` and `locale` alongside the original fields. |
| POST | `/api/v1/ai-search/observations/import` | Bearer (write) | Import verified observations from `{"rows":[...]}` (or `{"csv":"..."}` for CSV/TSV text). Each row keeps its declared `source` and `data_kind`; accepts `question`, `answer_engine`, `observed_at`, `brand_mentioned`, `competitor_mentioned`, `cited_url`, `answer_url`, `locale`, `notes`. Returns accepted/rejected counts and the resulting visibility status (201). No answer engine is queried. |
| GET | `/api/v1/ai-search/observations` | Bearer + project | Paged observations, including `answer_url` and `locale`. |
| POST | `/api/v1/ai-search/audit` | Bearer (write) | Queue readiness audit (202). |
| GET | `/api/v1/ai-search/readiness` | Bearer + project | Paged readiness items; filters `dimension,status`. |
| GET | `/api/v1/ai-search/export` | Bearer + project | Export `kind=readiness\|observations`. |

### Analytics (`analytics.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/analytics/records` | Bearer + project | Paged analytics rows; filters `source,dimension_type,q`. |
| GET | `/api/v1/analytics/summary` | Bearer + project | Totals grouped by source and data kind. |
| POST | `/api/v1/analytics/reports/generate` | Bearer (write) | Queue a weekly report (202). |
| POST | `/api/v1/analytics/reports/generate-now` | Bearer (write) | Synchronous report generation for small demo datasets. |
| GET | `/api/v1/analytics/reports` | Bearer + project | Paged report metadata. |
| GET | `/api/v1/analytics/reports/{report_id}` | Bearer + project | Full report content and data gaps. |
| GET | `/api/v1/analytics/reports/{report_id}/export` | Bearer + project | Export report as `pdf` (default), `csv` or `json`. |
| POST | `/api/v1/analytics/forecasts` | Bearer (write) | Create an assumption-based forecast (201). |
| GET | `/api/v1/analytics/forecasts` | Bearer + project | Recent forecasts (up to 100). |

### Workflows (`workflows.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/workflows/step-library` | Bearer | Allowed, non-destructive step types, including `public_audit` ("Queue public audit"). |
| GET | `/api/v1/workflows` | Bearer + project | Workflows for the project. |
| POST | `/api/v1/workflows` | Bearer (write) | Create workflow; steps validated against the library (201). |
| PATCH | `/api/v1/workflows/{workflow_id}` | Bearer (write) | Update workflow. |
| POST | `/api/v1/workflows/{workflow_id}/run` | Bearer (write) | Queue a run (202). |
| GET | `/api/v1/workflows/runs` | Bearer + project | Paged run history. |
| GET | `/api/v1/workflows/runs/{run_id}` | Bearer + project | Run detail and step results. |

### Integrations (`integrations.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/integrations/providers` | Bearer | Declared providers and modes. |
| GET | `/api/v1/integrations` | Bearer | Connection records; optional `project_id` filter. |
| POST | `/api/v1/integrations` | Bearer (write) | Create/upsert a connection; encrypts credentials (201). |
| GET | `/api/v1/integrations/{integration_id}` | Bearer | Connection metadata; **never returns secrets**. |
| GET | `/api/v1/integrations/supplied-signals` | Bearer + `project_id` | Per-signal supply status plus `status_explanations` for "Not supplied", "Supplied" and "Synthetic". Statuses are earned by uploaded rows; no provider API is called. |
| GET | `/api/v1/integrations/supplied-records` | Bearer + `project_id`, `signal` | Verbatim uploaded rows for a signal. |

The UI's **Google Search Overview** combines these two authenticated endpoints into one read-only panel. It never computes or invents a Search Console metric; a project without rows remains `Not supplied`, and a supplied project shows only the verbatim cells plus their `data_kind`. Public case studies use the sanitised `supplied_data` object already present in the case-study response and never call `supplied-records`.

### Demo (`demo.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| GET | `/api/v1/demo/scenarios` | Bearer | 12 scenario definitions (seeded on first call if missing). |
| GET | `/api/v1/demo/scenarios/{key}` | Bearer | One scenario. |
| POST | `/api/v1/demo/generate` | Bearer (write) | Queue synthetic dataset generation (202); `size` capped at 200,000. |
| POST | `/api/v1/demo/reset` | Bearer (write) | Queue deletion of demo projects/data; optional `regenerate`. |

### Public audits (`audits.py`)

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| POST | `/api/v1/audits/projects/{project_id}/public-audit/start` | Bearer (write) | Queue a `public_audit` job (202). The body is optional; `{ "start_url": "...", "name": "...", "config": {...} }` overrides the project domain and defaults. |
| GET | `/api/v1/audits/projects/{project_id}/public-audit` | Bearer + project | Return the persisted public-audit report when one exists, otherwise assemble a source-tracked audit from stored evidence: `meta`, `coverage`, `robots`, `counts`, `findings`, `roadmap`, `source_registry`, `missing_data`, `sections`. Returning the persisted report stops a later manual crawl from silently changing the published numbers. Also works before the first audit. |
| GET | `/api/v1/audits/projects/{project_id}/public-audit/export` | Bearer + project | `format=pptx\|pdf\|csv\|xlsx\|json`; `section=all\|findings\|roadmap`. `section=all&format=json` returns the complete audit JSON with every segment; other sections return flat rows. PPTX is a real editable PowerPoint deck built with `python-pptx`. |
| GET | `/api/v1/audits/projects/{project_id}/public-audit/reports` | Bearer + project | Up to 50 persisted `public_audit` report records. |
| GET | `/api/v1/audits/projects/{project_id}/public-audit/history` | Bearer + project | Every stored public-audit snapshot (oldest first): generated time, coverage, findings, severity counts, derived health score and per-finding counts. |
| GET | `/api/v1/audits/projects/{project_id}/public-audit/compare` | Bearer + project | Compare two snapshots via `base=<report_id>&target=<report_id>`; omit both for the two latest. Returns deltas, new/resolved/changed findings and an honesty note. Fewer than two reports returns `comparison_available: false` instead of an invented diff. |
| GET | `/api/v1/audits/projects/{project_id}/case-study-analytics` | Bearer + project | Anonymous case-study view count, recent view records and a no-PII statement. |
| GET | `/api/v1/public/case-studies` | Public | Index of every successfully published real-domain audit. Each row carries the case-study path, coverage counts, top findings, AI-visibility status and anonymous view count. |
| GET | `/api/v1/public/case-studies/sitemap.xml` | Public | Dynamic XML sitemap of the case-study index and every published case-study URL. |
| GET | `/api/v1/public/case-studies/{project_id}` | Public | Read-only, public-evidence-only audit. Returns 404 unless the project's `settings.public_audit` is `true` and the project is not the synthetic demo. User-supplied exports and manual AI observations are excluded. Includes an `analytics.view_count` derived from anonymous views. |
| POST | `/api/v1/public/case-studies/{project_id}/view` | Public | Record one anonymous page view (201). Stores project, report, path and source only — no IP, cookie, referrer or user identity. |

The queued job defaults to `max_urls=250`, `max_depth=3`, `concurrency=2`, `crawl_delay=1.0`, `timeout=12`, `respect_robots=true`, `sitemap_discovery=true`, `follow_external=false`, `allow_private=false` and `mode=live`. It runs crawl → orphan/link graph → issue/content/AEO rules → report persistence → automatic case-study publication for real domains. No Search Console, GA4, ranking or AI-visibility API is called; those gaps are listed in `missing_data`. The audit now includes an `ai_visibility` object: with no verified observations its status is `not_sampled`, never a claim of zero mentions or zero citations. Public case-study responses also include `meta.publication_scope`, `meta.private_data_policy` and a zeroed `supplied_data` object so the public Google Search Overview can show **Private data excluded** without disclosing uploaded rows.

### Honest-foundation additions

- **Derived health score:** `100 × weighted pass rate`, where each scored finding passes at `1 − min(affected URLs / fetched URLs, 1)` and weights are Critical 8, High 4, Medium 2, Low 1. Informational and positive groups are excluded. When there are fewer than 10 fetched URLs, or no scored finding, the value is `null` ("not enough evidence") — a one-URL smoke test is never scored as a site-wide result. It is explicitly **not** Ubersuggest's or any vendor's score and is labelled as SERPScope-derived in every API response, UI and export.
- **History and comparison:** reports are appended, never overwritten. The comparison endpoint uses stored snapshots, so a later crawl cannot silently rewrite published numbers. "Resolved" means a rule group no longer appears in the newer snapshot; it is not a ranking or traffic claim.
- **AI observation provenance:** only rows with `data_kind` in `observed`, `verified`, `verified_import`, `licensed_export` or `manual_observation` count as evidence. Synthetic/unverified rows stay stored and visible but are excluded from claims and reported as `unverified_row_count`. Published case studies always force `not_sampled`.
- **Scheduled audits:** add a `public_audit` step to a workflow (with `trigger: "scheduled"` and `schedule: hourly|daily|weekly|monthly`). The step queues a normal public-audit job; it does not call a vendor API. The scheduler tick is enqueued by both the standalone worker and the inline API worker.
- **Case-study analytics:** page views are anonymous counts only. No IP address, cookie, referrer or user identity is stored, and the count is never presented as traffic to the audited website.
- **GTM interaction events:** the website loads container `GTM-NZ3DFL7C` and pushes `serpscope_page_view`, `serpscope_search_submit`, `serpscope_audit_started`, `serpscope_audit_completed`, `serpscope_audit_failed`, `serpscope_export`, `serpscope_ai_import`, `serpscope_case_study_view`, `serpscope_tab_view` and `serpscope_login_success` to `dataLayer`. Events carry only route paths and fixed interaction labels — never an audited domain, email, search-box value, user identity or document title. Tag/trigger configuration inside the GTM container is performed in the GTM UI, not in this repository. DNT and a local opt-out flag suppress events. In the GTM UI, disable GA4's automatic page title and page location fields on every tag; otherwise GA4's own `page_view` can still send `dt`/`dl` parameters even though SERPScope never pushes them.

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@serpscope.local","password":"demo1234"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -X POST http://127.0.0.1:8000/api/v1/audits/projects/2/public-audit/start \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}'

curl http://127.0.0.1:8000/api/v1/jobs/1 -H "Authorization: Bearer $TOKEN"
curl http://127.0.0.1:8000/api/v1/audits/projects/2/public-audit -H "Authorization: Bearer $TOKEN"
curl -o audit.pptx 'http://127.0.0.1:8000/api/v1/audits/projects/2/public-audit/export?format=pptx' \
  -H "Authorization: Bearer $TOKEN"
```

### Export availability

Generated files are written under `EXPORT_DIR` only to be streamed by the authenticated export endpoints (for example `/api/v1/audits/projects/{project_id}/public-audit/export`). There is intentionally **no** public static file mount: `/api/v1/exports/files/...` returns 404 so a guessed filename cannot expose another project's export.

---

## Example: generate a labelled dataset via API

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@serpscope.local","password":"demo1234"}' | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# Queue generation
curl -X POST 'http://127.0.0.1:8000/api/v1/demo/generate' \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"size":1000,"label":"Interview demo"}'

# Poll the job, then read the new project's overview
curl 'http://127.0.0.1:8000/api/v1/jobs/1' -H "Authorization: Bearer $TOKEN"
curl 'http://127.0.0.1:8000/api/v1/projects/1/overview' -H "Authorization: Bearer $TOKEN"
```

All generated metrics in this flow are synthetic. See [DEMO_GUIDE.md](DEMO_GUIDE.md) and [INTEGRATIONS.md](INTEGRATIONS.md) for the boundaries of what the API can legitimately claim.
