import { AlertTriangle, CheckCircle2, Info, Loader2, ShieldCheck, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { toneFor } from '../lib/format';

export function Badge({ children, tone = 'neutral', className = '' }: { children: ReactNode; tone?: string; className?: string }) {
  const t = tone in { good: 1, warn: 1, bad: 1, neutral: 1 } ? tone : toneFor(children);
  const colors = {
    good: 'border-success/30 bg-success/10 text-success',
    warn: 'border-warning/30 bg-warning/10 text-warning',
    bad: 'border-danger/30 bg-danger/10 text-danger',
    neutral: 'border-edge bg-white/5 text-muted',
  } as const;
  return <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-semibold ${colors[t as keyof typeof colors]} ${className}`}>{children}</span>;
}

export function MetricCard({ label, value, sub, icon, tone = 'sky' }: { label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; tone?: 'sky' | 'violet' | 'emerald' | 'amber' | 'rose' }) {
  const tones = {
    sky: 'from-sky-500/20 text-accent',
    violet: 'from-violet-500/20 text-violet',
    emerald: 'from-emerald-500/20 text-success',
    amber: 'from-amber-500/20 text-warning',
    rose: 'from-rose-500/20 text-danger',
  } as const;
  return (
    <div className="panel relative overflow-hidden p-4 transition hover:border-accent/30">
      <div className={`pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full bg-gradient-to-b to-transparent blur-2xl ${tones[tone].split(' ')[0]}`} />
      <div className="flex items-start justify-between gap-3">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">{label}</div>
        {icon ? <div className={`rounded-lg bg-white/5 p-1.5 ${tones[tone].split(' ')[1]}`}>{icon}</div> : null}
      </div>
      <div className="mt-3 text-2xl font-bold tracking-tight text-white">{value}</div>
      {sub ? <div className="mt-1 text-xs text-muted">{sub}</div> : null}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="max-w-3xl">
        {eyebrow ? <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">{eyebrow}</div> : null}
        <h1 className="text-2xl font-bold tracking-tight text-white md:text-3xl">{title}</h1>
        {description ? <p className="mt-2 text-sm leading-6 text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Section({ title, description, actions, children, className = '' }: { title?: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`panel p-4 md:p-5 ${className}`}>
      {(title || actions) ? (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            {title ? <h2 className="text-sm font-semibold text-white">{title}</h2> : null}
            {description ? <p className="mt-1 text-xs leading-5 text-muted">{description}</p> : null}
          </div>
          {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function Spinner({ label = 'Loading' }: { label?: string }) {
  return <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted"><Loader2 className="h-4 w-4 animate-spin" /> {label}…</div>;
}

export function EmptyState({ title = 'No records yet', description = 'Run the relevant job or import a source to populate this view.' }: { title?: string; description?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-14 text-center">
      <div className="rounded-full border border-edge bg-white/5 p-3 text-muted"><Info className="h-5 w-5" /></div>
      <div className="text-sm font-semibold text-ink">{title}</div>
      <div className="max-w-md text-xs leading-5 text-muted">{description}</div>
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
      <AlertTriangle className="h-6 w-6 text-danger" />
      <div className="text-sm font-semibold text-ink">Could not load this view</div>
      <div className="max-w-lg text-xs text-muted">{message}</div>
      {retry ? <button className="btn" onClick={retry}>Retry</button> : null}
    </div>
  );
}

export function ProvenanceNote({ children = 'Every figure is queried from the database. Synthetic demo data is labelled and must not be presented as client performance.' }: { children?: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-accent/20 bg-accent/5 px-3 py-2 text-xs leading-5 text-muted">
      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
      <span>{children}</span>
    </div>
  );
}

export function Drawer({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative h-full w-full max-w-2xl overflow-y-auto border-l border-edge bg-panel p-5 shadow-2xl animate-fade-in">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent">Evidence record</div>
            <h2 className="mt-1 break-all text-lg font-semibold text-white">{title}</h2>
          </div>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close"><X className="h-4 w-4" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-b border-edge/60 py-2 last:border-0">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-1 break-words text-sm text-ink">{value ?? '—'}</div>
    </div>
  );
}

export function JsonBlock({ value }: { value: unknown }) {
  return <pre className="max-h-96 overflow-auto rounded-lg border border-edge bg-canvas/80 p-3 font-mono text-[11px] leading-5 text-slate-300">{JSON.stringify(value, null, 2)}</pre>;
}

export function SuccessIcon() {
  return <CheckCircle2 className="h-4 w-4" />;
}
