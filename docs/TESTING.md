# Testing

The backend has a pytest suite covering URL utilities, imports, exports, job/queue behaviour, RBAC, WebSocket authentication, crawler compliance, issue detection, orphan/link/keyword analysis, priority scoring and a 100,000-URL acceptance test. The frontend has **no unit-test script** in `package.json`; its available checks are TypeScript type-checking and a production build.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the systems under test and [SECURITY.md](SECURITY.md) for the security-relevant assertions.

## 1. Prerequisites

- Python 3.11 and the pinned packages in `backend/requirements.txt` (`pytest==8.3.4`, `pytest-cov==6.0.0`, FastAPI, SQLAlchemy, etc.).
- Node.js with the frontend dependencies installed for the frontend checks.
- No external services are required: tests use a local SQLite file and FastAPI's `TestClient`.

## 2. Running the backend tests

All commands run from the `backend/` directory:

```bash
cd backend

# Fast suite (36 tests in the current tree)
pytest -q -m "not slow"

# Full suite, including the large-dataset acceptance test
pytest -q

# Run only the large-dataset acceptance test
pytest -q -m slow

# Single file or single test
pytest -q tests/test_url_utils.py
pytest -q tests/test_jobs_and_api.py::test_job_cancellation_is_recorded_and_honoured_by_worker

# Coverage
pytest -q --cov=app --cov-report=term-missing
```

`backend/pytest.ini` sets `testpaths = tests`, registers the marker `slow: large-dataset acceptance tests (100,000 URLs)` and ignores `DeprecationWarning`. There is **no** `addopts = -m "not slow"`, so `pytest -q` collects the slow test too; use `-m "not slow"` to skip it.

### Scale test configuration

`tests/test_scale_100k.py` imports 100,000 URLs by default and asserts the import completes in under 90 seconds and that the final page is bounded (< 200,000 bytes). Override the row count with:

```bash
SEO_LAB_SCALE_URLS=20000 pytest -q -m slow
```

## 3. Test fixtures (`backend/tests/conftest.py`)

| Fixture / hook | Behaviour |
| --- | --- |
| Module import | Deletes `backend/data/test_serpscope.db` if present, then sets `DATABASE_URL=sqlite:///<backend>/data/test_serpscope.db`, `RUN_JOBS_IN_API=false` and `SECRET_KEY=test-only-secret` **before** importing the app |
| `_schema` (session, autouse) | Calls `init_db()` once to create all tables |
| `clean_db` (function, autouse) | Deletes every table in `reversed(Base.metadata.sorted_tables)` before each test, so tests do not leak state |
| `db` | Yields a SQLAlchemy `Session` and closes it |
| `demo_project` | Calls `app.services.demo.generate_demo(db, size=200, keyword_count=150, include_scenarios=False)` |
| `client` | `TestClient(app)` context manager (startup bootstrap creates the demo owner) |
| `auth_headers` | Logs in as `demo@serpscope.local` / `demo1234` and returns `{"Authorization": "Bearer <token>"}` |

`RUN_JOBS_IN_API=false` prevents the inline worker thread from starting during tests; jobs are executed explicitly via `run_job()` where needed.

## 4. Test inventory

| File | What it verifies |
| --- | --- |
| `test_url_utils.py` | URL normalisation (tracking params preserved/stripped, `www`, case), SSRF rejection list (`localhost`, `127.0.0.1`, `169.254.169.254`, `file://`, embedded credentials, `javascript:`, empty, 5000 chars), `allow_private` override, canonical resolution, host/page classification and CSV formula neutralisation |
| `test_jobs_and_api.py` | 401 for missing/invalid tokens and wrong passwords, `/api/health` public, `/auth/me` role, viewer scoping via memberships and 403 on writes/cross-org reads, pagination bounds (`limit=501` → 422), CSV BOM + attachment headers and XLSX bytes, job cancellation flow, terminal status and authenticated/project-scoped WebSocket progress |
| `test_imports.py` | CSV/JSON/XLSX column/row parsing, namespaced sitemap `<loc>` parsing, batched deduplicated `upsert_urls` with rejected internal/empty URLs and source merging, `/imports/url-list` API metadata, sitemap entries stored separately from inventory |
| `test_exports.py` | CSV formula escaping, JSON nested sanitisation, XLSX (`PK` header) and PDF (`%PDF`) generation, `make_export` format dispatch |
| `test_demo_and_issues.py` | Demo generator produces labelled synthetic data and planted issues, `detect_issues` emits evidence/explanations and `issue_urls`, high-value 404 ranking uses supplied revenue and includes score components |
| `test_orphans_links_keywords.py` | Orphan classification/confidence and no mislabelled 404s, link-graph proposals with reasons/anchors, keyword intent/clustering/mapping/cannibalisation, link-count recomputation from `link_edges` |
| `test_priority.py` | `clamp`/`log_scale` bounds, explainable score with components/weights summing to 1, low-confidence → `Review`, orphan component differentiation |
| `test_crawler_safety.py` | Robots permission checked before each request and redirect hop, fail-closed robots fetch errors, disallowed URLs excluded, cancellation between batches and private-target rejection |
| `test_scale_100k.py` | `@pytest.mark.slow` acceptance test: 100k Core-batched URL import speed (under 90s), count, bounded paginated API response and `has_more`/`page` correctness |

## 5. Frontend checks

From `frontend/`:

```bash
npm run typecheck   # tsc --noEmit
npm run build       # tsc -b && vite build
```

`npm run dev` starts Vite on `0.0.0.0:5173`, and `npm run preview` serves the production build locally. There is no Jest/Vitest/Playwright configuration or `test` script in `frontend/package.json`.

Manual smoke path for the UI:

1. Log in with the seeded demo account at `/login` (token written to `localStorage`).
2. Confirm `/overview` loads; switch projects using the persisted `serpscope-project` value.
3. Run an action from any module (e.g. "Start crawl" or "Detect issues") and watch the job panel advance to `succeeded`/`failed`/`cancelled`.
4. Open a tab with an `exportPath` to verify a download; check CSV cells that begin with `=` are prefixed with `'`.

## 6. Coverage and limitations of the suite

- Coverage is measured with `pytest-cov`; no minimum coverage threshold is configured, and `filterwarnings` suppresses `DeprecationWarning`, so some SQLAlchemy/FastAPI deprecations will not fail CI.
- The test database is deleted at **import** time and cleaned before every test; the suite is designed for serial execution. Running tests in parallel with xdist would contend for the same SQLite file and the module-level cleanup.
- One test temporarily mutates the global `HANDLERS` registry (`test_cancellable`) and removes it afterwards; a failure before cleanup can pollute later tests in the same process.
- Tests do not cover SSO, rate limiting, token revocation, PostgreSQL-specific behaviour, real outbound crawling, Alembic revision upgrades, or the container/edge setup described in [DEPLOYMENT.md](DEPLOYMENT.md). Crawler compliance is tested against local mock servers/parser behaviour rather than public websites.
- Security properties are tested at the unit level (SSRF inputs, CSV injection, 401/403 enforcement) rather than through a full penetration test; see the limitations in [SECURITY.md](SECURITY.md).
