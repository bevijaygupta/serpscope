import {
  Activity,
  BarChart3,
  FlaskConical,
  FolderKanban,
  Globe2,
  LayoutDashboard,
  Link2,
  MapPin,
  Network,
  Plug,
  Route,
  Search,
  Settings2,
  Share2,
  ShieldAlert,
  ShoppingBag,
  Sparkles,
  TrendingUp,
  Users,
  Workflow,
  FileText,
  type LucideIcon,
} from 'lucide-react';

export type ModuleAction = {
  label: string;
  method: 'post' | 'patch';
  path: string;
  defaultBody?: Record<string, unknown>;
  hint?: string;
  danger?: boolean;
};

export type ModuleTab = {
  key: string;
  label: string;
  path: string;
  exportPath?: string;
  expandPath?: string;
  hint?: string;
  named?: boolean;
};

export type ModuleConfig = {
  id: string;
  title: string;
  short: string;
  group: string;
  description: string;
  icon: LucideIcon;
  accent?: 'sky' | 'violet' | 'emerald' | 'amber' | 'rose';
  tabs: ModuleTab[];
  actions: ModuleAction[];
  custom?: 'overview' | 'projects' | 'crawler' | 'integrations' | 'demo' | 'settings';
};

const P = '{projectId}';

export const MODULES: ModuleConfig[] = [
  {
    id: 'overview', title: 'Overview', short: 'Overview', group: 'Command centre', icon: LayoutDashboard, accent: 'sky',
    description: 'Database-backed portfolio pulse: crawl coverage, issue pressure, opportunity volume and live job state.',
    custom: 'overview', tabs: [], actions: [],
  },
  {
    id: 'projects', title: 'Projects', short: 'Projects', group: 'Command centre', icon: FolderKanban, accent: 'sky',
    description: 'Create and switch client projects, manage delivery tasks, meeting notes and the audit trail.',
    custom: 'projects',
    tabs: [
      { key: 'tasks', label: 'Tasks', path: `/projects/${P}/tasks` },
      { key: 'notes', label: 'Meeting notes', path: `/projects/${P}/meeting-notes` },
      { key: 'audit', label: 'Audit log', path: `/projects/${P}/audit-log` },
    ],
    actions: [{ label: 'New task', method: 'post', path: `/projects/${P}/tasks`, defaultBody: { title: 'Review technical issue', priority: 'P1', status: 'open' } }],
  },
  {
    id: 'crawler', title: 'Crawler', short: 'Crawler', group: 'Discovery', icon: Activity, accent: 'sky',
    description: 'Robots-aware, delay-limited crawling with raw observations stored separately from interpreted URL records.',
    custom: 'crawler',
    tabs: [
      { key: 'runs', label: 'Crawl runs', path: `/crawler/runs?project_id=${P}`, expandPath: `/crawler/runs/{id}?project_id={projectId}` },
      { key: 'defaults', label: 'Safety defaults', path: '/crawler/config-defaults', named: true, hint: 'Robots.txt, crawl delay, cancellation and SSRF protections are enforced by the worker.' },
    ],
    actions: [{
      label: 'Start crawl', method: 'post', path: `/crawler/start?project_id=${P}`,
      defaultBody: { config: { start_url: 'https://demo.example.com/', max_urls: 500, max_depth: 4, concurrency: 2, crawl_delay: 0.5, respect_robots: true, follow_external: false, allow_private: false } },
      hint: 'Only crawl domains you are authorised to test. Demo URLs are synthetic.',
    }],
  },
  {
    id: 'technical', title: 'Technical Auditor', short: 'Technical', group: 'Discovery', icon: ShieldAlert, accent: 'rose',
    description: 'Rule-based technical issue detection with evidence, priority components and reviewable status workflow.',
    tabs: [
      { key: 'issues', label: 'Issue groups', path: `/technical/issues?project_id=${P}`, exportPath: `/technical/export?project_id=${P}`, expandPath: `/technical/issues/{id}?project_id={projectId}` },
      { key: '404s', label: 'High-value 404s', path: `/technical/high-value-404s?project_id=${P}`, hint: 'Ranked using supplied revenue, conversions, clicks and internal links — not invented values.' },
    ],
    actions: [{ label: 'Detect issues', method: 'post', path: `/technical/detect?project_id=${P}`, hint: 'Re-scans the current URL inventory and recomputes transparent priority explanations.' }],
  },
  {
    id: 'inventory', title: 'URL Intelligence', short: 'URL Intel', group: 'Discovery', icon: Search, accent: 'sky',
    description: 'One million-row-ready URL inventory with filtering, provenance, pagination and column-level exports.',
    tabs: [
      { key: 'urls', label: 'URL inventory', path: `/inventory/urls?project_id=${P}`, exportPath: `/inventory/export?project_id=${P}`, expandPath: `/inventory/urls/{id}?project_id={projectId}` },
      { key: 'summary', label: 'Composition', path: `/inventory/summary?project_id=${P}`, named: true },
    ],
    actions: [],
  },
  {
    id: 'orphans', title: 'Orphans', short: 'Orphans', group: 'Discovery', icon: Network, accent: 'violet',
    description: 'Union-based orphan reconciliation across sitemap, crawl and imported sources with explicit confidence.',
    tabs: [
      { key: 'orphans', label: 'Orphan register', path: `/orphans?project_id=${P}`, exportPath: `/orphans/export?project_id=${P}` },
      { key: 'summary', label: 'Summary', path: `/orphans/summary?project_id=${P}`, named: true },
    ],
    actions: [{ label: 'Detect orphans', method: 'post', path: `/orphans/detect?project_id=${P}` }],
  },
  {
    id: 'keywords', title: 'Keywords', short: 'Keywords', group: 'Intent & content', icon: Search, accent: 'violet',
    description: 'Import, classify and cluster keywords without inventing volumes; source and intent are always visible.',
    tabs: [
      { key: 'keywords', label: 'Keyword inventory', path: `/keywords?project_id=${P}`, exportPath: `/keywords/export?project_id=${P}` },
      { key: 'clusters', label: 'Clusters', path: `/keywords/clusters?project_id=${P}` },
      { key: 'summary', label: 'Summary', path: `/keywords/summary?project_id=${P}`, named: true },
    ],
    actions: [
      { label: 'Cluster keywords', method: 'post', path: `/keywords/cluster?project_id=${P}` },
      { label: 'Map to URLs', method: 'post', path: `/keywords/map?project_id=${P}` },
      { label: 'Bulk workflow', method: 'post', path: `/keywords/bulk-workflow?project_id=${P}`, defaultBody: { dry_run: false } },
      { label: 'Add keyword', method: 'post', path: `/keywords/inline?project_id=${P}`, defaultBody: { keywords: [{ keyword: 'cybersecurity provider singapore', intent: 'commercial', volume: null }], source: 'manual', confidence: 'synthetic' }, hint: 'Inline keywords are labelled synthetic unless you supply a real provider source and collected_at value.' },
    ],
  },
  {
    id: 'mapping', title: 'Keyword Mapping', short: 'Mapping', group: 'Intent & content', icon: Share2, accent: 'violet',
    description: 'One primary keyword per URL, reviewable reasoning, and cannibalisation conflicts surfaced explicitly.',
    tabs: [
      { key: 'mappings', label: 'URL mappings', path: `/keywords/mappings?project_id=${P}`, exportPath: `/keywords/export?project_id=${P}` },
      { key: 'conflicts', label: 'Cannibalisation', path: `/keywords/cannibalisation?project_id=${P}`, hint: 'Conflicts are interpretations, not observations. Review before acting.' },
    ],
    actions: [{ label: 'Regenerate mapping', method: 'post', path: `/keywords/map?project_id=${P}` }],
  },
  {
    id: 'content', title: 'Content', short: 'Content', group: 'Intent & content', icon: FileText, accent: 'violet',
    description: 'Content scoring and editable briefs. Recommendations stay proposals until a human approves them.',
    tabs: [
      { key: 'analyses', label: 'Analyses', path: `/content/analyses?project_id=${P}`, exportPath: `/content/export?project_id=${P}` },
      { key: 'briefs', label: 'Briefs', path: `/content/briefs?project_id=${P}` },
    ],
    actions: [
      { label: 'Analyse content', method: 'post', path: `/content/analyse?project_id=${P}` },
      { label: 'Generate briefs', method: 'post', path: `/content/briefs/generate?project_id=${P}` },
    ],
  },
  {
    id: 'links', title: 'Internal Links', short: 'Internal Links', group: 'Intent & content', icon: Link2, accent: 'violet',
    description: 'Graph analysis finds orphans, weakly linked commercial pages and reviewable anchor suggestions.',
    tabs: [
      { key: 'suggestions', label: 'Link suggestions', path: `/internal-links/suggestions?project_id=${P}`, exportPath: `/internal-links/export?project_id=${P}` },
      { key: 'graph', label: 'Graph summary', path: `/internal-links/graph-summary?project_id=${P}`, named: true },
    ],
    actions: [{ label: 'Analyse graph', method: 'post', path: `/internal-links/analyse?project_id=${P}` }],
  },
  {
    id: 'competitor', title: 'Competitor / Gap', short: 'Competitor', group: 'Market intelligence', icon: TrendingUp, accent: 'amber',
    description: 'Competitor domains and gap hypotheses. Nothing is scraped from third parties without an explicit import.',
    tabs: [
      { key: 'competitors', label: 'Competitor set', path: `/competitors?project_id=${P}`, exportPath: `/competitors/export?project_id=${P}` },
      { key: 'gaps', label: 'Opportunity gaps', path: `/competitors/gaps?project_id=${P}` },
    ],
    actions: [
      { label: 'Add competitor', method: 'post', path: `/competitors?project_id=${P}`, defaultBody: { domain: 'competitor.example', name: 'Example competitor', source: 'manual' } },
      { label: 'Analyse gaps', method: 'post', path: `/competitors/analyse?project_id=${P}` },
    ],
  },
  {
    id: 'international', title: 'International', short: 'International', group: 'Market intelligence', icon: Globe2, accent: 'amber',
    description: 'Market/language rollout plans and hreflang diagnostics derived from observed URL records.',
    tabs: [
      { key: 'plans', label: 'Market plans', path: `/international/plans?project_id=${P}`, exportPath: `/international/export?project_id=${P}` },
      { key: 'hreflang', label: 'Hreflang audit', path: `/international/hreflang?project_id=${P}` },
    ],
    actions: [{ label: 'Build plan', method: 'post', path: `/international/plan?project_id=${P}`, defaultBody: { markets: ['en-SG', 'ja-JP'], strategy: 'subdirectory' } }],
  },
  {
    id: 'local', title: 'Local / GBP', short: 'Local / GBP', group: 'Market intelligence', icon: MapPin, accent: 'amber',
    description: 'Location inventory and duplicate/consistency checks. No Google Business Profile claims are implied.',
    tabs: [{ key: 'locations', label: 'Locations', path: `/local/locations?project_id=${P}`, exportPath: `/local/export?project_id=${P}` }],
    actions: [
      { label: 'Add locations', method: 'post', path: `/local/locations/bulk?project_id=${P}`, defaultBody: { locations: [{ name: 'Singapore HQ', city: 'Singapore', country: 'SG' }] } },
      { label: 'Audit locations', method: 'post', path: `/local/audit?project_id=${P}` },
    ],
  },
  {
    id: 'ecommerce', title: 'E-commerce', short: 'E-commerce', group: 'Market intelligence', icon: ShoppingBag, accent: 'amber',
    description: 'Product-level canonical, schema and availability diagnostics for large catalogues.',
    tabs: [{ key: 'products', label: 'Product diagnostics', path: `/ecommerce/products?project_id=${P}`, exportPath: `/ecommerce/export?project_id=${P}` }],
    actions: [
      { label: 'Add products', method: 'post', path: `/ecommerce/products/bulk?project_id=${P}`, defaultBody: { products: [{ url: 'https://demo.example.com/products/category-0/product-1/', product_id: 'P-1', title: 'Demo product' }] } },
      { label: 'Audit catalogue', method: 'post', path: `/ecommerce/audit?project_id=${P}` },
    ],
  },
  {
    id: 'migration', title: 'Migration', short: 'Migration', group: 'Market intelligence', icon: Route, accent: 'amber',
    description: 'Redirect mapping with risk flags and validation output. No redirect is deployed automatically.',
    tabs: [
      { key: 'projects', label: 'Migration projects', path: `/migration/projects?project_id=${P}` },
      { key: 'mappings', label: 'Redirect map', path: `/migration/mappings?project_id=${P}`, exportPath: `/migration/export?project_id=${P}` },
    ],
    actions: [
      { label: 'New migration', method: 'post', path: `/migration/projects?project_id=${P}`, defaultBody: { name: 'Q1 platform migration', old_domain: 'old.example.com', new_domain: 'demo.example.com' } },
      { label: 'Add mappings', method: 'post', path: `/migration/mappings/bulk?project_id=${P}`, defaultBody: { mappings: [{ old_url: 'https://old.example.com/old-page/', new_url: 'https://demo.example.com/new-page/' }] } },
      { label: 'Validate map', method: 'post', path: `/migration/validate?project_id=${P}` },
    ],
  },
  {
    id: 'ai', title: 'AI Search / AEO', short: 'AI Search', group: 'Intelligence', icon: Sparkles, accent: 'violet',
    description: 'Answer-engine readiness based on explicit observations and audit rules — never simulated citations.',
    tabs: [
      { key: 'observations', label: 'Observations', path: `/ai-search/observations?project_id=${P}`, exportPath: `/ai-search/export?project_id=${P}` },
      { key: 'readiness', label: 'Readiness', path: `/ai-search/readiness?project_id=${P}`, named: true },
    ],
    actions: [
      { label: 'Add observation', method: 'post', path: `/ai-search/observations?project_id=${P}`, defaultBody: { question: 'best vapt provider singapore', answer_engine: 'manual-observation', cited_url: 'https://demo.example.com/services/vapt-1/', data_kind: 'observed', source: 'manual-observation', observed_at: new Date().toISOString(), brand_mentioned: false }, hint: 'Record only a response you actually observed. Demo visibility rows are labelled synthetic.' },
      { label: 'Run audit', method: 'post', path: `/ai-search/audit?project_id=${P}` },
    ],
  },
  {
    id: 'analytics', title: 'Analytics / Reporting', short: 'Reporting', group: 'Intelligence', icon: BarChart3, accent: 'sky',
    description: 'Imports, summary metrics and board-ready reports with missing data called out rather than filled in.',
    tabs: [
      { key: 'summary', label: 'Summary', path: `/analytics/summary?project_id=${P}`, named: true },
      { key: 'records', label: 'Analytics records', path: `/analytics/records?project_id=${P}` },
      { key: 'reports', label: 'Reports', path: `/analytics/reports?project_id=${P}` },
    ],
    actions: [
      { label: 'Queue report', method: 'post', path: `/analytics/reports/generate?project_id=${P}`, defaultBody: { period: 'last_28_days' } },
      { label: 'Generate now', method: 'post', path: `/analytics/reports/generate-now?project_id=${P}`, defaultBody: { period: 'last_28_days' } },
    ],
  },
  {
    id: 'forecasting', title: 'Forecasting', short: 'Forecasting', group: 'Intelligence', icon: TrendingUp, accent: 'sky',
    description: 'Editable scenario assumptions produce labelled estimates with explicit limitations.',
    tabs: [{ key: 'forecasts', label: 'Scenarios', path: `/analytics/forecasts?project_id=${P}` }],
    actions: [{ label: 'Create forecast', method: 'post', path: `/analytics/forecasts?project_id=${P}`, defaultBody: { name: 'Baseline scenario', months: 6, traffic_growth: 0.05, conversion_rate: 0.02 } }],
  },
  {
    id: 'workflows', title: 'Workflow Builder', short: 'Workflows', group: 'Automation', icon: Workflow, accent: 'emerald',
    description: 'Composable step library, manual/scheduled workflows and a complete run history with audit output.',
    tabs: [
      { key: 'workflows', label: 'Workflows', path: `/workflows?project_id=${P}` },
      { key: 'runs', label: 'Run history', path: `/workflows/runs?project_id=${P}` },
      { key: 'steps', label: 'Step library', path: '/workflows/step-library', named: true },
    ],
    actions: [
      { label: 'New workflow', method: 'post', path: `/workflows?project_id=${P}`, defaultBody: { name: 'Weekly technical audit', trigger: 'manual', steps: [{ type: 'detect_issues' }, { type: 'generate_report' }] } },
      { label: 'Run selected', method: 'post', path: `/workflows/{id}/run?project_id=${P}`, hint: 'Select a workflow row first, then run it from here.' },
    ],
  },
  {
    id: 'clients', title: 'Client / Team', short: 'Client / Team', group: 'Automation', icon: Users, accent: 'emerald',
    description: 'Organisations, memberships and project-level permissions with role-based write controls.',
    tabs: [
      { key: 'organizations', label: 'Organisations', path: '/clients/organizations' },
      { key: 'users', label: 'Team members', path: '/auth/users', named: true },
    ],
    actions: [
      { label: 'New organisation', method: 'post', path: '/clients/organizations', defaultBody: { name: 'New client', slug: 'new-client', plan: 'growth' } },
      { label: 'Add member', method: 'post', path: '/clients/organizations/{id}/members', defaultBody: { email: 'analyst@example.com', role: 'editor' } },
    ],
  },
  {
    id: 'integrations', title: 'Integrations', short: 'Integrations', group: 'Automation', icon: Plug, accent: 'emerald',
    description: 'Upload declared vendor exports, see which signals are truly supplied, and review provider records. No live vendor API is called.',
    custom: 'integrations',
    tabs: [
      { key: 'providers', label: 'Available providers', path: '/integrations/providers', named: true },
      { key: 'connected', label: 'Connected', path: `/integrations?project_id=${P}` },
    ],
    actions: [{ label: 'Connect provider', method: 'post', path: `/integrations?project_id=${P}`, defaultBody: { provider: 'google_search_console', name: 'GSC import', credentials: {} }, hint: 'Store credentials as environment variables in production; never paste live secrets into a demo.' }],
  },
  {
    id: 'demo', title: 'Demo Centre', short: 'Demo Centre', group: 'Automation', icon: FlaskConical, accent: 'emerald',
    description: 'Twelve interview-ready scenarios backed by deterministic synthetic data, with limitations stated up front.',
    custom: 'demo', tabs: [], actions: [],
  },
  {
    id: 'settings', title: 'Settings / Docs', short: 'Settings / Docs', group: 'Automation', icon: Settings2, accent: 'emerald',
    description: 'Provenance vocabulary, methodologies, export schemas and runtime configuration.',
    custom: 'settings', tabs: [], actions: [],
  },
];

export const MODULE_GROUPS = Array.from(new Set(MODULES.map((module) => module.group)));

export function getModule(id: string): ModuleConfig | undefined {
  return MODULES.find((module) => module.id === id);
}

export function resolvePath(path: string, projectId?: number | null, rowId?: string | number | null): string {
  return path
    .replaceAll('{projectId}', String(projectId ?? ''))
    .replaceAll('{id}', String(rowId ?? ''));
}
