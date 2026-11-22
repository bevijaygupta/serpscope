import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Columns3, Download, Search, X } from 'lucide-react';
import { compactJson, humanKey, shortUrl } from '../lib/format';
import { downloadFile } from '../lib/api';
import { EmptyState, Spinner } from './ui';

export type Row = Record<string, unknown>;

type Props = {
  rows: Row[];
  total?: number;
  loading?: boolean;
  search?: string;
  onSearch?: (value: string) => void;
  offset?: number;
  limit?: number;
  onPage?: (offset: number, limit: number) => void;
  exportPath?: string;
  exportParams?: Record<string, unknown>;
  expandLabel?: string;
  onExpand?: (row: Row) => void;
  maxColumns?: number;
  emptyTitle?: string;
  emptyDescription?: string;
};

const URL_KEYS = new Set(['url', 'source_url', 'target_url', 'old_url', 'new_url', 'loc', 'final_url', 'requested_url', 'cited_url']);

function renderCell(key: string, value: unknown) {
  if (value === null || value === undefined || value === '') return <span className="text-muted/60">—</span>;
  if (typeof value === 'boolean') return <span className={value ? 'text-success' : 'text-muted'}>{value ? 'true' : 'false'}</span>;
  if (URL_KEYS.has(key) && typeof value === 'string') {
    return <span className="mono text-accent" title={value}>{shortUrl(value)}</span>;
  }
  if (Array.isArray(value) || (typeof value === 'object' && !(value instanceof Date))) {
    return <span className="mono text-slate-400" title={compactJson(value, 1000)}>{compactJson(value, 72)}</span>;
  }
  const text = String(value);
  return <span className={text.length > 140 ? 'text-slate-300' : ''} title={text}>{text.length > 140 ? `${text.slice(0, 139)}…` : text}</span>;
}

export function DataTable({
  rows, total = rows.length, loading, search = '', onSearch, offset = 0, limit = 50, onPage,
  exportPath, exportParams, onExpand, expandLabel = 'Evidence', maxColumns = 9,
  emptyTitle, emptyDescription,
}: Props) {
  const [visible, setVisible] = useState<string[] | null>(null);
  const [showPicker, setShowPicker] = useState(false);

  const allColumns = useMemo(() => {
    const keys: string[] = [];
    rows.slice(0, 30).forEach((row) => Object.keys(row).forEach((key) => { if (!keys.includes(key)) keys.push(key); }));
    return keys;
  }, [rows]);

  const columns = useMemo(() => {
    const preferred = visible ?? allColumns;
    const prioritised = [...preferred].sort((a, b) => {
      const aScore = a === 'id' ? -2 : a.toLowerCase().includes('url') ? -1 : 0;
      const bScore = b === 'id' ? -2 : b.toLowerCase().includes('url') ? -1 : 0;
      return aScore - bScore;
    });
    return prioritised.slice(0, maxColumns);
  }, [allColumns, maxColumns, visible]);

  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);

  return (
    <div className="overflow-hidden rounded-lg border border-edge">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-edge bg-elevated/50 px-3 py-2">
        <div className="flex flex-1 items-center gap-2">
          {onSearch ? (
            <div className="relative w-full max-w-sm">
              <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" />
              <input className="input py-1.5 pl-8 pr-8 text-xs" placeholder="Search this view…" value={search} onChange={(e) => onSearch(e.target.value)} />
              {search ? <button className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-white" onClick={() => onSearch('')}><X className="h-3.5 w-3.5" /></button> : null}
            </div>
          ) : null}
          <span className="whitespace-nowrap text-[11px] text-muted">{from}–{to} of {total.toLocaleString()}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <button className="btn btn-ghost px-2 py-1.5 text-xs" onClick={() => setShowPicker((v) => !v)} title="Choose columns"><Columns3 className="h-3.5 w-3.5" /> Columns</button>
            {showPicker ? (
              <div className="absolute right-0 z-30 mt-1 max-h-72 w-56 overflow-y-auto rounded-lg border border-edge bg-elevated p-2 shadow-xl">
                <div className="mb-1 flex justify-between px-1 text-[10px] uppercase tracking-wider text-muted">
                  <span>Visible columns</span>
                  <button className="text-accent" onClick={() => setVisible(null)}>Reset</button>
                </div>
                {allColumns.map((key) => (
                  <label key={key} className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-white/5">
                    <input type="checkbox" className="accent-sky-400" checked={columns.includes(key)} onChange={() => {
                      const next = columns.includes(key) ? columns.filter((c) => c !== key) : [...columns, key];
                      setVisible(next);
                    }} />
                    <span className="truncate text-slate-300">{humanKey(key)}</span>
                  </label>
                ))}
              </div>
            ) : null}
          </div>
          {exportPath ? (
            <button className="btn btn-ghost px-2 py-1.5 text-xs" onClick={() => void downloadFile(exportPath, { ...exportParams, format: 'csv' }, 'serpscope_export.csv')}>
              <Download className="h-3.5 w-3.5" /> CSV
            </button>
          ) : null}
        </div>
      </div>

      {loading ? <Spinner /> : rows.length === 0 ? <EmptyState title={emptyTitle} description={emptyDescription} /> : (
        <div className="max-h-[620px] overflow-auto">
          <table className="w-full min-w-full border-collapse">
            <thead>
              <tr>
                {columns.map((key) => <th key={key} className="table-head whitespace-nowrap px-3 py-2.5">{humanKey(key)}</th>)}
                {onExpand ? <th className="table-head px-3 py-2.5">Action</th> : null}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={String(row.id ?? index)} className="transition hover:bg-white/[0.025]">
                  {columns.map((key) => <td key={key} className="table-cell max-w-[280px]">{renderCell(key, row[key])}</td>)}
                  {onExpand ? (
                    <td className="table-cell">
                      <button className="text-xs font-medium text-accent hover:underline" onClick={() => onExpand(row)}>{expandLabel}</button>
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {onPage && total > limit ? (
        <div className="flex items-center justify-between border-t border-edge bg-elevated/40 px-3 py-2 text-xs text-muted">
          <span>Page {Math.floor(offset / limit) + 1} of {Math.ceil(total / limit)}</span>
          <div className="flex gap-2">
            <select className="input w-auto py-1 text-xs" value={limit} onChange={(e) => onPage(0, Number(e.target.value))}>
              {[25, 50, 100, 250, 500].map((n) => <option key={n} value={n}>{n} / page</option>)}
            </select>
            <button className="btn px-2 py-1" disabled={offset <= 0} onClick={() => onPage(Math.max(0, offset - limit), limit)}><ChevronLeft className="h-3.5 w-3.5" /></button>
            <button className="btn px-2 py-1" disabled={offset + limit >= total} onClick={() => onPage(offset + limit, limit)}><ChevronRight className="h-3.5 w-3.5" /></button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
