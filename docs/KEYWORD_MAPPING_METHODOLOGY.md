# Keyword Mapping Methodology

This document describes `backend/app/services/keywords.py`, `backend/app/services/keyword_jobs.py`, the keyword models and the `/api/v1/keywords/*` router. The pipeline is deterministic and rule-based: it normalises supplied keywords, groups them with explicit similarity rules, then assigns at most one primary cluster/keyword per URL using a transparent weighted score.

Related documents: [CRAWLER_METHODOLOGY.md](CRAWLER_METHODOLOGY.md), [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md), [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md).

## 1. Where keyword data comes from

| Route | `Keyword.source` / `confidence` | Provenance |
| --- | --- | --- |
| `POST /api/v1/keywords/import` (CSV, TSV, TXT, XLSX, JSON) | `source = source_type` (e.g. `keyword_csv`, `competitor_csv`); `confidence` from a mapped column, default `"imported"`. | **Imported** file supplied by the user. Column aliases are matched for keyword, volume, difficulty, CPC, intent, topic, parent topic, country, language, confidence, competitor URL and collected date. No provider API is called. |
| `POST /api/v1/keywords/inline` | `source` defaults to `"manual"`; `confidence` defaults to `"imported"`; up to 10000 items. | **Manual/imported** user input. |
| `generate_demo()` in `demo.py` | `source = "synthetic_demo"`, `confidence = "synthetic"`, `evidence.data_kind = "synthetic"`. | **Synthetic / simulated** metrics for rule testing. Volume, difficulty, CPC and competition are generated from indices, not measured. |
| Clustering / mapping | Writes `KeywordCluster`, `KeywordMapping`. | **Derived** from the rows above plus `UrlRecord` title/H1/path. |
| Model-generated data | None. The `"semantic"` method is a character n-gram cosine rule; no embedding or LLM provider is invoked. | — |

`volume`, `difficulty`, `cpc`, `competition`, `serp_features` and `evidence` are **supplied fields**. These services do not refresh them from third-party APIs. The bulk workflow note states that fresh third-party research requires provider credentials.

## 2. Normalisation, tokens and intent

`normalize_keyword(value)`:

```python
text = (value or "").lower().strip()
text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
return re.sub(r"\s+", " ", text).strip()
```

Hyphens are preserved inside tokens; punctuation is replaced with spaces.

`keyword_tokens(value)` keeps tokens with `len(t) > 2` that are not in `STOPWORDS`:

```text
a an and are for how in is of on or the to what which why with best near me my your you do does can
```

`classify_intent(keyword, brand_terms=())` returns `(intent, reason)`:

1. If any configured brand term is a substring of the normalised keyword:
   - `login|official|website|careers` → `navigational`, reason `"brand term plus navigational modifier"`;
   - otherwise → `branded`, reason `"contains configured brand term"`.
2. Otherwise the following regex patterns are checked **in this order**:

| Order | Intent | Modifiers |
| --- | --- | --- |
| 1 | `local` | near me, nearby, `in <words>`, location, opening hours, address, directions |
| 2 | `transactional` | buy, price, pricing, quote, book, order, hire, purchase, discount, deal, sign up, free trial |
| 3 | `commercial investigation` | best, top, vs, versus, review, comparison, compare, alternative(s), software, tool, services/service |
| 4 | `navigational` | login, log in, dashboard, website, official, support, contact, careers |
| 5 | `informational` | what, how, why, guide, tutorial, ideas, tips, examples, definition, meaning, learn, checklist |

3. If more than one pattern matches → `mixed`, with the matched intents listed in the reason.
4. If exactly one matches → that intent.
5. If none match → `informational` with reason `"default: no commercial or local modifier detected"`.

`ensure_intents()` writes `Keyword.intent` and `intent_source` for every project keyword. A non-empty `intent_override` wins and sets `intent_source = "manual"`; otherwise the rule result is stored with `intent_source = "rule"` and `evidence.intent_reason`.

## 3. Clustering

`POST /api/v1/keywords/cluster` enqueues `cluster_keywords`. The job handler takes `method` from `config` (default `"normalized"`) and passes the remaining config to the service.

Defaults:

```python
cfg = {"threshold": 0.45, "brand_terms": [], "max_keywords": 100000}
```

Keywords are selected with `ORDER BY Keyword.id LIMIT max_keywords`. If there are no keywords, the result includes `"note": "No keywords imported"`.

