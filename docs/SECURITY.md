# Security

This document describes the security controls **actually implemented** in the SERPScope code, and the hardening that is still required before a real production deployment. Architecture context is in [ARCHITECTURE.md](ARCHITECTURE.md); operational setup is in [DEPLOYMENT.md](DEPLOYMENT.md).

## 1. Authentication — HMAC-signed bearer tokens

Implementation: `backend/app/core/security.py`, `backend/app/api/deps.py`, `backend/app/api/v1/auth.py`.

| Aspect | Implementation |
| --- | --- |
| Token format | Three base64url segments: header `{"alg":"HS256","typ":"JWT"}`, JSON body, HMAC-SHA256 signature over `header.body` |
| Signature key | `settings.secret_key` (environment variable `SECRET_KEY`) |
| Payload | `sub` (user id as string), `iat`, `exp`, plus `role` added at login |
| Lifetime | `access_token_expire_minutes` — default **1440 minutes (24 h)** |
| Verification | `decode_access_token()` requires `alg == "HS256"` and `typ == "JWT"`, recomputes the HMAC with `hmac.compare_digest`, then checks `exp`; malformed or algorithm-tampered tokens return `None` |
| Request enforcement | `current_user()` uses `HTTPBearer(auto_error=False)`, rejects missing/invalid/expired tokens with 401, loads the user from the database and rejects inactive users |
| Transport | Frontend stores the token in `localStorage` (`serpscope-token`) and sends `Authorization: Bearer …` on every axios request; a 401 clears the token and redirects to `/login` |

**Important:** the `role` claim is informational. Authorisation reloads the `User` from the database and uses `user.global_role`, so editing a token's role claim is not sufficient to gain access — but the token itself cannot be revoked before `exp` because it is stateless.

## 2. Password hashing — PBKDF2

Implementation: `backend/app/core/security.py::hash_password` / `verify_password`.

- Algorithm: `hashlib.pbkdf2_hmac("sha256", password, salt, 210_000)`.
- Salt: 16 random bytes from `secrets.token_bytes`.
- Stored format: `pbkdf2_sha256$210000$<salt-hex>$<digest-hex>` in `users.hashed_password`.
- Verification parses the encoded rounds/salt, recomputes the digest and compares with `hmac.compare_digest` (constant time). A wrong algorithm tag or malformed value returns `False`.
- Login normalises email with `.strip().lower()` and returns the same generic `401 Invalid email or password` for unknown users and wrong passwords.
- The seeded demo owner (`demo@serpscope.local` / `demo1234`) is created only when the `users` table is empty, via `app.main.bootstrap()`.

## 3. Authorisation — RBAC helpers

Implementation: `backend/app/api/deps.py`.

| Helper | Behaviour |
| --- | --- |
| `current_user` | Resolves the bearer token to an active `User`; raises 401 otherwise |
| `require_roles(*roles)` | Factory dependency: users with `global_role` in `{owner, admin}` are always allowed; otherwise the global role must be in the supplied roles (403 "Insufficient role") |
| `get_project(db, project_id, user)` | Loads the project (404 if missing). Owners/admins get access to any project; all other users need a `Membership` row matching their user and the project's `organization_id`, otherwise 403 "No access to this project" |
| `require_org(db, user, organization_id)` | Loads the organisation (404 if missing). Owners/admins bypass; other users need a `Membership` row for that organisation, otherwise 403 "No access to this organisation" |
| `check_write(user)` | Allows `global_role` in `{owner, admin, editor}`; otherwise 403 "Write permission required". Called by mutating endpoints such as `/imports/upload`, `/imports/url-list` and `/crawler/start` |
| Job WebSocket | `/api/v1/jobs/ws/{job_id}` accepts `Authorization: Bearer …` or a `token` query parameter, resolves the user with `decode_access_token()` and applies `get_project()` scope checks; closes with `4401`/`4404`/`4403` |
| `paginate(page, page_size)` | Bounds list queries to `page_size` 1–500 |

Role values are plain strings stored in `users.global_role`, `memberships.role` and `project_members.role`. There is no role enum or policy engine.

**Known RBAC nuances:** organisation/project membership grants *read* access through `get_project`/`require_org`, and tenant-scoped mutations now call those helpers before changing data. Write access itself is still decided solely by `global_role` via `check_write`; a user whose global role is `viewer` cannot write even if their membership role is `editor`. `require_roles` short-circuits for owners/admins regardless of the roles passed. `project_members` is stored but is not consulted by these helpers. Demo generate/reset is global by design and is now restricted to platform `owner`/`admin`.

## 4. SSRF validation — `validate_target_url`

