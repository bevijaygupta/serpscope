import { useEffect, useState } from 'react';
import { Users } from 'lucide-react';
import { get, post } from '../lib/api';

const SESSION_KEY = 'serpscope-live-session';

function anonymousSessionId(): string {
  try {
    const existing = sessionStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const generated = typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(SESSION_KEY, generated);
    return generated;
  } catch {
    return `tab-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  }
}

/**
 * Anonymous active-session badge. This is an on-site presence counter, not
 * Google Analytics Realtime; no cookie, IP, identity or GTM identifier is used.
 */
export function LiveVisitors() {
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const sessionId = anonymousSessionId();
    const ping = () => {
      void post<{ active: number }>('/presence/ping', { session_id: sessionId })
        .then((result) => { if (!cancelled) setCount(result.active); })
        .catch(() => {
          if (cancelled) return;
          void get<{ active: number }>('/presence/count')
            .then((result) => setCount(result.active))
            .catch(() => setCount(null));
        });
    };

    ping();
    const timer = window.setInterval(ping, 15_000);
    const onVisibility = () => { if (document.visibilityState === 'visible') ping(); };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return (
    <span
      className="hidden items-center gap-1.5 rounded-full border border-success/25 bg-success/5 px-2.5 py-1 text-[10px] font-semibold text-success sm:inline-flex"
      title="Anonymous active browser sessions. No IP, cookie or identity is stored; this is not Google Analytics Realtime."
    >
      <Users className="h-3 w-3" />
      <span className="mono">{count === null ? '--' : count}</span>
      <span className="uppercase tracking-wider text-muted">live</span>
    </span>
  );
}
