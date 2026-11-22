# Interview Demonstrations

Twelve questions → twelve live demos. Each entry gives the UI path, the API calls you can show alongside it, an **exact talking point** you can say out loud, the engineering tradeoff, and what the demo does **not** prove.

**Setup before any demo:** sign in with `demo@serpscope.local` / `demo1234`, generate a 1,000-URL dataset in **Demo Centre**, select it under **Projects → Workspaces**, and run **Detect technical issues** + **Detect orphan pages** from **Overview**. See [DEMO_GUIDE.md](DEMO_GUIDE.md).

> Rule for every answer: name the data source before you name the insight. If the number is synthetic, say "synthetic" in the first sentence.

---

## 1. "You have 1,000 pages. How will you research and map keywords in one day?"

**Live demo**
- UI: **Keywords** → *Keyword inventory* → **Cluster keywords** → *Clusters* → **Map to URLs** → **Keyword Mapping** → *URL mappings* → *Cannibalisation*.
- API: `POST /api/v1/keywords/cluster`, `POST /api/v1/keywords/map`, `GET /api/v1/keywords/mappings`, `GET /api/v1/keywords/cannibalisation`, `GET /api/v1/keywords/export?kind=mapping`.
- Track the returned `job_id` in **Overview → Active jobs** or `GET /api/v1/jobs/{id}`.

**Say:** *"I separate batch processing of supplied data from net-new provider research. Here I import a GSC/keyword CSV, cluster with a declared method, map one primary keyword per URL, and keep every mapping as `suggested` with reasoning. Cannibalisation is surfaced as an interpretation for a human to review, then exported with its evidence. I don't invent volumes — the 1,000 volumes you see are explicitly synthetic."*

**Tradeoff:** deterministic rules are reproducible and explainable; semantic clustering needs an external model and would introduce cost, latency and provenance questions.

**Not proven:** live SERP/volume research, provider API limits, or that the suggested mapping improves rankings.

---

## 2. "How will you identify orphan pages on a 100,000-page website?"

**Live demo**
- UI: generate 100,000 URLs in **Demo Centre** → **URL Intelligence** → *Composition* → **Orphans** → **Detect orphans** → *Orphan register* / *Summary* → **Internal Links** → *Graph summary*.
- API: `POST /api/v1/orphans/detect`, `GET /api/v1/orphans`, `GET /api/v1/orphans/summary`, `GET /api/v1/inventory/urls?limit=50&offset=99950`.

**Say:** *"I reconcile a union of authoritative URL sources — sitemap, crawl, imported analytics/CMS — against observed internal inlinks, using normalised URL keys. I never call an uncrawled URL a confirmed orphan; classification and confidence carry that uncertainty. Priority is a weighted score whose components I can show, and the UI only ever fetches a bounded page — the 100k acceptance test asserts a 50-row response."*

**Tradeoff:** union-based reconciliation avoids false positives but needs good source coverage; stricter confidence keeps trust at the cost of a bigger review queue.

**Not proven:** a live 100k crawl. Links are synthetic edges; missing crawl data is not proof of isolation.

---

## 3. "You discover important revenue-generating pages returning 404. What do you do?"

**Live demo**
- UI: **Technical Auditor** → **Detect issues** → *High-value 404s* → expand a row → **Projects** → *Delivery tasks* to assign a task.
- API: `GET /api/v1/technical/high-value-404s`, `GET /api/v1/technical/issues/{id}`, `POST /api/v1/projects/{id}/tasks`.

**Say:** *"I triage by business impact and confidence, not by status code alone. This endpoint joins the 404 with supplied clicks, revenue, conversions and backlink indicators, sorts by an explained score, and finds a token-matched replacement candidate. The action is a recommendation — restore, 301 to a relevant page, fix internal links or 410 if obsolete — and a human approves it."*

**Tradeoff:** token matching is cheap and auditable; semantic/embedding matching could find better replacements but would need a model and validation. A blanket homepage redirect would be safer to deploy but destroys intent.

**Not proven:** the revenue is simulated; replacement relevance requires human validation; no redirect is deployed.

---

## 4. "How do you manage SEO issues across a large enterprise website?"

**Live demo**
- UI: **Overview** quick action **Detect technical issues** → **Technical Auditor** → *Issue groups* → expand for affected URLs → change status via the row action → **Projects** → *Audit trail*.
- API: `POST /api/v1/technical/detect`, `GET /api/v1/technical/issues?priority=P0`, `PATCH /api/v1/technical/issues/{id}`, `GET /api/v1/technical/export`.

**Say:** *"I turn detections into an owned backlog. Every issue group has evidence, affected templates, priority components and an explanation; the workflow moves it from Detected to Validated to Closed. Segmenting by template means one fix can resolve hundreds of URLs, and the audit log records who changed what."*

**Tradeoff:** weighted scoring is transparent but static; ML prioritisation could adapt but would be harder to defend to a stakeholder.

