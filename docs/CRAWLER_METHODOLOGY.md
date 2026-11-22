# Crawler Methodology

This document describes the behaviour implemented in `backend/app/services/crawler.py`, `backend/app/services/crawl_jobs.py`, `backend/app/core/url_utils.py`, the inventory models, and the `/api/v1/crawler/*` and `/api/v1/jobs/*` routers. It is a description of the current code, not a statement that the crawl is exhaustive or that search engines saw the same pages.

Related documents: [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md), [KEYWORD_MAPPING_METHODOLOGY.md](KEYWORD_MAPPING_METHODOLOGY.md), [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md).

## 1. What is collected, and from where

| Data kind / label | Where it comes from | How it is represented |
| --- | --- | --- |
| **Live crawl** | `httpx` requests made by `CrawlEngine` to URLs supplied in the job config. | `Crawl.data_kind = config.mode` (default `"live"`); new `UrlRecord.data_kind = "live_crawl"`. Raw HTTP evidence is in `CrawlObservation`. |
| **Simulated crawl** | The same HTTP code path, but `config.mode` is not `"live"`. | New `UrlRecord.data_kind = "simulated"`. There is **no separate simulated fetcher** in `crawler.py`; `mode` changes the label only. |
| **Imported** | CSV/TSV, XLSX, JSON, sitemap XML, GSC/GA4/CMS-style exports ingested by `imports.py` / `import_jobs.py`. | `UrlRecord.data_kind` defaults to `"imported"`, `sources` records the import source type. Imported rows are not fetched by the crawler unless a crawl job visits them. |
| **Synthetic / simulated demo** | `demo.py` generates deterministic fake records with `data_kind = "synthetic"` and notes such as `"SYNTHETIC DEMONSTRATION RECORD"`. | These are for rule testing only; no real network request or provider response produced them. |
| **Derived** | Link counts, classifications, issues and scores computed later. | Written to `UrlRecord.internal_inlinks`, `OrphanRecord`, `Issue`, etc. See [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md) and [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md). |
| **Model-generated** | None of the crawler/analysis paths described here emits an LLM- or embedding-generated score. | The keyword `"semantic"` clustering method is a character-similarity rule, not a model call. |

The core design split is:

```text
CrawlObservation  = raw, uninterpreted evidence for one fetch
UrlRecord         = interpreted/overwritten SEO fields for one normalised URL key
LinkEdge          = observed source -> target anchor edge
Crawl             = job-level configuration, counters and final summary
```

## 2. Configuration

`CrawlConfig.from_dict()` merges user input over `DEFAULT_CONFIG`, keeps only declared fields, and clamps four values.

| Field | Code default | Effective behaviour in this version |
| --- | --- | --- |
| `start_url` | `""` | Depth-0 seed. At least one of `start_url` or `seed_urls` is required by the API. |
| `seed_urls` | `[]` | Additional depth-0 seeds. |
| `max_urls` | `500` | Clamped to `1..100000`. Loop stops when `visited >= max_urls`. |
| `max_depth` | `3` | Clamped to `0..20`. Discovered links are only enqueued when `depth < max_depth`. |
| `concurrency` | `4` | Clamped to `1..32`. Batch size and `ThreadPoolExecutor` worker count. |
| `timeout` | `10` | `httpx.Client` timeout in seconds for page fetches. Robots fetch uses `timeout=5`; sitemap discovery uses `timeout=8`. |
| `retries` | `1` | Up to `retries + 1` GET attempts per hop; backoff between failures is `0.5 * (attempt + 1)` seconds. |
| `user_agent` | `SEOAutomationLab/1.0 (+respects robots.txt)` | Sent as `User-Agent`; also used for `robots.txt` `can_fetch` / `crawl_delay`. |
| `crawl_delay` | `1.0` | Minimum seconds between requests to the same hostname. Effective delay is `max(config.crawl_delay, robots crawl_delay)`, and `time.sleep` is capped at 30 seconds per wait. |
| `javascript_rendering` | `False` | **No Playwright renderer is active.** If requested and no HTML was extracted, the record note reads: `"JS rendering requested; no HTML extracted (Playwright renderer not active)"`. |
| `follow_internal` | `True` | Controls whether internal `LinkEdge` rows are stored. It does **not** stop internal links from being enqueued for crawling. |
| `follow_external` | `False` | External link edges are stored and external targets are enqueued only when true. |
| `include_patterns` | `[]` | Case-insensitive `re.search` filters applied to **discovered links**, not to seeds. A non-empty list requires at least one match. |
| `exclude_patterns` | `[]` | Case-insensitive `re.search` filters applied to discovered links; any match excludes the link. |
| `query_handling` | `"strip_tracking"` | `"strip_tracking"` uses `normalize_url()` rules; `"drop_all"` removes the query entirely via `urljoin(url, parts.path)`. |
| `canonical_handling` | `"record"` | Stored in config, but `crawler.py` has no branch on this value; relative canonicals are always resolved and recorded when present. |
| `respect_robots` | `True` | Robots permission is checked **before** each request and before following each redirect hop. Disallowed URLs are excluded and never stored; robots fetch failures fail closed. |
| `sitemap_discovery` | `True` | Fetches `scheme://netloc/sitemap.xml`; only a `sitemap` result (not a `sitemap_index`) contributes up to `max_urls` depth-1 seeds. |
| `auth_headers` | `{}` | Extra request headers. `CrawlConfig.as_dict()` removes them, so they are not persisted in `Crawl.config`. |
| `allow_private` | `False` | Opt-in to private/internal network targets; dangerous and off by default. |
| `schedule` | `"manual"` | Stored in config. `crawler.py` itself contains no scheduler. |
| `mode` | `"live"` | Labels created records as `live_crawl` or `simulated`; it does not change fetch mechanics. |