Implementation: `backend/app/core/url_utils.py::validate_target_url`, used at the crawler API boundary (`app/api/v1/crawler.py::start_crawl`) and again inside the crawl engine for seeds and discovered links.

Rejected inputs:

- Empty/non-string URLs and URLs longer than 4096 characters.
- Any scheme other than `http` or `https` (blocks `file://`, `javascript:`, etc.).
- Missing hostname, or embedded `username`/`password` credentials.
- Hostnames `localhost`, `metadata`, `metadata.google.internal`, anything ending in `.localhost`, and literal IP addresses classified as private, loopback, link-local, reserved, multicast or unspecified (e.g. `127.0.0.1`, `169.254.169.254`).
- Ports outside 1–65535.

`allow_private=False` is the default. `start_crawl` exposes an `allow_private` config switch and the crawler has an `allow_private` setting; enabling it bypasses the private-address check for authorised internal testing. One-click **public audits** cannot use that switch: `sanitize_public_audit_config()` in `app/services/public_audit.py` forces `allow_private=False`, empty `auth_headers`, `mode="live"`, robots respect and a bounded crawl at both the API and job boundary.

**Limitations:**

- The check inspects the *literal host string*; it does **not** resolve DNS, so a public hostname that resolves to a private address (DNS rebinding / internal DNS) is not blocked, and there is no egress proxy or IP allowlist.
- Redirect targets are re-validated immediately before each redirect GET by the crawler's manual redirect loop; network-layer egress controls are still advisable because DNS results are not inspected.
- `allow_private=true` disables the main guard, so it must be restricted to trusted operators.

## 5. Crawler safety — robots.txt, crawl delay and cancellation

Implementation: `backend/app/services/crawler.py`, `backend/app/services/crawl_jobs.py`, `backend/app/services/jobs.py`.

| Control | Behaviour |
| --- | --- |
| Robots respect | `DEFAULT_CONFIG["respect_robots"] = True`; a thread-safe `RobotsCache` fetches `/robots.txt` per host, `parser.can_fetch()` gates each URL and redirect hop **before** the request, and `parser.crawl_delay()` feeds the per-host delay map. Disallowed URLs are excluded without a request; robots fetch failures fail closed |
| Crawl delay | `crawl_delay` defaults to `1.0` seconds; the effective delay is `max(configured delay, robots-provided delay)`, with a lower bound of 0. Configuration clamps `max_urls` to 1–100000 and `crawl_delay` to ≥ 0 |
| User agent | `SEOAutomationLab/1.0 (+respects robots.txt)`; robots lookup uses the same agent |
| Cancellation | `POST /api/v1/jobs/{id}/cancel` sets `jobs.cancel_requested`; `jobs.is_cancelled(job_id)` is polled by handlers and the crawler receives a `cancelled` callback. A cancelled crawl is persisted with `crawls.status = "cancelled"` and the job ends as `cancelled` |
| Scope | Seeds, discovered links and redirect hops are passed through `validate_target_url`; `follow_external` / `allow_private` config controls outbound scope |

**Limitations:** HTTP 4xx on `/robots.txt` is treated as explicit allow-all; other fetch failures fail closed (no URLs are crawled for that host). Sitemap discovery fetches `/sitemap.xml` before robots gating. Cancellation is cooperative — a handler that never calls `is_cancelled` cannot be interrupted by the API; there is no hard timeout or process kill. Crawl speed is bounded by concurrency and delay settings, not by a global rate limiter.

## 6. Upload restrictions

Implementation: `backend/app/api/v1/imports.py`, settings in `backend/app/core/config.py`.

- **Extension allowlist:** `.csv`, `.tsv`, `.txt`, `.xml`, `.json`, `.xlsx` (case-insensitive suffix check; 400 otherwise).
- **Size limit:** `MAX_BYTES = settings.max_upload_mb * 1024 * 1024`, default **50 MB**; the handler reads `MAX_BYTES + 1` bytes and returns 413 when exceeded. Empty uploads return 400.
- **Source type allowlist:** `csv_urls`, `sitemap`, `sitemap_index`, `gsc`, `ga4`, `cms`, `screaming_frog`, `sitebulb`, `backlinks`, `keyword_csv`, `competitor_csv`, `analytics`, `rank_tracking`, `authority`, `lighthouse`, `crux`, `serp_features`, `paid_ads`, `gbp`, `historical_audit`.
- **Data-kind allowlist:** `validated_data_kind()` rejects labels outside `UPLOAD_DATA_KINDS`. A file cannot be declared `live_crawl` (or `observed`), which would otherwise let an arbitrary upload masquerade as a first-party observation.
- **Filename sanitisation:** only alphanumeric characters plus `.`, `_`, `-` are kept, truncated to 120 characters, prefixed with a millisecond timestamp, and written under `settings.upload_path/<project_id>/`.
- **Inline alternative:** `POST /api/v1/imports/url-list` accepts at most 10,000 URLs per call (400 above that) and is intended for small lists.
- Uploads are recorded with an `audit_logs` entry (`import.upload`) and enqueue an `import_file` job; uploaded files are **not** exposed via a static mount.

