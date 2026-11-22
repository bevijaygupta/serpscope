# Orphan Detection Methodology

This document describes `backend/app/services/orphans.py`, the related `refresh_link_counts()` step, the `OrphanRecord` model, the `/api/v1/orphans/*` router and the `detect_orphans` job handler. The implementation is rule-based: an orphan is a URL in the reconciled source union with **zero discovered internal inlinks**.

Related documents: [CRAWLER_METHODOLOGY.md](CRAWLER_METHODOLOGY.md), [KEYWORD_MAPPING_METHODOLOGY.md](KEYWORD_MAPPING_METHODOLOGY.md), [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md).

## 1. Inputs and provenance

| Input | Table / field | May originate from |
| --- | --- | --- |
| URL inventory | `UrlRecord` (limited by `max_records`) | **Live crawl** (`data_kind = "live_crawl"`), **simulated crawl label** (`"simulated"`), **imported** CSV/sitemap/GSC/GA4/CMS-style data (`"imported"`), or **synthetic demo** data (`"synthetic"`). |
| Sitemap URLs | `SitemapEntry.loc` plus `UrlRecord.in_sitemap` | Imported sitemap XML, imported rows marked in sitemap, or synthetic demo sitemap entries. |
| Internal links | `LinkEdge` where `link_type == "internal"` | Crawler-observed anchors, imported crawl exports, or synthetic demo edges. |
| Business/performance evidence | `clicks`, `impressions`, `sessions`, `conversions`, `revenue`, `referring_domains`, `importance` on `UrlRecord` | Imported analytics/backlink data, user edits via `PATCH /api/v1/inventory/urls/{id}`, or synthetic demo values. The orphan engine does not fetch these itself. |
| Crawl status/indexability | `http_status`, `indexable`, `robots_allowed`, `redirect_chain`, `redirected_to`, `canonical`, `meta_robots`, `x_robots_tag` | Live/simulated crawl observations, imports, or synthetic demo records. |
| Configuration | `excluded_patterns`, `authoritative_sources`, `weights`, `max_records` | Job payload from `POST /api/v1/orphans/detect`. |

`OrphanRecord` has **no `data_kind` column**. Trust is expressed through `sources`, `crawled`, `in_sitemap`, `confidence` and the upstream `UrlRecord.data_kind`. No model-generated data is consumed by this engine; all classifications and scores are derived rules.

## 2. Configuration

```python
cfg = {
    "excluded_patterns": [],
    "authoritative_sources": ["sitemap", "crawler", "cms"],
    "weights": {},
    "max_records": 200000,
}
cfg.update(config or {})
```

| Key | Default | Use |
| --- | --- | --- |
| `excluded_patterns` | `[]` | Regex list applied with `re.search` to the raw item URL; any match forces `"Excluded or intentionally isolated URL"`. |
| `authoritative_sources` | `["sitemap", "crawler", "cms"]` | Strings compared against the merged `sources` list. `"sitemap"` is additionally satisfied by `in_sitemap = True`. |
| `weights` | `{}` | Passed to `calculate_priority()` as component weight overrides. |
| `max_records` | `200000` | Limit applied to the `UrlRecord` SELECT only; sitemap entries are not limited by it. |

Note: the crawler writes source labels of the form `crawl:<crawl_id>`, not the literal token `"crawler"`. Therefore the default `"crawler"` entry does not match crawl-derived sources unless the caller adds the actual label; crawl evidence still affects the result through `crawled`, status, and the zero-inlink test.

## 3. Step 1 — refresh link counts

`refresh_link_counts(db, project_id)` runs first:

1. Normalises every project `LinkEdge.source_url` and `target_url` with `normalize_url()` (default rules).
2. For `link_type == "internal"`: increments `inlinks[target]` and `outlinks_internal[source]`.
3. For external links: increments `outlinks_external[source]`.
4. Increments `broken[target]` for edges where `is_broken` is already true.
5. Writes `UrlRecord.internal_inlinks`, `internal_outlinks` and `external_links` for all project records, using `0` when no edge matched.
6. Builds a map of normalised URL → `http_status` and sets `edge.is_broken = True` where the target has a known status `>= 400`.
7. Commits and returns `{"records_updated", "internal_inlinks", "broken_targets"}`.

Limitations in this step: it never sets `is_broken` back to `False`; it does not update the legacy `UrlRecord.is_orphan` boolean; and the `broken[target]` count is returned in the summary but not written to any record field.