`CrawlConfig.rules()` returns only:

```python
{
    "strip_tracking_params": self.query_handling == "strip_tracking",
    "strip_fragment": True,
}
```

All other normalisation defaults come from `backend/app/core/url_utils.py`: lowercase host, preserved path case, default ports dropped, tracking parameter list (including `utm_*`, `gclid`, `fbclid`, `_ga`, `mc_cid`, etc.), sorted remaining query pairs, no `www` stripping, no forced HTTPS, no trailing-slash removal.

## 3. URL validation, robots and throttling

`validate_target_url()` rejects a URL before any network access when:

- it is empty, not a string, or longer than 4096 characters;
- its scheme is not `http` or `https`;
- it has no hostname;
- it contains embedded `username`/`password`;
- the host **as written** is a private/loopback/link-local/reserved/multicast/unspecified IP literal, or is `localhost`, `metadata`, `metadata.google.internal`, or a `.localhost` name, unless `allow_private=True`. DNS resolution is not performed, so a public hostname that resolves to a private address is not detected;
- its port is outside `1..65535`.

Validation runs again on every redirect hop. Invalid seeds increment `stats["excluded"]` and are recorded in `stats["errors"]`; invalid discovered links are excluded.

Robots behaviour:

- A thread-safe `RobotsCache` is created per engine instance and caches a `RobotFileParser` per hostname.
- `GET scheme://host/robots.txt` uses a 5-second timeout. HTTP 200 bodies are parsed; HTTP 4xx is treated as an explicit allow-all. Other statuses, validation failures and exceptions are recorded as errors and leave the parser `None`.
- When `respect_robots=True` and no parser could be obtained, `allowed()` returns `False`: the crawler **fails closed** and skips the URL instead of assuming consent. When `respect_robots=False`, no robots request is made and crawling is allowed.
- `RobotFileParser.crawl_delay(user_agent)` is stored per host when present. The effective delay is `max(config.crawl_delay, robots crawl_delay)`.
- `_fetch()` calls `allowed(current)` **before every GET**, including each redirect hop (max 10). A disallowed hop sets `robots_allowed=False`, `status_code=0`, `error="Disallowed by robots.txt"` and returns without issuing the request.
- The run loop increments `excluded`, records the robots error (or the underlying robots-fetch error), and does **not** store a `UrlRecord` or `CrawlObservation` for that URL.
- For URLs that are actually fetched, `UrlRecord.robots_allowed` is copied from the fetch result (`True` on success); imported and synthetic records can still carry `robots_allowed=False`.
- Requests to the same host are serialised through a lock around the throttle and timestamp update. `time.sleep` is capped at 30 seconds per wait.

## 4. Discovery and queueing

```text
seeds = [(start_url, 0)] + [(s, 0) for s in seed_urls]
if sitemap_discovery and start_url:
    GET /sitemap.xml
    if kind == "sitemap":
        seeds += [(entry.loc, 1) for entry in entries[:max_urls]]
```

Seed de-duplication uses `_canonical_for_crawl(url)` as the `seen` key. Discovered links are appended at `depth + 1` only when:

1. the current response status is 200–399;
2. `depth < max_depth`;
3. the link is internal, or `follow_external=True`;
4. `include_patterns` / `exclude_patterns` allow it;
5. `validate_target_url()` passes;
6. its canonical key has not already been seen.

`stats["discovered"]` starts as the number of validated unique seeds and is incremented for each newly enqueued link. It can therefore exceed `max_urls`; `visited` is the fetch counter that enforces the limit.

## 5. Fetching and HTML extraction

