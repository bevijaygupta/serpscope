# SERPScope public evidence packs

This folder contains complete, source-tracked audit output from live public
runs against `https://www.techmagnate.com/`. Nothing here is a screenshot of a
dashboard, and no Search Console, Analytics, rank-provider or AI-visibility
outcome data has been invented.

## Current pack

- [Techmagnate hosted audit, 2026-11-23](techmagnate_public_audit_hosted_2026-11-23/)

Open these files first:

1. [COMPLETE_AUDIT.md](techmagnate_public_audit_hosted_2026-11-23/COMPLETE_AUDIT.md) — every audit segment, all findings, all roadmap months, robots evidence, source registry, missing-data statements, report sections and the public case-study payload.
2. [RAW_OBSERVATIONS.md](techmagnate_public_audit_hosted_2026-11-23/RAW_OBSERVATIONS.md) — every request-level crawl observation in a readable table.
3. [MANIFEST.json](techmagnate_public_audit_hosted_2026-11-23/MANIFEST.json) — every downloaded file with endpoint, byte count and SHA-256 digest.
4. [DOWNLOAD_LOG.md](techmagnate_public_audit_hosted_2026-11-23/DOWNLOAD_LOG.md) — exact API route used for every file; zero download errors in the final run.
5. [exports/](techmagnate_public_audit_hosted_2026-11-23/exports/) — PPTX, PDF, CSV, XLSX and JSON for the full audit, findings and roadmap, plus raw crawl, inventory, issues, orphan, content, link and AI-readiness exports.

### Hosted figures

Job 17, persisted report 2, crawl 1, generated `2026-11-23T17:07:58Z`:

- 497 discovered URLs, 219 fetched, 0 failed, 1 robots exclusion.
- Status codes: 200: 219, 404: 30. Average content score: 82.8.
- 12 finding groups, 6 roadmap months, 6 explicit missing-data statements.
- Sitemap discovery timed out in this hosted run, so it reports **0 sitemap entries**. The earlier local 60-URL sample captured 60 sitemap entries from 9 documents; the two runs are kept separate and are never blended.

### Live verification

- Landing page: <https://serpscope.vercel.app/>
- Public read-only case study: <https://serpscope-api.onrender.com/api/v1/public/case-studies/2>
- Sign in to the workspace at `/login` with the demo account shown on that page, select the Techmagnate project, and open **Overview → Source-tracked public audit** to see every finding, every roadmap month, all coverage segments, all exports and the complete API payload.

### Reproduce the pack

```bash
# from the repository root, with the demo bearer token available
backend/.venv/Scripts/python.exe scripts/download_evidence_pack.py
```

The script records a SHA-256 manifest and refuses to run until the public-audit
job has succeeded. It only downloads data the API already exposes.
