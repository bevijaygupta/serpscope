import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Activity, ArrowRight, BarChart3, CheckCircle2, Database, FileText, Globe2,
  KeyRound, Linkedin, Presentation, Search, ShieldCheck, Sparkles, Workflow,
} from 'lucide-react';
import { get } from '../lib/api';
import { num } from '../lib/format';

type PublicAudit = {
  meta: { project_name: string; domain: string; generated_at: string };
  coverage: { fetched_urls: number; discovered_urls: number; sitemap_entries: number; robots_respected: boolean };
  findings: { id: string; title: string; severity: string; affected_count: number; observation: string }[];
  roadmap: { month: number; theme: string }[];
  missing_data: string[];
};

const FEATURES = [
  {
    icon: Search,
    title: 'Public site audit',
    text: 'Crawl real pages with robots.txt and crawl-delay checks. Store raw HTTP observations separately from interpreted SEO fields.',
  },
  {
    icon: Presentation,
    title: 'PPT + six-month roadmap',
    text: 'Export an editable board deck and a month-by-month plan with owners, deliverables, success checks and honest data gaps.',
  },
  {
    icon: KeyRound,
    title: 'Works without tool access',
    text: 'No Search Console or Analytics login required. Add GSC/GA4 CSV exports later to weight real queries and conversions.',
  },
  {
    icon: Sparkles,
    title: 'SEO, AEO and GEO evidence',
    text: 'Inspect titles, structure, schema, answer readiness and robots.txt AI-crawler policy without claiming guaranteed citations.',
  },
];

const STEPS = [
  ['01', 'Add a domain', 'Create a project with the public URL you are authorised to audit.'],
  ['02', 'Run public audit', 'SERPScope crawls, reads robots.txt and sitemaps, then rebuilds issues, orphans and AEO readiness.'],
  ['03', 'Export the pack', 'Download the audit, evidence CSV and PowerPoint deck with a six-month roadmap.'],
  ['04', 'Upgrade with access', 'If the client later shares GSC/GA4 exports, import them to improve prioritisation.'],
];

const FAQ = [
  {
    q: 'Can SERPScope produce a real audit without Search Console access?',
    a: 'Yes. It audits observable public evidence: robots.txt, sitemap files, HTTP status, redirects, canonicals, on-page HTML, internal links, structured data and answer-readiness rules. It labels Search Console, Analytics, rank and revenue metrics as not supplied instead of inventing them.',
  },
  {
    q: 'What can I give a stakeholder who asks for a PPT and roadmap?',
    a: 'The public audit generates an editable .pptx deck, a PDF/CSV/XLSX/JSON evidence pack and a six-month roadmap with owners and success checks. Every finding carries a source and limitation.',
  },
  {
    q: 'Does it guarantee AI search visibility?',
    a: 'No. SERPScope measures readiness from crawl evidence and records only manually observed AI answers. It does not claim inclusion, ranking or citation in ChatGPT, Claude, Perplexity or Google AI Overviews.',
  },
  {
    q: 'Is the demo data real?',
    a: 'The 1,000-URL demo dataset is deterministic synthetic data and is labelled as such. Real domains use the public crawler and are labelled live_crawl with source-tracked observations.',
  },
];