**Limitations:** only the filename suffix and byte length are checked — file content is not deeply validated, and there is no antivirus/malware scanning. XLSX content is parsed with openpyxl; keep that dependency patched. The upload directory must not be web-serving in the container setup.

## 7. CSV formula-injection neutralisation

Implementation: `backend/app/core/url_utils.py::safe_csv_value`, used by `backend/app/services/exports.py`.

- Any exported cell whose first character is `=`, `+`, `-`, `@`, tab or carriage return is prefixed with a literal apostrophe (`'`). `None` becomes an empty string.
- Applies to CSV exports and to nested values serialised into JSON exports; XLSX/PDF exports pass through the same sanitisation path.
- CSV responses are written with a UTF-8 BOM (`utf-8-sig`) and `Content-Disposition: attachment`; tests in [TESTING.md](TESTING.md) cover `=CMD(...)`, `@SUM(...)`, ordinary text and `None`.

**Limitations:** this is cell-level neutralisation only. It does not strip DDE payloads from trusted internal documents, and users should still treat exported spreadsheets from untrusted data with care.

## 8. Encrypted integration credentials

Implementation: `backend/app/core/crypto.py`, `backend/app/api/v1/integrations.py`, column `integrations.credentials_encrypted`.

- Encryption uses `cryptography.fernet.Fernet` (AES-CBC + HMAC under the hood).
- The key is derived as `base64.urlsafe_b64encode(sha256(settings.secret_key.encode()).digest())` — i.e. it comes from `SECRET_KEY`, not a separate stored key.
- The connect endpoint stores `encrypt(str(payload["credentials"]))` and returns only `{"id", "status", "note"}` with the explicit note that values are not returned. List/detail responses select columns that exclude `credentials_encrypted`.
- Default integration mode is `csv_import`; no live third-party API provider is called by this code.

**Limitations:**

- There is no KMS/HSM, per-tenant data key, or key rotation path. Rotating `SECRET_KEY` invalidates **both** all bearer tokens and all stored integration credentials, with no re-encryption routine.
- `credentials_encrypted` is `Text`; a database dump contains ciphertext, so database backups still need protection.
- The provider registry describes possible integrations; it does not implement OAuth token refresh or secret fetching from a vault.

## 9. Secrets and configuration hygiene

- All configuration comes from `Settings` (`pydantic-settings`) with `env_file=".env"` and `extra="ignore"`; secrets should be supplied as environment variables in deployment.
- `SECRET_KEY` has the development default `dev-only-secret-change-before-deployment` and **must** be overridden (a long random value, e.g. generated with `secrets.token_urlsafe(48)`).
- `CORS_ORIGINS` defaults to `http://localhost:5173,http://127.0.0.1:5173` with `allow_credentials=True`; restrict it to the real frontend origin in production. Methods and headers are currently wildcarded.
- `Settings.validate_production_settings()` fails fast when `ENVIRONMENT=production` with the default/weak `SECRET_KEY`, localhost or wildcard `CORS_ORIGINS`, or a SQLite `DATABASE_URL`.
- No third-party API keys, tokens or provider credentials are hardcoded in source. The demo account credentials are deliberately hardcoded for local/demo bootstrap only.
- The global exception handler logs the exception server-side and returns only `{"detail": "Internal server error"}`; raw SQL, paths and supplied values are never echoed to the caller.

## 10. Hardening implemented in this release

