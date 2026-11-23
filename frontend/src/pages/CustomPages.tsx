import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity, BarChart3, CheckCircle2, Clock3, Database, Download, FileStack,
  FolderPlus, Globe2, Play, Presentation, RefreshCw, Rocket, Search,
  ShieldAlert, Sparkles, TriangleAlert,
} from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ActionModal } from '../components/ActionModal';
import { DataTable, type Row } from '../components/DataTable';
import { Badge, Drawer, ErrorState, JsonBlock, KeyValue, PageHeader, ProvenanceNote, Section, Spinner } from '../components/ui';
import { downloadFile, errorMessage, get, post, unwrapList, waitForJob, type Job } from '../lib/api';
import { compactJson, humanKey, num, titleCase } from '../lib/format';
import type { ModuleAction, ModuleConfig } from '../lib/modules';
import { useApp } from '../state/AppContext';

function useRemote<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(path));
  const load = useCallback(() => {
    if (!path) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    setError('');
    get<T>(path)
      .then((value) => { if (!cancelled) setData(value); })
      .catch((e) => { if (!cancelled) setError(errorMessage(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => load(), [load]);
  return { data, error, loading, reload: load };
}

type PublicAuditData = {
  meta: {
    project_id: number; project_name: string; domain: string; is_demo: boolean;
    generated_at: string; method: string; crawl_id: number | null;
    crawl_name: string | null; crawl_config: Record<string, unknown>; data_kinds: string[];
  };
  coverage: {
    discovered_urls: number; fetched_urls: number; failed_urls: number; excluded_urls: number;
    inventory_urls: number; crawled_inventory_urls: number; robots_respected: boolean;
    javascript_rendering: boolean; sitemap_entries: number; sitemap: Record<string, unknown>;
  };
  robots: {
    url: string; status: number | null; ai_rules: Record<string, unknown>; document_excerpt: string;
  };
  counts: {
    status_codes: Record<string, number>; page_types: Record<string, number>;
    indexable: number; non_indexable: number; redirects: number; schema_pages: number;
    average_content_score: number | null;
  };
  source_registry: { source: string; type: string; confidence: string; used_for: string[] }[];
  missing_data: string[];
  deliverables: string[];
  findings: {
    id: string; title: string; severity: string; category: string;
    affected_count: number; observation: string; recommended_action: string;
    evidence: unknown; source: string[]; confidence: string; limitation: string;
  }[];
  roadmap: {
    month: number; theme: string; objective: string; actions: string[]; deliverables: string[];
    owner: string; success_checks: string[]; without_access: string; with_access: string;
  }[];
  sections: { heading: string; lines: string[] }[];
};

async function runPublicAuditJob(projectId: number, startUrl: string, onUpdate?: (job: Job) => void) {
  const queued = await post<{ job_id: number }>(`/audits/projects/${projectId}/public-audit/start`, {
    start_url: startUrl,
    name: `Public audit · ${startUrl}`,
  });
  const job = await waitForJob(queued.job_id, onUpdate, 900_000);
  if (job.status !== 'succeeded') throw new Error(job.error || job.message || `Audit job ${job.status}`);
  return job;
}

function PublicAuditPanel() {
  const { projectId, project, dataVersion, bumpData, notify } = useApp();
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [actionError, setActionError] = useState('');
  const audit = useRemote<PublicAuditData>(projectId ? `/audits/projects/${projectId}/public-audit` : null, [projectId, dataVersion]);

  const start = async () => {
    if (!projectId || !project?.domain) return;
    setRunning(true);
    setActionError('');
    setJob(null);
    try {
      await runPublicAuditJob(projectId, project.domain, setJob);
      audit.reload();
      bumpData();
      notify('Public audit completed. Audit, PPT and exports are ready.', 'success');
    } catch (e) {
      setActionError(errorMessage(e));
      notify(errorMessage(e), 'error');
    } finally {
      setRunning(false);
    }
  };

  const exportAudit = async (format: string, section: string, fallback: string) => {
    if (!projectId) return;
    try {
      await downloadFile(`/audits/projects/${projectId}/public-audit/export`, { format, section }, fallback);
    } catch (e) { notify(errorMessage(e), 'error'); }
  };

  const exportCrawl = async (format: string) => {
    const crawlId = audit.data?.meta.crawl_id;
    if (!crawlId) return;
    try {
      await downloadFile(`/crawler/runs/${crawlId}/export`, { format }, `serpscope-crawl-observations.${format}`);
    } catch (e) { notify(errorMessage(e), 'error'); }
  };

  const exports = [
    { label: 'Full JSON', format: 'json', section: 'all', file: 'serpscope-full-audit.json' },
    { label: 'PPTX', format: 'pptx', section: 'all', file: 'serpscope-audit.pptx' },
    { label: 'PDF', format: 'pdf', section: 'all', file: 'serpscope-audit.pdf' },
    { label: 'Summary CSV', format: 'csv', section: 'all', file: 'serpscope-audit-summary.csv' },
    { label: 'Summary XLSX', format: 'xlsx', section: 'all', file: 'serpscope-audit-summary.xlsx' },
    { label: 'Findings CSV', format: 'csv', section: 'findings', file: 'serpscope-findings.csv' },
    { label: 'Findings JSON', format: 'json', section: 'findings', file: 'serpscope-findings.json' },
    { label: 'Findings XLSX', format: 'xlsx', section: 'findings', file: 'serpscope-findings.xlsx' },
    { label: 'Roadmap CSV', format: 'csv', section: 'roadmap', file: 'serpscope-6-month-roadmap.csv' },
    { label: 'Roadmap JSON', format: 'json', section: 'roadmap', file: 'serpscope-6-month-roadmap.json' },
    { label: 'Roadmap XLSX', format: 'xlsx', section: 'roadmap', file: 'serpscope-6-month-roadmap.xlsx' },
  ];

  if (!projectId) return <Section title="Public audit"><div className="py-10 text-center text-xs text-muted">Select a project to run a public audit.</div></Section>;

  return (
    <Section
      title="Source-tracked public audit"
      description="One click crawls the selected domain, rebuilds issues and the internal-link graph, then creates a six-month roadmap and presentation pack. No Search Console or Analytics access is required."
      actions={<button className="btn btn-primary text-xs" disabled={running} onClick={() => void start()}>
        {running ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Globe2 className="h-3.5 w-3.5" />}
        {running ? 'Running…' : 'Run public audit'}
      </button>}
    >
      <div className="mb-4"><ProvenanceNote>Public evidence only: robots.txt, sitemaps, observed HTTP responses and explained rules. Vendor metrics are listed as missing, never invented.</ProvenanceNote></div>
      {actionError ? <div className="mb-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">{actionError}</div> : null}
      {running && job ? (
        <div className="mb-4 rounded-lg border border-accent/30 bg-accent/5 p-3">
          <div className="flex items-center justify-between text-xs text-ink"><span>{job.message || job.status}</span><span className="mono">{job.progress}/{job.total || 100}</span></div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5"><div className="h-full bg-accent transition-all" style={{ width: `${job.total ? (job.progress / job.total) * 100 : 20}%` }} /></div>
        </div>
      ) : null}
      {audit.loading ? <Spinner /> : audit.error ? <ErrorState message={audit.error} retry={audit.reload} /> : audit.data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {[
              ['Domain', audit.data.meta.domain],
              ['Fetched URLs', num(audit.data.coverage.fetched_urls)],
              ['Sitemap URLs', num(audit.data.coverage.sitemap_entries)],
              ['Findings', num(audit.data.findings.length)],
              ['Roadmap', `${audit.data.roadmap.length} months`],
            ].map(([label, value]) => (
              <div key={label} className="panel-flat p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</div>
                <div className="mt-1 truncate text-sm font-semibold text-ink" title={String(value)}>{value}</div>
              </div>
            ))}
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted"><ShieldAlert className="h-3.5 w-3.5 text-accent" /> All findings ({audit.data.findings.length})</h3>
              <div className="space-y-2">
                {audit.data.findings.map((finding) => (
                  <details key={finding.id} className="rounded-lg border border-edge bg-canvas/50 p-3">
                    <summary className="cursor-pointer list-none">
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-xs font-semibold text-ink">{finding.title}</div>
                        <Badge>{finding.severity}</Badge>
                      </div>
                      <div className="mt-1 text-[10px] text-muted">{finding.id} · {finding.category} · {finding.affected_count} affected · {finding.confidence}</div>
                    </summary>
                    <div className="mt-2 space-y-1 border-t border-edge pt-2 text-[11px] leading-5 text-muted">
                      <div><span className="font-semibold text-ink">Observation:</span> {finding.observation}</div>
                      <div><span className="font-semibold text-ink">Action:</span> {finding.recommended_action}</div>
                      <div><span className="font-semibold text-ink">Sources:</span> {finding.source.join(', ')}</div>
                      <div><span className="font-semibold text-ink">Limitation:</span> {finding.limitation || 'None stated'}</div>
                      <div className="pt-1"><JsonBlock value={finding.evidence} /></div>
                    </div>
                  </details>
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-muted"><Presentation className="h-3.5 w-3.5 text-accent" /> Six-month roadmap · all months</h3>
              <div className="space-y-2">
                {audit.data.roadmap.map((month) => (
                  <details key={month.month} className="rounded-lg border border-edge bg-canvas/50 p-3">
                    <summary className="cursor-pointer list-none">
                      <div className="text-xs font-semibold text-ink">M{month.month} · {month.theme}</div>
                      <div className="mt-1 text-[10px] text-muted">Owner: {month.owner}</div>
                    </summary>
                    <div className="mt-2 space-y-2 border-t border-edge pt-2 text-[11px] leading-5 text-muted">
                      <div>{month.objective}</div>
                      <div><span className="font-semibold text-ink">Actions:</span><ul className="ml-4 list-disc">{month.actions.map((item) => <li key={item}>{item}</li>)}</ul></div>
                      <div><span className="font-semibold text-ink">Deliverables:</span> {month.deliverables.join(', ')}</div>
                      <div><span className="font-semibold text-ink">Success checks:</span> {month.success_checks.join(' · ')}</div>
                      <div><span className="font-semibold text-ink">Without access:</span> {month.without_access}</div>
                      <div><span className="font-semibold text-ink">With access:</span> {month.with_access}</div>
                    </div>
                  </details>
                ))}
              </div>
              <div className="mt-3 rounded-lg border border-warning/20 bg-warning/5 p-3">
                <div className="text-[11px] font-semibold text-warning">Missing data stated explicitly ({audit.data.missing_data.length})</div>
                <ul className="mt-1 space-y-1 text-[10px] leading-4 text-muted">
                  {audit.data.missing_data.map((item) => <li key={item}>• {item}</li>)}
                </ul>
              </div>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <details className="rounded-lg border border-edge bg-canvas/50 p-3">
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-muted">Coverage, counts and crawl configuration</summary>
              <div className="mt-3 space-y-3">
                {[
                  ['Discovered', num(audit.data.coverage.discovered_urls)],
                  ['Fetched', num(audit.data.coverage.fetched_urls)],
                  ['Failed', num(audit.data.coverage.failed_urls)],
                  ['Excluded', num(audit.data.coverage.excluded_urls)],
                  ['Inventory URLs', num(audit.data.coverage.inventory_urls)],
                  ['Crawled inventory', num(audit.data.coverage.crawled_inventory_urls)],
                  ['Sitemap entries', num(audit.data.coverage.sitemap_entries)],
                  ['Robots respected', String(audit.data.coverage.robots_respected)],
                  ['JavaScript rendering', String(audit.data.coverage.javascript_rendering)],
                  ['Indexable', num(audit.data.counts.indexable)],
                  ['Non-indexable', num(audit.data.counts.non_indexable)],
                  ['Redirects', num(audit.data.counts.redirects)],
                  ['Schema pages', num(audit.data.counts.schema_pages)],
                  ['Average content score', String(audit.data.counts.average_content_score ?? 'n/a')],
                ].map(([label, value]) => <KeyValue key={label} label={label} value={value} />)}
                <JsonBlock value={{ status_codes: audit.data.counts.status_codes, page_types: audit.data.counts.page_types, sitemap: audit.data.coverage.sitemap, crawl_config: audit.data.meta.crawl_config, data_kinds: audit.data.meta.data_kinds }} />
              </div>
            </details>
            <details className="rounded-lg border border-edge bg-canvas/50 p-3">
              <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-muted">Robots evidence and source registry</summary>
              <div className="mt-3 space-y-3">
                <div className="text-[11px] text-muted"><span className="font-semibold text-ink">Robots URL:</span> {audit.data.robots.url} · status {String(audit.data.robots.status ?? 'n/a')}</div>
                <JsonBlock value={audit.data.robots.ai_rules} />
                <pre className="max-h-64 overflow-auto rounded border border-edge bg-canvas p-2 text-[10px] leading-4 text-muted">{audit.data.robots.document_excerpt || 'No robots.txt excerpt captured.'}</pre>
                <JsonBlock value={audit.data.source_registry} />
                <div className="text-[11px] font-semibold text-ink">Deliverables</div>
                <ul className="ml-4 list-disc text-[11px] text-muted">{audit.data.deliverables.map((item) => <li key={item}>{item}</li>)}</ul>
              </div>
            </details>
          </div>

          <details className="mt-4 rounded-lg border border-edge bg-canvas/50 p-3">
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-muted">Report sections and full audit JSON</summary>
            <div className="mt-3 space-y-3">
              {audit.data.sections.map((section) => (
                <div key={section.heading}>
                  <div className="text-xs font-semibold text-ink">{section.heading}</div>
                  <ul className="mt-1 ml-4 list-disc text-[11px] leading-5 text-muted">{section.lines.map((line) => <li key={line}>{line}</li>)}</ul>
                </div>
              ))}
              <div className="text-xs font-semibold text-ink">Complete API payload</div>
              <JsonBlock value={audit.data} />
            </div>
          </details>

          <div className="mt-4 flex flex-wrap gap-2 border-t border-edge pt-4">
            <span className="mr-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-muted"><Download className="h-3.5 w-3.5" /> Downloads</span>
            {exports.map((item) => (
              <button key={item.label} className="btn text-[11px]" onClick={() => void exportAudit(item.format, item.section, item.file)}>{item.label}</button>
            ))}
            {audit.data.meta.crawl_id ? (
              <>
                <button className="btn text-[11px]" onClick={() => void exportCrawl('csv')}>Raw crawl CSV</button>
                <button className="btn text-[11px]" onClick={() => void exportCrawl('json')}>Raw crawl JSON</button>
                <button className="btn text-[11px]" onClick={() => void exportCrawl('xlsx')}>Raw crawl XLSX</button>
              </>
            ) : null}
          </div>
          <div className="mt-2 text-[10px] text-muted">Generated {audit.data.meta.generated_at.slice(0, 16).replace('T', ' ')} UTC · crawl {String(audit.data.meta.crawl_id ?? 'n/a')} · robots respected: {String(audit.data.coverage.robots_respected)} · JS rendering: {String(audit.data.coverage.javascript_rendering)}</div>
        </>
      ) : <div className="py-10 text-center text-xs text-muted">No audit available yet. Run one to create source-tracked findings and exports.</div>}
    </Section>
  );
}

/* ---------------------------------- Overview --------------------------------- */

type OverviewData = {
  project: { id: number; name: string; domain: string; is_demo?: boolean };
  cards: Record<string, number>;
  latest_crawl: { discovered: number; crawled: number; failed: number; summary: Record<string, unknown> } | null;
  data_composition: { data_kind: string; urls: number }[];
  provenance_note: string;
};

function OverviewPage() {
  const { projectId, jobs, runAction, dataVersion } = useApp();
  const overview = useRemote<OverviewData>(projectId ? `/projects/${projectId}/overview` : null, [projectId, dataVersion]);
  const issues = useRemote<{ items: Row[] }>(projectId ? `/technical/issues?project_id=${projectId}&limit=6` : null, [projectId, dataVersion]);
  const data = overview.data;

  const cards = [
    { key: 'urls_crawled', label: 'URLs in inventory', icon: Database, tone: 'sky' as const },
    { key: 'critical_issues', label: 'Critical issues', icon: ShieldAlert, tone: 'rose' as const },
    { key: 'high_priority_issues', label: 'High-priority issues', icon: TriangleAlert, tone: 'amber' as const },
    { key: 'high_priority_opportunities', label: 'P0/P1 opportunities', icon: Sparkles, tone: 'violet' as const },
    { key: 'orphan_pages', label: 'Orphan pages', icon: Activity, tone: 'violet' as const },
    { key: 'keyword_mappings_completed', label: 'Keyword mappings', icon: Search, tone: 'sky' as const },
    { key: 'content_opportunities', label: 'Content opportunities', icon: FileStack, tone: 'violet' as const },
    { key: 'active_jobs', label: 'Active jobs', icon: Clock3, tone: 'emerald' as const },
  ];

  const quickActions: { label: string; description: string; method: 'post'; path: string; icon: typeof Activity }[] = [
    { label: 'Detect technical issues', description: 'Re-run all rules with evidence', method: 'post', path: `/technical/detect?project_id=${projectId}`, icon: ShieldAlert },
    { label: 'Detect orphan pages', description: 'Reconcile all URL sources', method: 'post', path: `/orphans/detect?project_id=${projectId}`, icon: Activity },
    { label: 'Analyse internal links', description: 'Generate reviewable suggestions', method: 'post', path: `/internal-links/analyse?project_id=${projectId}`, icon: Activity },
    { label: 'Generate report', description: 'Build a board-ready report', method: 'post', path: `/analytics/reports/generate?project_id=${projectId}`, icon: BarChart3 },
  ];

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow="Command centre · live database view"
        title={data ? `${data.project.name} overview` : 'Portfolio overview'}
        description={data ? `${data.project.domain} · ${data.project.is_demo ? 'Synthetic demonstration project — metrics are not real client performance.' : 'Imported and observed data with full provenance.'}` : 'A single source of truth for crawl coverage, issue pressure and opportunity volume.'}
        actions={<button className="btn" onClick={overview.reload}><RefreshCw className="h-3.5 w-3.5" /> Refresh</button>}
      />
      <div className="mb-5"><ProvenanceNote>{data?.provenance_note || 'Figures are queried from the database. Demo projects contain synthetic records only.'}</ProvenanceNote></div>

      {overview.loading ? <Section><Spinner /></Section> : overview.error ? <Section><ErrorState message={overview.error} retry={overview.reload} /></Section> : data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {cards.map((card) => {
              const Icon = card.icon;
              return (
                <div key={card.key} className="panel p-4 transition hover:border-accent/30">
                  <div className="flex items-start justify-between">
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">{card.label}</span>
                    <Icon className="h-4 w-4 text-muted" />
                  </div>
                  <div className="mt-3 text-2xl font-bold text-white">{num(data.cards[card.key] ?? 0)}</div>
                </div>
              );
            })}
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <Section title="URL data composition" description="Source types are never blended silently." className="lg:col-span-2">
              {data.data_composition.length ? (
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data.data_composition} margin={{ top: 8, right: 8, bottom: 4, left: -14 }}>
                      <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="data_kind" axisLine={false} tickLine={false} />
                      <YAxis axisLine={false} tickLine={false} />
                      <Tooltip contentStyle={{ background: '#131a27', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }} />
                      <Bar dataKey="urls" fill="#38bdf8" radius={[5, 5, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <div className="py-16 text-center text-sm text-muted">No URLs generated yet. Visit Demo Centre to create a labelled dataset.</div>}
            </Section>

            <Section title="Latest crawl" description="Raw observations remain available for audit.">
              {data.latest_crawl ? (
                <div className="space-y-3">
                  <KeyValue label="Discovered" value={num(data.latest_crawl.discovered)} />
                  <KeyValue label="Crawled" value={num(data.latest_crawl.crawled)} />
                  <KeyValue label="Failed" value={num(data.latest_crawl.failed)} />
                  <KeyValue label="Summary" value={<span className="mono text-xs text-slate-400">{compactJson(data.latest_crawl.summary, 220)}</span>} />
                </div>
              ) : <div className="py-10 text-center text-sm text-muted">No crawl recorded for this project.</div>}
            </Section>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-3">
            <Section title="Quick automation" description="Every action is a tracked background job." className="lg:col-span-2">
              <div className="grid gap-3 sm:grid-cols-2">
                {quickActions.map((action) => {
                  const Icon = action.icon;
                  return (
                    <button key={action.label} className="group rounded-lg border border-edge bg-canvas/50 p-3 text-left transition hover:border-accent/40 hover:bg-accent/5" onClick={() => void runAction(action.method, action.path)}>
                      <div className="flex items-center gap-2 text-sm font-medium text-ink"><Icon className="h-4 w-4 text-accent" /> {action.label}</div>
                      <div className="mt-1 text-xs text-muted">{action.description}</div>
                    </button>
                  );
                })}
              </div>
            </Section>

            <Section title="Active jobs" description="Live state polled from the jobs table.">
              {jobs.filter((job) => !['succeeded', 'failed', 'cancelled'].includes(job.status)).length === 0 ? (
                <div className="py-10 text-center text-xs text-muted">No jobs running.</div>
              ) : (
                <div className="space-y-2">
                  {jobs.filter((job) => !['succeeded', 'failed', 'cancelled'].includes(job.status)).slice(0, 5).map((job: Job) => (
                    <div key={job.id} className="rounded-lg border border-edge p-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs text-ink">{job.name}</span>
                        <Badge tone="warn">{job.status}</Badge>
                      </div>
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5">
                        <div className="h-full bg-accent" style={{ width: `${job.total ? (job.progress / job.total) * 100 : 20}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>
          </div>

          <div className="mt-5">
            <PublicAuditPanel />
          </div>

          <div className="mt-5">
            <Section title="Priority issue groups" description="Ranked by transparent weighted scores.">
              {issues.loading ? <Spinner /> : issues.error ? <ErrorState message={issues.error} /> : (
                <DataTable
                  rows={unwrapList(issues.data).items}
                  onExpand={() => undefined}
                  expandLabel="Open"
                  maxColumns={7}
                />
              )}
            </Section>
          </div>
        </>
      ) : null}
    </div>
  );
}

/* ---------------------------------- Projects ---------------------------------- */

function ProjectsPage() {
  const { projects, projectId, setProjectId, refreshProjects, dataVersion, notify } = useApp();
  const navigate = useNavigate();
  const [name, setName] = useState('New client project');
  const [domain, setDomain] = useState('demo.example.com');
  const [creating, setCreating] = useState(false);
  const tasks = useRemote<{ items: Row[] }>(projectId ? `/projects/${projectId}/tasks` : null, [projectId, dataVersion]);
  const audit = useRemote<{ items: Row[] }>(projectId ? `/projects/${projectId}/audit-log` : null, [projectId, dataVersion]);
  const [tab, setTab] = useState('tasks');

  const create = async () => {
    setCreating(true);
    try {
      await post('/projects', { name, domain, description: 'Created from the Projects workspace' });
      await refreshProjects();
      notify('Project created', 'success');
    } catch (e) { notify(errorMessage(e), 'error'); }
    finally { setCreating(false); }
  };

  return (
    <div className="animate-fade-in">
      <PageHeader eyebrow="Command centre" title="Projects" description="Create, switch and govern client workspaces. All writes are recorded in the audit log." />
      <div className="grid gap-5 lg:grid-cols-3">
        <Section title="Workspaces" description={`${projects.length} project${projects.length === 1 ? '' : 's'} available`}>
          <div className="space-y-2">
            {projects.map((project) => (
              <button key={project.id} onClick={() => setProjectId(project.id)} className={`w-full rounded-lg border p-3 text-left transition ${project.id === projectId ? 'border-accent/50 bg-accent/10' : 'border-edge bg-canvas/40 hover:border-accent/30'}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-ink">{project.name}</span>
                  {project.id === projectId ? <CheckCircle2 className="h-4 w-4 shrink-0 text-accent" /> : null}
                </div>
                <div className="mt-1 truncate text-xs text-muted">{project.domain}</div>
              </button>
            ))}
          </div>
        </Section>

        <Section title="Create project" description="A blank project starts with no data until you import or generate it.">
          <div className="space-y-3">
            <div><label className="label">Project name</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
            <div><label className="label">Domain</label><input className="input" value={domain} onChange={(e) => setDomain(e.target.value)} /></div>
            <button className="btn btn-primary w-full" disabled={creating || !name || !domain} onClick={() => void create()}><FolderPlus className="h-4 w-4" /> Create workspace</button>
            <button className="btn w-full" onClick={() => navigate('/demo')}><Rocket className="h-4 w-4" /> Generate demo dataset</button>
          </div>
        </Section>

        <Section title="Selected project" description="Configuration and delivery context.">
          {projectId ? (
            <div className="space-y-1">
              <KeyValue label="Project ID" value={projectId} />
              <KeyValue label="Name" value={projects.find((p) => p.id === projectId)?.name} />
              <KeyValue label="Domain" value={projects.find((p) => p.id === projectId)?.domain} />
              <KeyValue label="Status" value={projects.find((p) => p.id === projectId)?.status} />
            </div>
          ) : <div className="py-10 text-center text-xs text-muted">No project selected.</div>}
        </Section>
      </div>

      <div className="mt-5">
        <div className="mb-3 flex gap-2">
          {['tasks', 'audit'].map((key) => (
            <button key={key} className={`btn text-xs ${tab === key ? 'btn-primary' : ''}`} onClick={() => setTab(key)}>{key === 'tasks' ? 'Delivery tasks' : 'Audit trail'}</button>
          ))}
        </div>
        <Section>
          {tab === 'tasks' ? (
            tasks.loading ? <Spinner /> : <DataTable rows={unwrapList(tasks.data).items} maxColumns={8} />
          ) : (
            audit.loading ? <Spinner /> : <DataTable rows={unwrapList(audit.data).items} maxColumns={8} />
          )}
        </Section>
      </div>
    </div>
  );
}

/* ---------------------------------- Crawler ----------------------------------- */

function CrawlerPage() {
  const { projectId, project, dataVersion, bumpData, notify } = useApp();
  const [tab, setTab] = useState('runs');
  const [action, setAction] = useState<ModuleAction | null>(null);
  const [selected, setSelected] = useState<Row | null>(null);
  const [observations, setObservations] = useState<Row[]>([]);
  const [loadingObs, setLoadingObs] = useState(false);
  const [auditRunning, setAuditRunning] = useState(false);
  const [auditStatus, setAuditStatus] = useState('');
  const runs = useRemote<{ items: Row[] }>(projectId ? `/crawler/runs?project_id=${projectId}` : null, [projectId, dataVersion]);
  const defaults = useRemote<unknown>('/crawler/config-defaults', []);

  const openObservations = async (row: Row) => {
    setSelected(row);
    setObservations([]);
    setLoadingObs(true);
    try {
      const data = await get<unknown>(`/crawler/runs/${row.id}/observations?limit=100`);
      setObservations(unwrapList<Row>(data).items);
    } catch { setObservations([]); }
    finally { setLoadingObs(false); }
  };

  const runAudit = async () => {
    if (!projectId || !project?.domain) return;
    setAuditRunning(true);
    setAuditStatus('Queuing public audit…');
    try {
      const job = await runPublicAuditJob(projectId, project.domain, (update) => setAuditStatus(update.message || update.status));
      setAuditStatus(`Completed ${job.progress}/${job.total || 100}`);
      bumpData();
      runs.reload();
      notify('Public audit completed. Open Overview for the audit panel and exports.', 'success');
    } catch (e) {
      setAuditStatus(errorMessage(e));
      notify(errorMessage(e), 'error');
    } finally { setAuditRunning(false); }
  };

  return (
    <div className="animate-fade-in">
      <PageHeader eyebrow="Discovery" title="Crawler" description="Robots-aware, concurrency-limited crawling. Raw HTTP observations are stored separately from interpreted fields and can be exported." actions={
        <>
          <button className="btn" onClick={() => setAction({ label: 'Start crawl', method: 'post', path: `/crawler/start?project_id=${projectId}`, defaultBody: { config: { start_url: project?.domain || 'https://demo.example.com/', max_urls: 500, max_depth: 4, concurrency: 2, crawl_delay: 0.5, respect_robots: true, follow_external: false, allow_private: false } }, hint: `Only crawl domains you are authorised to test. Selected: ${project?.domain || 'none'}.` })}><Play className="h-3.5 w-3.5" /> Start crawl</button>
          <button className="btn btn-primary" disabled={auditRunning || !project?.domain} onClick={() => void runAudit()}>
            {auditRunning ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Globe2 className="h-3.5 w-3.5" />}
            {auditRunning ? 'Auditing…' : 'Run public audit'}
          </button>
        </>
      } />
      <div className="mb-5"><ProvenanceNote>Crawler respects robots.txt and crawl delay, blocks private/loopback targets, supports cancellation, and records every raw observation.</ProvenanceNote></div>
      {auditStatus ? <div className="mb-4 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 text-xs text-ink">{auditStatus}</div> : null}
      <div className="mb-4 flex gap-2">
        {['runs', 'defaults'].map((key) => <button key={key} className={`btn text-xs ${tab === key ? 'btn-primary' : ''}`} onClick={() => setTab(key)}>{key === 'runs' ? 'Crawl runs' : 'Safety defaults'}</button>)}
      </div>
      {tab === 'runs' ? (
        <Section>
          {runs.loading ? <Spinner /> : runs.error ? <ErrorState message={runs.error} /> : (
            <DataTable rows={unwrapList(runs.data).items} onExpand={(row) => void openObservations(row)} expandLabel="Observations" maxColumns={9} />
          )}
        </Section>
      ) : (
        <Section title="Enforced worker defaults">
          {defaults.loading ? <Spinner /> : defaults.error ? <ErrorState message={defaults.error} /> : (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {Object.entries((defaults.data && typeof defaults.data === 'object' ? defaults.data : {}) as Record<string, unknown>).map(([key, value]) => (
                <div key={key} className="panel-flat p-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">{humanKey(key)}</div>
                  <div className="mt-1.5 text-sm text-ink">{typeof value === 'object' ? compactJson(value, 180) : String(value)}</div>
                </div>
              ))}
            </div>
          )}
        </Section>
      )}
      <Drawer open={Boolean(selected)} title={`Observations · run ${selected?.id ?? ''}`} onClose={() => setSelected(null)}>
        {loadingObs ? <Spinner /> : observations.length === 0 ? <div className="py-12 text-center text-sm text-muted">No observations recorded for this run.</div> : (
          <DataTable rows={observations} maxColumns={8} />
        )}
      </Drawer>
      <ActionModal action={action} projectId={projectId} onClose={() => setAction(null)} />
    </div>
  );
}

/* --------------------------------- Demo Centre -------------------------------- */

type Scenario = {
  key: string; title: string; question: string; context: string; challenge: string;
  steps: string[]; modules: string[]; expected_findings: string[];
  interpretation: string; recommended_actions: string[]; limitations: string;
  interview_explanation: string; dataset_info: Record<string, unknown>;
};

function DemoCentrePage() {
  const { projectId, runAction, refreshProjects, notify, dataVersion } = useApp();
  const scenarios = useRemote<{ items: Scenario[] }>('/demo/scenarios', [dataVersion]);
  const [selected, setSelected] = useState<Scenario | null>(null);
  const [size, setSize] = useState(1000);
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (scenarios.data?.items?.length && !selected) setSelected(scenarios.data.items[0]);
  }, [scenarios.data, selected]);

  const filtered = (scenarios.data?.items ?? []).filter((scenario) => `${scenario.title} ${scenario.question}`.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="animate-fade-in">
      <PageHeader eyebrow="Automation · interview toolkit" title="Demo Centre" description="Twelve scenario definitions with deterministic synthetic datasets. Each card states its limitations so nothing is mistaken for real performance." />
      <div className="mb-5"><ProvenanceNote>All generated clicks, traffic, revenue and keyword metrics are synthetic. The platform labels them at record level and in every export.</ProvenanceNote></div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Section title="Scenarios" description="Pick a prompt to see the full analyst walkthrough." className="lg:col-span-1">
          <input className="input mb-3 text-xs" placeholder="Filter scenarios…" value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="max-h-[620px] space-y-2 overflow-y-auto pr-1">
            {scenarios.loading ? <Spinner /> : scenarios.error ? <ErrorState message={scenarios.error} /> : filtered.map((scenario, index) => (
              <button key={scenario.key} onClick={() => setSelected(scenario)} className={`w-full rounded-lg border p-3 text-left transition ${selected?.key === scenario.key ? 'border-accent/50 bg-accent/10' : 'border-edge bg-canvas/40 hover:border-accent/30'}`}>
                <div className="flex items-start gap-2">
                  <span className="mono text-[10px] text-muted">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <div className="text-xs font-semibold text-ink">{scenario.title}</div>
                    <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-muted">{scenario.question}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </Section>

        <Section title={selected?.title || 'Scenario detail'} description={selected?.challenge} className="lg:col-span-2">
          {!selected ? <Spinner /> : (
            <div className="space-y-5">
              <div className="rounded-lg border border-accent/20 bg-accent/5 p-3 text-sm italic leading-6 text-slate-300">“{selected.question}”</div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Context</h3>
                  <p className="text-sm leading-6 text-slate-300">{selected.context}</p>
                </div>
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Interpretation</h3>
                  <p className="text-sm leading-6 text-slate-300">{selected.interpretation}</p>
                </div>
              </div>
              <div>
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Execution steps</h3>
                <ol className="space-y-1.5">
                  {selected.steps.map((step, index) => (
                    <li key={step} className="flex items-start gap-2 text-sm text-slate-300"><span className="mono text-accent">{String(index + 1).padStart(2, '0')}</span>{step}</li>
                  ))}
                </ol>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Expected findings</h3>
                  <div className="flex flex-wrap gap-1.5">{selected.expected_findings.map((item) => <Badge key={item}>{item}</Badge>)}</div>
                </div>
                <div>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Modules</h3>
                  <div className="flex flex-wrap gap-1.5">{selected.modules.map((item) => <Badge key={item} tone="good">{item}</Badge>)}</div>
                </div>
              </div>
              <div className="rounded-lg border border-warning/20 bg-warning/5 p-3">
                <div className="text-xs font-semibold text-warning">Limitations</div>
                <p className="mt-1 text-xs leading-5 text-muted">{selected.limitations}</p>
              </div>
              <div className="rounded-lg border border-success/20 bg-success/5 p-3">
                <div className="text-xs font-semibold text-success">Interview explanation</div>
                <p className="mt-1 text-xs leading-5 text-slate-300">{selected.interview_explanation}</p>
              </div>
              <div className="rounded-lg border border-edge bg-canvas/50 p-3">
                <div className="text-xs font-semibold text-ink">Dataset profile</div>
                <div className="mono mt-1.5 text-xs text-muted">{compactJson(selected.dataset_info, 400)}</div>
              </div>
            </div>
          )}
        </Section>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Section title="Generate synthetic dataset" description="Creates a new labelled project with deterministic planted issues.">
          <div className="space-y-3">
            <div><label className="label">URLs</label><input className="input" type="number" min={100} max={200000} step={100} value={size} onChange={(e) => setSize(Number(e.target.value))} /></div>
            <button className="btn btn-primary w-full" onClick={() => void runAction('post', '/demo/generate', { size, label: `Interview demo ${new Date().toISOString().slice(0, 10)}` }).then(() => refreshProjects())}><Rocket className="h-4 w-4" /> Generate dataset</button>
            <p className="text-[11px] leading-4 text-muted">Sizes above 100,000 are intended for scale demonstration and may take several minutes.</p>
          </div>
        </Section>
        <Section title="Reset demo data" description="Removes generated demo records and re-seeds the scenario catalogue.">
          <button className="btn btn-danger w-full" onClick={() => void runAction('post', '/demo/reset', {})}>Reset demo environment</button>
        </Section>
        <Section title="Selected workspace" description="Dataset jobs operate independently of the selected project.">
          <KeyValue label="Project ID" value={projectId ?? '—'} />
          <KeyValue label="Scenarios loaded" value={scenarios.data?.items?.length ?? 0} />
          <button className="btn mt-3 w-full" onClick={() => { void refreshProjects(); notify('Workspace list refreshed'); }}><RefreshCw className="h-3.5 w-3.5" /> Refresh projects</button>
        </Section>
      </div>
    </div>
  );
}

/* ------------------------------- Settings / Docs ------------------------------- */

const DOC_INDEX = [
  ['README.md', 'Platform overview and feature map'],
  ['INSTALLATION.md', 'Local, Docker and production setup'],
  ['ARCHITECTURE.md', 'System boundaries and job lifecycle'],
  ['DATABASE_SCHEMA.md', 'Tables, indexes and provenance fields'],
  ['API_DOCUMENTATION.md', 'Endpoint catalogue and examples'],
  ['CRAWLER_METHODOLOGY.md', 'Robots, delays, SSRF and raw observations'],
  ['ORPHAN_DETECTION_METHODOLOGY.md', 'Source union and classification rules'],
  ['KEYWORD_MAPPING_METHODOLOGY.md', 'Intent, clustering and cannibalisation'],
  ['PRIORITY_SCORING_METHODOLOGY.md', 'Weights, components and explanations'],
  ['INTEGRATIONS.md', 'Provider registry and credential handling'],
  ['SECURITY.md', 'Auth, RBAC, SSRF and secrets'],
  ['TESTING.md', 'Test strategy and commands'],
  ['DEPLOYMENT.md', 'Containers, migrations and operations'],
  ['DEMO_GUIDE.md', 'Running the synthetic dataset'],
  ['INTERVIEW_DEMONSTRATIONS.md', 'Twelve scenario walkthroughs'],
  ['ROADMAP.md', 'Delivered, partial and planned work'],
  ['CHANGELOG.md', 'Version history'],
];

function SettingsDocsPage() {
  const dataKinds = useRemote<{ key: string; label: string; description: string }[]>('/meta/data-kinds', []);
  const methods = useRemote<Record<string, string>>('/meta/methodologies', []);
  const columns = useRemote<Record<string, string[]>>('/meta/export-columns', []);
  const [section, setSection] = useState('provenance');

  return (
    <div className="animate-fade-in">
      <PageHeader eyebrow="Automation · control plane" title="Settings & Documentation" description="Provenance vocabulary, scoring methodologies, export schemas and the full implementation documentation index." />
      <div className="mb-4 flex flex-wrap gap-2">
        {['provenance', 'methodologies', 'exports', 'docs'].map((key) => (
          <button key={key} className={`btn text-xs ${section === key ? 'btn-primary' : ''}`} onClick={() => setSection(key)}>{titleCase(key)}</button>
        ))}
      </div>

      {section === 'provenance' ? (
        <Section title="Data-kind vocabulary" description="Every stored record declares what it is. These labels flow into UI badges and exports.">
          {dataKinds.loading ? <Spinner /> : dataKinds.error ? <ErrorState message={dataKinds.error} /> : (
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {(dataKinds.data ?? []).map((kind) => (
                <div key={kind.key} className="panel-flat p-4">
                  <div className="flex items-center justify-between"><span className="text-sm font-semibold text-ink">{kind.label}</span><Badge>{kind.key}</Badge></div>
                  <p className="mt-2 text-xs leading-5 text-muted">{kind.description}</p>
                </div>
              ))}
            </div>
          )}
        </Section>
      ) : null}

      {section === 'methodologies' ? (
        <Section title="Methodology summaries" description="Detailed versions ship in the docs directory.">
          {methods.loading ? <Spinner /> : methods.error ? <ErrorState message={methods.error} /> : (
            <div className="space-y-3">
              {Object.entries(methods.data ?? {}).map(([key, value]) => (
                <div key={key} className="rounded-lg border border-edge bg-canvas/50 p-3">
                  <div className="text-xs font-semibold text-accent">{humanKey(key)}</div>
                  <p className="mt-1 text-sm leading-6 text-slate-300">{value}</p>
                </div>
              ))}
            </div>
          )}
        </Section>
      ) : null}

      {section === 'exports' ? (
        <Section title="Export schemas" description="Column lists exposed by the API for auditable downloads.">
          {columns.loading ? <Spinner /> : columns.error ? <ErrorState message={columns.error} /> : (
            <div className="grid gap-3 md:grid-cols-2">
              {Object.entries(columns.data ?? {}).map(([key, value]) => (
                <div key={key} className="panel-flat p-4">
                  <div className="text-xs font-semibold text-ink">{humanKey(key)}</div>
                  <div className="mt-2 flex flex-wrap gap-1">{value.map((column) => <Badge key={column}>{column}</Badge>)}</div>
                </div>
              ))}
            </div>
          )}
        </Section>
      ) : null}

      {section === 'docs' ? (
        <Section title="Documentation index" description="Repository documentation is maintained alongside the code in /docs.">
          <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
            {DOC_INDEX.map(([file, description]) => (
              <div key={file} className="flex items-start gap-2 rounded-lg border border-edge bg-canvas/50 p-3">
                <FileStack className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <div>
                  <div className="mono text-xs text-ink">{file}</div>
                  <div className="mt-0.5 text-[11px] leading-4 text-muted">{description}</div>
                </div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}
    </div>
  );
}

/* --------------------------------- Dispatcher --------------------------------- */

export function CustomPage({ module }: { module: ModuleConfig }) {
  switch (module.custom) {
    case 'overview': return <OverviewPage />;
    case 'projects': return <ProjectsPage />;
    case 'crawler': return <CrawlerPage />;
    case 'demo': return <DemoCentrePage />;
    case 'settings': return <SettingsDocsPage />;
    default: return <ErrorState message="Custom page not implemented" />;
  }
}