**Not proven:** real detection coverage, real business loss, or that a fix was validated by a real recrawl.

---

## 5. "How would you grow a Singapore cybersecurity website?"

**Live demo**
- UI: **International** → *Market plans*, *Hreflang audit*, action **Build plan**; **Keywords** → *Clusters*; **Internal Links** → *Link suggestions*.
- API: `POST /api/v1/international/plan`, `GET /api/v1/international/plans`, `GET /api/v1/international/hreflang`, `GET /api/v1/keywords/clusters`.

**Say:** *"I split commercial intent — VAPT, managed security, cloud security, incident response — from informational clusters, then design the internal-link architecture so articles feed service pages. Market and language are inputs, not just translation: the plan includes local proof and an hreflang validation task. I show the partial-hreflang records the generator planted."*

**Tradeoff:** subdirectory plans are simpler to operate; subdomains or ccTLDs may send stronger local signals but cost more to govern.

**Not proven:** live SERP/competitor data, local search demand, or any ranking outcome.

---

## 6. "How do you report SEO progress to senior management?"

**Live demo**
- UI: **Analytics / Reporting** → **Generate now** → open the report → export PDF → **Settings / Docs** → *Provenance*.
- API: `POST /api/v1/analytics/reports/generate-now`, `GET /api/v1/analytics/reports/{id}`, `GET /api/v1/analytics/reports/{id}/export?format=pdf`, `GET /api/v1/meta/data-kinds`.

**Say:** *"I report outcomes and gaps, not vanity charts. The generator compares an equivalent prior period when one is supplied, states revenue only when it was supplied, and prints a Data gaps section otherwise. Every record carries a data kind, so a board slide cannot accidentally present synthetic traffic as real performance."*

**Tradeoff:** honest gap disclosure can make a report look less polished; it is the difference between a defensible number and a misleading one.

**Not proven:** live GSC/GA4 figures, revenue attribution, or causal impact of SEO work.

---

## 7. "How do you prevent SEO losses during a migration?"

**Live demo**
- UI: **Migration** → *Migration projects* → *Redirect map* → **Validate map** → export; then **Technical Auditor** → *Issue groups*.
- API: `POST /api/v1/migration/mappings/bulk`, `POST /api/v1/migration/validate`, `GET /api/v1/migration/mappings?risk=P0`, `GET /api/v1/migration/export`.

**Say:** *"I build and validate the old-to-new map before launch, with clicks and revenue attached to each old URL so traffic-weighted risk defines launch blockers. I compare canonicals, indexability and sitemap presence, then plan a post-launch recrawl. The tool produces the map and the findings; it never pushes redirect rules."*

**Tradeoff:** conservative "block launch on P0" reduces risk but can delay delivery; automated 1:1 redirects are fast but wrong for changed intent.

**Not proven:** any deployed redirect, live post-launch indexation, or preservation of traffic.

---

## 8. "How would you manage SEO for 500 business locations?"

**Live demo**
- UI: **Local / GBP** → *Locations* → **Audit locations** → export `gbp_location_audit`.
- API: `POST /api/v1/local/locations/bulk`, `GET /api/v1/local/locations?issue=...`, `POST /api/v1/local/audit`, `GET /api/v1/local/export`.

**Say:** *"I use bulk QA — NAP field completeness, duplicate groups and landing-page mapping — with a manual review gate. Duplicates are suspects, not verdicts: a shared call-centre number is common. I only use official APIs where permission exists; here the records are labelled synthetic and no GBP call is made."*

**Tradeoff:** heuristics scale across hundreds of locations but need review; official API data would be authoritative but requires consent and quota management.

**Not proven:** live GBP data, real duplicate listings, or that a merge was correct.

---

## 9. "How would you manage thousands of product and category pages?"

**Live demo**
- UI: **E-commerce** → *Product diagnostics* → **Audit catalogue** → export; **Technical Auditor** → *Issue groups*.
- API: `POST /api/v1/ecommerce/products/bulk`, `POST /api/v1/ecommerce/audit`, `GET /api/v1/ecommerce/products?issue=...`, `GET /api/v1/ecommerce/export`.

**Say:** *"I fix at the template level and handle exceptions at product level: canonical rules, schema requirements, identifier checks and facet control. The seeded catalogue has missing SKUs, missing canonicals, missing Product schema and duplicate descriptions on predictable indices, so the audit is repeatable."*

**Tradeoff:** template rules scale but can be too broad; product-level review is precise but expensive.

**Not proven:** a Merchant Center connection, live feed diagnostics, or indexation/trafic improvements.

---

## 10. "How would you improve a brand's visibility in AI search?"