`_fetch()` uses `httpx.Client(follow_redirects=False, ...)` and manually follows at most 10 hops:

- a 3xx response with a `Location` header is followed with `urljoin(current, location)`;
- `redirect_chain` accumulates hop URLs and the final URL;
- if no response is obtained, `status_code = 0` and `error` records the exception type/message (truncated to 1000 characters);
- HTML is parsed only when `content-type` contains `html` or no content-type was supplied.

`extract_page()` removes `script`, `style`, `noscript` and `svg` nodes, collapses whitespace, and produces:

| Extracted field | Rule |
| --- | --- |
| `title` | First `<title>` text. |
| `meta_description` | `<meta name="description">` or `<meta property="description">`. |
| `h1`, `h2` | All matches, capped at 20 and 50 entries respectively. |
| `canonical` | `<link rel="canonical">` href, resolved relative to the final URL; empty when absent. |
| `meta_robots` | Meta robots content. |
| `schema_types` | `@type` values from JSON-LD blocks; a parse failure appends the literal `invalid-json-ld`. |
| `og` | Lowercased `og:*` properties. |
| `hreflang` | Lowercased language keys with `href` resolved against the final URL. |
| `pagination` | Booleans `next` / `prev` from `<link rel>` or `<a rel>`. |
| `word_count` | Whitespace-separated tokens in visible text. |
| `image_count`, `images_missing_alt` | All `<img>` elements; missing-alt means blank/whitespace `alt`. |
| `body_excerpt` | First 12000 characters of visible text; stored in `CrawlObservation.body_excerpt` and as `CrawlObservation.extracted` without that key. |
| `links` | All `<a href>` values resolved against the final URL, with anchor text truncated to 300 characters. `javascript:`, `mailto:`, `tel:` and `data:` hrefs are skipped. |

## 6. Raw evidence and interpreted records

For each fetched URL, `_store()` writes one `CrawlObservation` containing `requested_url`, `final_url`, `status_code`, lowercased response `headers`, `redirect_chain`, `body_excerpt` (12k), `response_time_ms`, `content_size`, `extracted`, `error` and `observed_at`.

It then upserts one `UrlRecord` keyed by `(project_id, url_hash)` where `url_hash = sha256(normalize_url(requested_url, rules))`. Consequences:

- the key is based on the **requested** URL, not the final redirect destination;
- an existing imported record keeps its original `data_kind` but receives the newly crawled fields;
- a new record gets `sources = ["crawl:<crawl_id>"]` and `data_kind = "live_crawl"` or `"simulated"`;
- `last_seen`, `crawled`, `crawled_at`, `http_status`, `content_type`, `response_time_ms`, `content_size`, on-page fields, `redirect_chain`, `redirected_to`, `crawl_depth` and `page_type` are overwritten on every visit.

Indexability is computed as:

```python
robots_txt = (meta_robots + " " + x_robots_tag).lower()
noindex    = "noindex" in robots_txt
indexable  = None if status in (0, None) else (200 <= status < 300 and not noindex)
```

`page_type` comes from the path/title rule in `classify_page_type()`: `product`, `category`, `article`, `service`, `location`, `faq`, `careers`, `support`, `homepage`, or `unknown`. It is a heuristic label, not a vendor classification.

## 7. Link edges

`LinkEdge` rows are written when the relevant `follow_*` flag allows them:

- `link_type = "internal"` when `is_same_host(target, final_url or requested_url)`; this treats `www` and non-`www` forms of the same host as internal;
- `link_type = "external"` otherwise;
- `source_url` is the final URL (or requested URL when unavailable);
- `is_broken = False` at crawl time.

Later, `refresh_link_counts()` in the orphan engine can mark an edge broken when the target URL's known `http_status >= 400`. See [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md).

## 8. Counters, progress and final status

`CrawlEngine.stats` contains:

| Key | Meaning |
| --- | --- |
| `discovered` | Validated unique seeds plus newly enqueued links. |
| `crawled` | Fetches with `200 <= status < 300`. |
| `failed` | Fetches with status `0`/`None` or a non-empty error. |
| `excluded` | Invalid URL, private/credential rejection, robots disallow, or pattern filters. |
| `by_status` | Counts keyed by `str(status_code)`. |
| `redirects` | Responses with a non-empty redirect chain. |
| `indexable`, `non_indexable` | Counts from the `indexable` expression above; `None` is neither. |
| `slow_pages` | Responses with `response_time_ms > 2000`. |
| `duplicate_titles`, `duplicate_descriptions` | At the end: `sum(count - 1)` over lowercased non-empty strings seen more than once. |
| `depth_distribution` | Fetches keyed by `str(depth)`. |
| `errors` | Error dictionaries. The in-`_store()` append is capped at 100 entries; robots-disallow errors added by `run()` are not subject to that cap. |

