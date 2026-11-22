# Demo Guide

The Demo Centre is the entry point for every walkthrough in this portfolio project.

> **All data in these scenarios is synthetic.** URLs live under `demo.example.com`; clicks, sessions, conversions, revenue, keyword volumes, locations, products and AI observations are invented by `backend/app/services/demo.py` for rule testing. They are labelled `synthetic` / `simulated` in the database, UI and exports. No scenario represents a real client, a real crawl or a live vendor response.

- [Generate the dataset](#generate-the-dataset)
- [Planted issue inventory](#planted-issue-inventory)
- [The 12 scenarios](#the-12-scenarios)
- [Before you present: action-modal caveats](#before-you-present-action-modal-caveats)
- [Limits to state out loud](#limits-to-state-out-loud)

---

## Generate the dataset

### UI

1. Sign in as `demo@serpscope.local` / `demo1234`.
2. Open **Demo Centre** in the left navigation (Automation group). The left panel lists all 12 scenario definitions; clicking one shows its context, steps, expected findings, modules, limitations and interview explanation.
3. In **Generate synthetic dataset**, set `URLs` (default `1000`, allowed 100–200,000) and click **Generate dataset**.
4. Watch the job finish (toast + job list). Then use **Projects → Workspaces** to select the new `Interview demo …` project.
5. **Reset demo environment** deletes all demo projects and the demo organisation, then re-seeds the scenario catalogue. `POST /demo/reset` with `{"regenerate": true, "size": 1000}` resets and rebuilds in one job.

### API

```bash
# Queue generation (202)
curl -X POST http://127.0.0.1:8000/api/v1/demo/generate \
  -H 'Authorization: Bearer <TOKEN>' -H 'Content-Type: application/json' \
  -d '{"size":1000,"keyword_count":1000,"label":"Interview demo","include_scenarios":true}'

# Read scenario catalogue (seeded automatically if empty)
curl http://127.0.0.1:8000/api/v1/demo/scenarios -H 'Authorization: Bearer <TOKEN>'
```

Rules from `backend/app/api/v1/demo.py` and `backend/app/services/demo_jobs.py`:

- `size` is clamped to a minimum of 100 and rejected above 200,000 (`400`).
- Generation is deterministic: `random.Random(20261122)` and modulo-based issue placement mean the same size always yields the same planted counts.
- Reset deletes rows from all demo-related tables for projects where `is_demo=1`, deletes the `demo-organisation`, and deletes `generate_demo`/`reset_demo` jobs. It does **not** archive anything.

For a 1,000-URL dataset the generator also creates: 1,000 keywords, 857 sitemap entries (143 deliberate omissions), 19 planted orphan targets, 1,000 GSC-style + 200 query analytics rows (fixed period `2026-11-02` → `2026-11-08`), 250 locations, 200 products, 250 migration mappings, 30 AI visibility observations, a Singapore international plan and three example workflows.

---

## Planted issue inventory

`_planted_issue(i)` applies an `if / elif` chain, so each index gets **at most one** planted pattern; counts below are exact for the given size.

| Planted pattern | Formula | 1,000 URLs | 100,000 URLs | Where it surfaces |
| --- | --- | ---: | ---: | --- |
| High-value 404 | `i % 137 == 17` | 8 | 730 | Technical Auditor → **High-value 404s**; has simulated clicks/revenue/conversions/backlinks |
| Ordinary 404 | `i % 151 == 31` | 7 | 659 | Technical Auditor → issue group `http_404` |
| Redirect chain | `i % 173 == 43` | 6 | 570 | URL inventory detail (`redirect_chain`), migration-style findings |
| Server error | `i % 181 == 59` | 6 | 543 | `http_5xx` issue group |
| Canonical conflict | `i % 191 == 71` | 5 | 512 | Technical issue group + URL detail |
| noindex in sitemap | `i % 211 == 83` | 5 | 461 | Indexability / sitemap reconciliation |
| Duplicate metadata | `i % 223 == 97` | 5 | 432 | Duplicate title/description rules |
| Thin content | `i % 229 == 101` | 4 | 420 | Word-count / H1 / alt rules |
| Slow + oversized | `i % 233 == 109` | 4 | 412 | Response-time / content-size rules |
| Invalid schema | `i % 239 == 113` | 4 | 398 | Structured-data rules |
| Partial hreflang | `i % 241 == 127` | 4 | 393 | International → **Hreflang audit** |
| Intentional 410 | `i % 251 == 131` | 4 | 377 | Should not be treated as an accidental 404 |
| Orphan target (separate rule) | `i % 53 == 7` | 19 | 1,887 | Orphans register; internal inlinks forced to 0 |
| Sitemap omission (separate rule) | `i % 7 == 3` | 143 omitted | 14,286 omitted | Source-union / sitemap-only classification |

The generator's result object returns the realised `planted_issues` dictionary; the test `test_demo_generation_creates_labelled_data_and_planted_issues` asserts that high-value and ordinary 404s exist and that all records carry `data_kind == "synthetic"`.

---

## The 12 scenarios

These are the exact `SCENARIOS` entries seeded by `backend/app/services/scenarios.py` and displayed in **Demo Centre**. The UI cards are definitions; they do not build a dataset by themselves — generate one first.

### 1. 1,000-page keyword mapping

**Question:** *You have 1,000 pages. How will you research and map keywords in one day?*

| | |
| --- | --- |
| **Demonstrates** | Batch processing of supplied keyword/GSC data: classify intent, cluster, map one primary keyword per URL, surface cannibalisation. |
| **Where to click** | **Keywords** → *Keyword inventory*, *Clusters*, *Summary*; actions **Cluster keywords**, **Map to URLs**, **Bulk workflow**; then **Keyword Mapping** → *URL mappings*, *Cannibalisation*. |
| **Expected findings** | Mapped and unmapped URLs, cannibalisation conflicts, a human review queue (`status = suggested`), reasoning on each mapping. |
| **Limitations** | Volumes are simulated (`volume = (i * 37) % 5000`); no live provider research. Fresh third-party data needs provider credentials. |

### 2. 100,000-page orphan detection

**Question:** *How will you identify orphan pages on a 100,000-page website?*

| | |
| --- | --- |
| **Demonstrates** | Reconciliation of sitemap + crawl + analytics/CMS-style sources, URL normalisation, internal link graph, confidence and weighted priority. |
| **Where to click** | Generate a 100,000-URL dataset in **Demo Centre**; **URL Intelligence** → *URL inventory*, *Composition*; **Orphans** → action **Detect orphans**, tabs *Orphan register*, *Summary*; **Internal Links** → *Graph summary*. |
| **Expected findings** | Confirmed crawl orphans, potential orphans, sitemap-only orphans, unverified URLs; `priority_score` 0–100 with `score_components`. |
| **Limitations** | Internal links are synthetic edges; no live crawl. Missing crawl data is not proof of isolation — confidence marks this explicitly. Large generation may take minutes. |

### 3. High-revenue 404s

**Question:** *You discover important revenue-generating pages returning 404. What do you do?*

| | |
| --- | --- |
| **Demonstrates** | Business-impact triage and safe remediation instead of blanket redirects to the homepage. |
| **Where to click** | **Technical Auditor** → action **Detect issues**, tab *High-value 404s* (expand a row for evidence); optionally **Analytics / Reporting** → *Summary*. |
| **Expected findings** | Eight planted high-value 404s at 1k URLs, ranked by simulated revenue, with `explanation`, `components.revenue_impact` and `recommended_action`. |
| **Limitations** | Revenue is simulated; replacement matching is token-based and needs human validation. The tool recommends 301/restore/410 — it does not deploy anything. |

### 4. Enterprise technical audit

**Question:** *How do you manage SEO issues across a large enterprise website?*

| | |
| --- | --- |
| **Demonstrates** | Turning raw detections into an owned, prioritised, reviewable backlog segmented by template. |
| **Where to click** | **Overview** quick action **Detect technical issues**; **Technical Auditor** → *Issue groups* (expand for affected URLs); **Projects** → *Delivery tasks*, *Audit trail*. Use the issue row action to change status. |
| **Expected findings** | Issue groups such as `http_404`, `http_5xx`, canonical conflicts; P0/P1 counts, affected templates, evidence and priority explanations; a Detected → Closed workflow. |
| **Limitations** | Observations are synthetic. Priority is a weighted rule, not a measured business loss. |

### 5. Singapore cybersecurity growth

**Question:** *How would you grow a Singapore cybersecurity website?*

| | |
| --- | --- |
| **Demonstrates** | Commercial vs informational intent, service-page architecture, supporting clusters and hreflang planning. |
| **Where to click** | **International** → *Market plans*, *Hreflang audit*, action **Build plan**; **Keywords** → *Clusters*; **Internal Links** → *Link suggestions*. |
| **Expected findings** | Service-page plan (VAPT, managed security, cloud security, incident response, consulting), informational clusters, hreflang recommendations and partial-hreflang records. |
| **Limitations** | No live SERP or competitor analytics. Competitor domains in the plan are `*.example`. Hreflang is a validation task, not a guarantee of ranking. |

### 6. Enterprise SEO reporting

**Question:** *How do you report SEO progress to senior management?*

| | |
| --- | --- |
| **Demonstrates** | Narrative reporting with equivalent-period comparison and explicit disclosure of data gaps. |
| **Where to click** | **Analytics / Reporting** → *Summary*, *Analytics records*, *Reports*; actions **Generate now** (synchronous) or **Queue report**; open a report and use the export button for PDF/CSV/JSON. |
| **Expected findings** | Executive summary, organic trends, open priority groups, next-week plan, and a **Data gaps** section when no comparison period or revenue data is supplied. |
| **Limitations** | Metrics are synthetic (`synthetic_gsc` / `synthetic_ga4` sources). No live API connection; charts alone do not prove business impact. |

### 7. Website migration

**Question:** *How do you prevent SEO losses during a migration?*

| | |
| --- | --- |
| **Demonstrates** | Pre-launch redirect mapping, traffic-weighted risk, and post-launch validation planning. |
| **Where to click** | **Migration** → *Migration projects*, *Redirect map*, actions **New migration**, **Add mappings**, **Validate map**; **Technical Auditor** → *Issue groups*. |
| **Expected findings** | 250 sample mappings, unmapped high-click URLs, redirect status/chain findings, canonical and indexability comparisons, risk flags. |
| **Limitations** | No redirect rules are deployed. Post-launch recrawl is a process recommendation, not an executed action. |

### 8. Local SEO at scale

**Question:** *How would you manage SEO for 500 business locations?*

| | |
| --- | --- |
| **Demonstrates** | Bulk location QA: NAP consistency, duplicate suspects and landing-page mapping with human review. |
| **Where to click** | **Local / GBP** → *Locations*; actions **Add locations**, **Audit locations**; export the GBP location audit. |
| **Expected findings** | 250 seeded locations at 1k URLs (up to 500 at larger sizes), incomplete profiles, duplicate groups, missing landing pages. |
| **Limitations** | No official GBP API credentials. Shared call-centre numbers are not automatically errors; duplicates require review. |

### 9. E-commerce SEO

**Question:** *How would you manage thousands of product and category pages?*

| | |
| --- | --- |
| **Demonstrates** | Template-level canonical/schema rules with product-level exceptions and feed consistency checks. |
| **Where to click** | **E-commerce** → *Product diagnostics*; actions **Add products**, **Audit catalogue**; **Technical Auditor** → *Issue groups*; export merchant diagnostics. |
| **Expected findings** | Missing identifiers (`i % 9 == 0`), missing canonicals (`i % 11 == 0`), missing schema (`i % 5 == 0`), out-of-stock rows (`i % 29 == 0`) and duplicate descriptions (`i % 13 == 0`). |
| **Limitations** | Feed diagnostics are imported/synthetic examples. No Merchant Center connection and no live feed fetch. |

### 10. AI search strategy

**Question:** *How would you improve a brand's visibility in AI search?*

| | |
| --- | --- |
| **Demonstrates** | Separating measurable answer-readiness from manually observed visibility, without promising inclusion. |
| **Where to click** | **AI Search / AEO** → *Readiness*, *Observations*; actions **Run audit**, **Add observation** (edit the default body — see caveats below); export `kind=readiness\|observations`. |
| **Expected findings** | 30 synthetic manual observations, question/entity gaps from the readiness rules, `data_kind` labels on every row. |
| **Limitations** | No LLM provider call, no answer-engine sampling and no outcome guarantee. Readiness is rule-derived from content evidence; visibility comes only from observations. |

### 11. Multi-client SEO operations

**Question:** *How do you manage multiple clients and teams?*

| | |
| --- | --- |
| **Demonstrates** | Organisation/project separation, roles, tasks, approvals and audit logging. |
| **Where to click** | **Client / Team** → *Organisations*, *Team members*; **Projects** → *Workspaces*, *Delivery tasks*, *Audit trail*; **Integrations** for connection records. |
| **Expected findings** | Project-level data separation, owners/deadlines, material actions in the audit log, write permissions enforced by `check_write`. |
| **Limitations** | Demo roles are illustrative; owners/admins see all projects. Production RBAC needs hardening (see [ROADMAP.md](ROADMAP.md)). |

### 12. Automation architecture

**Question:** *Have you built an automation tool? How does it work?*

| | |
| --- | --- |
| **Demonstrates** | The full data flow: upload/import → enqueue job → worker executes a service → progress → result + export. |
| **Where to click** | **Overview** → *Active jobs* and quick actions; **Crawler** → *Start crawl*, *Crawl runs*, expand *Observations*; **Workflow Builder** → *Workflows*, *Run history*, *Step library*; **Settings / Docs** → *Methodologies*, *Exports*. |
| **Expected findings** | Job states `queued → claimed → running → succeeded/failed/cancelled`, cancellation requests, failure messages, run history with step results, exported CSV/XLSX/PDF. |
| **Limitations** | The queue is database-backed and local; Redis/Celery would be needed for higher throughput. The crawler is conservative (no JS rendering). The workflow `notify` step requires a configured provider that does not exist in this build. |

---

## Before you present: action-modal defaults

The generic **ActionModal** sends the `defaultBody` declared in `frontend/src/lib/modules.ts`. The previously reported mismatches were corrected:

| Module action | Default body now sends | Note |
| --- | --- | --- |
| Keywords → **Add keyword** | `{ "keywords": [{ "keyword": ..., "intent": ... }], "source": "manual", "confidence": "synthetic" }` | Matches `/keywords/inline`; the inline row is explicitly labelled synthetic. |
| AI Search → **Add observation** | `{ "question": ..., "answer_engine": ..., "data_kind": "observed", ... }` | Matches `/ai-search/observations`; record only responses you actually observed. |
| Workflow Builder → **New workflow** | Steps use `detect_issues` and `generate_report` | Both are valid step types. |
| Crawler → **Start crawl** | `{ "config": { "start_url": "https://demo.example.com/", "max_urls": 500, ... } }` | Correct nested shape. Keep the fictional seed unless you are authorised to crawl the target. |

Only edit the JSON when you deliberately want different inputs; the API field names are documented in [API_DOCUMENTATION.md](API_DOCUMENTATION.md).

---

## Limits to state out loud

- The dataset is deterministic and synthetic; the same size always produces the same "findings".
- No live GSC, GA4, GBP, Merchant Center, Semrush, Ahrefs or LLM API is contacted.
- No real crawl results are included in the demo data; the crawler module can only fetch domains you are authorised to test.
- Forecasts are arithmetic scenarios on user-supplied inputs, not predictions.
- AI-search outcomes are never guaranteed; observations are manual or synthetic.
- Exports carry `data_kind` so a screenshot cannot be quietly presented as real performance.

For question-by-question talking points, see [INTERVIEW_DEMONSTRATIONS.md](INTERVIEW_DEMONSTRATIONS.md).