**Live demo**
- UI: **AI Search / AEO** → *Readiness* → **Run audit** → *Observations* → **Add observation** (edit body per [DEMO_GUIDE.md](DEMO_GUIDE.md#before-you-present-action-modal-caveats)) → export.
- API: `POST /api/v1/ai-search/audit`, `GET /api/v1/ai-search/readiness`, `POST /api/v1/ai-search/observations`, `GET /api/v1/meta/data-kinds`.

**Say:** *"I keep two things separate: readiness, which is rule-derived from our own content evidence, and visibility, which comes only from recorded observations. I add question headings, concise answers and provenance where the audit finds gaps. I never claim guaranteed inclusion in an answer engine — that is not measurable from our side."*

**Tradeoff:** rule-based readiness is explainable and free; sampling real answer engines would be closer to reality but needs provider access, repeatable prompts and careful ethics.

**Not proven:** answer-engine sampling, LLM provider calls, citation inclusion or traffic outcomes.

---

## 11. "How do you manage multiple clients and teams?"

**Live demo**
- UI: **Client / Team** → *Organisations* / *Team members* → **Projects** → *Workspaces*, *Delivery tasks*, *Audit trail* → **Integrations** → *Connected*.
- API: `GET /api/v1/clients/organizations`, `POST /api/v1/clients/organizations/{id}/members`, `GET /api/v1/clients/projects/{id}/permissions`, `GET /api/v1/projects/{id}/audit-log`.

**Say:** *"Work is structured by organisation and project. Owners/admins can see all projects, other roles need membership, and writes require owner/admin/editor. Material actions are written to an audit log. Governance is part of delivery, not an afterthought."*

**Tradeoff:** simple global roles are easy to reason about; fine-grained per-module permissions would be more precise but heavier to maintain.

**Not proven:** production-grade RBAC, SSO/SCIM, or tenant isolation guarantees — the test suite covers the current rules, and [ROADMAP.md](ROADMAP.md) lists hardening work.

---

## 12. "Have you built an automation tool? How does it work?"

**Live demo**
- UI: **Overview** → quick actions and *Active jobs* → **Crawler** → **Start crawl**, *Crawl runs*, expand *Observations* → **Workflow Builder** → *Workflows*, *Run history*, *Step library* → **Settings / Docs** → *Methodologies*, *Exports*.
- API: `POST /api/v1/imports/upload`, `POST /api/v1/technical/detect`, `GET /api/v1/jobs/{id}`, `POST /api/v1/jobs/{id}/cancel`, `GET /api/v1/workflows/step-library`, `POST /api/v1/workflows/{id}/run`.

**Say:** *"The pipeline is: upload or configure → validate input → enqueue a job row → worker claims it atomically → service writes results with provenance → UI polls progress → export. Long operations never block the browser, cancellation is checked between batches, and failures are recorded on the job rather than crashing the worker. I chose a database queue for zero infrastructure; Redis/Celery is the scale-up path."*

**Tradeoff:** SQLite + a polling worker is simple and portable but not a distributed queue; WebSocket progress is implemented as one-second database polling, not push events.

**Not proven:** high-throughput operation, exactly-once execution, JS-rendered crawling, or notification delivery (the workflow `notify` step has no provider in this build).

---

## Real public audit (separate from the 12 synthetic scenarios)

**Live demo**
- UI: **Overview** → *Source-tracked public audit* → **Run public audit**, or **Crawler** → **Run public audit**; poll the job, then open *Crawl runs / Observations* and the generated report.
- API: `POST /api/v1/audits/projects/{id}/public-audit/start`, `GET .../public-audit`, `GET .../export?format=pptx`, `GET /api/v1/public/case-studies/{id}` (public when the project sets `settings.public_audit=true`).

**Say:** *"The demo data is synthetic, so I also built a one-click audit that uses only public evidence. It fetches robots.txt, sitemaps and pages with a conservative delay, stores raw observations, and produces a source-tracked finding list, a six-month roadmap and an editable deck. Every rule finding says where it came from and what it cannot prove."*

**Real evidence to show:** on `https://www.techmagnate.com/` a narrow 60-URL sample discovered 303 URLs, fetched 60 with zero failures, stored 60 sitemap entries from 9 documents, and found 12 named AI/search agents explicitly allowed in robots.txt. Findings were AEO readiness gaps 140, slow responses 52, missing schema 60, crawl scope 60, AI-crawler policy 12 and sitemap evidence 60. The 60-URL sample is **not** exhaustive; the in-app default is 250 URLs.

**Tradeoff:** public-only evidence is reproducible and needs no vendor credentials, but it cannot measure traffic, rankings, indexation or AI answers. The roadmap explains what can be done now and how GSC/GA4/rank data would upgrade prioritisation later.

**Not proven:** real GSC/GA4 metrics, JS-rendered content, private pages, answer-engine visibility or traffic outcomes. Explicit AI-agent allowances in robots.txt are declared policy, not an inclusion guarantee.

---

## Closing line for any interview

> "What you saw is a reference implementation with honest labels. The engineering — provenance, bounded queries, explainable scoring, queued jobs, source-tracked public audits and review gates — is real. The 12 walkthrough scenarios use synthetic data and the live vendor integrations are deliberately out of scope; the real audit uses public evidence only and states exactly what is missing."