| `method` | Grouping / union rule | Threshold |
| --- | --- | --- |
| `exact` | Exact `keyword.strip().lower()` string grouping. | none |
| `normalized` (default) | `normalize_keyword()` phrase grouping. | none |
| `intent` | Group by `classify_intent(keyword, brand_terms)[0]`. | none |
| `token` | Pairwise Jaccard similarity of `keyword_tokens()` sets: `|A ∩ B| / |A ∪ B|`. | `threshold`, default `0.45` |
| `semantic` | Pairwise cosine similarity of character 3-grams of `normalize_keyword()` with spaces removed: `dot / (||a|| * ||b||)`. | `semantic_threshold`, default `0.55` |
| `serp_overlap` | Jaccard of normalised URLs from `evidence["serp_urls"]` or `evidence["serp_results"]`; pairs with either set empty are skipped. | `serp_threshold`, default `0.3` |

An unsupported method raises `ValueError` and the job is marked failed. All methods use `UnionFind`, so similarity is transitive: if A–B and B–C pass, all three land in one cluster even if A–C would not.

For each resulting cluster:

- members are sorted by `-(volume or 0)`, then keyword;
- `primary_keyword` is the first member (highest **supplied** volume);
- the label is the three most frequent member tokens, or the primary keyword when no tokens remain;
- `name` is `"<Title-cased label> (<member count>)"`;
- `parent_topic` comes from the first member;
- `intent` is the majority intent class computed inside clustering (not the manually edited `Keyword.intent`);
- `reasoning` records the method, member count, total supplied volume, dominant intent and de-duplicated evidence reasons, truncated to 500 characters;
- `Keyword.cluster_id` and `Keyword.cluster_method` are updated for every member.

Previous `KeywordCluster` rows for the project are deleted before rebuild. The returned summary includes `clusters_sample` (first 20) and `thresholds` (all config keys containing `"threshold"`). `PATCH /api/v1/keywords/clusters/{id}` allows manual edits to `name`, `parent_topic`, `intent`, `review_status`, `primary_keyword`, `reasoning` and `split_keywords`, but a later clustering run deletes and recreates clusters, discarding those edits.

## 4. Mapping clusters to URLs

`POST /api/v1/keywords/map` enqueues `map_keywords`. Defaults: `{"max_urls": 100000, "brand_terms": []}`. If no clusters exist, the job returns `{"mapped": 0, "error": "No clusters available; run clustering first"}`.

For each `UrlRecord` (ordered by `id`, limited by `max_urls`):

```python
page_text = f"{title or ''} {' '.join(h1 or [])} {path.replace('-', ' ').replace('_', ' ')}"
page_tokens = keyword_tokens(page_text)
page_intent = classify_intent(page_text or url, brand_terms)
```

For each cluster, the code uses the union of `keyword_tokens()` over `KeywordCluster.keywords[].keyword`, and computes:

| Term | Formula |
| --- | --- |
| `overlap` | `jaccard(page_tokens, cluster_tokens)`, or `0.0` if `page_tokens` is empty. |
| `coverage` | `len(page_tokens ∩ cluster_tokens) / max(1, len(cluster_tokens))`. |
| `intent_match` | `1.0` if cluster intent equals page intent; `0.4` if either is `"mixed"`; otherwise `0.0`. |
| `volume_score` | `min(1.0, log10(1 + volume) / 4)`, where `volume = sum(int(k["volume"] or 0))` over cluster members. |
| `uniqueness` | `0.25` if the cluster's primary keyword has not been claimed yet, else `0.0`. |

```python
score = 0.35 * overlap + 0.25 * coverage + 0.20 * intent_match \
        + 0.10 * volume_score + uniqueness
```

The best-scoring cluster is assigned only when `score >= 0.18`; otherwise the URL is listed in `unmapped_urls` (sample limited to 20). Because `uniqueness` can add `0.25`, the raw score can exceed `1.0`; stored `confidence` is `round(min(0.99, score), 3)`.

The winning primary keyword is added to `used_primary` (lowercased). The mapping is then written with:

| Field | Value |
| --- | --- |
| `primary_keyword` | `cluster.primary_keyword` |
| `secondary_keywords` | `cluster.keywords[1:6]` |
| `supporting_keywords` | `cluster.keywords[6:16]` |
| `intent`, `cluster_name`, `page_type` | From the cluster and URL record. |
| `funnel_stage` | `informational → awareness`, `commercial investigation → consideration`, `transactional → conversion`, `local → conversion`; anything else (e.g. `branded`, `mixed`) → `consideration`. |
| `target_location` | Literal `"Singapore"` when the lowercased URL ends with `/sg/` or contains `.sg`; otherwise `""`. |
| `confidence` | The clipped rule score above, **not** a statistical probability. |
| `reasoning` | `"token overlap/coverage <coverage>, intent match <intent_match>, cluster method=<method>, page type=<page_type>"`. |
| `recommended_changes` | `"Add a title including the primary keyword"` if no title; `"Add an H1 aligned to the primary intent"` if no H1; `"Align content with detected intent (<cluster.intent>)"` if `intent_match < 1`. |
| `cannibalisation_risk` | `"conflict"` if the primary was already used in this run; `"watch"` if `coverage < 0.15`; otherwise `"none"`. |
| `source`, `status` | `"rule-based"`, `"suggested"`. |

