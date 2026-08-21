import {
  AvailabilityItem,
  AvailabilityReason,
  ExtensionSnapshot,
  SnapshotCodexAccount,
  SnapshotFilters,
} from '../contracts/snapshot';

export interface DashboardMetric {
  label?: string;
  value: string;
  subtitle?: string;
}

export interface DashboardCards {
  sessions: DashboardMetric;
  totalTokens: DashboardMetric;
  tokensSaved: DashboardMetric;
  cacheRatio: DashboardMetric;
  observedCost: DashboardMetric;
  estimatedCost: DashboardMetric;
  estimatedSavings: DashboardMetric;
}

export interface DashboardCodexAccount {
  title: string;
  syncedAtLabel: string;
  primaryUsageLabel: string;
  secondaryUsageLabel: string;
  creditBalanceLabel: string;
  primaryResetLabel?: string;
  secondaryResetLabel?: string;
  spendControlLabel?: string;
}

export interface DashboardDailyPoint {
  date: string;
  sessions: number;
  totalTokens: number;
  cacheRatio: number | null;
  observedCostUsd: number | null;
  estimatedCostUsd: number | null;
  estimatedSavingsUsd: number | null;
}

export interface DashboardBreakdownPoint {
  label: string;
  sessions: number;
  totalTokens: number;
}

export interface DashboardModelBreakdownPoint extends DashboardBreakdownPoint {
  estimatedCostUsd: number | null;
  costEventsTotal: number;
  costEventsPriced: number;
  costComplete: boolean;
  costLabel: string;
}

export interface DashboardClientBreakdownPoint extends DashboardBreakdownPoint {
  share: number;
  shareLabel: string;
}

export interface DashboardViewModel {
  generatedAt: string;
  database: string;
  lastImportedLabel: string;
  filters: SnapshotFilters;
  isEmpty: boolean;
  cards: DashboardCards;
  codexAccount?: DashboardCodexAccount;
  dimensions: ExtensionSnapshot['dimensions'];
  quality: ExtensionSnapshot['quality'];
  series: { daily: DashboardDailyPoint[] };
  breakdowns: {
    projects: DashboardBreakdownPoint[];
    models: DashboardModelBreakdownPoint[];
    sources: DashboardBreakdownPoint[];
    clients: DashboardClientBreakdownPoint[];
  };
}

const availabilityCopy: Record<AvailabilityReason, string> = {
  source_does_not_report_cost: 'A fonte selecionada não informa custo monetário observado.',
  insufficient_pricing_data: 'Não há dados de preço suficientes para esta seleção.',
  no_optimization_data: 'Não há dados de otimização suficientes para esta seleção.',
};

function formatInteger(value: number): string {
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 }).format(value);
}

function formatPercent(value: number | null): string {
  if (value === null) return 'Não disponível';
  return `${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value * 100)}%`;
}

function formatPercentPoints(value: number | null | undefined): string {
  if (value === null || value === undefined) return 'Não disponível';
  return `${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}%`;
}

function formatUsd(value: number | null): string {
  if (value === null) return 'Não disponível';
  return `US$ ${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}`;
}

function formatDateTime(raw: string | null | undefined): string {
  if (!raw) return 'não disponível';
  const normalized = raw.includes('T') ? raw : `${raw.replace(' ', 'T')}Z`;
  const parsed = new Date(normalized);
  return Number.isNaN(parsed.getTime())
    ? raw
    : new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(parsed);
}

function formatEpochSeconds(value: number | null | undefined): string | undefined {
  if (value === null || value === undefined) return undefined;
  return formatDateTime(new Date(value * 1000).toISOString());
}

function lastImportedLabel(snapshot: ExtensionSnapshot): string {
  const freshness = snapshot.freshness;
  if (!freshness?.last_imported_at) return 'Última coleta: não disponível';
  const formatted = formatDateTime(freshness.last_imported_at);
  const artifactLabel = freshness.artifacts_tracked === 1 ? 'arquivo' : 'arquivos';
  return `Última coleta: ${formatted} · ${freshness.artifacts_tracked} ${artifactLabel}`;
}

function metric(
  value: string,
  availability?: AvailabilityItem,
): DashboardMetric {
  const reason = availability?.reason;
  return {
    value,
    subtitle: reason ? availabilityCopy[reason] : undefined,
  };
}

function costLabel(snapshot: ExtensionSnapshot): string {
  return snapshot.billing.mode === 'api'
    ? 'Custo estimado API'
    : 'Custo equivalente via API';
}

