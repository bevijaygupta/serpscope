import { useState, type FormEvent } from 'react';
import { UploadCloud } from 'lucide-react';
import { errorMessage, post } from '../lib/api';
import { ProvenanceNote } from './ui';
import { useApp } from '../state/AppContext';

type ImportResult = {
  accepted: number;
  rejected: number;
  errors: string[];
  sources: string[];
  data_kinds: string[];
  visibility_status: string;
  verified_observations: number;
  note: string;
};

/** Import only observations a human actually saw. No answer engine is queried. */
export function AiObservationImport() {
  const { projectId, bumpData, notify } = useApp();
  const [source, setSource] = useState('verified-export');
  const [dataKind, setDataKind] = useState('observed');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!projectId || !file) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const text = await file.text();
      const isJson = file.name.toLowerCase().endsWith('.json');
      let body: Record<string, unknown>;
      if (isJson) {
        const parsed: unknown = JSON.parse(text);
        const rows = Array.isArray(parsed)
          ? parsed
          : (parsed && typeof parsed === 'object' && Array.isArray((parsed as { rows?: unknown }).rows)
              ? (parsed as { rows: unknown[] }).rows
              : null);
        if (!rows) throw new Error('JSON must be an array of observations or { "rows": [...] }');
        body = { rows, source, data_kind: dataKind };
      } else {
        body = { csv: text, source, data_kind: dataKind };
      }
      const payload = await post<ImportResult>(
        `/ai-search/observations/import?project_id=${projectId}`, body,
      );
      setResult(payload);
      bumpData();
      notify(`Imported ${payload.accepted} observation(s); status is ${payload.visibility_status}.`, 'success');
    } catch (cause) {
      setError(errorMessage(cause));
      notify(errorMessage(cause), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mb-5 rounded-xl border border-violet/25 bg-violet/5 p-4">
      <div className="text-xs font-semibold text-white">Import verified AI observations</div>
      <p className="mt-1 text-[11px] leading-5 text-muted">
        Upload a CSV or JSON export of answers you genuinely observed. Each row keeps its own source and data-kind
        label; nothing here calls ChatGPT, Claude, Perplexity or Google AI Overviews.
      </p>
      <div className="mb-3"><ProvenanceNote>
        An empty verified log stays <strong>Not sampled</strong> — never “no mentions”. Rows labelled synthetic or
        unverified are stored verbatim but excluded from every visibility claim.
      </ProvenanceNote></div>
      {!projectId ? (
        <div className="py-4 text-center text-xs text-muted">Select a project to import observations.</div>
      ) : (
        <form className="grid gap-3 md:grid-cols-4 md:items-end" onSubmit={(event) => void submit(event)}>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-muted">
            Source label
            <input className="mt-1 w-full rounded-lg border border-edge bg-canvas/60 px-2.5 py-2 text-xs text-ink outline-none"
              value={source} onChange={(event) => setSource(event.target.value)} placeholder="licensed-export" />
          </label>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-muted">
            Data-kind
            <select className="mt-1 w-full rounded-lg border border-edge bg-canvas/60 px-2.5 py-2 text-xs text-ink outline-none"
              value={dataKind} onChange={(event) => setDataKind(event.target.value)}>
              <option value="observed">observed (counts as evidence)</option>
              <option value="licensed_export">licensed_export (counts as evidence)</option>
              <option value="imported">imported (unverified)</option>
              <option value="synthetic">synthetic (never a claim)</option>
            </select>
          </label>
          <label className="block text-[10px] font-semibold uppercase tracking-wider text-muted">
            CSV or JSON file
            <input type="file" accept=".csv,.json,.tsv,.txt"
              className="mt-1 block w-full text-[11px] text-slate-300 file:mr-2 file:rounded-md file:border-0 file:bg-accent/15 file:px-3 file:py-1.5 file:text-[11px] file:text-accent"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <button className="btn btn-primary justify-center text-xs" disabled={busy || !file}>
            <UploadCloud className="h-3.5 w-3.5" /> {busy ? 'Importing…' : 'Import observations'}
          </button>
          <div className="md:col-span-4 text-[10px] leading-5 text-muted">
            Columns: question, answer_engine, observed_at, brand_mentioned, competitor_mentioned, cited_url,
            answer_url, locale, source, data_kind, notes. Only question and answer_engine are required.
          </div>
        </form>
      )}
      {error ? <div className="mt-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-[11px] text-danger">{error}</div> : null}
      {result ? (
        <div className="mt-3 rounded-lg border border-success/30 bg-success/5 px-3 py-2 text-[11px] leading-5 text-slate-300">
          <div className="font-semibold text-success">
            {result.accepted} accepted · {result.rejected} rejected · verified observations: {result.verified_observations} · status: {result.visibility_status}
          </div>
          <div>{result.note}</div>
          {result.errors.length ? <div className="mt-1 text-warning">{result.errors.join(' | ')}</div> : null}
        </div>
      ) : null}
    </div>
  );
}