Previous `KeywordMapping` rows for the project are deleted before a mapping run. The engine assigns one primary cluster per URL; it does not rewrite page content.

## 5. Cannibalisation report

After mappings are stored, `map_clusters_to_urls()` runs a SQL aggregation:

```sql
SELECT primary_keyword, COUNT(*) c, GROUP_CONCAT(url) urls
FROM keyword_mappings
WHERE project_id = :p
GROUP BY lower(primary_keyword)
HAVING c > 1
ORDER BY c DESC
LIMIT 5000
```

Each row is returned with `risk = "high"` and recommendation `"Consolidate pages or differentiate intent and primary keyword"`. `GET /api/v1/keywords/cannibalisation` exposes the same duplicate-primary check (also capped at 5000 rows). `GET /api/v1/keywords/mappings` can filter by `q` or `cannibalisation_risk`.

## 6. Jobs and API

| Endpoint / job | Behaviour |
| --- | --- |
| `POST /api/v1/keywords/import` | 202 + `job_id`; stores the upload and enqueues `import_keywords`. |
| `POST /api/v1/keywords/inline` | 201; synchronous insert of up to 10000 keyword objects/strings. |
| `POST /api/v1/keywords/cluster` | 202; advertises methods `exact`, `normalized`, `token`, `semantic`, `intent`, `serp_overlap`. |
| `POST /api/v1/keywords/map` | 202; enqueues `map_keywords`. |
| `POST /api/v1/keywords/bulk-workflow` | 202; `ensure_intents` → `cluster_keywords` → `map_keywords` → cannibalisation summary. Progress values are 10, 35, 70, 95, 100. Note: "Automated processing of imported data only; fresh third-party keyword research requires provider credentials." |
| `GET /api/v1/keywords` / `/summary` / `/clusters` / `/mappings` / `/export` | Read/export imported keywords, derived clusters and derived mappings. |

Keyword job handlers update job progress but do not call `is_cancelled()` inside clustering or mapping. A cancel request changes the final job status; it does not stop the currently running loop. See [CRAWLER_METHODOLOGY.md](CRAWLER_METHODOLOGY.md) for the shared job lifecycle.

## 7. Limitations present in the code

- Page text for mapping is only `title + H1 + path`; page body content is not used.
- Greedy assignment is ordered by `UrlRecord.id`, so an early URL can claim a primary keyword that a later, better-matching URL would have used.
- `semantic` clustering uses character 3-grams, not embeddings or SERP semantics, despite the method name.
- `serp_overlap` needs `serp_urls` / `serp_results` already present in `Keyword.evidence`; the standard keyword importer does not collect SERP data.
- The default `threshold = 0.45` applies to the `token` method; `semantic` uses `semantic_threshold = 0.55` and `serp_overlap` uses `serp_threshold = 0.3`. The returned `thresholds` map also includes unused default keys.
- Intent is pattern/brand-term based; `best` and `near` are stopwords for tokenisation, and multiple intent modifiers collapse to `mixed`.
- `target_location = "Singapore"` is a hardcoded URL rule, not a geo validation step.
- `confidence` is a clipped rule score; it is not calibrated, not an accuracy estimate, and not model-generated.
- Manual cluster edits are overwritten by the next clustering run; manual `KeywordMapping` edits are overwritten by the next mapping run.
- The cannibalisation query uses `GROUP_CONCAT`, which is SQLite-flavoured SQL.
- Synthetic demo keywords are deterministic fake data; their volumes and CPC values must not be presented as research findings.

## What this does not prove

Clustering does not prove that keywords share a search intent in the real SERP, that the supplied volume/difficulty/CPC values are accurate, that a mapped URL currently ranks for the primary keyword, that one URL per cluster is always correct, or that following `recommended_changes` will improve traffic. It proves only that the supplied keywords and URL fields satisfied the documented deterministic rules and thresholds. No model-generated or live provider evidence is part of these outputs.

## Related documents

- [CRAWLER_METHODOLOGY.md](CRAWLER_METHODOLOGY.md) — source of `UrlRecord.title`, `h1`, `path`, `page_type` and crawl-derived inventory.
- [ORPHAN_DETECTION_METHODOLOGY.md](ORPHAN_DETECTION_METHODOLOGY.md) — the other engine that consumes the shared URL inventory.
- [PRIORITY_SCORING_METHODOLOGY.md](PRIORITY_SCORING_METHODOLOGY.md) — how separate rule-based issue/orphan scores are calculated.
