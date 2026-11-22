import { useEffect, useState } from 'react';
import { Play, X } from 'lucide-react';
import type { ModuleAction } from '../lib/modules';
import { resolvePath } from '../lib/modules';
import { useApp } from '../state/AppContext';

export function ActionModal({ action, projectId, rowId, onClose }: { action: ModuleAction | null; projectId: number | null; rowId?: string | number | null; onClose: () => void }) {
  const { runAction } = useApp();
  const [body, setBody] = useState('{}');
  const [error, setError] = useState('');

  useEffect(() => {
    if (action) {
      setBody(JSON.stringify(action.defaultBody ?? {}, null, 2));
      setError('');
    }
  }, [action]);

  if (!action) return null;

  const path = resolvePath(action.path, projectId, rowId);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4">
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      <div className="panel relative w-full max-w-lg p-5 animate-fade-in">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent">Confirm action</div>
            <h2 className="mt-1 text-lg font-semibold text-white">{action.label}</h2>
            <code className="mono mt-1 block text-muted">{action.method.toUpperCase()} {path}</code>
          </div>
          <button className="btn btn-ghost p-1" onClick={onClose}><X className="h-4 w-4" /></button>
        </div>
        {action.hint ? <p className="mb-3 rounded-lg border border-warning/20 bg-warning/5 p-2.5 text-xs leading-5 text-warning">{action.hint}</p> : null}
        <label className="label" htmlFor="action-body">Request body (JSON)</label>
        <textarea id="action-body" className="input h-48 font-mono text-xs" value={body} onChange={(e) => setBody(e.target.value)} spellCheck={false} />
        {error ? <p className="mt-2 text-xs text-danger">{error}</p> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className={`btn ${action.danger ? 'btn-danger' : 'btn-primary'}`} onClick={() => {
            try {
              const parsed = JSON.parse(body || '{}');
              void runAction(action.method, path, parsed);
              onClose();
            } catch (e) {
              setError(e instanceof Error ? e.message : 'Invalid JSON');
            }
          }}><Play className="h-3.5 w-3.5" /> Run action</button>
        </div>
      </div>
    </div>
  );
}