export function Landing() {
  const [caseStudy, setCaseStudy] = useState<PublicAudit | null>(null);
  const [caseError, setCaseError] = useState('');

  useEffect(() => {
    document.title = 'SERPScope — Public SEO Audit, PPT & 6-Month Roadmap';
    get<PublicAudit>('/public/case-studies/2')
      .then(setCaseStudy)
      .catch(() => setCaseError('Published case study is temporarily unavailable. The live demo still generates the same audit pack.'));
  }, []);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-40 border-b border-edge bg-canvas/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-5">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-sky-400 to-violet-600 text-white shadow-glow"><Activity className="h-5 w-5" /></div>
            <div className="leading-tight">
              <div className="text-sm font-bold text-white">SERPScope</div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted">Evidence-first SEO</div>
            </div>
          </Link>
          <nav className="ml-auto hidden items-center gap-6 text-xs font-medium text-muted md:flex">
            <a href="#how-it-works" className="hover:text-ink">How it works</a>
            <a href="#proof" className="hover:text-ink">Real audit</a>
            <a href="#faq" className="hover:text-ink">FAQ</a>
            <a href="https://github.com/bevijaygupta/serpscope" target="_blank" rel="noreferrer" className="hover:text-ink">Source</a>
          </nav>
          <Link to="/login" className="btn btn-primary ml-auto text-xs md:ml-0"><KeyRound className="h-3.5 w-3.5" /> Open demo</Link>
        </div>
      </header>

      <main>
        <section className="relative overflow-hidden border-b border-edge">
          <div className="absolute inset-0 opacity-25" style={{ backgroundImage: 'radial-gradient(circle at 15% 20%, #38bdf8 0, transparent 32%), radial-gradient(circle at 85% 60%, #8b5cf6 0, transparent 38%)' }} />
          <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-20 lg:grid-cols-[1.15fr_0.85fr] lg:py-28">
            <div>
              <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-widest text-accent">
                <ShieldCheck className="h-3.5 w-3.5" /> Source-tracked · no invented metrics
              </div>
              <h1 className="text-4xl font-extrabold leading-[1.08] tracking-tight text-white sm:text-5xl lg:text-6xl">
                Real SEO audit. <span className="bg-gradient-to-r from-sky-400 to-violet-400 bg-clip-text text-transparent">PPT and 6-month roadmap.</span> No tool access needed.
              </h1>
              <p className="mt-6 max-w-2xl text-base leading-8 text-slate-300 sm:text-lg">
                SERPScope turns public website evidence into a defensible audit, an editable board deck and a delivery roadmap. If Search Console or Analytics is refused, the tool states the gap and keeps working.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/login" className="btn btn-primary px-5 py-3 text-sm">Run a public audit <ArrowRight className="h-4 w-4" /></Link>
                <a href="#proof" className="btn px-5 py-3 text-sm"><BarChart3 className="h-4 w-4" /> See real-domain findings</a>
              </div>
              <div className="mt-9 grid max-w-2xl grid-cols-2 gap-3 sm:grid-cols-4">
                {[['23', 'SEO modules'], ['17', 'Docs'], ['12', 'Scenarios'], ['CSV', 'PPT · XLSX · PDF']].map(([value, label]) => (
                  <div key={label} className="rounded-xl border border-edge bg-panel/60 p-3">
                    <div className="text-lg font-bold text-white">{value}</div>
                    <div className="mt-0.5 text-[10px] uppercase tracking-wider text-muted">{label}</div>
                  </div>
                ))}
              </div>
            </div>
            <div className="panel relative p-5 shadow-2xl">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-muted">Live evidence preview</div>
                  <div className="mt-1 text-sm font-semibold text-white">{caseStudy?.meta.domain || 'Public audit pipeline'}</div>
                </div>
                <span className="rounded-full border border-success/30 bg-success/10 px-2.5 py-1 text-[10px] font-semibold text-success">LIVE CRAWL</span>
              </div>
              {caseStudy ? (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    {[
                      ['URLs fetched', num(caseStudy.coverage.fetched_urls)],
                      ['Sitemap URLs', num(caseStudy.coverage.sitemap_entries)],
                      ['Findings', num(caseStudy.findings.length)],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-lg border border-edge bg-canvas/60 p-3">
                        <div className="text-xl font-bold text-white">{value}</div>
                        <div className="mt-1 text-[10px] text-muted">{label}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 space-y-2">
                    {caseStudy.findings.slice(0, 3).map((finding) => (
                      <div key={finding.id} className="flex items-start gap-2 rounded-lg border border-edge bg-canvas/40 p-3">
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                        <div className="min-w-0">
                          <div className="truncate text-xs font-medium text-ink">{finding.title}</div>
                          <div className="mt-0.5 text-[11px] text-muted">{finding.affected_count} affected · {finding.severity}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 rounded-lg border border-violet/30 bg-violet/10 p-3 text-[11px] leading-5 text-slate-300">
                    Roadmap: {caseStudy.roadmap.map((m) => `M${m.month} ${m.theme}`).join(' · ')}
                  </div>
                  <div className="mt-3 text-[10px] text-muted">Generated {caseStudy.meta.generated_at.slice(0, 16).replace('T', ' ')} UTC · robots respected: {String(caseStudy.coverage.robots_respected)}</div>
                </>
              ) : (
                <div className="py-16 text-center text-xs text-muted">{caseError || 'Loading published audit…'}</div>
              )}
            </div>
          </div>
        </section>

        <section className="border-b border-edge py-16">
          <div className="mx-auto max-w-7xl px-5">
            <div className="max-w-2xl">
              <h2 className="text-2xl font-bold text-white sm:text-3xl">One audit pack. Two access modes.</h2>
              <p className="mt-3 text-sm leading-7 text-muted">The core workflow never depends on a client sharing private dashboards. Vendor data is an upgrade, not a prerequisite.</p>
            </div>
            <div className="mt-10 grid gap-5 md:grid-cols-2">
              <div className="panel p-6">
                <div className="flex items-center gap-2 text-sm font-semibold text-accent"><Search className="h-4 w-4" /> Without GSC / GA4 access</div>
                <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-300">
                  <li>Robots-aware public crawl with raw observations.</li>
                  <li>Sitemap and internal-link reconstruction.</li>
                  <li>Technical, content, AEO and structured-data rules.</li>
                  <li>PPT, PDF, CSV, XLSX and JSON exports.</li>
                  <li>Missing private data listed explicitly.</li>
                </ul>
              </div>
              <div className="panel p-6">
                <div className="flex items-center gap-2 text-sm font-semibold text-violet"><Database className="h-4 w-4" /> With access later</div>
                <ul className="mt-4 space-y-3 text-sm leading-6 text-slate-300">
                  <li>Import GSC queries, clicks, impressions and landing pages.</li>
                  <li>Import GA4 sessions, conversions and revenue.</li>
                  <li>Weight roadmap items using observed business impact.</li>
                  <li>Compare equivalent periods instead of guessing trends.</li>
                  <li>Keep provenance labels on every imported metric.</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section id="how-it-works" className="border-b border-edge py-16">
          <div className="mx-auto max-w-7xl px-5">
            <h2 className="text-2xl font-bold text-white sm:text-3xl">How the public audit works</h2>
            <div className="mt-10 grid gap-5 md:grid-cols-4">
              {STEPS.map(([n, title, text]) => (
                <div key={n} className="rounded-xl border border-edge bg-panel/50 p-5">
                  <div className="mono text-xs font-semibold text-accent">{n}</div>
                  <h3 className="mt-3 text-sm font-semibold text-white">{title}</h3>
                  <p className="mt-2 text-xs leading-6 text-muted">{text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-edge py-16">
          <div className="mx-auto max-w-7xl px-5">
            <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <div key={title} className="panel p-5">
                  <Icon className="h-5 w-5 text-accent" />
                  <h3 className="mt-4 text-sm font-semibold text-white">{title}</h3>
                  <p className="mt-2 text-xs leading-6 text-muted">{text}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="proof" className="border-b border-edge py-16">
          <div className="mx-auto grid max-w-7xl gap-10 px-5 lg:grid-cols-[1fr_1fr]">
            <div>
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-edge bg-white/5 px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-muted"><Globe2 className="h-3 w-3" /> Real domain · public evidence</div>
              <h2 className="text-2xl font-bold text-white sm:text-3xl">What people can find on a real site audit</h2>
              <p className="mt-4 text-sm leading-7 text-muted">
                The published Techmagnate audit was produced from robots.txt, sitemap files and a robots-respecting crawl. It contains no Search Console or Analytics claims. Open the demo, switch to the Techmagnate project and regenerate it to inspect every raw observation.
              </p>
              {caseStudy ? (
                <div className="mt-6 space-y-3">
                  {caseStudy.findings.slice(0, 6).map((finding) => (
                    <div key={finding.id} className="rounded-lg border border-edge bg-panel/50 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-xs font-semibold text-ink">{finding.title}</div>
                        <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-muted">{finding.severity}</span>
                      </div>
                      <div className="mt-1.5 text-[11px] leading-5 text-muted">{finding.observation}</div>
                    </div>
                  ))}
                </div>
              ) : <div className="mt-6 text-xs text-muted">{caseError || 'Loading…'}</div>}
            </div>
            <div className="panel p-6">
              <div className="flex items-center gap-2 text-sm font-semibold text-white"><FileText className="h-4 w-4 text-accent" /> Deliverables in the pack</div>
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                {[
                  ['Site audit', 'Findings with source, confidence and limitation.'],
                  ['PPT deck', 'Editable slides for stakeholder review.'],
                  ['6-month roadmap', 'Monthly outcomes, owners and success checks.'],
                  ['Evidence export', 'CSV/XLSX/JSON rows with provenance columns.'],
                  ['AEO readiness', 'Machine-readability rules, not visibility claims.'],
                  ['Gap statement', 'Names every private dataset that was not supplied.'],
                ].map(([title, text]) => (
                  <div key={title} className="rounded-lg border border-edge bg-canvas/50 p-3">
                    <div className="text-xs font-semibold text-ink">{title}</div>
                    <div className="mt-1 text-[11px] leading-5 text-muted">{text}</div>
                  </div>
                ))}
              </div>
              <Link to="/login" className="btn btn-primary mt-6 w-full justify-center py-2.5 text-xs"><Workflow className="h-4 w-4" /> Open the audit workspace</Link>
            </div>
          </div>
        </section>

        <section id="faq" className="border-b border-edge py-16">
          <div className="mx-auto max-w-4xl px-5">
            <h2 className="text-2xl font-bold text-white sm:text-3xl">Frequently asked questions</h2>
            <div className="mt-8 space-y-4">
              {FAQ.map((item) => (
                <details key={item.q} className="group rounded-xl border border-edge bg-panel/50 p-5">
                  <summary className="cursor-pointer list-none text-sm font-semibold text-white marker:hidden">{item.q}</summary>
                  <p className="mt-3 text-sm leading-7 text-muted">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="py-20">
          <div className="mx-auto max-w-4xl px-5 text-center">
            <Sparkles className="mx-auto h-7 w-7 text-accent" />
            <h2 className="mt-5 text-3xl font-bold text-white sm:text-4xl">Show the work, not just the claim.</h2>
            <p className="mx-auto mt-4 max-w-2xl text-sm leading-7 text-muted">Sign in to the public demo, choose a real or synthetic project and produce the same audit, PPT and roadmap the tool documents.</p>
            <Link to="/login" className="btn btn-primary mx-auto mt-8 px-6 py-3 text-sm">Open SERPScope <ArrowRight className="h-4 w-4" /></Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-edge px-5 py-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 text-[11px] text-muted">
          <div>© {new Date().getFullYear()} SERPScope · public-evidence SEO operations</div>
          <div className="flex items-center gap-4">
            <a href="https://github.com/bevijaygupta/serpscope" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-ink">Source</a>
            <a href="/sitemap.xml" className="hover:text-ink">Sitemap</a>
            <a href="/llms.txt" className="hover:text-ink">llms.txt</a>
            <a href="https://www.linkedin.com/" target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-ink"><Linkedin className="h-3 w-3" /> LinkedIn</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
