# Testing

The backend has a pytest suite covering URL utilities, DNS-aware SSRF hardening, imports and upload cleanup, export filename confinement and format validation, jobs and cancellation-safe publication/imports, RBAC/tenant scoping/rate limits, WebSocket authentication, crawler compliance, cancellation before sitemap discovery and caller-override stripping, issue detection, orphan/link/keyword analysis, priority scoring and a 100,000-URL acceptance test. The frontend has **no unit-test script** in `package.json`; its available checks are TypeScript type-checking and a production build.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the systems under test and [SECURITY.md](SECURITY.md) for the security-relevant assertions.

## 1. Prerequisites

- Python 3.11 and the pinned packages in `backend/requirements.txt` (`pytest==8.3.4`, `pytest-cov==6.0.0`, FastAPI, SQLAlchemy, etc.).
- Node.js with the frontend dependencies installed for the frontend checks.
- No external services are required: tests use a local SQLite file and FastAPI's `TestClient`.

## 2. Running the backend tests

All commands run from the `backend/` directory:

```bash
cd backend

# Fast suite (89 tests; the full suite has 90 including the slow 100k test)
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

Measured locally with the pinned virtualenv on 27 Nov 2026 (SQLite, no external services):

| URLs | API acceptance test call (import + bounded page) | Service import | CSV export | JSON export | XLSX export |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.52s | 0.12s | 0.01s / 178 KB | 0.01s / 276 KB | 0.40s / 29 KB |
| 10,000 | 2.31s | 1.28s | 0.11s / 1,807 KB | 0.10s / 2,784 KB | 0.95s / 242 KB |
| 100,000 | 21.28s | 13.81s | 1.12s / 18,366 KB | 1.01s / 28,132 KB | 8.34s / 2,373 KB |

The first column is the `pytest --durations=3` call time for `tests/test_scale_100k.py`; it includes the 50-row paginated API check. The remaining columns are from an in-memory SQLAlchemy harness calling `upsert_urls()` and `export_csv`/`export_json`/`export_xlsx` directly. All three runs accepted every URL with zero rejections or errors. These are local benchmarks, not a live 100,000-page crawl.

## 3. Test fixtures (`backend/tests/conftest.py`)

| Fixture / hook | Behaviour |
| --- | --- |
| Module import | Deletes `backend/data/test_serpscope.db` if present, then sets `DATABASE_URL=sqlite:///<backend>/data/test_serpscope.db`, `RUN_JOBS_IN_API=false`, `SECRET_KEY=test-only-secret` and `RATE_LIMIT_ENABLED=false` **before** importing the app |
| `_schema` (session, autouse) | Calls `init_db()` once to create all tables |
| `public_dns_for_test_hosts` (autouse) | Maps `example.com`, `*.example.com` and `*.example` to `93.184.216.34` so DNS-aware SSRF checks are deterministic |
| `clean_db` (function, autouse) | Deletes every table in `reversed(Base.metadata.sorted_tables)` before each test, so tests do not leak state |
| `db` | Yields a SQLAlchemy `Session` and closes it |
| `demo_project` | Calls `app.services.demo.generate_demo(db, size=200, keyword_count=150, include_scenarios=False)` |
| `client` | `TestClient(app)` context manager (startup bootstrap creates the demo owner) |
| `auth_headers` | Logs in as `demo@serpscope.local` / `demo1234` and returns `{"Authorization": "Bearer <token>"}` |

`RUN_JOBS_IN_API=false` prevents the inline worker thread from starting during tests; jobs are executed explicitly via `run_job()` where needed. `RATE_LIMIT_ENABLED=false` keeps the fixed-window throttle from interfering with test assertions.

## 4. Test inventory

