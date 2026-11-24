import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, Bell, CheckCircle2, ChevronDown, CircleDot, FlaskConical, Menu, X,
  AlertTriangle, Loader2, LogOut, ShieldCheck,
} from 'lucide-react';
import { MODULES, MODULE_GROUPS } from '../lib/modules';
import { clearToken, get } from '../lib/api';
import { useApp } from '../state/AppContext';
import { Badge } from './ui';
import { LiveVisitors } from './LiveVisitors';

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="relative grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-sky-400 to-violet-600 text-white shadow-glow">
        <Activity className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-bold tracking-tight text-white">SERPScope</div>
        <div className="text-[10px] uppercase tracking-[0.18em] text-muted">Enterprise intelligence</div>
      </div>
    </div>
  );
}

function JobPanel({ onClose }: { onClose: () => void }) {
  const { jobs } = useApp();
  return (
    <div className="absolute right-0 top-12 z-50 w-[380px] rounded-xl border border-edge bg-elevated p-3 shadow-2xl">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-semibold text-white">Background jobs</span>
        <button className="btn btn-ghost p-1" onClick={onClose}><X className="h-4 w-4" /></button>
      </div>
      {jobs.length === 0 ? <div className="py-6 text-center text-xs text-muted">No jobs recorded yet.</div> : (
        <div className="max-h-96 space-y-2 overflow-y-auto">
          {jobs.map((job) => {
            const done = ['succeeded', 'failed', 'cancelled'].includes(job.status);
            const Icon = job.status === 'succeeded' ? CheckCircle2 : job.status === 'failed' || job.status === 'cancelled' ? AlertTriangle : Loader2;
            const color = job.status === 'succeeded' ? 'text-success' : job.status === 'failed' || job.status === 'cancelled' ? 'text-danger' : 'text-accent';
            return (
              <div key={job.id} className="rounded-lg border border-edge bg-canvas/60 p-2.5">
                <div className="flex items-start gap-2">
                  <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color} ${done ? '' : 'animate-spin'}`} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-medium text-ink">{job.name}</div>
                    <div className="truncate text-[11px] text-muted">{job.message || job.job_type}</div>
                  </div>
                  <Badge tone={job.status === 'succeeded' ? 'good' : job.status === 'failed' || job.status === 'cancelled' ? 'bad' : 'warn'}>{job.status}</Badge>
                </div>
                {!done && job.total > 0 ? (
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5">
                    <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.min(100, (job.progress / job.total) * 100)}%` }} />
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

type AuditRibbonData = {
  meta: { domain: string; generated_at: string };
  coverage: { discovered_urls: number; fetched_urls: number; sitemap_entries: number };
  findings: unknown[];
  derived_evidence?: { competitors?: number; keywords?: number; keyword_gaps?: number; keyword_mappings?: number };
};

function EvidenceRibbon() {
  const { projectId, dataVersion } = useApp();
  const [audit, setAudit] = useState<AuditRibbonData | null>(null);

  useEffect(() => {
    if (!projectId) { setAudit(null); return; }
    let cancelled = false;
    get<AuditRibbonData>(`/audits/projects/${projectId}/public-audit`)
      .then((value) => { if (!cancelled) setAudit(value); })
      .catch(() => { if (!cancelled) setAudit(null); });
    return () => { cancelled = true; };
  }, [projectId, dataVersion]);

  if (!audit) return null;
  const metrics = [
    ['Fetched', audit.coverage.fetched_urls],
    ['Discovered', audit.coverage.discovered_urls],
    ['Sitemap', audit.coverage.sitemap_entries],
    ['Findings', audit.findings.length],
    ['Competitors', audit.derived_evidence?.competitors ?? 0],
    ['Keywords', audit.derived_evidence?.keywords ?? 0],
    ['Gaps', audit.derived_evidence?.keyword_gaps ?? 0],
  ];
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-accent/20 bg-gradient-to-r from-accent/[0.08] to-violet-500/[0.06] px-4 py-2.5">
      <span className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-accent">
        <Activity className="h-3.5 w-3.5" /> Live public evidence
      </span>
      {metrics.map(([label, value]) => (
        <span key={String(label)} className="text-[11px] text-muted">
          <span className="font-bold text-ink">{Number(value).toLocaleString()}</span> {label}
        </span>
      ))}
      <span className="min-w-0 flex-1 truncate text-[10px] text-muted" title={audit.meta.domain}>{audit.meta.domain}</span>
      <Link to="/overview#gap-fix-center" className="text-[11px] font-semibold text-accent hover:underline">Gap &amp; Fix Center →</Link>
    </div>
  );
}

export function Layout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [jobsOpen, setJobsOpen] = useState(false);
  const [user, setUser] = useState<{ full_name: string; global_role: string } | null>(null);
  const location = useLocation();
  const navigate = useNavigate();
  const { projects, projectId, setProjectId, loadingProjects, jobs, toast } = useApp();

  useEffect(() => {
    get<{ full_name: string; global_role: string }>('/auth/me').then(setUser).catch(() => undefined);
  }, []);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  const activeCount = jobs.filter((job) => !['succeeded', 'failed', 'cancelled'].includes(job.status)).length;

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="border-b border-edge px-5 py-4"><Logo /></div>
      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
        {MODULE_GROUPS.map((group) => (
          <div key={group}>
            <div className="mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted/70">{group}</div>
            <div className="space-y-0.5">
              {MODULES.filter((m) => m.group === group).map((module) => {
                const Icon = module.icon;
                return (
                  <NavLink
                    key={module.id}
                    to={`/${module.id}`}
                    className={({ isActive }) => `group flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition ${isActive ? 'bg-accent/12 text-white shadow-[inset_2px_0_0_0_#38bdf8]' : 'text-muted hover:bg-white/5 hover:text-ink'}`}
                  >
                    <Icon className="h-4 w-4 shrink-0 opacity-80 group-hover:opacity-100" />
                    <span className="truncate">{module.short}</span>
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="border-t border-edge p-3">
        <div className="rounded-lg border border-edge bg-gradient-to-br from-sky-500/10 to-violet-500/10 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-white"><ShieldCheck className="h-4 w-4 text-accent" /> Evidence-first by design</div>
          <p className="mt-1.5 text-[11px] leading-4 text-muted">Source · timestamp · methodology · quality status on every metric.</p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-canvas">
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-[248px] border-r border-edge bg-panel/95 backdrop-blur lg:block">{sidebar}</aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/70" onClick={() => setMobileOpen(false)} />
          <aside className="relative h-full w-[270px] border-r border-edge bg-panel">{sidebar}</aside>
        </div>
      ) : null}

      <div className="lg:pl-[248px]">
        <header className="sticky top-0 z-30 border-b border-edge bg-canvas/85 backdrop-blur-xl">
          <div className="flex h-16 items-center gap-3 px-4 md:px-7">
            <button className="btn btn-ghost p-2 lg:hidden" onClick={() => setMobileOpen(true)}><Menu className="h-5 w-5" /></button>
            <div className="relative min-w-[180px] max-w-xs flex-1">
              <select
                className="input appearance-none py-2 pl-3 pr-8 text-xs"
                value={projectId ?? ''}
                onChange={(e) => setProjectId(Number(e.target.value))}
                disabled={loadingProjects}
              >
                {projects.length === 0 ? <option value="">No projects</option> : null}
                {projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.domain}</option>)}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
            </div>
            <div className="ml-auto flex items-center gap-2">
              <LiveVisitors />
              <NavLink to="/demo" className="btn btn-ghost hidden text-xs sm:inline-flex"><FlaskConical className="h-4 w-4" /> Demo Centre</NavLink>
              <div className="relative">
                <button className="btn relative p-2" onClick={() => setJobsOpen((v) => !v)} title="Background jobs">
                  <Bell className="h-4 w-4" />
                  {activeCount > 0 ? <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-[9px] font-bold text-canvas">{activeCount}</span> : null}
                </button>
                {jobsOpen ? <JobPanel onClose={() => setJobsOpen(false)} /> : null}
              </div>
              <div className="hidden items-center gap-2 border-l border-edge pl-3 md:flex">
                <div className="grid h-8 w-8 place-items-center rounded-full bg-violet/20 text-xs font-bold text-violet">{(user?.full_name || 'DS').slice(0, 2).toUpperCase()}</div>
                <div className="leading-tight">
                  <div className="text-xs font-medium text-ink">{user?.full_name || 'Demo user'}</div>
                  <div className="text-[10px] uppercase tracking-wider text-muted">{user?.global_role || 'viewer'}</div>
                </div>
                <button className="btn btn-ghost p-1.5" title="Sign out" onClick={() => { clearToken(); navigate('/login'); }}><LogOut className="h-4 w-4" /></button>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-[1600px] px-4 py-7 md:px-7">
          <EvidenceRibbon />
          <Outlet />
        </main>

        <footer className="border-t border-edge px-7 py-5 text-[11px] text-muted">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-1.5"><CircleDot className="h-3 w-3 text-success" /> SERPScope · v1.0 · source-tracked intelligence</span>
            <span>Synthetic demo data is clearly labelled and is never real client performance.</span>
          </div>
        </footer>
      </div>

      {toast ? (
        <div className={`fixed bottom-5 right-5 z-[60] flex max-w-sm items-start gap-2 rounded-lg border px-4 py-3 text-sm shadow-2xl animate-fade-in ${toast.tone === 'error' ? 'border-danger/40 bg-danger/10 text-danger' : toast.tone === 'success' ? 'border-success/40 bg-success/10 text-success' : 'border-accent/40 bg-accent/10 text-accent'}`}>
          {toast.tone === 'success' ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> : <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
          <span>{toast.message}</span>
        </div>
      ) : null}
    </div>
  );
}