`on_progress(visited, total, message)` is called once at start (`"Starting crawl"`) and after each completed fetch (`"Fetched <n> URLs"`). The total is `min(max_urls, discovered)`.

## 9. Jobs and cancellation

`POST /api/v1/crawler/start` validates the body, creates a database-backed job (`status = "queued"`) and returns HTTP 202 with a `job_id`. A worker claims the job (`queued` → `claimed` → `running`), then `run_crawl_job()`:

1. creates the `Crawl` row with `status = "running"`, `started_at`, `config` (minus `auth_headers`) and `data_kind = config.mode`;
2. runs `CrawlEngine.run()` in a second DB session;
3. writes `discovered`, `crawled`, `failed`, `excluded`, the full `summary`, `finished_at`, and sets `status = "cancelled"` if the job was cancelled, otherwise `"completed"`.

Cancellation:

- `POST /api/v1/jobs/{job_id}/cancel` sets `Job.cancel_requested = True`; it does not kill a thread immediately.
- `CrawlEngine.run()` checks `is_cancelled(job_id)` at the top of each batch loop and appends `{"url": "", "error": "Cancelled by user"}` before breaking.
- In-flight fetches in the current batch finish. Work already flushed to the database remains.
- `run_job()` ultimately marks the job `cancelled` and sets `"Cancelled by user"` when `cancel_requested` is true; otherwise `succeeded`.
- `GET /api/v1/jobs/{id}` exposes `cancel_requested`; `WS /api/v1/jobs/ws/{job_id}` polls the job row once per second and requires a bearer token (header or `token` query parameter) with access to the job's project.

## 10. API surface

| Endpoint | Behaviour |
| --- | --- |
| `GET /api/v1/crawler/config-defaults` | Returns `DEFAULT_CONFIG` with `auth_headers` removed. |
| `POST /api/v1/crawler/start` | 202 + `job_id`; requires `start_url` or `seed_urls`. Validates `start_url` plus only the **first 50** supplied seeds in the API layer (the engine validates all seeds at run time). |
| `GET /api/v1/crawler/runs` | Paginated crawl runs with counters and `data_kind`. |
| `GET /api/v1/crawler/runs/{crawl_id}` | One project-scoped run, including config and summary. |
| `GET /api/v1/crawler/runs/{crawl_id}/observations` | Raw observations, optional `status` filter, paginated. |
| `GET /api/v1/crawler/runs/{crawl_id}/export` | Exports a limited subset of observation columns (up to 200000 rows). |
| `GET /api/v1/jobs/{job_id}`, `POST /api/v1/jobs/{job_id}/cancel`, `WS /api/v1/jobs/ws/{job_id}` | Job state, cancellation request and authenticated DB-polling progress. |

## 11. Limitations present in the code

- No JavaScript rendering, screenshot capture, browser execution, or resource loading beyond the initial HTML document.
- `follow_internal=False` stops internal `LinkEdge` storage but internal links are still enqueued by `run()`.
- The sitemap-discovery GET to `/sitemap.xml` is not gated by robots parsing; discovered sitemap URLs are validated and robots-checked when crawled.
- `validate_target_url()` is string-based: IP literals and known local names are rejected, but DNS results are not inspected and no egress firewall is applied.
- `canonical_handling` and `schedule` are stored but not acted upon by the engine.
- Sitemap discovery fetches only `/sitemap.xml`; a sitemap index is not expanded into child sitemaps.
- The `UrlRecord` hash is based on the requested URL, so redirects can create separate records for old and final URLs.
- Imported/synthetic records can be updated by a crawl without changing their `data_kind`.
- Private-network targets are rejected unless `allow_private=True`; there is no authentication system in the crawler beyond static `auth_headers`.
- `max_urls`, `max_depth`, pattern filters and duplicate counters bound work; they do not guarantee completeness.

## What this does not prove

A completed crawl does **not** prove that all site URLs were discovered, that Googlebot or another search engine rendered or indexed the pages, that JavaScript-only content is absent, that internal links are exhaustive, that a `200` response means a useful page, or that generated/imported business metrics reflect real traffic or revenue. It proves only what this conservative HTTP client observed under the configured limits, with the stated labels for live, simulated, imported and synthetic data.

## Related documents

- [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md) — how observed links and URLs become orphan classifications.
- [KEYWORD_MAPPING_METHODOLOGY.md](KEYWORD_MAPPING_METHODOLOGY.md) — how imported or synthetic keyword lists are clustered and mapped to the shared URL inventory.
- [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md) — the transparent formulas used to score issues and orphans.