function estimatedCostMetric(snapshot: ExtensionSnapshot): DashboardMetric {
  const summary = snapshot.summary;
  const exactCost = summary.estimated_cost_usd;
  const knownCost = summary.known_estimated_cost_usd ?? exactCost;
  const displayCost = exactCost ?? knownCost;
  const label = costLabel(snapshot);
  const totalEvents = summary.estimated_cost_events_total;
  const pricedEvents = summary.estimated_cost_events_priced;
  const coverage = summary.estimated_cost_coverage;
  const complete = summary.estimated_cost_complete;
  const hasCoverage =
    typeof totalEvents === 'number' &&
    typeof pricedEvents === 'number' &&
    typeof coverage === 'number' &&
    typeof complete === 'boolean';

  let coverageNote: string | undefined;
  if (hasCoverage && totalEvents > 0) {
    const status = complete ? 'Estimativa completa' : 'Estimativa parcial';
    coverageNote = `${status}. Cobertura: ${formatInteger(pricedEvents)} de ${formatInteger(totalEvents)} eventos · ${formatPercent(coverage)}.`;
  }

  let billingNote: string;
  switch (snapshot.billing.mode) {
    case 'api':
      billingNote = 'Estimativa baseada em tokens e preços da API; não é cobrança observada.';
      break;
    case 'chatgpt_codex_plan':
      billingNote = 'Uso identificado como plano ChatGPT/Codex; mostra quanto o mesmo consumo custaria pelos preços da API e não representa gasto real.';
      break;
    case 'mixed':
      billingNote = 'O período contém mais de uma forma de cobrança; o valor usa preços da API como referência e não representa gasto real.';
      break;
    default:
      billingNote = 'Forma de cobrança não identificada; o valor usa preços da API como referência e não representa gasto real.';
      break;
  }

  const unavailableReason = displayCost === null
    ? snapshot.availability.estimated_cost.reason
    : null;
  const unavailableNote = unavailableReason
    ? availabilityCopy[unavailableReason]
    : undefined;

  return {
    label,
    value: formatUsd(displayCost),
    subtitle: [coverageNote, unavailableNote, billingNote].filter(Boolean).join(' '),
  };
}

function planDisplayName(planType: string | null | undefined): string {
  if (!planType) return 'Plano não disponível';
  const known: Record<string, string> = {
    pro: 'ChatGPT Pro',
    plus: 'ChatGPT Plus',
  };
  return known[planType.toLowerCase()] ?? planType;
}

function creditBalanceLabel(account: SnapshotCodexAccount): string {
  if (account.credits?.unlimited === true) return 'Créditos ilimitados';
  const raw = account.credits?.balance;
  if (raw === null || raw === undefined) return 'Não disponível';
  const value = Number(raw);
  if (!Number.isFinite(value)) return `${raw} créditos`;
  return `${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)} créditos`;
}

function codexAccountViewModel(
  account: SnapshotCodexAccount | undefined,
): DashboardCodexAccount | undefined {
  if (!account?.available) return undefined;
  return {
    title: `Codex — ${planDisplayName(account.plan_type)}`,
    syncedAtLabel: `Conta sincronizada: ${formatDateTime(account.captured_at)}`,
    primaryUsageLabel: formatPercentPoints(account.primary_used_percent),
    secondaryUsageLabel: formatPercentPoints(account.secondary_used_percent),
    creditBalanceLabel: creditBalanceLabel(account),
    primaryResetLabel: formatEpochSeconds(account.primary_resets_at),
    secondaryResetLabel: formatEpochSeconds(account.secondary_resets_at),
    spendControlLabel: account.spend_control_reached === true
      ? 'Limite de gastos atingido'
      : account.spend_control_reached === false
        ? 'Limite de gastos não atingido'
        : undefined,
  };
}

export function toDashboardViewModel(
  snapshot: ExtensionSnapshot,
  filters: SnapshotFilters,
): DashboardViewModel {
  const freshnessLabel = lastImportedLabel(snapshot);
  const modelCostLabel = costLabel(snapshot);
  return {
    generatedAt: snapshot.generated_at,
    database: `${snapshot.database} · ${freshnessLabel}`,
    lastImportedLabel: freshnessLabel,
    filters,
    isEmpty: snapshot.summary.sessions === 0,
    cards: {
      sessions: metric(formatInteger(snapshot.summary.sessions)),
      totalTokens: metric(formatInteger(snapshot.summary.total_tokens)),
      tokensSaved: metric(formatInteger(snapshot.summary.tokens_saved)),
      cacheRatio: metric(formatPercent(snapshot.summary.cache_ratio)),
      observedCost: metric(
        formatUsd(snapshot.summary.observed_cost_usd),
        snapshot.availability.observed_cost,
      ),
      estimatedCost: estimatedCostMetric(snapshot),
      estimatedSavings: metric(
        formatUsd(snapshot.summary.estimated_savings_usd),
        snapshot.availability.estimated_savings,
      ),
    },
    codexAccount: codexAccountViewModel(snapshot.codex_account),
    dimensions: snapshot.dimensions,
    quality: snapshot.quality,
    series: {
      daily: snapshot.series.daily.map((row) => ({
        date: row.date,
        sessions: row.sessions,
        totalTokens: row.total_tokens,
        cacheRatio: row.cache_ratio,
        observedCostUsd: row.observed_cost_usd,
        estimatedCostUsd: row.estimated_cost_usd,
        estimatedSavingsUsd: row.estimated_savings_usd,
      })),
    },
    breakdowns: {
      projects: snapshot.breakdowns.projects.map((row) => ({
        label: row.project,
        sessions: row.sessions,
        totalTokens: row.total_tokens,
      })),
      models: snapshot.breakdowns.models.map((row) => ({
        label: row.model,
        sessions: row.sessions,
        totalTokens: row.total_tokens,
        estimatedCostUsd: row.estimated_cost_usd,
        costEventsTotal: row.cost_events_total,
        costEventsPriced: row.cost_events_priced,
        costComplete: row.cost_complete,
        costLabel: modelCostLabel,
      })),
      sources: snapshot.breakdowns.sources.map((row) => ({
        label: row.source,
        sessions: row.sessions,
        totalTokens: row.total_tokens,
      })),
      clients: (snapshot.breakdowns.clients ?? []).map((row) => ({
        label: row.client,
        sessions: row.sessions,
        totalTokens: row.total_tokens,
        share: row.share,
        shareLabel: formatPercent(row.share),
      })),
    },
  };
}
