import axios, { type AxiosRequestConfig, type AxiosResponse } from 'axios';

const TOKEN_KEY = 'serpscope-token';

// Default expects a same-origin /api rewrite (Vercel -> Render). Override with
// VITE_API_URL when serving the API from a different origin.
export const API_BASE_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      if (!window.location.pathname.startsWith('/login')) window.location.href = '/login';
    }
    const detail = error?.response?.data?.detail || error?.response?.data?.error || error?.message || 'Request failed';
    return Promise.reject(new Error(typeof detail === 'string' ? detail : JSON.stringify(detail)));
  },
);

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function hasToken() {
  return Boolean(localStorage.getItem(TOKEN_KEY));
}

export async function get<T = unknown>(path: string, params?: Record<string, unknown>, config?: AxiosRequestConfig): Promise<T> {
  const response: AxiosResponse<T> = await api.get(path, { params, ...config });
  return response.data;
}

export async function post<T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const response: AxiosResponse<T> = await api.post(path, body ?? {}, config);
  return response.data;
}

export async function patch<T = unknown>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const response: AxiosResponse<T> = await api.patch(path, body ?? {}, config);
  return response.data;
}

/** Multipart upload for user-supplied vendor exports. */
export async function uploadFile<T = unknown>(path: string, form: FormData): Promise<T> {
  const response: AxiosResponse<T> = await api.post(path, form, { headers: { 'Content-Type': 'multipart/form-data' } });
  return response.data;
}

export type Page<T = Record<string, unknown>> = {
  items: T[];
  total: number;
  offset: number;
  limit: number;
};

/** Normalises the several list shapes used by the API into an array + total. */
export function unwrapList<T = Record<string, unknown>>(payload: unknown): { items: T[]; total: number } {
  if (Array.isArray(payload)) return { items: payload as T[], total: payload.length };
  if (payload && typeof payload === 'object') {
    const obj = payload as Record<string, unknown>;
    if (Array.isArray(obj.items)) return { items: obj.items as T[], total: Number(obj.total ?? obj.items.length) };
    if (Array.isArray(obj.data)) return { items: obj.data as T[], total: Number(obj.total ?? obj.data.length) };
    const arrays = Object.values(obj).filter(Array.isArray);
    if (arrays.length === 1) return { items: arrays[0] as T[], total: (arrays[0] as T[]).length };
  }
  return { items: [], total: 0 };
}

/** Records that are themselves dictionaries of named lists (e.g. counts). */
export function unwrapNamedLists(payload: unknown): Record<string, unknown[]> {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return {};
  return Object.fromEntries(
    Object.entries(payload as Record<string, unknown>).filter(([, value]) => Array.isArray(value)),
  ) as Record<string, unknown[]>;
}

export type Job = {
  id: number;
  project_id?: number | null;
  job_type: string;
  name: string;
  status: 'queued' | 'claimed' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  progress: number;
  total: number;
  message: string;
  error?: string | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  result?: Record<string, unknown> | null;
};

export async function waitForJob(jobId: number, onUpdate?: (job: Job) => void, timeoutMs = 600_000): Promise<Job> {
  const started = Date.now();
  let lastStatus = '';
  while (Date.now() - started < timeoutMs) {
    const job = await get<Job>(`/jobs/${jobId}`);
    if (job.status !== lastStatus || job.status === 'running') onUpdate?.(job);
    lastStatus = job.status;
    if (['succeeded', 'failed', 'cancelled'].includes(job.status)) return job;
    await new Promise((resolve) => setTimeout(resolve, 700));
  }
  throw new Error(`Job ${jobId} did not finish within ${Math.round(timeoutMs / 1000)}s`);
}

export async function downloadFile(path: string, params: Record<string, unknown>, fallbackName: string) {
  const response = await api.get(path, { params, responseType: 'blob' });
  const disposition = String(response.headers['content-disposition'] || '');
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const url = URL.createObjectURL(new Blob([response.data]));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = match ? match[1] : fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export async function login(email: string, password: string) {
  const data = await post<{ access_token: string; token_type: string }>('/auth/login', { email, password });
  setToken(data.access_token);
  return data;
}
