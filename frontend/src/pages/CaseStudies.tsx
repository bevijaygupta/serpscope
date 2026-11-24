import { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowRight, CheckCircle2, Database, FileText, Globe2, ShieldCheck, Sparkles,
} from 'lucide-react';
import { get, post, errorMessage } from '../lib/api';
import { trackEvent } from '../lib/analytics';
import { LiveVisitors } from '../components/LiveVisitors';

const BASE_URL = 'https://serpscopelive.vercel.app';
const numViews = (value: number | undefined) => new Intl.NumberFormat('en').format(value ?? 0);

type CaseStudySummary = {
  project_id: number;
  report_id: number;
  name: string;
  domain: string;
  generated_at: string;
  fetched_urls: number;
  sitemap_entries: number;
  findings: number;
  roadmap_months: number;
  roadmap_themes: string[];
  top_findings: { title: string; severity: string; affected_count: number }[];
  ai_visibility_status: string;
  view_count: number;
  case_study_path: string;
  case_study_url: string;
};

type CaseStudyDetail = {
  meta: {
    project_id: number; domain: string; generated_at: string; method: string;
    data_kinds: string[]; publication_scope?: string; private_data_policy?: string;
  };
  coverage: {
    discovered_urls: number; fetched_urls: number; failed_urls: number;
    sitemap_entries: number; robots_respected: boolean;
  };
  counts: { indexable: number; non_indexable: number; redirects: number; schema_pages: number };
  ai_visibility?: {
    status: string; notice: string; observation_count: number;
    engines: {
      engine: string; status: string; observations: number;
      brand_mentions_observed: number; cited_urls_recorded: number;
    }[];
    publication_note?: string;
  };
  findings: {
    id: string; title: string; severity: string; affected_count: number;
    observation: string; recommended_action: string; limitation: string;
  }[];
  roadmap: { month: number; theme: string; objective: string; deliverables: string[] }[];
  source_registry: { source: string; type: string; confidence: string; used_for: string[] }[];
  missing_data: string[];
  analytics?: { view_count: number; note: string };
};