## 4. Step 2 — reconcile URLs

`detect_orphans()` builds a dictionary keyed by `normalize_url(rec.url)`:

- For each `UrlRecord`, `sources` are unioned; numeric metrics use `max(existing, record_value)` for `clicks`, `impressions`, `sessions`, `conversions`, `revenue`, `referring_domains` and `importance`.
- `crawled` is an OR over records.
- `indexable`, `status` and `robots_allowed` take the last non-`None` value encountered.
- `in_sitemap` is true if any record has it or the normalised URL appears in `SitemapEntry` / `UrlRecord.in_sitemap`.
- `redirected` is true when `redirected_to` is set or `redirect_chain` has more than one entry.
- `canonicalised` is true when `canonical` is set and `normalize_url(canonical) != key`.
- Sitemap URLs with no `UrlRecord` are added with default values (`crawled = False`, `indexable = None`, `page_type = "unknown"`, `sources = ["sitemap"]`).

Internal inlinks are then counted per normalised target from all internal `LinkEdge` rows. The engine **skips a URL entirely when `inlinks > 0`**. Consequently the reported `orphan_urls` are strictly zero-inlink URLs, even if the source union is incomplete.

Existing `OrphanRecord` rows for the project are deleted and rebuilt on every run; this is a full refresh, not an incremental update.

## 5. Classification rules

Rules are evaluated in this exact order. The first match wins.

| Order | Condition | `classification` |
| --- | --- | --- |
| 1 | URL matches any `excluded_patterns`, or `status in (404, 410, 403)` | `Excluded or intentionally isolated URL` |
| 2 | `redirected` | `Redirected orphan` |
| 3 | `canonicalised` | `Canonicalised orphan` |
| 4 | `referring_domains > 0` | `Backlink-supported orphan` |
| 5 | `clicks > 0` or `impressions > 0` | `Search-visible orphan` |
| 6 | `sessions > 0` | `Analytics-active orphan` |
| 7 | `in_sitemap` and not `crawled` | `Sitemap-only orphan` |
| 8 | `crawled` and `has_authoritative` | `Confirmed crawl orphan` |
| 9 | `has_performance` (`clicks` or `impressions` or `sessions`) and not `crawled` | `Potential orphan` |
| 10 | `crawled` | `Confirmed crawl orphan` if `has_authoritative`, otherwise `Unverified URL` |
| 11 | otherwise | `Unverified URL` |

`has_authoritative` means at least one configured `authoritative_sources` string is present in `sources`, with the special `sitemap` case described above. Because of ordering, a 403 is treated as intentionally isolated rather than as an error orphan. A URL with 404/410/403 is never scored as a confirmed orphan.

Each classification carries a fixed `likely_cause` and `recommended_action` string in `OrphanRecord`, for example:

| Classification | Likely cause | Recommended action |
| --- | --- | --- |
| `Confirmed crawl orphan` | No internal link discovered despite authoritative source and crawl | Add contextual internal links from relevant authoritative pages |
| `Potential orphan` | Appears in performance/CMS data but was not discovered by the crawl | Verify accessibility and crawl configuration before linking |
| `Sitemap-only orphan` | In sitemap but not linked and not crawled | Check indexability and add internal links or remove obsolete sitemap entry |
| `Search-visible orphan` | Has organic visibility but no discovered internal links | Prioritise internal links from pages ranking for related topics |
| `Backlink-supported orphan` | External links exist but internal discovery path is missing | Add internal links and update canonical/sitemap if needed |
| `Redirected orphan` / `Canonicalised orphan` | Stale source lists or canonical target to confirm | Update source lists / confirm canonical target and clean source lists |
| `Excluded or intentionally isolated URL` | Excluded by config or deliberately non-indexable | No action unless business intent changed |
| `Unverified URL` | Insufficient evidence | Manual verification required |

## 6. Confidence

```python
confidence = (
    "high" if crawled and in_sitemap
    else "medium" if crawled or in_sitemap
    else "unverified"
)
if classification in {"Excluded or intentionally isolated URL", "Unverified URL"}:
    confidence = "unverified"
```

This string is stored in `OrphanRecord.confidence` and passed to `calculate_priority()`. It is distinct from the `confidence` **component** in the score, which is derived from `indexable` (see below).

## 7. Scoring

`orphan_components()` produces six 0–100 components using `log_scale(value, scale) = 0 if value <= 0 else clamp(100 * log10(1 + value) / log10(1 + scale))`:

| Component | Exact formula |
| --- | --- |
| `business_impact` | `clamp(max(type_boost, importance * 100))`, with `type_boost`: homepage 90, service 85, product 85, category 70, article 45, anything else 30. |
| `organic_performance` | `clamp(max(log_scale(clicks, 1000), log_scale(impressions, 20000) * 0.6, log_scale(sessions, 2000) * 0.5))` |
| `revenue_impact` | `clamp(max(log_scale(revenue, 50000), log_scale(conversions, 200) * 0.8))` |
| `technical_severity` | `clamp(100 - min(inlinks, 20) * 5)` if `inlinks == 0`, else `20`. Since only zero-inlink URLs reach scoring, this is effectively always `100`. |
| `confidence` | `70` if `indexable is True`, `40` if `indexable is None`, `20` otherwise. |
| `affected_urls` | `clamp(log_scale(referring_domains, 500) * 0.8 + (20 if inlinks == 0 else 0))` |

These components are passed to `calculate_priority()` with the job's `weights` override and context:

```text
Sources=<comma-joined sources or 'none'>; classification=<classification>
```

The returned `priority`, `priority_score` and `score_components` are stored on `OrphanRecord`. The full explanation, normalised weights and per-component contributions are computed by the shared scorer but are **not persisted** on `OrphanRecord`. See [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md) for the weighted-sum formula and bands.

Important interaction: `priority_band()` downgrades to `"Review"` only when the confidence string is `unverified`, `insufficient` or `estimated` **and** the score is below 70. The strings `"medium"` and `"high"` are not in that set, so a medium-confidence orphan can still receive `P0`/`P1`/`P2` normally.

## 8. Result and API

`detect_orphans()` returns:

```python
{
    "detected_at": now,
    "total_urls_considered": len(all_urls),
    "orphan_urls": created,
    "by_classification": dict(counts),
    "method": "union_of_sources_minus_discovered_internal_inlinks",
}
```

| Endpoint | Behaviour |
| --- | --- |
| `POST /api/v1/orphans/detect` | 202 + `job_id`; config is passed to the `detect_orphans` job unchanged. |
| `GET /api/v1/orphans` | Filters by `classification`, `priority` and URL substring `q`; ordered by `priority_score` descending. |
| `GET /api/v1/orphans/summary` | Counts, summed revenue and summed clicks grouped by classification. |
| `GET /api/v1/orphans/export` | Exports the listed `OrphanRecord` columns (up to 200000 rows). |

The handler in `analysis_jobs.py` sets progress 10 → 100 but does not call `is_cancelled()` inside the analysis. A cancellation requested while the handler is running is reflected in the final job status, not by an early stop in the orphan loop.

## 9. Limitations present in the code

- `max_records` limits `UrlRecord` rows but not `SitemapEntry` rows, so the union can exceed the nominal cap.
- Source matching is literal: `"crawler"` is not the label written by the crawler (`crawl:<id>`), and synthetic demo sources (`synthetic_sitemap`) only satisfy authority through `in_sitemap`.
- An orphan is defined by **discovered** internal links. Missed links, blocked pages or JS-only links can create false orphans.
- `refresh_link_counts()` does not clear stale `is_broken` flags and does not maintain `UrlRecord.is_orphan`.
- Redirected, canonicalised, excluded and error URLs are still emitted as `OrphanRecord` rows, but with their own classifications; they are not all confirmed link-less pages.
- The classification confidence string and the score's `confidence` component measure different things.
- Numeric evidence is `max()`-merged across records; conflicting imports are not reconciled or averaged.
- No model-generated or provider-verified signals are used; synthetic demo metrics are simulated for rule testing only.

## What this does not prove

An `OrphanRecord` does not prove that a page is truly unreachable, that users cannot navigate to it, that search engines ignore it, that adding a link will change rankings or revenue, or that the page should be kept. It proves only that, given the supplied URL/link evidence and the configured rules, zero internal inlinks were observed and a specific transparent classification and score were produced. Confidence labels describe evidence presence, not certainty of business impact.

## Related documents

- [CRAWLER_METHODOLOGY.md](CRAWLER_METHODOLOGY.md) — where `UrlRecord` fields, `LinkEdge` rows and raw observations come from.
- [KEYWORD_MAPPING_METHODOLOGY.md](KEYWORD_MAPPING_METHODOLOGY.md) — how keywords are mapped to these URLs.
- [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md) — the shared weighted formula, thresholds and band rules.
