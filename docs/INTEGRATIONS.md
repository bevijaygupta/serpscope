# Integrations

**Short version:** SERPScope integrates with **files**, not live vendor APIs. You can upload GSC/GA4-style CSV exports, keyword/rank/backlink/authority exports, Lighthouse/CrUX/SERP/paid/GBP/history exports, XML sitemaps, and Screaming Frog/Sitebulb-style crawl CSVs. Rows from declared vendor exports are stored **verbatim** and can change an audit signal from `Not supplied` to `Supplied`; the provider registry can store connection records and encrypted credentials, but it does **not** call Google, Semrush, Ahrefs, an LLM provider, or any other external service.

- [What actually works](#what-actually-works)
- [File imports](#file-imports)
- [Supplied data and signal coverage](#supplied-data-and-signal-coverage)
- [Recognised CSV columns](#recognised-csv-columns)
- [Sitemaps and sitemap indexes](#sitemaps-and-sitemap-indexes)
- [Provider registry](#provider-registry)
- [Credential handling](#credential-handling)
- [Demo-mode connection records](#demo-mode-connection-records)
- [What is not implemented](#what-is-not-implemented)

---

## What actually works

| Capability | Implementation | Status |
| --- | --- | --- |
| URL inventory from delimited text | `POST /api/v1/imports/upload`, `imports/url-list` | **Working** for CSV/TSV/text with a URL-like column |
| XML sitemap import | `source_type=sitemap` → `parse_sitemap()` → `SitemapEntry` + `UrlRecord` | **Working** for standard `<urlset>` XML |
| Sitemap index import | `source_type=sitemap_index` | **Partial**: `<loc>` entries are added as URLs; child sitemaps are not fetched |
| Keyword CSV import | `POST /api/v1/keywords/import`, `import_keywords` job | **Working** for delimited text |
| Competitor keyword CSV | `source_type=competitor_csv` | **Working** as imported keyword rows with competitor evidence; no competitor site is queried |
| Screaming Frog / Sitebulb CSV | `source_type=screaming_frog` / `sitebulb` | **Working** as URL/metric enrichment via the generic CSV column mapper |
| GSC / GA4-style CSV | `source_type=gsc` / `ga4` / `analytics` | **Working** as URL-level metrics on `UrlRecord` and as verbatim supplied rows; it does not create `AnalyticsRecord` rows |
| Private/vendor signal exports | `source_type=rank_tracking`, `authority`, `lighthouse`, `crux`, `serp_features`, `paid_ads`, `gbp`, `historical_audit` | **Working** as verbatim `SuppliedMetric` rows; query/domain/location-only files no longer require a URL column |
| Supplied-signal API | `GET /api/v1/integrations/supplied-signals`, `GET /api/v1/integrations/supplied-records` | **Working**; reports row counts, source types, periods, samples and original metrics |
| JSON / XLSX upload | `parse_table()` → `imports/url-list` job and keyword import | **Working** for JSON arrays/objects and XLSX first worksheet; values are converted to strings and mapped by header |
| OAuth / API-key provider modes | registry declarations only | **Not implemented** |
| Live LLM answer sampling | none | **Not implemented** |

The crawler (`POST /api/v1/crawler/start`) is a separate capability: it fetches **authorised public URLs** over HTTP with robots/limits/SSRF checks. It is not a vendor integration and it is not used by the synthetic demo generator.

---

## File imports

### Upload endpoint

`POST /api/v1/imports/upload` is `multipart/form-data`:

| Field | Example | Notes |
| --- | --- | --- |
| `file` | `gsc_export.csv` | Required. |
| `project_id` | `1` | Required; project access is checked. |
| `source_type` | `gsc` | Default `csv_urls`; must be in `SOURCE_TYPES` below. |
| `data_kind` | `synthetic_verification` | Default `imported`; retained on URL records and every supplied row. Use `synthetic_verification` for test files so they can never be mistaken for real client data. |

Allowed `source_type` values (from `backend/app/api/v1/imports.py`):

```
csv_urls, sitemap, sitemap_index, gsc, ga4, cms, screaming_frog,
sitebulb, backlinks, keyword_csv, competitor_csv, analytics,
rank_tracking, authority, lighthouse, crux, serp_features,
paid_ads, gbp, historical_audit
```

Allowed extensions: `.csv`, `.tsv`, `.txt`, `.xml`, `.json`, `.xlsx`. CSV/TSV/TXT are delimiter-sniffed; JSON accepts an array of objects or an object with `items`/`rows`/`data`; XLSX reads the first worksheet's header row and converts cell values to strings. Uploads are capped by `MAX_UPLOAD_MB` (default 50 MB), sanitised to a safe filename, written under `data/uploads/<project_id>/`, confined to `settings.upload_path` by `_safe_upload_path()` when queued, processed by the `import_file` background job and deleted in `finally` after import. The response is `202` with a `job_id`:

```json
{ "job_id": 42, "status": "queued", "file": "gsc_export.csv", "bytes": 18320 }
```

`GET /api/v1/imports/sources?project_id=1` shows `row_count`, `rejected_count`, `data_kind` and `meta_info` with the detected **column mapping**, the first 20 errors and `supplied_metric_rows`. That mapping is the audit trail for how a vendor export was interpreted.

The Integrations page performs this exact multipart call and waits for the returned `job_id`; after the job succeeds it refreshes signal coverage, the verbatim row table and recent imports.

### Inline URL list

For small lists, `POST /api/v1/imports/url-list` accepts up to 10,000 URLs synchronously and returns `accepted`, `rejected`, `errors` and `data_source_id`. It supports optional `normalization_rules` (see `backend/app/core/url_utils.py`: lowercase host/path, strip tracking params, strip www, force HTTPS, trailing-slash handling, preserve parameters).

### Normalisation and deduplication

`upsert_urls()` in `backend/app/services/imports.py`:

- validates that the URL is HTTP(S), has a hostname, no embedded credentials, is not private/loopback by default, and is ≤ 4,096 characters;
- computes `normalize_url()` and a SHA-256 `url_hash` as the comparison key;
- deduplicates within and across batches;
- appends the source name to `sources` when a URL already exists instead of overwriting provenance;
- updates supplied metrics (`clicks`, `impressions`, `sessions`, `conversions`, `revenue`, `referring_domains`, `page_type`, `title`, etc.) only when a non-empty value is provided;
- marks `in_sitemap` when the source is a sitemap.

The demo generator uses the same URL model but labels every record `synthetic`; imported rows are `imported`. Both can coexist in one inventory and are separated by the `data_kind` filter and the Overview composition chart.

---

## Supplied data and signal coverage

Every import also writes its original rows to `supplied_metrics`, a verbatim store that is separate from the interpreted URL inventory. This is what makes a private signal honest: the audit never calls a vendor API and never estimates a private metric, but if the user supplies a real export the UI can prove it.

| Source type | Signal | What it can supply |
| --- | --- | --- |
| `gsc` | `gsc` | Search Console queries, impressions, clicks, CTR and position |
| `ga4`, `analytics` | `ga4` | Sessions, conversions and revenue |
| `keyword_csv`, `competitor_csv` | `keywords` | Keyword volume, difficulty and CPC |
| `rank_tracking` | `rank` | Positions and history |
| `backlinks` | `backlinks` | Inbound backlinks and referring domains |
| `authority` | `authority` | Third-party domain authority |
| `lighthouse` | `performance` | Lighthouse / Core Web Vitals |
| `crux` | `crux` | CrUX field data |
| `serp_features` | `serp` | SERP features and rich results |
| `paid_ads` | `paid` | Paid keywords, ads and spend |
| `gbp` | `local` | Google Business Profile and local visibility |
| `historical_audit` | `historical` | Retained audit history and trends |

The `supplied_metrics` row keeps `project_id`, `source`, `signal`, `data_kind`, `dimension`, `period_start`, `period_end`, the original `metrics` dict and the parent `data_source_id`. Dimensions are detected from URL/page/query/keyword/domain/location-style columns; dates from date/period/day/month/week-style columns. If no URL-like column exists, URL-enrichment sources still populate the inventory but query/domain/location exports are accepted as verbatim supplied rows instead of failing.

### APIs

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://serpscope-api.onrender.com/api/v1/integrations/supplied-signals?project_id=1"

curl -H "Authorization: Bearer $TOKEN" \
  "https://serpscope-api.onrender.com/api/v1/integrations/supplied-records?project_id=1&signal=gsc&limit=50"
```

`supplied-signals` returns all 12 signals with `supplied`, `rows`, `sources`, `latest_period` and a small `sample`. `supplied-records` returns up to 500 original rows for one signal. Both endpoints enforce project access.

### Effect on the public audit

`build_public_audit()` reads the same store and adds:

- `supplied_data` with per-signal status, row counts, source types and samples;
- a dynamic `missing_data` register — for example, the GSC statement disappears only after `gsc` rows exist;
- `source_registry` entries of type `user_supplied_export` with confidence `user_declared`;
- `data_kinds` entries such as `user_supplied:gsc`;
- report sections and PPT notes that name the datasets actually supplied.

The Gap & Fix Center reads `supplied_data` to change matrix rows such as GA4, GSC, ranks, backlinks, performance, local and history to `Supplied`, and exposes the same object in its JSON gap-pack export. Existing persisted audit reports stay authoritative for crawl findings, but `GET /api/v1/audits/projects/{id}/public-audit`, all audit exports and the public case-study endpoint refresh supplied-data status, missing-data statements, source registry, data kinds and report sections at read time — a new crawl is not required after an import. The derived public-evidence health score still uses only crawl findings; supplied data improves context, not a fabricated score.

### Google Search Overview

The authenticated **Overview → Google Search Overview** is the single interpretive surface for Search Console data. It reads `supplied-signals` for the current status and `supplied-records?signal=gsc` for the verbatim rows, then displays only the cells the user supplied: dimension, period, original metrics and data-kind label. It performs no client-side totals, averages, CTR calculation, ranking, forecasting or trend inference, and it never calls a Search Console API or GTM event. With no stored rows it stays `Not supplied` and points to Integrations; after an import it shows the labelled rows and links back to the full ledger in Integrations.

Published case studies use the same panel in `public` mode: they read only the already-sanitised `supplied_data` from `/api/v1/public/case-studies/{id}`, force **Private data excluded** and never request `supplied-records`. A private export therefore cannot leak onto a public page even if one exists in the project.

---

## Recognised CSV columns

Column detection is case-insensitive and alias-based (`URL_COLUMN_ALIASES` and `_find_col` in `imports.py` / `import_jobs.py`). Delimiters `,`, `;`, tab and `|` are sniffed; UTF-8 BOM is handled.

### URL/metric imports (`import_file`)

| Canonical field | Example aliases |
| --- | --- |
| URL | `url`, `address`, `page`, `page url`, `landing page`, `landing page + query string`, `full url`, `final url`, `location`, `loc`, `canonical`, `source url`, `old url`, `new url` |
| Clicks | `clicks`, `organic clicks` |
| Impressions | `impressions`, `organic impressions` |
| Sessions | `sessions`, `users`, `pageviews` |
| Conversions | `conversions`, `key events`, `transactions` |
| Revenue | `revenue`, `item revenue`, `value` |
| Title | `title`, `page title`, `h1` |
| Referring domains | `referring domains`, `domains`, `backlinks` |

If no URL-like column is found in `csv_urls`, `cms`, `screaming_frog` or `sitebulb`, the job fails with `No URL-like column found. Columns: ...`. Query/domain/location-style exports declared as `gsc`, `rank_tracking`, `gbp`, etc. are accepted as verbatim supplied rows instead of being forced through URL enrichment.

**GSC-style example** (export → URL inventory):

```csv
Landing Page + Query String,Organic clicks,Organic impressions,Organic CTR,Position
https://demo.example.com/services/vapt-1/,42,1800,2.3%,18.4
```

**GA4-style example:**

```csv
Landing page,Session key event rate,Sessions,Total revenue
https://demo.example.com/services/vapt-1/,0.04,310,1250.00
```

`CTR` and `Position` columns are not mapped by the URL import job; they are useful in a keyword import or as extra context in a spreadsheet. The import records the exact mapping it used.

**Screaming Frog / Sitebulb-style example:**

```csv
Address,Title,Status Code,Internal inlinks,Response Time
https://demo.example.com/services/vapt-1/,VAPT services,200,7,312
```

Only aliased fields are stored; `Status Code` and response time from a third-party crawl CSV are not mapped into the interpreted `http_status`/`response_time_ms` fields by the generic mapper. Use a real crawl in **Crawler** if you need raw observations.

### Keyword imports (`import_keywords`)

`POST /api/v1/keywords/import` accepts `.csv`, `.tsv`, `.txt`, `.xlsx` by extension and maps:

| Canonical field | Example aliases |
| --- | --- |
| Keyword | `keyword`, `query`, `search query`, `term`, `search term`, `phrase` |
| Volume | `volume`, `search volume`, `monthly volume`, `avg monthly searches` |
| Difficulty | `difficulty`, `keyword difficulty`, `kd`, `competition difficulty` |
| CPC | `cpc`, `cost per click` |
| Intent | `intent`, `search intent` |
| Topic / parent topic | `topic`, `category`, `group` / `parent topic`, `parent`, `theme` |
| Country / language | `country`, `location`, `region` / `language`, `lang` |
| Confidence | `confidence`, `data confidence` |
| Competitor URL | `competitor url`, `url`, `page`, `sitemap url` |
| Collected at | `date collected`, `collected at`, `date` |

Values are carried through with their source name and `confidence`; the platform does not invent missing volumes. With `source_type=competitor_csv`, the competitor domain is attached to each row's `evidence`.

---

## Sitemaps and sitemap indexes

`parse_sitemap()` uses `xml.etree.ElementTree` and handles namespaced `<urlset>` documents:

- `<urlset>`: extracts `loc`, `lastmod`, `changefreq`, `priority`. `<loc>` values go into `UrlRecord` with `in_sitemap=true`; full entries are also stored in `SitemapEntry`.
- `<sitemapindex>`: extracts child `<loc>` values and adds them as URLs with source `sitemap_index`. The **file importer** does not fetch the referenced sitemap files.
- Sitemap import is file-based: point the upload at an exported sitemap, or use the demo dataset (which plants `synthetic-sitemap.xml` entries and deliberately omits URLs where `i % 7 == 3`).

**Live public-audit discovery is separate from file import.** `CrawlEngine._discover_sitemaps()` fetches `/robots.txt`, robots-declared `Sitemap:` URLs plus `/sitemap.xml` and `/sitemap_index.xml`, expands one index level into child sitemaps, stores every fetched document as a raw `CrawlObservation`, and records `Crawl.summary.sitemap` (`declared_sitemaps`, `sitemap_files`, `sitemap_urls`, `errors`). Same-host `<loc>` entries are upserted as `data_kind=public_sitemap`, `source=sitemap`, `in_sitemap=true` with provenance `sitemap-discovery`, so orphan analysis can distinguish sitemap-only URLs from discovered links. The robots document and explicit allow/disallow rules for 12 known AI/search agents are stored under `Crawl.summary.robots`; they are evidence of declared policy, **not** a guarantee of answer-engine inclusion.

Public-audit outputs never call GSC, GA4, rank tracking or LLM APIs. The audit response includes a `source_registry` (`robots.txt`, `sitemap files` and `crawl observations` = verified; `rule engine` = derived; `Search Console / GA4` = `not_supplied` only when no GSC/GA4 export was supplied) and a dynamic `missing_data` register for every private source that could upgrade the analysis later. Uploaded exports are registered as `user_supplied_export` / `user_declared` and listed in `supplied_data`.

---

## Provider registry

`GET /api/v1/integrations/providers` returns declared providers and modes:

| Provider | Declared modes |
| --- | --- |
| `google_search_console` | `csv_import`, `oauth_api` |
| `google_analytics_4` | `csv_import`, `oauth_api` |
| `google_sheets` | `csv_import`, `oauth_api` |
| `google_business_profile` | `csv_import`, `oauth_api` |
| `google_merchant_center` | `csv_import`, `oauth_api` |
| `screaming_frog` | `csv_import` |
| `sitebulb` | `csv_import` |
| `semrush` | `csv_import`, `api_key` |
| `ahrefs` | `csv_import`, `api_key` |
| `llm_provider` | `api_key` |

The note returned by the endpoint is explicit: *"CSV import works without credentials. API modes require configured credentials and permissions."* In this implementation, **only the CSV path has code behind it**; the other modes are metadata for a future connector layer.

`POST /api/v1/integrations` creates or upserts a connection (unique by provider + project + organisation), validates provider and mode, and sets a status:

- `csv_ready` — default for `csv_import` mode;
- `not_configured` — default for non-CSV modes or seeded demo records;
- `configured` — set when credentials are supplied.

`GET /api/v1/integrations` and `GET /api/v1/integrations/{id}` expose `id`, `provider`, `display_name`, `status`, `mode`, `config`, `last_sync_at`, `notes` — but never credentials.

---

## Credential handling

`backend/app/core/crypto.py` uses Fernet symmetric encryption:

```python
key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
credentials_encrypted = Fernet(key).encrypt(str(credentials).encode()).decode()
```

When `POST /api/v1/integrations` receives a `credentials` field, it stores `credentials_encrypted` and flips status to `configured`. The API response says: *"Credentials stored encrypted; values are not returned."* There is no endpoint that decrypts or displays them.

Operational notes:

- The encryption key is derived from `SECRET_KEY`. **Changing `SECRET_KEY` makes previously stored credentials unreadable**; they are not migrated.
- For a real deployment, prefer injecting secrets from a secret manager/environment rather than pasting them into a demo UI. The frontend action hint says exactly this.
- Encryption at rest is not the same as OAuth token management, rotation, scope validation or provider consent. None of those are implemented.

---

## Demo-mode connection records

`generate_demo()` seeds three illustrative rows, all with status `not_configured`:

| Provider | Mode | Note stored on the record |
| --- | --- | --- |
| `google_search_console` | `csv_import` | "Import GSC exports as CSV. Official API requires OAuth credentials." |
| `google_analytics_4` | `csv_import` | "Import GA4 exports as CSV. No credentials are stored in demo mode." |
| `screaming_frog` | `csv_import` | "Upload a crawling export to enrich the shared URL inventory." |

These rows are evidence of the intended integration surface, **not** proof of a connected account.

---

## What is not implemented

Be explicit about these in interviews:

1. **No live vendor API calls.** There is no OAuth handshake, token refresh, provider client, rate-limit handling, or GSC/GA4/Semrush/Ahrefs/GBP/Merchant request code.
2. **JSON and XLSX parsing is structural only.** `parse_table()` reads the first XLSX worksheet with `openpyxl` and accepts JSON arrays of objects or objects with `items`/`rows`/`data`; all values are converted to strings before header mapping. Nested JSON values are stringified, so provider-specific payload shapes still need a dedicated adapter. XLSX is also fully supported for **exports** via `openpyxl`.
3. **AnalyticsRecord rows are not created by file imports.** URL-level metrics from CSV land on `UrlRecord`, and verbatim private rows land on `SuppliedMetric`. The demo generator creates GSC/GA4-style `AnalyticsRecord` rows directly for reporting demonstrations.
4. **No JavaScript rendering** in the crawler (`javascript_rendering: false` in defaults).
5. **No automatic sitemap fetching**, no incremental recrawl scheduling beyond the workflow tick, and no deployment of redirects.
6. **No LLM provider call.** `llm_provider` is a registry entry only; AI-search observations are manual or synthetic, and readiness is rule-based. No answer-engine inclusion or traffic outcome is guaranteed.
7. **No inference of private metrics.** Volume, rank, traffic, backlink authority, Core Web Vitals and local visibility are never guessed from public HTML. They change from `Not supplied` only when labelled rows are actually stored.

See [ROADMAP.md](ROADMAP.md) for prioritised next steps and [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for the endpoint catalogue.
