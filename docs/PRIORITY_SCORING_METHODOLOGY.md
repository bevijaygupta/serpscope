# Priority Scoring Methodology

This document describes `backend/app/services/priority.py` and its call sites in `issues.py`, `orphans.py` and `keyword_jobs.py`. Priorities are **transparent rule-based formulas** with named components, weights, contributions and an explanation string. They are not black-box AI, not a trained model, and not a probability of business impact.

Related documents: [CRAWLER_METHODOLOGY.md](CRAWLER_METHODOLOGY.md), [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md), [KEYWORD_MAPPING_METHODOLOGY.md](KEYWORD_MAPPING_METHODOLOGY.md).

## 1. Core formula

Every component is on a `0..100` scale. Missing components default to `0` and are still reported, so evidence gaps remain visible.

```python
w = {**DEFAULT_WEIGHTS, **(weights or {})}
total_weight = sum(w.values()) or 1.0
used = {k: clamp(float(components.get(k, 0) or 0)) for k in w}
contributions = {k: used[k] * (w[k] / total_weight) for k in w}
score = round(sum(contributions.values()), 2)
```

```text
score = Σ component[k] × (weight[k] / Σ weights)
```

`clamp(value, low=0, high=100)` keeps component values in range. If custom weights do not sum to `1.0`, they are normalised; if their sum is zero, `total_weight` falls back to `1.0`.

Default weights:

| Component | Raw weight | Normalised weight (defaults sum to 1.0) |
| --- | ---: | ---: |
| `business_impact` | 0.25 | 0.25 |
| `organic_performance` | 0.18 | 0.18 |
| `revenue_impact` | 0.20 | 0.20 |
| `technical_severity` | 0.15 | 0.15 |
| `confidence` | 0.10 | 0.10 |
| `affected_urls` | 0.12 | 0.12 |

`log_scale(value, scale=1000)` is used for count/money-like inputs:

```python
0 if value <= 0
else clamp(100 * log10(1 + value) / log10(1 + scale))
```

At `value == scale` the result is about 100; larger values clamp at 100. Several components multiply a log-scaled value by `0.5`, `0.6` or `0.8` and take the `max()` of competing signals.

## 2. Bands and the Review rule

Thresholds are:

```python
THRESHOLDS = {"P0": 80, "P1": 60, "P2": 35, "P3": 0}
```

`priority_band(score, confidence)` first checks:

```python
if confidence in {"unverified", "insufficient", "estimated"} and score < 70:
    return "Review"
```

Then it returns the first band whose threshold is met, in order `P0 → P1 → P2 → P3`. Consequences:

- A low-confidence score of 69 becomes `"Review"`, not `P1`.
- The same score with confidence `"verified"`, `"imported"`, `"high"` or `"medium"` follows the normal thresholds: 69 → `P2`.
- `"Review"` is not one of the numeric thresholds; it is a separate guard.

`calculate_priority()` returns:

| Key | Content |
| --- | --- |
| `score` | Rounded weighted sum. |
| `priority` | Band from `priority_band()`. |
| `components` | Clamped component values actually used. |
| `weights` | Normalised weights rounded to 4 decimals. |
| `contributions` | Per-component contribution rounded to 2 decimals. |
| `formula` | Human-readable `"business_impact(85.0) x 0.25 + ..."` string. |
| `confidence` | The confidence string passed by the caller. |
| `explanation` | Score, formula, non-zero contributions, confidence, band and optional context. |

## 3. Issue components

`issue_components()` converts rule metadata and aggregated URL evidence into components:

| Component | Exact calculation |
| --- | --- |
| `business_impact` | `impact_map`: `critical=100`, `high=80`, `medium=50`, `low=20`, `unknown=10`; default `10`. |
| `organic_performance` | `clamp(max(log_scale(clicks, 2000), log_scale(impressions, 50000) * 0.6))` |
| `revenue_impact` | `clamp(max(log_scale(revenue, 100000), log_scale(conversions, 500) * 0.8))` |
| `technical_severity` | `severity_map`: `critical=100`, `high=80`, `medium=50`, `low=20`, `info=5`; default `50`. |
| `confidence` | `confidence_map`: `verified=100`, `imported=75`, `estimated=50`, `unverified=25`; default `25`. |
| `affected_urls` | `log_scale(affected_count, 10000)` |

### Where issue evidence comes from

`issues.detect_issues()` scans `UrlRecord` rows in batches of 2000 (up to `max_records = 200000`) and groups findings by rule code. Relevant detection thresholds include:

