# Roadmap

This roadmap describes what is implemented, what is partially implemented, and what would need to be built next. It reflects the current repository only. The application is a portfolio-ready enterprise SEO platform with deterministic synthetic demonstration data; it is not a live SEO data provider.

For verified setup steps, read [Installation](./INSTALLATION.md). For the current API surface, read [API Documentation](./API_DOCUMENTATION.md). For the boundary between implemented behavior and declared integrations, read [Integrations](./INTEGRATIONS.md).

## Legend

- **Implemented** — present in code and exercised by the current test suite where applicable.
- **Partial** — a usable interface or scaffold exists, but important behavior is missing.
- **Planned** — not implemented; proposed future work.
- **Priority** — `High` means a correctness, security, or primary-demo blocker; `Medium` means important for credibility or operability; `Low` means polish or extensibility.

## Current status

### Implemented

| Area | Status | Evidence in the current build |
|---|---|---|
| FastAPI application shell | Implemented | `backend/app/main.py` wires all `/api/v1` routers, health check, no public static mount, OpenAPI docs, and an inline worker tick. |
| Local authentication and RBAC | Implemented | Demo login, JWT access tokens with unique `jti`, persisted single-token and account-wide revocation (REST + job WebSocket), password hashing, role checks, and project-scoped data access are present; refresh tokens and SSO are still absent. |
| Abuse throttling | Implemented | Mutating routes use a shared database-backed fixed-window counter keyed by an HMAC digest of UTC day, bucket and socket peer; workers share one budget. Edge/WAF limits and account lockout remain absent. |
| Project, domain, and crawl management | Implemented | CRUD APIs and database-backed projects, domains, and crawl definitions are present. |
| Deterministic synthetic demo data | Implemented | `backend/app/services/demo.py` generates a labelled, repeatable dataset with planted issue classes. |
| Scenario catalogue | Implemented | `backend/app/services/scenarios.py` defines twelve curated scenarios, including a full audit preset. |
| Issues, recommendations, and exports | Implemented | Issue listing and aggregation, recommendations, CSV/JSON export endpoints, and website-page export are present. |
| Keyword research and clustering | Implemented | Synthetic keyword datasets, SERP summaries, clustering, cannibalisation checks, and keyword-to-page mapping are present. |
| AI search visibility | Implemented | Synthetic prompt tracking, answer-engine visibility snapshots, and gap detection are present. |
| Content briefs and content gap analysis | Implemented | Brief generation, brief CRUD, competitor gap data, and topic suggestions are present. |
| Internal linking and orphan detection | Implemented | Synthetic link graph, page-level link suggestions, and orphan target detection are present. |
| Live crawler and simulation | Implemented | Robots checks before each request and redirect hop, fail-closed robots errors, per-host delay, SSRF validation, cancellation, raw observations, URL inventory, issue generation and progress are present. `mode` changes `data_kind` only; no JS renderer is active. |
| Public-evidence audit | Implemented | One-click `public_audit` job crawls robots.txt, sitemaps and public pages, then assembles source-tracked findings, a six-month roadmap, an explicit missing-data list and PPTX/PDF/CSV/XLSX/JSON exports. The read-only case-study endpoint is gated by `settings.public_audit=true`. Verified locally with a 60-URL sample and on the hosted demo with 219 fetched URLs; the endpoints serve the persisted job report, and the full JSON export contains all segments. |
| Workflows and scheduled jobs | Implemented | Workflow definitions and runs, schedule CRUD, job listing, job details and cancellation are present; no REST retry endpoint exists and claimed jobs have no automatic retry. |
| Reports | Implemented | Report generation, retrieval, data-gap notes and CSV/JSON/XLSX/PDF exports are present; public audits add editable PPTX decks. |
| Import jobs | Implemented | CSV/TSV/TXT, XML sitemaps, JSON and XLSX uploads are parsed into URL/keyword inventory with source tracking and bounded batches. |
| Database migrations | Implemented | Alembic baseline revision `0001_initial_schema.py`, incremental revisions `0002_supplied_metrics`, `0003_honest_foundation`, `0004_token_revocation`, `0005_user_token_version` and `0006_shared_rate_limits`, plus `create_all()` bootstrap for fresh databases. |
| Frontend application | Implemented | React/Vite SPA with 23 module pages, API client, auth state, project state, Demo Centre and in-app documentation index. |
| Test suite | Implemented | Backend pytest suite passes with `90 passed` using `-m "not slow"` and `91 passed` for the full suite; the 100,000-URL scale test is included, with 1k/10k/100k benchmarks recorded in [TESTING.md](TESTING.md). |

