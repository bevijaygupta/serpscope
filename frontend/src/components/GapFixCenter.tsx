import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Copy, Database, Download, Gauge, Search, ShieldAlert, Sparkles, Zap } from 'lucide-react';
import { errorMessage, get, unwrapList } from '../lib/api';
import { num, titleCase } from '../lib/format';
import type { PublicAuditData } from '../pages/CustomPages';
import { Badge, ProvenanceNote, Section, Spinner } from './ui';

type Row = Record<string, unknown>;
type FixKind = 'error' | 'gap' | 'opportunity';

type FixItem = {
  key: string;
  title: string;
  severity: string;
  affected: number;
  problem: string;
  fix: string;
  samples: string[];
  replacements: { url: string; title: string; similarity: number }[];
  source: string[];
  confidence: string;
  limitation: string;
  module: string;
  kind: FixKind;
  effort: string;
  draft: string;
  score: number;
};

function useJson<T>(path: string | null, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(Boolean(path));
  const load = useCallback(() => {
    if (!path) { setLoading(false); return; }
    let cancelled = false;
    setLoading(true);
    setError('');
    get<T>(path)
      .then((value) => { if (!cancelled) setData(value); })
      .catch((cause) => { if (!cancelled) setError(errorMessage(cause)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => load(), [load]);
  return { data, error, loading };
}

function str(value: unknown): string {
  return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function arr<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function obj(value: unknown): Row {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Row : {};
}

function severityTone(severity: string) {
  const s = severity.toLowerCase();
  if (s === 'high' || s === 'critical' || s === 'p0') return 'bad';
  if (s === 'medium' || s === 'p1' || s === 'p2') return 'warn';
  if (s === 'positive' || s === 'info') return 'good';
  return 'neutral';
}

function severityWeight(severity: string) {
  const s = severity.toLowerCase();
  if (s === 'critical' || s === 'high' || s === 'p0') return 4;
  if (s === 'medium' || s === 'p1') return 3;
  if (s === 'low' || s === 'p2') return 2;
  return 1;
}

function effortTone(effort: string) {
  if (effort === 'Easy') return 'good';
  if (effort === 'Medium') return 'warn';
  if (effort === 'Hard') return 'bad';
  return 'neutral';
}

function estimateEffort(code: string, title: string, problem = '') {
  const c = `${code} ${title} ${problem}`.toLowerCase();
  if (/missing[ _-]?(title|h1|description|meta)|duplicate[ _-]?(title|description|meta)|thin content|anchor|alt text/.test(c)) return 'Easy';
  if (/404|redirect|canonical|broken|internal link|sitemap|orphan|pagination|index/.test(c)) return 'Medium';
  if (/slow|performance|schema|structured|aeo|answer|visibility|render/.test(c)) return 'Hard';
  return 'Review';
}

function topicFromUrl(url: string) {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split('/').filter(Boolean);
    const last = parts[parts.length - 1] || parsed.hostname;
    return titleCase(decodeURIComponent(last).replace(/[-_+]/g, ' ').replace(/\.[a-z0-9]+$/i, ''));
  } catch {
    return 'This page';
  }
}

function brandFromDomain(domain: string) {
  try {
    return titleCase(new URL(domain).hostname.replace(/^www\./, '').split('.')[0]);
  } catch {
    return 'Your brand';
  }
}

function draftCopy(code: string, samples: string[], domain: string) {
  const id = code.toLowerCase();
  const topic = topicFromUrl(samples[0] || domain);
  const brand = brandFromDomain(domain);
  if (id.includes('title') && !id.includes('meta')) return `Title draft per URL: ${topic} | ${brand}`;
  if (id.includes('description') || id.includes('meta')) return `Meta description draft per URL: ${topic} explained — practical guidance, services and next steps from ${brand}. Review before publishing.`;
  if (id.includes('h1') || id.includes('heading')) return `H1 draft per URL: ${topic}`;
  if (id.includes('schema') || id.includes('structured')) return `Structured-data draft: add verified Organization and WebSite JSON-LD for ${brand}. Do not invent ratings, reviews or prices.`;
  return '';
}

function publicEvidenceScore(audit: PublicAuditData) {
  const fetched = Math.max(1, audit.coverage.fetched_urls || 1);
  const severityPoints: Record<string, number> = { critical: 4, high: 4, p0: 4, medium: 2, p1: 2, p2: 2, low: 1, p3: 1 };
  const categories: Record<string, { earned: number; possible: number }> = {};
  let earned = 0;
  let possible = 0;
  for (const finding of audit.findings) {
    const weight = severityPoints[str(finding.severity).toLowerCase()] ?? 1;
    const exposure = Math.max(0, 1 - Math.min(1, Number(finding.affected_count ?? 0) / fetched));
    const category = str(finding.category) || 'other';
    categories[category] ??= { earned: 0, possible: 0 };
    categories[category].earned += weight * exposure;
    categories[category].possible += weight;
    earned += weight * exposure;
    possible += weight;
  }
  const rows = Object.entries(categories).map(([category, value]) => ({
    category: category.toLowerCase() === 'aeo'
      ? 'AEO readiness'
      : titleCase(category.replace(/[-_]/g, ' ')),
    score: value.possible ? Math.round((value.earned / value.possible) * 100) : 100,
    rules: value.possible,
  })).sort((a, b) => a.score - b.score);
  const score = possible ? Math.round((earned / possible) * 100) : 100;
  return {
    score,
    rows,
    formula: `Derived from ${audit.findings.length} public findings. Each rule passes at 1 − min(affected URLs / fetched URLs, 1), weighted High=4, Medium=2, Low=1. AEO rows measure readiness, not live AI visibility. This is not Ubersuggest's health score.`,
  };
}

function outboundLinkCount(row: Row) {
  const match = str(row.notes).match(/([\d,]+)\s+outbound links/i);
  return match ? Number(match[1].replace(/,/g, '')) : 0;
}

function matchesSeverity(item: FixItem, filter: string) {
  const s = item.severity.toLowerCase();
  if (filter === 'high') return ['high', 'critical', 'p0'].includes(s);
  if (filter === 'medium') return ['medium', 'p1', 'p2'].includes(s);
  if (filter === 'low') return ['low', 'p3', 'info', 'informational'].includes(s);
  return true;
}

function moduleFor(category: string, code = '') {
  const c = `${category} ${code}`.toLowerCase();
  if (c.includes('competitor') || c.includes('gap') || c.includes('anchor')) return 'competitor';
  if (c.includes('keyword') || c.includes('mapping') || c.includes('cannibal')) return 'mapping';
  if (c.includes('status') || c.includes('index') || c.includes('canonical') || c.includes('redirect')) return 'technical';
  if (c.includes('aeo') || c.includes('answer') || c.includes('schema') || c.includes('structured') || c.includes('ai')) return 'ai';
  if (c.includes('content') || c.includes('title') || c.includes('h1') || c.includes('description')) return 'content';
  if (c.includes('link') || c.includes('orphan')) return 'links';
  if (c.includes('performance') || c.includes('speed')) return 'inventory';
  if (c.includes('sitemap') || c.includes('method') || c.includes('crawl')) return 'crawler';
  if (c.includes('local') || c.includes('gbp')) return 'local';
  if (c.includes('international') || c.includes('hreflang')) return 'international';
  if (c.includes('ecommerce') || c.includes('product')) return 'ecommerce';
  return 'overview';
}

function downloadJson(name: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function GapFixCenter({ projectId, audit, dataVersion }: { projectId: number; audit: PublicAuditData | null; dataVersion: number }) {
  const [query, setQuery] = useState('');
  const [severity, setSeverity] = useState('all');
  const [kind, setKind] = useState('all');
  const [effort, setEffort] = useState('all');
  const [copiedKey, setCopiedKey] = useState('');

  const issues = useJson<Row>(`/technical/issues?project_id=${projectId}&limit=100`, [projectId, dataVersion]);
  const competitors = useJson<Row>(`/competitors?project_id=${projectId}&limit=100`, [projectId, dataVersion]);
  const gaps = useJson<Row>(`/competitors/gaps?project_id=${projectId}&limit=100`, [projectId, dataVersion]);
  const keywords = useJson<Row>(`/keywords?project_id=${projectId}&limit=100`, [projectId, dataVersion]);
  const mappings = useJson<Row>(`/keywords/mappings?project_id=${projectId}&limit=100`, [projectId, dataVersion]);

  const issueRows = useMemo(() => issues.data ? unwrapList<Row>(issues.data).items : [], [issues.data]);
  const competitorRows = useMemo(() => competitors.data ? unwrapList<Row>(competitors.data).items : [], [competitors.data]);
  const gapRows = useMemo(() => gaps.data ? unwrapList<Row>(gaps.data).items : [], [gaps.data]);
  const keywordRows = useMemo(() => keywords.data ? unwrapList<Row>(keywords.data).items : [], [keywords.data]);
  const mappingRows = useMemo(() => mappings.data ? unwrapList<Row>(mappings.data).items : [], [mappings.data]);
  const evidenceLoading = issues.loading || competitors.loading || gaps.loading || keywords.loading || mappings.loading;
  const suppliedData = audit?.supplied_data ?? {};
  const hasSignal = (...keys: string[]) => keys.some((key) => Boolean(suppliedData[key]?.supplied));
  const signalRowsCount = (...keys: string[]) => keys.reduce((sum, key) => sum + (suppliedData[key]?.rows ?? 0), 0);
  const signalPeriod = (...keys: string[]) => keys.map((key) => suppliedData[key]?.latest_period).filter(Boolean).join(', ');
  const suppliedEntries = Object.entries(suppliedData);
  const suppliedCount = suppliedEntries.filter(([, value]) => value.supplied).length;
  const aiVisibility = audit?.ai_visibility;
  const score = useMemo(() => audit ? publicEvidenceScore(audit) : null, [audit]);
  const benchmark = useMemo(() => competitorRows
    .map((row) => ({ domain: str(row.domain) || str(row.name), links: outboundLinkCount(row) }))
    .filter((row) => row.domain)
    .sort((a, b) => b.links - a.links)
    .slice(0, 6), [competitorRows]);

  const copyDraft = async (item: FixItem) => {
    let copied = false;
    try {
      await navigator.clipboard.writeText(item.draft);
      copied = true;
    } catch {
      // Fall back for browsers that deny clipboard access without window focus.
      try {
        const area = document.createElement('textarea');
        area.value = item.draft;
        area.style.position = 'fixed';
        area.style.opacity = '0';
        document.body.appendChild(area);
        area.select();
        copied = document.execCommand('copy');
        area.remove();
      } catch {
        copied = false;
      }
    }
    setCopiedKey(copied ? item.key : '');
  };

  const signalRows = useMemo(() => {
    if (!audit) return [];
    const derived = audit.derived_evidence;
    const visibility = audit.ai_visibility;
    const overview = visibility?.engines?.find((row) => row.engine.toLowerCase().includes('overview'));
    const sampled = Boolean(visibility?.observation_count);
    const schemaMissing = arr<Row>(audit.findings).find((f) => f.id === 'missing_schema')?.affected_count ?? 0;
    const aiRules = Object.keys(obj(audit.robots.ai_rules)).length;
    return [
      {
        signal: 'Organic traffic, sessions and revenue', suite: 'Traffic trends by month and channel',
        ours: hasSignal('ga4') ? `${num(signalRowsCount('ga4'))} user-supplied GA4 rows${signalPeriod('ga4') ? ` · latest ${signalPeriod('ga4')}` : ''}` : 'Not supplied — GA4 sessions, conversions and revenue are absent',
        status: hasSignal('ga4') ? 'Supplied' : 'Not supplied',
        fix: 'Review the verbatim GA4 rows in Integrations. Sessions, conversions and revenue are claimed only as supplied.',
      },
      {
        signal: 'Search queries, impressions, CTR, position', suite: 'GSC query and landing-page report',
        ours: hasSignal('gsc') ? `${num(signalRowsCount('gsc'))} user-supplied Search Console rows${signalPeriod('gsc') ? ` · latest ${signalPeriod('gsc')}` : ''}` : 'Not supplied — no GSC queries, clicks or average positions',
        status: hasSignal('gsc') ? 'Supplied' : 'Not supplied',
        fix: 'Review the verbatim rows in Integrations. No query is claimed unless a row was supplied.',
      },
      {
        signal: 'Keyword volume, difficulty and CPC', suite: 'Provider estimates for every keyword',
        ours: `${num(derived?.keywords ?? keywordRows.length)} observed topic candidates; ${hasSignal('keywords') ? `${num(signalRowsCount('keywords'))} user-supplied estimate rows` : 'volume, difficulty and CPC are null'}`,
        status: hasSignal('keywords') ? 'Supplied + derived' : 'Derived proxy',
        fix: 'Candidates come from public titles, H1s, URL paths and anchors. Upload a keyword export to add real estimates.',
      },
      {
        signal: 'Rank tracking and position history', suite: 'Daily positions per keyword',
        ours: hasSignal('rank') ? `${num(signalRowsCount('rank'))} user-supplied rank rows${signalPeriod('rank') ? ` · latest ${signalPeriod('rank')}` : ''}` : 'Not supplied — no rank tracking provider connected',
        status: hasSignal('rank') ? 'Supplied' : 'Not supplied',
        fix: 'Upload a rank export in Integrations; positions are shown exactly as supplied, never inferred.',
      },
      {
        signal: 'Backlinks and domain authority', suite: 'Referring domains and authority score',
        ours: `${num(derived?.competitors ?? competitorRows.length)} outbound hostnames observed${hasSignal('backlinks') || hasSignal('authority') ? `; ${num(signalRowsCount('backlinks', 'authority'))} user-supplied inbound/authority rows` : '; no inbound backlink data'}`,
        status: hasSignal('backlinks') || hasSignal('authority') ? 'Supplied + observed' : 'Partial / observed',
        fix: 'Upload inbound backlink or authority exports to add real data. Outbound hostnames are link candidates, not market-share claims.',
      },
      {
        signal: 'Top pages by performance', suite: 'Best pages by traffic and conversions',
        ours: `${num(audit.coverage.inventory_urls)} inventory URLs, ${num(audit.coverage.fetched_urls)} fetched public pages, ${num(audit.counts.page_types?.article ?? 0)} articles${hasSignal('ga4') ? `; ${num(signalRowsCount('ga4'))} user-supplied analytics rows` : ''}`,
        status: hasSignal('ga4') ? 'Supplied + observed' : 'Observed',
        fix: hasSignal('ga4') ? 'Review the supplied analytics rows in Integrations; crawl evidence remains separate.' : 'Pages are ranked by crawl evidence. Upload GA4 data to rank them by business impact.',
      },
      {
        signal: 'Overall SEO health score', suite: 'Derived public-evidence score, not a vendor score',
        ours: `${score?.score ?? 100}/100 — weighted pass rate across ${audit.findings.length} observed finding groups`,
        status: 'Derived proxy',
        fix: 'Fix the highest-severity, highest-exposure rules, then rerun the audit to recompute the same transparent formula.',
      },
      {
        signal: 'Site audit errors and warnings', suite: 'Prioritised crawl issues',
        ours: `${num(audit.findings.length)} audit findings, ${num(issueRows.length)} issue groups with priority scores`,
        status: 'Observed + derived',
        fix: 'Open the priority fix queue below for evidence, affected URLs, effort estimates and copy drafts.',
      },
      {
        signal: 'Competitor keyword gaps', suite: 'Keywords competitors rank for',
        ours: `${num(derived?.keyword_gaps ?? gapRows.length)} anchor/topic gaps from ${num(derived?.competitors ?? competitorRows.length)} link-observed hosts`,
        status: 'Derived proxy',
        fix: 'Validate each topic against business priorities. No rank or traffic is claimed for a competitor hostname.',
      },
      {
        signal: 'Internal links and orphan pages', suite: 'Link equity and orphan reports',
        ours: `${num(audit.coverage.inventory_urls)} inventory URLs reconciled; orphan register available in the Orphans module`,
        status: 'Observed',
        fix: 'Review the Orphans and Internal Links modules for source-by-source reconciliation and suggestions.',
      },
      {
        signal: 'AI search / answer readiness', suite: 'Beyond Ubersuggest',
        ours: `${num(aiRules)} AI crawler rules parsed; ${num(audit.counts.schema_pages)} pages with schema, ${num(schemaMissing)} commercial pages without it`,
        status: 'Unique evidence',
        fix: 'Readiness is measured from robots.txt and HTML rules, never claimed as ChatGPT or Perplexity visibility.',
      },
      {
        signal: 'Live AI citations', suite: 'ChatGPT / Perplexity / Claude cited URLs',
        ours: sampled ? `${num(visibility?.cited_urls_recorded ?? 0)} cited-url observation(s) recorded` : 'Not sampled — no live answer-engine fetch is performed',
        status: sampled ? 'Observed' : 'Not sampled',
        fix: 'Record a real answer with engine, question, timestamp and cited URL. No citation is inferred from crawl evidence.',
      },
      {
        signal: 'Google AI Overview presence', suite: 'AI Overview observation',
        ours: overview?.status === 'not_sampled' || !overview ? 'Not sampled — no Google AI Overview fetch is performed' : `${num(overview.observations)} observation(s), ${num(overview.brand_mentions_observed)} mentioned`,
        status: overview?.status === 'not_sampled' || !overview ? 'Not sampled' : 'Observed',
        fix: 'Add a verified observation for the exact query, locale and date. An empty log means not sampled, not absent.',
      },
      {
        signal: 'AI brand mentions', suite: 'Answer-engine mention tracking',
        ours: sampled ? `${num(visibility?.brand_mentions_observed ?? 0)} mention(s) in ${num(visibility?.observation_count ?? 0)} recorded observation(s)` : 'Not sampled — mention tracking needs a verified export or observation',
        status: sampled ? 'Observed' : 'Not sampled',
        fix: 'Upload a licensed AI visibility export or record verified observations. Never treat an empty log as zero visibility.',
      },
      {
        signal: 'Content ideas and topic clusters', suite: 'Blog and content ideas',
        ours: `${num(derived?.keywords ?? keywordRows.length)} observed topics with ${num(derived?.keyword_mappings ?? mappingRows.length)} page mappings`,
        status: 'Derived proxy',
        fix: 'Use the Content and Keyword Mapping modules to review briefs. Business validation is required before publishing.',
      },
      {
        signal: 'Page speed and Core Web Vitals', suite: 'Lighthouse and field performance',
        ours: hasSignal('performance') || hasSignal('crux') ? `${num(signalRowsCount('performance', 'crux'))} user-supplied performance rows${signalPeriod('performance', 'crux') ? ` · latest ${signalPeriod('performance', 'crux')}` : ''}` : 'Not supplied — no Lighthouse or field performance dataset was imported',
        status: hasSignal('performance') || hasSignal('crux') ? 'Supplied' : 'Not supplied',
        fix: 'Upload Lighthouse or CrUX exports in Integrations. Response status alone is not a speed score.',
      },
      {
        signal: 'Local SEO and Google Business Profile', suite: 'Map pack and local rankings',
        ours: hasSignal('local') ? `${num(signalRowsCount('local'))} user-supplied GBP/local rows${signalPeriod('local') ? ` · latest ${signalPeriod('local')}` : ''}` : 'Not supplied — no GBP, NAP or location dataset was supplied',
        status: hasSignal('local') ? 'Supplied' : 'Not supplied',
        fix: 'Upload a GBP/local export in Integrations. Local visibility cannot be inferred from a public crawl.',
      },
      {
        signal: 'Paid ads and SERP features', suite: 'Ad traffic, snippets and rich results',
        ours: hasSignal('serp', 'paid') ? `${num(signalRowsCount('serp', 'paid'))} user-supplied SERP/paid rows${signalPeriod('serp', 'paid') ? ` · latest ${signalPeriod('serp', 'paid')}` : ''}` : 'Not supplied — no SERP or advertising data was sampled',
        status: hasSignal('serp', 'paid') ? 'Supplied' : 'Not supplied',
        fix: 'Upload SERP-feature or paid-ads exports in Integrations. Schema presence is reported separately, not as a rich-result claim.',
      },
      {
        signal: 'Historical trends and forecasting', suite: 'Month-over-month movement',
        ours: hasSignal('historical') ? `${num(signalRowsCount('historical'))} user-supplied historical rows${signalPeriod('historical') ? ` · latest ${signalPeriod('historical')}` : ''}` : 'Not supplied — only the current public crawl is observed',
        status: hasSignal('historical') ? 'Supplied' : 'Not supplied',
        fix: 'Upload retained audit snapshots in Integrations or re-run scheduled audits. Future movements must never be presented as measured history.',
      },
    ];
  }, [audit, issueRows, competitorRows, gapRows, keywordRows, mappingRows, score]);

  const fixQueue = useMemo<FixItem[]>(() => {
    const items: FixItem[] = [];

    arr<Row>(audit?.findings ?? []).forEach((finding) => {
      const evidence = obj(finding.evidence);
      const samples = arr<string>(evidence.sample_urls);
      const code = str(finding.id);
      items.push({
        key: `finding-${code}`,
        title: str(finding.title) || code,
        severity: str(finding.severity),
        affected: Number(finding.affected_count ?? 0),
        problem: str(finding.observation),
        fix: str(finding.recommended_action) || 'Review the source evidence and apply the rule recommendation.',
        samples,
        replacements: [],
        source: arr<string>(finding.source),
        confidence: str(finding.confidence),
        limitation: str(finding.limitation),
        module: moduleFor(str(finding.category), code),
        kind: 'error',
        effort: estimateEffort(code, str(finding.title), str(finding.observation)),
        draft: draftCopy(code, samples, audit?.meta.domain ?? ''),
        score: severityWeight(str(finding.severity)) * 10000 + Number(finding.affected_count ?? 0),
      });
    });

    issueRows.forEach((issue) => {
      const evidence = obj(issue.evidence);
      const samples = arr<string>(evidence.sample_urls);
      const code = str(issue.code);
      const replacements = arr<Row>(evidence.replacements).map((r) => ({
        url: str(r.url), title: str(r.title), similarity: Number(r.similarity ?? 0),
      }));
      items.push({
        key: `issue-${str(issue.id)}`,
        title: str(issue.name) || code,
        severity: str(issue.severity) || str(issue.priority),
        affected: Number(issue.affected_count ?? 0),
        problem: `${code} · priority ${str(issue.priority)} · score ${str(issue.priority_score)}. ${str(issue.priority_explanation).slice(0, 240)}`,
        fix: replacements.length
          ? `Suggested replacement pages: ${replacements.slice(0, 3).map((r) => r.url).join(' · ')}`
          : `Review ${code} evidence and apply the documented technical rule.`,
        samples,
        replacements,
        source: [str(evidence.detection_rule) || 'rule engine', str(evidence.data_kind) || 'derived'],
        confidence: 'verified_from_public_evidence',
        limitation: `Business impact: ${str(issue.business_impact) || 'unknown'}. Priority is a transparent rule score, not a revenue estimate.`,
        module: moduleFor(str(issue.category), code),
        kind: 'error',
        effort: estimateEffort(code, str(issue.name), str(issue.priority_explanation)),
        draft: draftCopy(code, samples, audit?.meta.domain ?? ''),
        score: severityWeight(str(issue.severity) || str(issue.priority)) * 10000 + Number(issue.affected_count ?? 0),
      });
    });

    gapRows.forEach((row, index) => {
      const evidence = obj(row.evidence);
      const observedLinks = arr<Row>(evidence.observed_links);
      const samples = [str(row.competitor_url), ...observedLinks.slice(0, 3).map((link) => str(link.target))].filter(Boolean);
      items.push({
        key: `gap-${str(row.id)}-${index}`,
        title: `Competitor topic gap: ${str(row.keyword)}`,
        severity: str(row.priority) || 'P2',
        affected: Number(evidence.link_count ?? observedLinks.length),
        problem: `Observed ${num(evidence.link_count ?? observedLinks.length)} links from ${str(evidence.competitor_domain) || 'an external host'} with the anchor “${str(row.keyword)}”. No matching public page is recorded (${str(row.gap_type)}).`,
        fix: str(row.recommendation) || 'Compare the observed topic with public pages and decide whether a new page or an update is justified.',
        samples,
        replacements: [],
        source: [str(evidence.method) || 'outbound_links_in_public_crawl', `crawl ${str(evidence.crawl_id)}`],
        confidence: 'derived_from_public_evidence',
        limitation: 'Anchor and link evidence only; no competitor rank, traffic or market share is claimed.',
        module: 'competitor',
        kind: 'gap',
        effort: 'Medium',
        draft: '',
        score: severityWeight(str(row.priority) || 'P2') * 10000 + Number(evidence.link_count ?? 0),
      });
    });

    mappingRows.forEach((row, index) => {
      const changes = arr<string>(row.recommended_changes);
      if (!changes.length) return;
      items.push({
        key: `mapping-${str(row.id)}-${index}`,
        title: `Content opportunity: ${str(row.primary_keyword)}`,
        severity: 'P2',
        affected: 1,
        problem: str(row.reasoning) || `Observed topic mapped to ${str(row.url)}.`,
        fix: changes.join(' '),
        samples: [str(row.url)].filter(Boolean),
        replacements: [],
        source: [str(row.source) || 'public_page_evidence', `confidence ${num(row.confidence)}`],
        confidence: str(row.source) || 'derived',
        limitation: 'Volume, difficulty, CPC and rank are not supplied.',
        module: 'mapping',
        kind: 'opportunity',
        effort: 'Easy',
        draft: `Content brief starter: ${str(row.primary_keyword)} — validate intent, then outline against the observed public page evidence.`,
        score: 20000,
      });
    });

    return items.sort((a, b) => b.score - a.score);
  }, [audit, issueRows, gapRows, mappingRows]);

  const filteredFixes = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return fixQueue.filter((item) => {
      if (!matchesSeverity(item, severity)) return false;
      if (kind !== 'all' && item.kind !== kind) return false;
      if (effort === 'quick') {
        if (item.effort !== 'Easy' || !['high', 'critical', 'p0'].includes(item.severity.toLowerCase())) return false;
      } else if (effort !== 'all' && item.effort !== effort) return false;
      if (!needle) return true;
      return `${item.title} ${item.problem} ${item.fix} ${item.kind} ${item.effort} ${item.samples.join(' ')}`.toLowerCase().includes(needle);
    });
  }, [fixQueue, query, severity, kind, effort]);

  const quickWins = useMemo(() => fixQueue.filter((item) => item.effort === 'Easy' && ['high', 'critical', 'p0'].includes(item.severity.toLowerCase())).length, [fixQueue]);

  const exportPack = () => downloadJson(`serpscope-gap-and-fix-${projectId}.json`, {
    generated_at: new Date().toISOString(),
    project_id: projectId,
    domain: audit?.meta.domain ?? '',
    source: 'public evidence audit; vendor data appears only when a user supplied and labelled it',
    signal_coverage: signalRows,
    supplied_data: suppliedData,
    health_score: score,
    competitor_benchmark: benchmark,
    priority_fix_queue: fixQueue,
    competitor_topic_gaps: gapRows,
    derived_keywords_sample: keywordRows,
    keyword_mappings_sample: mappingRows,
    source_registry: audit?.source_registry ?? [],
    roadmap: audit?.roadmap ?? [],
    coverage: audit?.coverage ?? null,
    counts: audit?.counts ?? null,
    missing_data: audit?.missing_data ?? [],
  });

  if (!audit) return <Section title="Gap & Fix Center" description="Run or open a public audit to populate this view."><Spinner /></Section>;

  return (
    <Section
      title="Gap & Fix Center"
      description="Every row is public evidence or an explained rule. Vendor-only signals are shown as not supplied, never invented."
      actions={<button className="btn text-xs" onClick={exportPack}><Download className="h-3.5 w-3.5" /> Export gap pack</button>}
    >
      <ProvenanceNote>Competitor domains are external hostnames observed in outbound links. Topic gaps use observed anchors. No search volume, rank, traffic or AI-citation outcome is claimed.</ProvenanceNote>

      {evidenceLoading ? <div className="mt-3"><Spinner /></div> : null}
      {(issues.error || gaps.error || mappings.error) ? (
        <div className="mt-3 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {[issues.error, gaps.error, mappings.error].filter(Boolean).join(' ')}
        </div>
      ) : null}

      {score ? (
        <div className="mt-5 rounded-xl border border-edge bg-canvas/40 p-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-3xl">
              <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-white"><Gauge className="h-4 w-4 text-sky-400" /> Overall SEO health score <Badge tone="warn">Derived from public evidence</Badge></h3>
              <p className="mt-1 text-[11px] leading-5 text-muted">{score.formula}</p>
            </div>
            <div className="text-right">
              <div className="text-3xl font-bold text-white">{score.score}<span className="text-sm text-muted">/100</span></div>
              <div className="text-[10px] text-muted">transparent proxy · not an Ubersuggest score</div>
            </div>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {score.rows.map((row) => (
              <div key={row.category} className="rounded-lg border border-edge bg-panel/40 px-3 py-2">
                <div className="flex items-center justify-between gap-2 text-[11px]">
                  <span className="truncate text-slate-300">{row.category}</span>
                  <Badge tone={row.score >= 80 ? 'good' : row.score >= 50 ? 'warn' : 'bad'}>{row.score}/100</Badge>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5">
                  <div className={`h-full rounded-full ${row.score >= 80 ? 'bg-success' : row.score >= 50 ? 'bg-warning' : 'bg-danger'}`} style={{ width: `${row.score}%` }} />
                </div>
                <div className="mt-1 text-[10px] text-muted">{row.rules} weighted rule{row.rules === 1 ? '' : 's'}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-5 rounded-xl border border-edge bg-canvas/40 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-white"><Database className="h-4 w-4 text-emerald-400" /> User-supplied data in this audit <Badge tone={suppliedCount ? 'good' : 'bad'}>{suppliedCount}/{suppliedEntries.length} signals supplied</Badge></h3>
            <p className="mt-1 max-w-3xl text-[11px] leading-5 text-muted">Rows below are verbatim user uploads, not inferred by the public crawl. Unsupplied vendor signals stay explicit gaps.</p>
          </div>
          <Link to="/integrations" className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline">Open Integrations <ArrowUpRight className="h-3 w-3" /></Link>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {suppliedEntries.map(([key, value]) => (
            <div key={key} className="rounded-lg border border-edge bg-panel/40 px-3 py-2">
              <div className="flex items-center justify-between gap-2 text-[11px]">
                <span className="truncate text-slate-300">{value.label}</span>
                <Badge tone={value.supplied ? 'good' : 'bad'}>{value.supplied ? 'Supplied' : 'Not supplied'}</Badge>
              </div>
              <div className="mt-1 text-[10px] text-muted">
                {value.supplied
                  ? `${num(value.rows)} rows${value.sources.length ? ` · ${value.sources.join(', ')}` : ''}${value.latest_period ? ` · latest ${value.latest_period}` : ''}`
                  : 'No user export supplied'}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 rounded-xl border border-edge bg-canvas/40 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-white"><Sparkles className="h-4 w-4 text-violet-400" /> AI citations, Overviews and mentions <Badge tone={aiVisibility?.observation_count ? 'good' : 'warn'}>{aiVisibility?.status === 'observations_recorded' ? 'Observed' : 'Not sampled'}</Badge></h3>
            <p className="mt-1 max-w-3xl text-[11px] leading-5 text-muted">{aiVisibility?.notice || 'No live answer-engine sampling is performed. An empty log means not sampled, not absent.'}</p>
          </div>
          <Link to="/ai" className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline">Record a verified observation <ArrowUpRight className="h-3 w-3" /></Link>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(aiVisibility?.engines ?? []).map((row) => (
            <div key={row.engine} className="rounded-lg border border-edge bg-panel/40 px-3 py-2">
              <div className="flex items-center justify-between gap-2 text-[11px]">
                <span className="truncate text-slate-300">{row.engine}</span>
                <Badge tone={row.status === 'not_sampled' ? 'neutral' : 'good'}>{row.status === 'not_sampled' ? 'Not sampled' : 'Observed'}</Badge>
              </div>
              <div className="mt-1 text-[10px] text-muted">
                {row.status === 'not_sampled'
                  ? 'No live check recorded'
                  : `${num(row.observations)} observation(s) · ${num(row.brand_mentions_observed)} mentioned · ${num(row.cited_urls_recorded)} cited`}
              </div>
            </div>
          ))}
        </div>
        {aiVisibility?.publication_note ? <p className="mt-3 text-[10px] text-muted">{aiVisibility.publication_note}</p> : null}
      </div>

      <div className="mt-5 rounded-xl border border-edge bg-canvas/40 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-white"><ArrowUpRight className="h-4 w-4 text-accent" /> Observed-host benchmark <Badge tone="neutral">Outbound links only</Badge></h3>
            <p className="mt-1 max-w-3xl text-[11px] leading-5 text-muted">External hostnames found in this site&apos;s public outbound links, ranked by observed link count. This is not a backlink, authority or market-share benchmark.</p>
          </div>
          <Link to="/competitor" className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline">Open Competitors <ArrowUpRight className="h-3 w-3" /></Link>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {benchmark.length ? benchmark.map((row, index) => (
            <div key={row.domain} className="flex items-center justify-between gap-2 rounded-lg border border-edge bg-panel/40 px-3 py-2 text-[11px]">
              <span className="truncate text-slate-300"><span className="mr-1 text-muted">#{index + 1}</span>{row.domain}</span>
              <Badge tone="good">{num(row.links)} links</Badge>
            </div>
          )) : <div className="text-[11px] text-muted">No external hostnames were observed in outbound links.</div>}
        </div>
      </div>

      <div className="mt-5 overflow-x-auto rounded-xl border border-edge">
        <table className="w-full min-w-[980px] text-left text-xs">
          <thead className="bg-white/5 text-[10px] uppercase tracking-wider text-muted">
            <tr><th className="p-3">Signal an all-in-one SEO tool shows</th><th className="p-3">What SERPScope has</th><th className="p-3">Status</th><th className="p-3">How to close the gap</th></tr>
          </thead>
          <tbody>
            {signalRows.map((row) => (
              <tr key={row.signal} className="border-t border-edge align-top">
                <td className="p-3">
                  <div className="font-semibold text-ink">{row.signal}</div>
                  <div className="mt-0.5 text-[10px] text-muted">{row.suite}</div>
                </td>
                <td className="p-3 text-slate-300">{row.ours}</td>
                <td className="p-3"><Badge tone={row.status === 'Not supplied' ? 'bad' : row.status.includes('Derived') || row.status.includes('Partial') ? 'warn' : 'good'}>{row.status}</Badge></td>
                <td className="p-3 text-muted">{row.fix}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-7 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold text-white"><ShieldAlert className="h-4 w-4 text-rose-400" /> Where this site is lagging — priority fix queue <Badge tone="good"><Zap className="h-3 w-3" /> {num(quickWins)} quick wins</Badge></h3>
          <p className="mt-1 text-[11px] text-muted">{num(fixQueue.length)} items — errors, competitor gaps and content opportunities ranked by rule severity and observed evidence. Effort is a rule estimate; business impact is unknown unless private data is supplied.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 rounded-lg border border-edge bg-canvas/60 px-3 py-2 text-xs text-muted">
            <Search className="h-3.5 w-3.5" />
            <input className="w-44 bg-transparent text-ink outline-none placeholder:text-muted/70" placeholder="Filter errors and fixes" value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
          <select aria-label="Filter by severity" className="rounded-lg border border-edge bg-canvas/60 px-2.5 py-2 text-xs text-ink outline-none" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="all">All severities</option>
            <option value="high">High / critical</option>
            <option value="medium">Medium / P1–P2</option>
            <option value="low">Low / P3</option>
          </select>
          <select aria-label="Filter by type" className="rounded-lg border border-edge bg-canvas/60 px-2.5 py-2 text-xs text-ink outline-none" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="all">All types</option>
            <option value="error">Errors</option>
            <option value="gap">Competitor gaps</option>
            <option value="opportunity">Opportunities</option>
          </select>
          <select aria-label="Filter by estimated effort" className="rounded-lg border border-edge bg-canvas/60 px-2.5 py-2 text-xs text-ink outline-none" value={effort} onChange={(e) => setEffort(e.target.value)}>
            <option value="all">All effort</option>
            <option value="quick">Quick wins (easy + high)</option>
            <option value="Easy">Easy</option>
            <option value="Medium">Medium</option>
            <option value="Hard">Hard</option>
            <option value="Review">Review</option>
          </select>
        </div>
      </div>

      <div className="mt-3 space-y-3">
        {filteredFixes.slice(0, 40).map((item) => (
          <details key={item.key} className="group rounded-xl border border-edge bg-panel/40 p-4">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2">
              <Badge tone={severityTone(item.severity)}>{item.severity || 'info'}</Badge>
              <Badge tone={item.kind === 'error' ? 'bad' : item.kind === 'gap' ? 'warn' : 'good'}>{item.kind}</Badge>
              <Badge tone={effortTone(item.effort)}>{item.effort} effort</Badge>
              <span className="text-xs font-semibold text-ink">{item.title}</span>
              <span className="text-[10px] text-muted">{num(item.affected)} affected</span>
              <span className="ml-auto text-[10px] text-accent">Open evidence ↓</span>
            </summary>
            <div className="mt-3 grid gap-4 lg:grid-cols-[1fr_1fr]">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted">Observed problem</div>
                <p className="mt-1 text-xs leading-6 text-slate-300">{item.problem || 'See source evidence.'}</p>
                {item.samples.length ? (
                  <>
                    <div className="mt-3 text-[10px] font-semibold uppercase tracking-wider text-muted">Affected or observed URLs</div>
                    <ul className="mt-1 space-y-1">
                      {item.samples.slice(0, 5).map((url) => <li key={url} className="mono truncate text-[10px] text-slate-400" title={url}>{url}</li>)}
                    </ul>
                  </>
                ) : null}
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-accent">How to fix it</div>
                <p className="mt-1 text-xs leading-6 text-ink">{item.fix}</p>
                {item.draft ? (
                  <div className="mt-3 rounded-lg border border-accent/20 bg-accent/5 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="text-[10px] font-semibold uppercase tracking-wider text-accent">Rule-based copy draft · review before publishing</div>
                      <button className="btn btn-ghost text-[10px]" onClick={() => { void copyDraft(item); }}>
                        <Copy className="h-3 w-3" /> {copiedKey === item.key ? 'Copied' : 'Copy'}
                      </button>
                    </div>
                    <p className="mt-1 text-[11px] leading-5 text-ink">{item.draft}</p>
                  </div>
                ) : null}
                {item.replacements.length ? (
                  <ul className="mt-2 space-y-1">
                    {item.replacements.slice(0, 3).map((r) => (
                      <li key={r.url} className="text-[10px] text-slate-400">
                        <span className="mono">{r.url}</span> · {Math.round(r.similarity * 100)}% token overlap · {r.title}
                      </li>
                    ))}
                  </ul>
                ) : null}
                <div className="mt-3 text-[10px] leading-5 text-muted">
                  Source: {item.source.join(' · ') || 'rule engine'} · Confidence: {item.confidence || 'derived'}
                  {item.limitation ? ` · Limitation: ${item.limitation}` : ''}
                </div>
                <Link to={`/${item.module}`} className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-accent hover:underline">
                  Open the {item.module} module <ArrowUpRight className="h-3 w-3" />
                </Link>
              </div>
            </div>
          </details>
        ))}
        {filteredFixes.length === 0 ? <div className="py-8 text-center text-xs text-muted">No errors, gaps or opportunities match this filter.</div> : null}
        {filteredFixes.length > 40 ? <div className="text-center text-[11px] text-muted">Showing the top 40 of {num(filteredFixes.length)} matching items. Export the gap pack for the complete queue.</div> : null}
      </div>

      <div className="mt-7 grid gap-5 xl:grid-cols-2">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white"><Sparkles className="h-4 w-4 text-violet-400" /> Competitor topic gaps</h3>
          <p className="mt-1 text-[11px] text-muted">Observed external anchors with no comparable public page. No rank or traffic claim.</p>
          <div className="mt-3 max-h-96 overflow-auto rounded-xl border border-edge">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-elevated text-[10px] uppercase tracking-wider text-muted">
                <tr><th className="p-2.5">Topic</th><th className="p-2.5">Observed host</th><th className="p-2.5">Evidence</th><th className="p-2.5">Priority</th></tr>
              </thead>
              <tbody>
                {gapRows.map((row, index) => {
                  const evidence = obj(row.evidence);
                  return (
                    <tr key={`${str(row.id)}-${index}`} className="border-t border-edge align-top">
                      <td className="p-2.5 font-medium text-ink"><span className="mono">{str(row.keyword)}</span><div className="mt-0.5 text-[10px] text-muted">{str(row.intent)} · {str(row.gap_type)}</div></td>
                      <td className="p-2.5 text-slate-400">{str(evidence.competitor_domain) || '—'}</td>
                      <td className="p-2.5 text-muted">{num(evidence.link_count)} links · {num(evidence.anchor_observations)} anchors<div className="mt-0.5 text-[10px]">{str(row.recommendation).slice(0, 110)}</div></td>
                      <td className="p-2.5"><Badge tone={severityTone(str(row.priority))}>{str(row.priority) || 'P2'}</Badge></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <h3 className="text-sm font-semibold text-white">Content and keyword opportunities</h3>
          <p className="mt-1 text-[11px] text-muted">Derived from public titles, H1s, anchors and URL paths. Volume, difficulty and CPC are deliberately null.</p>
          <div className="mt-3 max-h-96 overflow-auto rounded-xl border border-edge">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-elevated text-[10px] uppercase tracking-wider text-muted">
                <tr><th className="p-2.5">Observed topic</th><th className="p-2.5">Mapped URL</th><th className="p-2.5">Intent / confidence</th><th className="p-2.5">Volume</th></tr>
              </thead>
              <tbody>
                {mappingRows.slice(0, 60).map((row, index) => (
                  <tr key={`${str(row.id)}-${index}`} className="border-t border-edge align-top">
                    <td className="p-2.5 font-medium text-ink">{str(row.primary_keyword)}</td>
                    <td className="p-2.5"><span className="mono block max-w-[280px] truncate text-[10px] text-slate-400" title={str(row.url)}>{str(row.url)}</span><span className="text-[10px] text-muted">{arr<string>(row.recommended_changes)[0] ?? ''}</span></td>
                    <td className="p-2.5 text-muted">{str(row.intent)} · {num(row.confidence)}</td>
                    <td className="p-2.5 text-muted">not supplied</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-2 text-[10px] text-muted">
            {num(keywordRows.length)} sampled keywords and {num(mappingRows.length)} sampled mappings shown from {num(audit.derived_evidence?.keywords ?? keywordRows.length)} and {num(audit.derived_evidence?.keyword_mappings ?? mappingRows.length)} total records.
          </div>
        </div>
      </div>

      <div className="mt-7 grid gap-5 xl:grid-cols-2">
        <div>
          <h3 className="text-sm font-semibold text-white">Data we deliberately did not invent</h3>
          <ul className="mt-3 space-y-2">
            {audit.missing_data.map((item) => (
              <li key={item} className="rounded-lg border border-edge bg-canvas/40 px-3 py-2 text-[11px] leading-5 text-muted">{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-white">Evidence sources and confidence</h3>
          <div className="mt-3 max-h-72 overflow-auto rounded-xl border border-edge">
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 bg-elevated text-[10px] uppercase tracking-wider text-muted">
                <tr><th className="p-2.5">Source</th><th className="p-2.5">Type</th><th className="p-2.5">Confidence</th><th className="p-2.5">Used for</th></tr>
              </thead>
              <tbody>
                {audit.source_registry.map((source) => (
                  <tr key={source.source} className="border-t border-edge align-top">
                    <td className="p-2.5 text-slate-300">{source.source}</td>
                    <td className="p-2.5 text-muted">{source.type}</td>
                    <td className="p-2.5"><Badge tone="good">{source.confidence}</Badge></td>
                    <td className="p-2.5 text-muted">{source.used_for.join(' · ')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Section>
  );
}
