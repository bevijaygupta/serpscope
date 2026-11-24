import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { RefreshCw, Zap } from 'lucide-react';
import { DataTable, type Row } from '../components/DataTable';
import { ActionModal } from '../components/ActionModal';
import { AiObservationImport } from '../components/AiObservationImport';
import { Badge, Drawer, ErrorState, JsonBlock, KeyValue, PageHeader, ProvenanceNote, Section, Spinner } from '../components/ui';
import { errorMessage, get, unwrapList, unwrapNamedLists } from '../lib/api';
import { trackEvent } from '../lib/analytics';
import { compactJson, humanKey, num } from '../lib/format';
import { getModule, resolvePath, type ModuleAction, type ModuleConfig } from '../lib/modules';
import { useApp } from '../state/AppContext';
import { CustomPage } from './CustomPages';

function NamedView({ payload }: { payload: unknown }) {
  const named = unwrapNamedLists(payload);
  const entries = Object.entries(named);
  if (entries.length > 0) {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        {entries.map(([key, values]) => (
          <Section key={key} title={humanKey(key)} description={`${values.length} entries`}>
            <div className="space-y-2">
              {values.slice(0, 60).map((value, index) => (
                <div key={index} className="rounded-lg border border-edge bg-canvas/50 p-3 text-xs text-slate-300">
                  {typeof value === 'object' && value !== null ? compactJson(value, 300) : String(value)}
                </div>
              ))}
              {values.length === 0 ? <div className="text-xs text-muted">No entries.</div> : null}
            </div>
          </Section>
        ))}
      </div>
    );
  }
  if (Array.isArray(payload)) {
    return <DataTable rows={payload as Row[]} />;
  }
  if (payload && typeof payload === 'object') {
    const obj = payload as Record<string, unknown>;
    const counts = Object.entries(obj).filter(([, value]) => typeof value === 'number' || typeof value === 'string' || typeof value === 'boolean');
    if (counts.length > 0) {
      return (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {counts.map(([key, value]) => (
            <div key={key} className="panel-flat p-4">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">{humanKey(key)}</div>
              <div className="mt-2 text-xl font-bold text-white">{num(value)}</div>
            </div>
          ))}
        </div>
      );
    }
    return (
      <div className="grid gap-3 md:grid-cols-2">
        {Object.entries(obj).map(([key, value]) => <Section key={key} title={humanKey(key)}><JsonBlock value={value} /></Section>)}
      </div>
    );
  }
  return <div className="py-10 text-center text-sm text-muted">No data available.</div>;
}

export function ModulePage() {
  const { moduleId = '' } = useParams();
  const module = getModule(moduleId);
  if (!module) return <ErrorState message={`Unknown module: ${moduleId}`} />;
  if (module.custom) return <CustomPage module={module} />;
  return <GenericModule module={module} />;
}