### Partial

| Area | Status | Current limitation | Priority |
|---|---|---|---|
| Container deployment | Partial | All Compose assets are present, but the stack has not been built in this environment; local source setup is the verified path. | Medium |
| Integration providers | Partial | Provider registry, encrypted credential records and dormant GSC/GA4/LLM adapters exist, but all live calls are gated off and no provider credentials/accounts are configured in this deployment. | Medium |
| Crawler depth | Partial | `canonical_handling` and `schedule` config keys are stored but unused; JS rendering/Playwright is not implemented; DNS validation and redirect-hop checks exist but egress firewall/connection-time enforcement is still absent; sitemap indexes expand up to three bounded levels with cycle prevention. | High |
| Public-audit coverage | Partial | Local verification used a deliberately narrow 60-URL sample; the hosted run fetched 219 URLs under the 250-URL default. Neither is exhaustive. Robots rules for named AI agents are evidence of declared policy only; no GSC/GA4, rank or AI-answer visibility data is used. The hosted sitemap discovery timed out and is reported as 0 entries. | Medium |
| Issue rule coverage | Partial | Some declared rules (`excessive_depth`, `broken_external_link`) have no detector. | Medium |
| Production RBAC | Partial | Writes are gated by global role; per-project write roles and a role-management UI are not implemented. | Medium |
| Pagination consistency | Partial | Responses use `items,total,page,page_size,has_more`, while most requests use `offset`/`limit`. | Low |
| Production observability | Partial | Basic logging exists, but no structured metrics, tracing, or alerting stack is configured. | Medium |

## Proposed roadmap

### Phase 1 — Correctness and demo reliability

**Priority: High**

1. Trigger **Manual Deploy → Deploy latest commit** in Render, then verify the hosted public-audit endpoints, exports and case study against project 2; Vercel deploys `main` automatically.
2. Build and verify the provided Compose stack, or continue documenting local source setup as the only supported path.
3. Add network egress controls, connection-time address pinning and resolved-IP allow/deny rules; DNS checks and redirect-hop validation already exist.
4. Implement real JS rendering (for example Playwright) or remove the misleading `javascript_rendering` option.
5. Align request pagination parameters with response pagination fields, or document a deliberate compatibility layer.

### Phase 2 — Import and integration honesty

**Priority: Medium**

1. Keep the dormant GSC/GA4/LLM adapters disabled until real provider accounts exist; then add read-only validation calls and capability flags for implemented versus simulated operations.
2. Supply real OAuth clients, refresh tokens and property identifiers as deployment secrets, then enable a single provider at a time and verify verbatim row storage and public-case-study exclusion.
3. Add audit metadata showing whether each result came from live data, cached data, or synthetic generation.

### Phase 3 — Enterprise operability

**Priority: Medium**

1. Add structured request logging, correlation IDs, job metrics, and basic health dependencies.
2. Add per-project write roles and UI gating that mirror backend RBAC.
3. Add tenant/project isolation tests across every endpoint that accepts a project identifier.
4. Test and document each incremental Alembic revision against production-like data.

### Phase 4 — Product depth

**Priority: Low**

1. Expand issue detection rules and expose methodology pages that explain formulas and thresholds.
2. Add more realistic search-console-like time series and SERP simulators while keeping demo data deterministic.
3. Improve report templates with branding, charts, and downloadable formats.
4. Add a workspace-level saved-view system for recurring analyses.

## Non-goals for the current build

- Claiming live Google Search Console, Google Analytics, Semrush, Ahrefs, Screaming Frog, Shopify, WordPress, or LLM provider access.
- Guaranteeing AI-search visibility improvements from generated recommendations.
- Treating synthetic demo metrics as customer or production measurements.
- Shipping an incomplete container stack as the primary installation path.

## Definition of done for future changes

A change should be considered complete only when:

1. The implementation and tests reflect the documented behavior.
2. Demo data remains deterministic and explicitly labelled.
3. API changes are reflected in [API Documentation](./API_DOCUMENTATION.md).
4. Integration changes are reflected in [Integrations](./INTEGRATIONS.md).
5. Demo steps are updated in [Demo Guide](./DEMO_GUIDE.md) when user-visible flows change.
6. User-visible behavior is added to [CHANGELOG.md](./CHANGELOG.md).
