export function num(value: unknown, digits = 0): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
}

export function money(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '—';
  if (n === 0) return '$0';
  if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(1)}k`;
  return `$${n.toFixed(n % 1 ? 2 : 0)}`;
}

export function pct(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(n) ? `${n.toFixed(n % 1 ? 1 : 0)}%` : '—';
}

export function date(value: unknown): string {
  if (!value) return '—';
  const d = new Date(String(value));
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function titleCase(value: unknown): string {
  return String(value ?? '')
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function shortUrl(value: unknown, max = 64): string {
  const text = String(value ?? '');
  try {
    const u = new URL(text);
    const compact = `${u.hostname}${u.pathname}${u.search}`;
    return compact.length > max ? `${compact.slice(0, max - 1)}…` : compact;
  } catch {
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
  }
}

export function toneFor(value: unknown): 'good' | 'warn' | 'bad' | 'neutral' {
  const v = String(value ?? '').toLowerCase();
  if (['p0', 'critical', 'high', 'failed', 'broken', 'danger', '404', '500'].includes(v)) return 'bad';
  if (['p1', 'medium', 'warning', 'weakly_linked', '301', 'review', 'pending', 'in_progress'].includes(v)) return 'warn';
  if (['p2', 'p3', 'low', 'info', 'succeeded', 'verified', 'approved', 'good', '200', 'resolved'].includes(v)) return 'good';
  return 'neutral';
}

export function compactJson(value: unknown, max = 240): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value.length > max ? `${value.slice(0, max)}…` : value;
  try {
    const text = JSON.stringify(value);
    return text.length > max ? `${text.slice(0, max)}…` : text;
  } catch {
    return String(value);
  }
}

export function humanKey(key: string): string {
  return titleCase(key.replace(/([a-z])([A-Z])/g, '$1 $2'));
}