| File | What it verifies |
| --- | --- |
| `test_url_utils.py` | URL normalisation (tracking params preserved/stripped, `www`, case), SSRF rejection list (`localhost`, `127.0.0.1`, `169.254.169.254`, `file://`, embedded credentials, `javascript:`, empty, 5000 chars), numeric/hex IP spellings, reserved host suffixes, private DNS answers and fail-closed DNS errors, canonical resolution, host/page classification and CSV formula neutralisation; `allow_private` is only for direct local tooling |
| `test_jobs_and_api.py` | 401 for missing/invalid tokens and wrong passwords, `/api/health` public and DB-probed, pinned JWT alg/typ headers, unknown export format → 400, collision-free export filenames, no public export mount, `/auth/me` role, viewer scoping via memberships and 403 on writes/cross-org reads, pagination bounds (`limit=501` → 422), CSV BOM + attachment headers and XLSX bytes, job cancellation flow, terminal status and authenticated/project-scoped WebSocket progress, public case-study private-data exclusion |
| `test_imports.py` | CSV/JSON/XLSX column/row parsing, namespaced sitemap `<loc>` parsing, batched deduplicated `upsert_urls` with rejected internal/empty URLs and source merging, `/imports/url-list` API metadata, provenance labels restricted at upload and inline-list boundaries, sitemap entries stored separately from inventory, queued-upload path confinement, post-import upload cleanup and no row/metric persistence after cancellation |
| `test_exports.py` | CSV formula escaping, JSON nested sanitisation, XLSX (`PK` header) and PDF (`%PDF`) generation, `make_export` format dispatch, editable PPTX generation, unsupported-format rejection and export-path/download filename confinement |
| `test_demo_and_issues.py` | Demo generator produces labelled synthetic data and planted issues, `detect_issues` emits evidence/explanations and `issue_urls`, high-value 404 ranking uses supplied revenue and includes score components, and demo reset preserves the currently running reset job |
| `test_orphans_links_keywords.py` | Orphan classification/confidence and no mislabelled 404s, link-graph proposals with reasons/anchors, keyword intent/clustering/mapping/cannibalisation, link-count recomputation from `link_edges` |
| `test_priority.py` | `clamp`/`log_scale` bounds, explainable score with components/weights summing to 1, low-confidence → `Review`, orphan component differentiation |
| `test_honest_foundation.py` | Health-score evidence threshold, audit history/compare, AI observation provenance and `not_sampled`, scheduled public audits, hostile public-audit config clamping and cancellation-safe audit/report/case-study publication, production config fail-fast, anonymous case-study analytics, `not_supplied` signal explanations |
| `test_supplied_metrics.py` | User-supplied GSC rows change only declared signal status; audits without supplied data keep every vendor gap explicit |
| `test_public_evidence_derivation.py` | Derived result keys, external-link evidence when not followed, public-evidence keywords/competitors/gaps |
| `test_presence.py` | Anonymous visitor token requirement and distinct-session counting without identity storage |
| `test_crawler_safety.py` | Robots permission checked before each request and redirect hop, fail-closed robots fetch errors, disallowed URLs excluded, cancellation before sitemap discovery or page requests, private-target and private-redirect rejection, fail-closed DNS checks, stripping of caller `allow_private`/`auth_headers` overrides, and bounded nested sitemap indexes with cycle prevention and depth-limit errors |
| `test_token_revocation.py` | Logout stores only a token digest in the shared database, revokes only the presented token across sessions and the job WebSocket (`4401`), `logout-all` bumps `token_version` to supersede every earlier session with `401`, and a fresh login still succeeds |
| `test_tenant_and_rate_limits.py` | Cross-tenant rejection for projects/clients/jobs/integrations/users and child writes, plus generic 429 throttling |
| `test_scale_100k.py` | `@pytest.mark.slow` acceptance test: 100k Core-batched URL import speed (under 90s), count, bounded paginated API response and `has_more`/`page` correctness; rerun at 1k/10k/100k for the benchmark table above |

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
- CI (`.github/workflows/ci.yml`) runs the backend suite, frontend typecheck/build, required-file checks and an invariant check that fails if the counts change from **23 modules / 17 docs / 24 screenshots / 12 interview scenarios**.
- Tests do not cover SSO, distributed rate limiting, PostgreSQL-specific behaviour, real outbound crawling, Alembic revision upgrades, or the container/edge setup described in [DEPLOYMENT.md](DEPLOYMENT.md). Token revocation is tested for database persistence, account-wide version invalidation and job-WebSocket rejection, but not under concurrent multi-worker load. Crawler compliance is tested against local mock servers/parser behaviour rather than public websites.
- Security properties are tested at the unit level (SSRF inputs, CSV injection, 401/403 enforcement) rather than through a full penetration test; see the limitations in [SECURITY.md](SECURITY.md).