function useSeo(title: string, description: string, path: string, jsonLd: Record<string, unknown>) {
  useEffect(() => {
    document.title = title;
    const canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
      ?? document.createElement('link');
    if (!canonical.parentElement) {
      canonical.rel = 'canonical';
      document.head.appendChild(canonical);
    }
    canonical.href = `${BASE_URL}${path}`;

    const setMeta = (attribute: 'name' | 'property', key: string, content: string) => {
      let node = document.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`);
      if (!node) {
        node = document.createElement('meta');
        node.setAttribute(attribute, key);
        document.head.appendChild(node);
      }
      node.content = content;
    };
    setMeta('name', 'description', description);
    setMeta('property', 'og:url', `${BASE_URL}${path}`);
    setMeta('property', 'og:title', title);
    setMeta('property', 'og:description', description);
    setMeta('property', 'og:type', 'article');
    setMeta('name', 'twitter:card', 'summary_large_image');
    setMeta('name', 'twitter:title', title);
    setMeta('name', 'twitter:description', description);

    let script = document.getElementById('serpscope-case-study-jsonld') as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement('script');
      script.id = 'serpscope-case-study-jsonld';
      script.type = 'application/ld+json';
      document.head.appendChild(script);
    }
    script.textContent = JSON.stringify(jsonLd);

    return () => {
      document.getElementById('serpscope-case-study-jsonld')?.remove();
      const cleanCanonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]');
      if (cleanCanonical) cleanCanonical.href = `${BASE_URL}/`;
    };
  }, [title, description, path, jsonLd]);
}

function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <section className="border-b border-edge bg-panel/30">
      <div className="mx-auto max-w-7xl px-5 py-14">
        <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-widest text-accent">
          <ShieldCheck className="h-3.5 w-3.5" /> {eyebrow}
        </div>
        <h1 className="mt-5 text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-muted">{description}</p>
      </div>
    </section>
  );
}

export function CaseStudies() {
  const [items, setItems] = useState<CaseStudySummary[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'ItemList',
    name: 'SERPScope public SEO audit case studies',
    numberOfItems: items.length,
  };

  useSeo(
    'SEO Audit Case Studies | SERPScope',
    'Every successful SERPScope public audit is published as a source-tracked SEO case study with findings, a six-month roadmap and explicit data gaps.',
    '/case-studies',
    jsonLd,
  );

  useEffect(() => {
    let cancelled = false;
    get<{ items: CaseStudySummary[] }>('/public/case-studies')
      .then((payload) => { if (!cancelled) setItems(payload.items || []); })
      .catch((cause) => { if (!cancelled) setError(errorMessage(cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-40 border-b border-edge bg-canvas/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-5">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-sky-400 to-violet-600 text-white shadow-glow">
              <Database className="h-5 w-5" />
            </div>
            <span className="text-sm font-bold text-white">SERPScope</span>
          </Link>
          <nav className="ml-auto flex items-center gap-5 text-xs font-medium text-muted">
            <Link to="/" className="hover:text-ink">Home</Link>
          </nav>
          <div className="flex items-center gap-3">
            <LiveVisitors />
            <Link to="/login" className="btn btn-primary text-xs">Open demo</Link>
          </div>
        </div>
      </header>

      <PageHeader
        eyebrow="Public evidence only"
        title="SEO audit case studies"
        description="Every successful real-domain audit is published automatically. Each page shows the crawled evidence, every finding, the six-month roadmap and the datasets the tool deliberately refused to invent. Private uploads are never included."
      />

      <main className="mx-auto max-w-7xl px-5 py-12">
        {error ? <div className="rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">{error}</div> : null}
        {loading ? <div className="text-sm text-muted">Loading published audits…</div> : null}
        {!loading && !error && items.length === 0 ? (
          <div className="rounded-xl border border-edge bg-panel/50 p-8 text-center text-sm text-muted">
            No audits have been published yet. Run a one-field audit on the home page and it will appear here automatically.
          </div>
        ) : null}
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <article key={item.project_id} className="panel flex flex-col p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-[10px] font-semibold uppercase tracking-widest text-muted">Published audit</div>
                  <h2 className="mt-2 truncate text-base font-semibold text-white">{item.domain}</h2>
                </div>
                <span className="rounded-full border border-success/30 bg-success/10 px-2 py-1 text-[10px] text-success">Live crawl</span>
              </div>
              <div className="mt-5 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-lg border border-edge bg-canvas/50 p-2">
                  <div className="text-lg font-bold text-white">{item.fetched_urls}</div>
                  <div className="text-[10px] text-muted">Fetched</div>
                </div>
                <div className="rounded-lg border border-edge bg-canvas/50 p-2">
                  <div className="text-lg font-bold text-white">{item.findings}</div>
                  <div className="text-[10px] text-muted">Findings</div>
                </div>
                <div className="rounded-lg border border-edge bg-canvas/50 p-2">
                  <div className="text-lg font-bold text-white">{item.roadmap_months}</div>
                  <div className="text-[10px] text-muted">Roadmap mo.</div>
                </div>
              </div>
              <div className="mt-4 space-y-2">
                {item.top_findings.map((finding) => (
                  <div key={finding.title} className="flex items-start gap-2 rounded-lg border border-edge bg-canvas/40 p-2.5">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium text-ink">{finding.title}</div>
                      <div className="text-[10px] text-muted">{finding.affected_count} affected · {finding.severity}</div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-4 text-[10px] text-muted">
                AI visibility: {item.ai_visibility_status === 'not_sampled' ? 'Not sampled' : 'Observed'} · {numViews(item.view_count)} anonymous views · Generated {String(item.generated_at).slice(0, 16).replace('T', ' ')} UTC
              </div>
              <Link to={item.case_study_path} className="btn btn-primary mt-auto w-full justify-center py-2 text-xs">
                Read case study <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </article>
          ))}
        </div>
      </main>
    </div>
  );
}

export function CaseStudyDetail() {
  const { projectId } = useParams();
  const [audit, setAudit] = useState<CaseStudyDetail | null>(null);
  const [viewCount, setViewCount] = useState<number | null>(null);
  const recordedView = useRef<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const domain = audit?.meta.domain || 'Published SEO audit';
  const description = audit
    ? `Source-tracked SEO audit of ${domain}: ${audit.findings.length} public-evidence findings, ${audit.roadmap.length} roadmap months and explicit missing-data statements.`
    : 'Source-tracked public SEO audit case study from SERPScope.';
  const path = `/case-studies/${projectId || ''}`;
  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: `${domain} — public SEO audit case study`,
    description,
    datePublished: audit?.meta.generated_at,
    mainEntityOfPage: `${BASE_URL}${path}`,
    author: { '@type': 'Organization', name: 'SERPScope', url: BASE_URL },
    publisher: { '@type': 'Organization', name: 'SERPScope', url: BASE_URL },
  };

  useSeo(`${domain} SEO Audit Case Study | SERPScope`, description, path, jsonLd);

  useEffect(() => {
    let cancelled = false;
    get<CaseStudyDetail>(`/public/case-studies/${projectId}`)
      .then((payload) => {
        if (cancelled) return;
        setAudit(payload);
        setViewCount(payload.analytics?.view_count ?? 0);
        if (projectId && recordedView.current !== projectId) {
          recordedView.current = projectId;
          trackEvent('serpscope_case_study_view', { source: 'case_study_detail' });
          void post(`/public/case-studies/${projectId}/view`, { source: 'case_study_detail' })
            .then(() => setViewCount((count) => (count ?? 0) + 1))
            .catch(() => { /* analytics is non-critical; never block the case study */ });
        }
      })
      .catch((cause) => { if (!cancelled) setError(errorMessage(cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [projectId]);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-40 border-b border-edge bg-canvas/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-4 px-5">
          <Link to="/case-studies" className="flex items-center gap-2 text-xs font-medium text-muted hover:text-ink">
            <ArrowRight className="h-3.5 w-3.5 rotate-180" /> All case studies
          </Link>
          <Link to="/" className="ml-auto text-xs font-medium text-muted hover:text-ink">Home</Link>
          <LiveVisitors />
          <Link to="/login" className="btn btn-primary text-xs">Open demo</Link>
        </div>
      </header>

      <PageHeader
        eyebrow="Source-tracked public audit"
        title={domain}
        description={audit
          ? `Generated ${String(audit.meta.generated_at).slice(0, 16).replace('T', ' ')} UTC from robots.txt, sitemaps and ${audit.coverage.fetched_urls} fetched public URLs. Every claim below carries evidence; private vendor data is excluded.`
          : 'Loading the published evidence pack…'}
      />

      <main className="mx-auto max-w-7xl px-5 py-12">
        {error ? <div className="rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">{error}</div> : null}
        {loading ? <div className="text-sm text-muted">Loading case study…</div> : null}
        {audit ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {[
                ['Discovered URLs', audit.coverage.discovered_urls],
                ['Fetched URLs', audit.coverage.fetched_urls],
                ['Sitemap entries', audit.coverage.sitemap_entries],
                ['Findings', audit.findings.length],
                ['Roadmap months', audit.roadmap.length],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl border border-edge bg-panel/50 p-4">
                  <div className="text-2xl font-bold text-white">{String(value)}</div>
                  <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{label}</div>
                </div>
              ))}
            </section>

            {viewCount !== null ? (
              <p className="mt-3 text-[10px] leading-5 text-muted">
                {numViews(viewCount)} anonymous page views · {audit.analytics?.note || 'No IP, cookie or user identity is stored.'}
              </p>
            ) : null}

            <section className="mt-6 rounded-xl border border-violet/30 bg-violet/10 p-5">
              <div className="flex items-center gap-2 text-sm font-semibold text-white"><Sparkles className="h-4 w-4 text-violet-400" /> AI citations, AI Overviews and mentions</div>
              <p className="mt-2 text-xs leading-6 text-slate-300">
                {audit.ai_visibility?.notice || 'No live answer-engine sampling is performed.'}
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {(audit.ai_visibility?.engines ?? []).map((engine) => (
                  <div key={engine.engine} className="rounded-lg border border-edge bg-canvas/50 p-3">
                    <div className="text-xs font-semibold text-ink">{engine.engine}</div>
                    <div className="mt-1 text-[10px] text-muted">
                      {engine.status === 'not_sampled' ? 'Not sampled' : `${engine.observations} observation(s) · ${engine.brand_mentions_observed} mentioned · ${engine.cited_urls_recorded} cited`}
                    </div>
                  </div>
                ))}
              </div>
              {audit.ai_visibility?.publication_note ? <p className="mt-3 text-[10px] text-muted">{audit.ai_visibility.publication_note}</p> : null}
            </section>

            <section className="mt-8">
              <h2 className="text-xl font-semibold text-white">All findings</h2>
              <div className="mt-4 space-y-3">
                {audit.findings.map((finding) => (
                  <article key={finding.id} className="rounded-xl border border-edge bg-panel/50 p-5">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h3 className="text-sm font-semibold text-white">{finding.title}</h3>
                      <span className="rounded-full bg-white/5 px-2 py-1 text-[10px] text-muted">{finding.severity} · {finding.affected_count} affected</span>
                    </div>
                    <p className="mt-2 text-xs leading-6 text-slate-300">{finding.observation}</p>
                    <p className="mt-2 text-xs leading-6 text-accent">Fix: {finding.recommended_action}</p>
                    <p className="mt-2 text-[10px] text-muted">{finding.limitation}</p>
                  </article>
                ))}
              </div>
            </section>

            <section className="mt-8 grid gap-5 lg:grid-cols-2">
              <div className="panel p-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-white"><FileText className="h-4 w-4 text-accent" /> Six-month roadmap</h2>
                <div className="mt-4 space-y-3">
                  {audit.roadmap.map((month) => (
                    <div key={month.month} className="rounded-lg border border-edge bg-canvas/50 p-3">
                      <div className="text-xs font-semibold text-ink">M{month.month} · {month.theme}</div>
                      <div className="mt-1 text-[11px] leading-5 text-muted">{month.objective}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="panel p-5">
                <h2 className="flex items-center gap-2 text-sm font-semibold text-white"><ShieldCheck className="h-4 w-4 text-success" /> Evidence and data limits</h2>
                <div className="mt-4 space-y-2 text-[11px] leading-5 text-muted">
                  {audit.missing_data.map((line) => <p key={line}>• {line}</p>)}
                </div>
                <div className="mt-4 border-t border-edge pt-4 text-[10px] text-muted">
                  {audit.meta.private_data_policy || 'User-supplied exports are excluded from this public case study.'}
                </div>
              </div>
            </section>

            <section className="mt-8 panel p-5">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-white"><Globe2 className="h-4 w-4 text-accent" /> Source registry</h2>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-[11px]">
                  <thead className="text-[10px] uppercase tracking-wider text-muted">
                    <tr><th className="p-2">Source</th><th className="p-2">Type</th><th className="p-2">Confidence</th><th className="p-2">Used for</th></tr>
                  </thead>
                  <tbody>
                    {audit.source_registry.map((row) => (
                      <tr key={`${row.source}-${row.type}`} className="border-t border-edge">
                        <td className="p-2 font-medium text-ink">{row.source}</td>
                        <td className="p-2">{row.type}</td>
                        <td className="p-2">{row.confidence}</td>
                        <td className="p-2">{row.used_for.join('; ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="mt-8 flex flex-wrap gap-3">
              <Link to="/" className="btn btn-primary"><ArrowRight className="h-4 w-4" /> Audit your own site in one field</Link>
              <Link to="/case-studies" className="btn">See all published audits</Link>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}
