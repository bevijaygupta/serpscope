import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { errorMessage, get, hasToken, logout as revokeToken, patch, post, unwrapList, type Job } from '../lib/api';

export type Project = { id: number; name: string; domain: string; status: string; is_demo?: boolean };

type Toast = { id: number; message: string; tone: 'info' | 'success' | 'error' };

type AppContextValue = {
  projects: Project[];
  projectId: number | null;
  project: Project | null;
  setProjectId: (id: number) => void;
  loadingProjects: boolean;
  refreshProjects: () => Promise<void>;
  jobs: Job[];
  refreshJobs: () => Promise<void>;
  dataVersion: number;
  bumpData: () => void;
  runAction: (method: 'post' | 'patch', path: string, body?: unknown) => Promise<void>;
  toast: Toast | null;
  notify: (message: string, tone?: Toast['tone']) => void;
  logout: () => void;
};

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectIdState] = useState<number | null>(() => {
    const saved = Number(localStorage.getItem('serpscope-project'));
    return Number.isFinite(saved) && saved > 0 ? saved : null;
  });
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [dataVersion, setDataVersion] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);

  const notify = useCallback((message: string, tone: Toast['tone'] = 'info') => {
    setToast({ id: Date.now(), message, tone });
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(timer);
  }, [toast]);

  const refreshProjects = useCallback(async () => {
    try {
      setLoadingProjects(true);
      const payload = await get('/projects');
      const list = unwrapList<Project>(payload).items;
      setProjects(list);
      setProjectIdState((current) => {
        const valid = list.find((p) => p.id === current);
        const next = valid?.id ?? list[0]?.id ?? null;
        if (next) localStorage.setItem('serpscope-project', String(next));
        return next;
      });
    } catch (error) {
      notify(errorMessage(error), 'error');
    } finally {
      setLoadingProjects(false);
    }
  }, [notify]);

  const refreshJobs = useCallback(async () => {
    try {
      const payload = await get('/jobs?limit=8');
      setJobs(unwrapList<Job>(payload).items);
    } catch {
      // Jobs panel is non-critical; auth guard handles session expiry.
    }
  }, []);

  useEffect(() => {
    if (!hasToken()) return;
    void refreshProjects();
    void refreshJobs();
    const timer = setInterval(() => void refreshJobs(), 4000);
    return () => clearInterval(timer);
  }, [refreshProjects, refreshJobs]);

  const setProjectId = useCallback((id: number) => {
    localStorage.setItem('serpscope-project', String(id));
    setProjectIdState(id);
    setDataVersion((v) => v + 1);
  }, []);

  const bumpData = useCallback(() => setDataVersion((v) => v + 1), []);

  const runAction = useCallback(async (method: 'post' | 'patch', path: string, body: unknown = {}) => {
    try {
      const result = method === 'post' ? await post(path, body) : await patch(path, body);
      const jobId = typeof result === 'object' && result && 'job_id' in result ? Number((result as { job_id: unknown }).job_id) : null;
      if (jobId) {
        notify(`Job #${jobId} queued — tracking progress`);
        void refreshJobs();
        let ticks = 0;
        const timer = setInterval(async () => {
          ticks += 1;
          try {
            const job = await get<Job>(`/jobs/${jobId}`);
            if (['succeeded', 'failed', 'cancelled'].includes(job.status) || ticks > 900) {
              clearInterval(timer);
              notify(job.status === 'succeeded' ? `${job.name} completed` : `${job.name}: ${job.status}${job.error ? ` — ${job.error}` : ''}`, job.status === 'succeeded' ? 'success' : 'error');
              bumpData();
              void refreshJobs();
            }
          } catch (error) {
            clearInterval(timer);
            notify(errorMessage(error), 'error');
          }
        }, 900);
      } else {
        notify('Change saved', 'success');
        bumpData();
        void refreshJobs();
      }
    } catch (error) {
      notify(errorMessage(error), 'error');
    }
  }, [bumpData, notify, refreshJobs]);

  const value = useMemo<AppContextValue>(() => ({
    projects,
    projectId,
    project: projects.find((p) => p.id === projectId) ?? null,
    setProjectId,
    loadingProjects,
    refreshProjects,
    jobs,
    refreshJobs,
    dataVersion,
    bumpData,
    runAction,
    toast,
    notify,
    logout: () => { void revokeToken(); },
  }), [projects, projectId, setProjectId, loadingProjects, refreshProjects, jobs, refreshJobs, dataVersion, bumpData, runAction, toast, notify]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