function GenericModule({ module }: { module: ModuleConfig }) {
  const { projectId, dataVersion, bumpData } = useApp();
  const [activeTab, setActiveTab] = useState(module.tabs[0]?.key ?? '');
  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [payload, setPayload] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [rawSearch, setRawSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(50);
  const [action, setAction] = useState<ModuleAction | null>(null);
  const [rowId, setRowId] = useState<string | number | null>(null);
  const [expanded, setExpanded] = useState<Row | null>(null);
  const [expandData, setExpandData] = useState<unknown>(null);
  const [expandLoading, setExpandLoading] = useState(false);

  const tab = module.tabs.find((t) => t.key === activeTab) ?? module.tabs[0];

  useEffect(() => {
    setActiveTab(module.tabs[0]?.key ?? '');
    setRawSearch('');
    setOffset(0);
  }, [module]);

  useEffect(() => {
    trackEvent('serpscope_tab_view', { module_id: module.id, tab: activeTab });
  }, [module.id, activeTab]);

  const path = useMemo(() => {
    if (!tab || !projectId) return '';
    const resolved = resolvePath(tab.path, projectId);
    if (tab.named) return resolved;
    const url = new URL(resolved, window.location.origin);
    if (rawSearch) url.searchParams.set('q', rawSearch);
    url.searchParams.set('offset', String(offset));
    url.searchParams.set('limit', String(limit));
    return `${url.pathname}${url.search}`;
  }, [tab, projectId, rawSearch, offset, limit]);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    get(path)
      .then((data) => {
        if (cancelled) return;
        if (tab?.named) {
          setPayload(data);
          setRows([]);
          setTotal(0);
        } else {
          const parsed = unwrapList<Row>(data);
          setRows(parsed.items);
          setTotal(parsed.total);
          setPayload(data);
        }
      })
      .catch((e) => { if (!cancelled) setError(errorMessage(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [path, tab?.named, dataVersion]);

  useEffect(() => {
    if (!expanded || !tab?.expandPath || !projectId) return;
    let cancelled = false;
    setExpandLoading(true);
    get(resolvePath(tab.expandPath, projectId, String(expanded.id ?? '')))
      .then((data) => { if (!cancelled) setExpandData(data); })
      .catch((e) => { if (!cancelled) setExpandData({ error: errorMessage(e) }); })
      .finally(() => { if (!cancelled) setExpandLoading(false); });
    return () => { cancelled = true; };
  }, [expanded, tab?.expandPath, projectId]);

  const exportParams = useMemo(() => ({ project_id: projectId, q: rawSearch }), [projectId, rawSearch]);

  return (
    <div className="animate-fade-in">
      <PageHeader
        eyebrow={`${module.group} · ${module.id}`}
        title={module.title}
        description={module.description}
        actions={[
          <button key="refresh" className="btn" onClick={bumpData} title="Refresh data"><RefreshCw className="h-3.5 w-3.5" /> Refresh</button>,
          ...module.actions.map((item) => (
            <button key={item.label} className={`btn ${item.label.toLowerCase().includes('detect') || item.label.toLowerCase().includes('analyse') ? 'btn-primary' : ''}`} onClick={() => { setRowId(null); setAction(item); }}>
              <Zap className="h-3.5 w-3.5" /> {item.label}
            </button>
          )),
        ]}
      />

      <div className="mb-5"><ProvenanceNote>{tab?.hint || undefined}</ProvenanceNote></div>

      {module.id === 'ai' && activeTab === 'observations' && projectId ? <AiObservationImport /> : null}

      {module.tabs.length > 1 ? (
        <div className="mb-4 flex gap-1 overflow-x-auto rounded-lg border border-edge bg-panel/60 p-1">
          {module.tabs.map((item) => (
            <button key={item.key} onClick={() => { setActiveTab(item.key); setOffset(0); setRawSearch(''); setExpanded(null); }}
              className={`whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition ${item.key === activeTab ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-white/5 hover:text-ink'}`}>
              {item.label}
            </button>
          ))}
        </div>
      ) : null}

      {!projectId && !tab?.path.startsWith('/auth') && !tab?.path.startsWith('/clients') && !tab?.path.startsWith('/integrations') && !tab?.path.startsWith('/workflows/step-library') && !tab?.path.startsWith('/crawler/config-defaults') ? (
        <Section><div className="py-10 text-center text-sm text-muted">Select or create a project to load this module.</div></Section>
      ) : error ? (
        <Section><ErrorState message={error} retry={bumpData} /></Section>
      ) : loading ? (
        <Section><Spinner label={`Loading ${tab?.label ?? 'data'}`} /></Section>
      ) : tab?.named ? (
        <NamedView payload={payload} />
      ) : (
        <DataTable
          rows={rows}
          total={total}
          search={rawSearch}
          onSearch={tab && ['/inventory/urls', '/keywords?', '/technical/issues'].some((p) => tab.path.includes(p)) ? (value) => { setRawSearch(value); setOffset(0); } : undefined}
          offset={offset}
          limit={limit}
          onPage={(nextOffset, nextLimit) => { setOffset(nextOffset); setLimit(nextLimit); }}
          exportPath={tab?.exportPath ? resolvePath(tab.exportPath, projectId) : undefined}
          exportParams={exportParams}
          onExpand={tab?.expandPath ? (row) => { setExpanded(row); setExpandData(null); } : undefined}
        />
      )}

      <Drawer open={Boolean(expanded)} title={expanded ? String(expanded.url || expanded.name || expanded.title || `Record #${expanded.id}`) : ''} onClose={() => setExpanded(null)}>
        {expandLoading ? <Spinner /> : <div className="space-y-2">
          <div className="mb-4 flex flex-wrap gap-2">
            {Object.entries(expanded ?? {}).filter(([, value]) => typeof value !== 'object').slice(0, 8).map(([key, value]) => <Badge key={key}>{humanKey(key)}: {String(value).slice(0, 40)}</Badge>)}
          </div>
          <KeyValue label="Record" value={<JsonBlock value={expanded} />} />
          {expandData ? <KeyValue label="API detail" value={<JsonBlock value={expandData} />} /> : null}
        </div>}
      </Drawer>

      <ActionModal action={action} projectId={projectId} rowId={rowId} onClose={() => setAction(null)} />
    </div>
  );
}