| Control | Where | Behaviour |
| --- | --- | --- |
| Provenance-safe public audits | `backend/app/services/public_audit.py`, `backend/app/api/v1/audits.py`, `backend/app/services/public_audit_jobs.py` | Untrusted config is clamped to public-evidence limits at enqueue **and** at job execution; private hosts, auth headers, synthetic mode and JavaScript rendering cannot be enabled |
| Upload provenance labels | `backend/app/api/v1/meta.py`, `backend/app/api/v1/imports.py` | Only declared upload kinds are accepted; `live_crawl`/`observed` are reserved for real crawler or reviewed observation paths |
| Pinned token algorithm | `backend/app/core/security.py` | Explicit HS256/typ check before signature verification |
| Production config guard | `backend/app/core/config.py` | Startup fails on weak secrets, localhost/wildcard CORS or SQLite in production |
| No public export directory | `backend/app/main.py` | The `StaticFiles` mount over `EXPORT_DIR` was removed; downloads are streamed only by authenticated endpoints |
| Real health probe | `backend/app/main.py` | `/api/health` runs `SELECT 1` and returns HTTP 503 with a generic `degraded` status if the database is unreachable |
| Edge security headers | `vercel.json` | HSTS, `nosniff`, `X-Frame-Options`, referrer/permissions policies and a CSP restricting scripts, connections, fonts, frames and object/base/form targets |
| CI invariant checks | `.github/workflows/ci.yml` | CI verifies 23 modules, 17 docs, 24 screenshots and 12 interview scenarios |
| Tenant-scoped reads and writes | `backend/app/api/deps.py`, `backend/app/api/v1/*.py` | `get_project`/`ProjectDep` and `require_org` guard project, organisation, job, integration, user, client and child-resource endpoints; project creation defaults to a caller's own membership; overview counters are scoped; platform owner/admin is the only global bypass |
| In-process mutating-rate throttle | `backend/app/main.py`, `backend/app/core/config.py` | A 600-second fixed window keyed by an HMAC digest of UTC day, route bucket and socket peer host; login `10`, presence `60`, other mutations `120` per window; `429` plus numeric `Retry-After`; disabled by `RATE_LIMIT_ENABLED=false` in tests |

The throttle reads only `request.client.host` (the socket peer) and reduces it with `HMAC-SHA256(SECRET_KEY, "day|bucket|peer")` to a 32-character digest. It never reads `X-Forwarded-For`, cookies, authorisation headers, referrer, query strings, request bodies, user IDs, path IDs or audited domains, and the `429` response contains no key, peer or path. It is correct for the single Render web process declared in `render.yaml`; horizontal scaling multiplies the effective budget unless an edge limiter is added.

**CSP limitation:** the static landing page uses inline GTM/gtag snippets and JSON-LD, so `script-src` still contains `'unsafe-inline'`. Moving those snippets to nonce-based delivery would allow tightening this policy.

## 11. Known limitations / production hardening still needed

| Gap | Impact / recommendation |
| --- | --- |
| **No SSO / external IdP** | `POST /api/v1/auth/register` is open and creates `viewer` users; production should use SSO/admin provisioning and disable self-registration |
| **Rate limiting is in-process only** | Mutating routes are throttled by socket peer (10 logins, 60 presence pings, 120 other mutations per 600 seconds), but there is no gateway/WAF limit, distributed store or account-level lockout. Behind a shared proxy, all visitors can share one bucket; multiple workers multiply the budget. Add edge rate limiting and failed-login backoff for real production. |
| **No token revocation or refresh** | Tokens live 24 h and cannot be invalidated server-side; add a denylist or short-lived tokens with refresh |
| **Shared `SECRET_KEY`** | Token signing and Fernet credential encryption derive from one secret; separate keys so rotation does not couple tokens and stored credentials |
| **Token in `localStorage`** | Vulnerable to XSS token theft; prefer `HttpOnly`/`Secure` cookies or a BFF. An edge CSP is now present, but inline legacy snippets mean `script-src` still allows inline scripts |
| **No CSRF token** | Mitigated today by bearer-token auth (not cookies), but re-evaluate if auth moves to cookies |
| **SSRF is string-based** | No DNS resolution checks, egress firewall, or redirect-time network enforcement |
| **RBAC still relies on global write roles** | Tenant membership now gates reads and scoped writes, but write permission is still decided by `global_role`; `project_members` is not consulted. A per-action permission matrix is needed if tenant admins must delegate writes. |
| **Baseline-only migrations** | Alembic `0001_initial_schema` and `create_all()` create fresh tables but do not alter existing ones; test and author incremental revisions before schema changes reach production |
| **No Redis/Celery** | The queue is a single `jobs` table with conditional-update claiming; it is not a high-throughput broker, has no visibility timeout or automatic retry of orphaned `claimed` jobs |
| **Single-writer SQLite by default** | Move to PostgreSQL and a managed connection pool for concurrent workers |
| **Partial audit coverage** | `audit()` exists and is used on some actions (e.g. imports), but not uniformly across every mutating endpoint |
| **TLS / secret storage** | Terminate TLS at the edge, store `SECRET_KEY` in a secrets manager, and add key rotation for Fernet credentials |
| **Demo bootstrap** | Remove or guard the automatic demo organisation/owner creation before exposing the service |

## 12. Related documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — request and job lifecycles, data-flow rules
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — identity, audit, jobs and integrations tables
- [TESTING.md](TESTING.md) — security-relevant test coverage
- [DEPLOYMENT.md](DEPLOYMENT.md) — environment variables and container topology
