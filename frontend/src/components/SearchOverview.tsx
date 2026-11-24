import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ShieldCheck } from 'lucide-react';
import { get } from '../lib/api';
import { Badge, ErrorState, KeyValue, ProvenanceNote, Section, Spinner } from './ui';

type MetricMap = Record<string, string>;

type SuppliedSignal = {
  signal: string;
  label: string;
  supplied: boolean;
  rows: number;
  sources: string[];
  latest_period: string;
  sample: { dimension: string; period: string; metrics: MetricMap }[];
};

type SignalsResponse = {
  items: SuppliedSignal[];
  note?: string;
  status_explanations?: Record<string, string>;
};

type SuppliedRecord = {
  id: number | string;
  source: string;
  signal: string;
  data_kind: string;
  dimension: string;
  period: string;
  metrics: MetricMap;
};

type AuditSuppliedSignal = {
  label?: string;
  supplied?: boolean;
  rows?: number;
  sources?: string[];
  latest_period?: string;
  sample?: { dimension: string; period: string; metrics: MetricMap }[];
};

type AuditSlice = {
  meta?: Record<string, unknown>;
  supplied_data?: Record<string, AuditSuppliedSignal>;
  missing_data?: string[];
};

type DisplayRow = {
  dimension: string;
  period: string;
  metrics: MetricMap;
  data_kind?: string;
  source?: string;
};

const NOT_SUPPLIED_FALLBACK = 'No real export was supplied; the audit says Not supplied instead of guessing.';

/** The single interpretive Search Console surface. It never computes or invents a metric. */
export function SearchOverview({
  projectId,
  dataVersion = 0,
  audit = null,
  mode = 'workspace',
}: {
  projectId?: number | null;
  dataVersion?: number;
  audit?: AuditSlice | null;
  mode?: 'workspace' | 'public';
}) {
  const [signals, setSignals] = useState<SignalsResponse | null>(null);
  const [records, setRecords] = useState<SuppliedRecord[]>([]);
  const [loading, setLoading] = useState(mode === 'workspace' && Boolean(projectId));
  const [error, setError] = useState('');

  useEffect(() => {
    if (mode !== 'workspace' || !projectId) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    Promise.all([
      get<SignalsResponse>(`/integrations/supplied-signals?project_id=${projectId}`),
      get<{ items: SuppliedRecord[] }>(`/integrations/supplied-records?project_id=${projectId}&signal=gsc&limit=50`),
    ])
      .then(([signalPayload, recordPayload]) => {
        if (cancelled) return;
        setSignals(signalPayload);
        setRecords(recordPayload.items || []);
      })
      .catch((cause) => {
        if (!cancelled) setError(cause instanceof Error ? cause.message : 'Search data is temporarily unavailable.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [mode, projectId, dataVersion]);

  const isPublic = mode === 'public';
  const auditGsc = audit?.supplied_data?.gsc ?? null;
  const gsc: (SuppliedSignal | AuditSuppliedSignal) | null = isPublic
    ? auditGsc
    : signals?.items.find((item) => item.signal === 'gsc') ?? auditGsc;
  const supplied = !isPublic && Boolean(gsc?.supplied && (gsc.rows ?? 0) > 0);
  const publicPolicy = (audit?.meta as { private_data_policy?: string } | undefined)?.private_data_policy;
  const explanation = isPublic
    ? publicPolicy || 'Private Search Console exports are excluded from published case studies.'
    : signals?.status_explanations?.not_supplied || NOT_SUPPLIED_FALLBACK;
  const gapStatement = audit?.missing_data?.find((line) => /search console/i.test(line));
  const sample: DisplayRow[] = records.length
    ? records.map((row) => ({
        dimension: row.dimension,
        period: row.period,
        metrics: row.metrics || {},
        data_kind: row.data_kind,
        source: row.source,
      }))
    : (gsc?.sample ?? []).map((row) => ({ dimension: row.dimension, period: row.period, metrics: row.metrics || {} }));

  return (
    <Section
      title="Google Search Overview"
      description="One place for query, page, impression, click, CTR and position data — only when you supply it."
      actions={!isPublic ? <Link to="/integrations" className="text-[11px] font-semibold text-accent hover:underline">Open Integrations →</Link> : undefined}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={supplied ? 'good' : isPublic ? 'neutral' : 'warn'}>
          {supplied ? 'Supplied' : isPublic ? 'Private data excluded' : 'Not supplied'}
        </Badge>
        <span className="text-[11px] text-muted">No GTM event or Search Console API call is made here.</span>
      </div>

      <ProvenanceNote>
        {explanation}{' '}
        {isPublic
          ? 'No private export values are rendered on this page.'
          : 'Values below are copied verbatim from your export. SERPScope does not calculate totals, averages, CTR, rankings or trends from these cells.'}
      </ProvenanceNote>

      {loading ? <div className="mt-4"><Spinner label="Loading Search Console status" /></div> : null}
      {error ? <div className="mt-4"><ErrorState message={error} /></div> : null}

      {!loading && !error && supplied && gsc ? (
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <KeyValue label="Signal" value={gsc.label || 'Search Console'} />
            <KeyValue label="Verbatim rows" value={String(gsc.rows)} />
            <KeyValue label="Sources" value={gsc.sources?.join(', ') || 'not stated'} />
            <KeyValue label="Latest imported rows" value={gsc.latest_period || 'not stated'} />
          </div>
          <div className="overflow-x-auto rounded-lg border border-edge">
            <table className="w-full text-left text-[11px]">
              <thead className="text-[10px] uppercase tracking-wider text-muted">
                <tr>
                  <th className="p-2">Dimension</th>
                  <th className="p-2">Period</th>
                  <th className="p-2">Supplied cells</th>
                  <th className="p-2">Label</th>
                </tr>
              </thead>
              <tbody>
                {sample.slice(0, 8).map((row, index) => (
                  <tr key={`${row.dimension}-${row.period}-${index}`} className="border-t border-edge">
                    <td className="p-2 font-medium text-ink">{row.dimension || '—'}</td>
                    <td className="p-2 text-muted">{row.period || '—'}</td>
                    <td className="p-2">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(row.metrics).slice(0, 8).map(([key, value]) => (
                          <span key={key} className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-300">
                            {key}: <span className="font-semibold text-ink">{String(value)}</span>
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="p-2 text-muted">{row.data_kind || 'see Integrations'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-muted">
            Showing up to 8 verbatim rows. The full retained ledger and its data-kind labels stay in Integrations.
            The dimension falls back to the import file name when the export has no detected query or page column.
          </p>
        </div>
      ) : null}

      {!loading && !error && !supplied ? (
        <div className="mt-4 rounded-lg border border-edge bg-canvas/50 p-4">
          <div className="flex items-start gap-2 text-xs text-slate-300">
            <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
            <span>{gapStatement || explanation}</span>
          </div>
          {isPublic ? (
            <p className="mt-3 text-[11px] text-muted">
              Published case studies contain public crawl evidence only. Uploaded Search Console exports are never disclosed here.
            </p>
          ) : (
            <div className="mt-3 flex flex-wrap items-center gap-3 text-[11px] text-muted">
              <Search className="h-3.5 w-3.5 text-accent" />
              <span>Import a Search Console CSV/XLSX/JSON export in Integrations to replace this gap with labelled rows.</span>
              <Link to="/integrations" className="font-semibold text-accent hover:underline">Add GSC export →</Link>
            </div>
          )}
        </div>
      ) : null}
    </Section>
  );
}