| Evidence | Rule / condition |
| --- | --- |
| `http_status == 404` | `http_404`; replacement candidates are rule-based token-overlap matches (Jaccard `> 0.12`, top 3) from live 2xx pages. |
| 400–499 / ≥500 | `http_4xx` / `http_5xx`. |
| `len(redirect_chain) > 1` | `redirect_chain`; a repeated normalised chain of length > 2 adds `redirect_loop`. |
| Canonical differs from URL | `canonical_mismatch`; canonical equal to redirect target adds `canonical_chain`; sitemap/hreflang/200 adds `canonical_conflict`. |
| Sitemap + noindex | `noindex_in_sitemap`. Robots-blocked requires `robots_allowed is False` plus clicks/impressions/sitemap. |
| Crawled + missing title/description/H1 | `missing_title`, `missing_description`, `missing_h1`. |
| Lowercased duplicate title/description | `duplicate_title`, `duplicate_description`; duplicates are counted across the inventory but only reported for crawled records. |
| `word_count < 100`, crawled, page type not `homepage`/`category` | `thin_content`. |
| `response_time_ms > 2500`; `content_size > 2_000_000` | `slow_response`, `oversized_page`. (The crawler's own `slow_pages` stat uses `> 2000`.) |
| Product/service/article without schema; `invalid-json-ld` | `missing_schema`, `invalid_schema`. |
| Hreflang without `x-default`/`en`, invalid targets or no self-reference | `hreflang_error`. |
| Category/product with pagination object but no next/prev | `pagination_problem`. |
| ≥2 query parameters, crawled, status 200 | `parameter_duplication`. |
| Status 200, `word_count < 60`, zero clicks, in sitemap | `soft_404` (indicators only; manual confirmation required). |
| `LinkEdge.is_broken` | Grouped as `broken_internal_link` with up to 20 linking sources in evidence. |
| `OrphanRecord.classification` in `Confirmed crawl orphan` / `Sitemap-only orphan` | `orphan_page` (up to 50000 rows from the orphan engine). |

For each grouped rule, the issue-level `confidence` string passed to `calculate_priority()` is `"verified"` when `code.startswith("http_")`, otherwise `"imported"`. The `business_impact` argument is `"critical"` when any affected URL has `revenue > 1000` or `clicks > 500`, `"high"` when any has `clicks > 50`, otherwise `"unknown"`. Metric inputs are **summed** over grouped URLs; `affected_count = len(urls)`.

Stored fields: `Issue.priority`, `Issue.priority_score`, `Issue.priority_explanation`, `Issue.business_impact`, `Issue.affected_count`, `Issue.page_templates`, and `Issue.evidence` with `sample_urls`, `detection_rule`, `data_kind = "derived_from_observations"` and suggested replacements. `IssueUrl` rows keep per-URL evidence, including the upstream `data_kind` (`live_crawl`, `imported`, `synthetic`, etc.). `Issue.source = "rule-engine"`.

A rule detection disappearing on a later run marks only previously `Detected` rule-engine issues as `Resolved` with `validation_status = "pending"`. Manual edits and non-rule-engine issues are preserved.

### High-value 404 workflow

`high_value_404s()` scores each URL with `http_status = 404` (limited to 5000 rows, ordered by revenue then clicks) using:

- `affected_count = 1`, `severity = "high"`;
- `confidence` component `100` (`"verified"`) when clicks/revenue/sessions exist, otherwise `25` (`"unverified"`);
- `business_impact = "critical"` when `revenue > 1000` or `conversions > 10`, `"high"` when `clicks > 50`, otherwise `"unknown"`;
- a second, string confidence passed to the scorer via the expression `components["confidence"] >= 50 and "verified" or "unverified"`.

Replacement suggestions come from `choose_replacements()` token overlap, not from a model. The API exposes this at `GET /api/v1/technical/high-value-404s`.

## 4. Orphan components

`orphan_components()` uses a different set of derivations:

| Component | Exact calculation |
| --- | --- |
| `business_impact` | `clamp(max(type_boost, importance * 100))`; `type_boost`: homepage 90, service 85, product 85, category 70, article 45, default 30. |
| `organic_performance` | `clamp(max(log_scale(clicks, 1000), log_scale(impressions, 20000) * 0.6, log_scale(sessions, 2000) * 0.5))` |
| `revenue_impact` | `clamp(max(log_scale(revenue, 50000), log_scale(conversions, 200) * 0.8))` |
| `technical_severity` | `clamp(100 - min(inlinks, 20) * 5)` when `inlinks == 0`, else `20`. The orphan engine only scores zero-inlink URLs, so this is effectively always `100`. |
| `confidence` | `70` if `indexable is True`, `40` if `indexable is None`, `20` otherwise. This is indexability-derived, **not** the `OrphanRecord.confidence` classification string. |
| `affected_urls` | `clamp(log_scale(referring_domains, 500) * 0.8 + (20 if inlinks == 0 else 0))` |

`detect_orphans()` passes its `weights` config override and a confidence string of `high`, `medium` or `unverified` from the classification evidence. `OrphanRecord` stores `priority`, `priority_score` and `score_components`; it does not store the explanation, normalised weights or contributions.

### Illustrative calculation (not real data)

For a zero-inlink service page with `importance = 0.85`, `clicks = 100`, `impressions = 1000`, `sessions = 50`, no revenue/conversions, `referring_domains = 2`, `indexable = True` and classification confidence `"medium"`:

```text
business_impact      = max(85, 85) = 85
organic_performance  ≈ max(66.8, 41.9, 25.9) ≈ 66.8
revenue_impact       = 0
technical_severity   = 100
confidence           = 70
affected_urls        ≈ 17.7 * 0.8 + 20 ≈ 34.1

score ≈ 85*0.25 + 66.8*0.18 + 0*0.20 + 100*0.15 + 70*0.10 + 34.1*0.12
      ≈ 59.4 → P2
```

`"medium"` is not in the Review guard set, so the band is `P2`. These are invented numbers used only to demonstrate the arithmetic.

## 5. Call sites and job behaviour

| Caller | Weights | Confidence string | Context |
| --- | --- | --- | --- |
| `issues.detect_issues()` | default (no override) | `"verified"` for `http_*`, else `"imported"` | `"<n> URLs affected; code=<code>"` |
| `issues.high_value_404s()` | default | verified/unverified via numeric component check | none |
| `orphans.detect_orphans()` | `config["weights"]` | `high` / `medium` / `unverified` from evidence | `"Sources=...; classification=..."` |

Jobs:

- `POST /api/v1/technical/detect` enqueues `detect_issues`; `POST /api/v1/orphans/detect` enqueues `detect_orphans` with config.
- A `refresh_priorities` job re-runs `detect_orphans` with its config, then `detect_issues`.
- These handlers report progress (typically 10/25/65/100) but do not call `is_cancelled()` inside the scoring loops. A cancellation changes the final job status; it does not interrupt a running handler.
- `GET /api/v1/technical/issues` and `GET /api/v1/orphans` sort by `priority_score` descending and accept a `priority` filter.

## 6. Provenance of scored values

| Layer | Status |
| --- | --- |
| Component inputs (`clicks`, `revenue`, `http_status`, `inlinks`, etc.) | **Derived** or copied from `UrlRecord`, `LinkEdge`, `SitemapEntry` and `OrphanRecord`. The upstream rows may be **live crawl**, **simulated**, **imported** or **synthetic demo** data. |
| `business_impact`, confidence and severity inputs | Rule metadata plus threshold checks on those upstream values. |
| Score, weights, contributions, band | **Derived** by `calculate_priority()`. |
| Model-generated score | None. No LLM, embedding, vendor score or trained model is used by these modules. |

## 7. Limitations present in the code

- `business_impact` and `confidence` are coarse string maps; they are not calibrated against outcomes.
- `log_scale()` saturates at its chosen scale, so very large counts/revenue values stop increasing a component.
- Issue scores aggregate all affected URLs, so one extreme URL can influence the whole group through summed metrics and the `business_impact` threshold checks.
- Orphan `technical_severity` is effectively a constant `100`, because only zero-inlink URLs are scored.
- The classifier's confidence string (`high`/`medium`/`unverified`) and the score's `confidence` component (from `indexable`) are separate signals; `medium` does not trigger the Review guard.
- `OrphanRecord` does not persist the full explanation, while `Issue` does.
- The declared rules `excessive_depth` and `broken_external_link` exist in `RULES` but no detection code populates those groups in `detect_issues()`.
- `robots_blocked` is normally triggered by imported or synthetic records with `robots_allowed=False`. A live crawl that is disallowed by robots is excluded before storage, so it does not create a crawled record with `robots_allowed=False`; only fetched URLs are stored with the actual permission result.
- Synthetic demo metrics are simulated; scores computed from them demonstrate formulas, not real-world priority.

## What this does not prove

A `P0`/`P1` label does not prove that an issue causes real traffic or revenue loss, that a fix will succeed, that the underlying imported numbers are accurate, or that a lower-priority item is safe to ignore. It proves only that the documented components, weights, thresholds and confidence guard produced that label from the available evidence. The score is an explainable triage rule, not a prediction or a model-generated judgement.

## Related documents

- [CRAWLER_METHODOLOGY.md](CRAWLER_METHODOLOGY.md) — origin of crawl observations and `UrlRecord` evidence.
- [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md) — how zero-inlink URLs are classified before scoring.
- [KEYWORD_MAPPING_METHODOLOGY.md](KEYWORD_MAPPING_METHODOLOGY.md) — a separate deterministic scoring formula for keyword-to-URL mapping.
