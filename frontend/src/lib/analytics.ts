/** Privacy-conscious dataLayer events. The GTM container decides what to send to Google. */
type AnalyticsValue = string | number | boolean | null | undefined;
type AnalyticsParams = Record<string, AnalyticsValue>;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    doNotTrack?: string;
  }
}

const OPT_OUT_KEY = 'serpscope-analytics-optout';

function analyticsDisabled(): boolean {
  try {
    const navigatorDoNotTrack = (navigator as Navigator & { doNotTrack?: string }).doNotTrack;
    if (window.doNotTrack === '1' || navigatorDoNotTrack === '1') return true;
    return localStorage.getItem(OPT_OUT_KEY) === '1';
  } catch {
    return false;
  }
}

/** Push a named event without ever including a URL under audit or user identity. */
export function trackEvent(name: string, params: AnalyticsParams = {}): void {
  if (typeof window === 'undefined' || analyticsDisabled()) return;
  try {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({
      event: name,
      ...params,
      // Path only: never the query string or document title, which can contain
      // an audited domain or a user-entered search term.
      page_path: window.location.pathname,
      timestamp: new Date().toISOString(),
    });
  } catch {
    // Analytics must never break the product flow.
  }
}

export function trackPageView(path?: string): void {
  trackEvent('serpscope_page_view', {
    page_path: path ?? window.location.pathname,
  });
}

export function setAnalyticsOptOut(optOut: boolean): void {
  try {
    if (optOut) localStorage.setItem(OPT_OUT_KEY, '1');
    else localStorage.removeItem(OPT_OUT_KEY);
  } catch {
    // Storage can be disabled; the DNT signal above still applies.
  }
}
