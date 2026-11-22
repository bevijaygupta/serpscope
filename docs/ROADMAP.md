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
| FastAPI application shell | Implemented | `backend/app/main.py` wires all `/api/v1` routers, health check, static frontend mount, OpenAPI docs, and an inline worker tick. |
| Local authentication and RBAC | Implemented | Demo login, JWT access tokens, password hashing, role checks, and project-scoped data access are present. |
| Project, domain, and crawl management | Implemented | CRUD APIs and database-backed projects, domains, and crawl definitions are present. |
| Deterministic synthetic demo data | Implemented | `backend/app/services/demo.py` generates a labelled, repeatable dataset with planted issue classes. |
| Scenario catalogue | Implemented | `backend/app/services/scenarios.py` defines twelve curated scenarios, including a full audit preset. |
| Issues, recommendations, and exports | Implemented | Issue listing and aggregation, recommendations, CSV/JSON export endpoints, and website-page export are present. |
| Keyword research and clustering | Implemented | Synthetic keyword datasets, SERP summaries, clustering, cannibalisation checks, and keyword-to-page mapping are present. |
| AI search visibility | Implemented | Synthetic prompt tracking, answer-engine visibility snapshots, and gap detection are present. |
| Content briefs and content gap analysis | Implemented | Brief generation, brief CRUD, competitor gap data, and topic suggestions are present. |
| Internal linking and orphan detection | Implemented | Synthetic link graph, page-level link suggestions, and orphan target detection are present. |
| Live crawler and simulation | Implemented | Robots checks before each request and redirect hop, fail-closed robots errors, per-host delay, SSRF validation, cancellation, raw observations, URL inventory, issue generation and progress are present. `mode` changes `data_kind` only; no JS renderer is active. |
| Workflows and scheduled jobs | Implemented | Workflow definitions and runs, schedule CRUD, job listing, job details, cancellation, and retry are present. |
| Reports | Implemented | Report generation, retrieval, data-gap notes and CSV/JSON/XLSX/PDF exports are present. |
| Import jobs | Implemented | CSV/TSV/TXT, XML sitemaps, JSON and XLSX uploads are parsed into URL/keyword inventory with source tracking and bounded batches. |
| Database migrations | Implemented | Alembic baseline revision `0001_initial_schema.py` plus `create_all()` bootstrap for fresh databases. |
| Frontend application | Implemented | React/Vite SPA with 23 module pages, API client, auth state, project state, Demo Centre and in-app documentation index. |
| Test suite | Implemented | Backend pytest suite passes with `36 passed, 1 deselected` using `-m "not slow"` and `37 passed` for the full suite; the 100,000-URL scale test is included. |

### Partial

| Area | Status | Current limitation | Priority |
|---|---|---|---|
| Container deployment | Partial | All Compose assets are present, but the stack has not been built in this environment; local source setup is the verified path. | Medium |
| Integration providers | Partial | Provider registry, encrypted credential records and connection declarations exist, but no live vendor API calls are implemented. | Medium |
| Crawler depth | Partial | `canonical_handling` and `schedule` config keys are stored but unused; JS rendering/Playwright is not implemented; target validation is string-based, without DNS/egress enforcement. | High |
| Issue rule coverage | Partial | Some declared rules (`excessive_depth`, `broken_external_link`) have no detector. | Medium |
| Production RBAC | Partial | Writes are gated by global role; per-project write roles and a role-management UI are not implemented. | Medium |
| Pagination consistency | Partial | Responses use `items,total,page,page_size,has_more`, while most requests use `offset`/`limit`. | Low |
| Production observability | Partial | Basic logging exists, but no structured metrics, tracing, or alerting stack is configured. | Medium |

## Proposed roadmap

### Phase 1 — Correctness and demo reliability

**Priority: High**

1. Build and verify the provided Compose stack, or continue documenting local source setup as the only supported path.
2. Harden crawler target validation with DNS resolution, private-range checks on resolved addresses and network egress controls.
3. Implement real JS rendering (for example Playwright) or remove the misleading `javascript_rendering` option.
4. Align request pagination parameters with response pagination fields, or document a deliberate compatibility layer.

### Phase 2 — Import and integration honesty

**Priority: Medium**

1. Add explicit provider adapters for declared integrations, with clear capability flags for implemented versus simulated operations.
2. Replace placeholder connection checks with safe, read-only validation calls where live credentials are configured.
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
