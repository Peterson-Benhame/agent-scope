import {
  AvailabilityItem,
  AvailabilityReason,
  ExtensionSnapshot,
  SnapshotFilters,
} from '../contracts/snapshot';

export interface DashboardMetric {
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

export interface DashboardViewModel {
  generatedAt: string;
  database: string;
  lastImportedLabel: string;
  filters: SnapshotFilters;
  isEmpty: boolean;
  cards: DashboardCards;
  dimensions: ExtensionSnapshot['dimensions'];
  quality: ExtensionSnapshot['quality'];
  series: { daily: DashboardDailyPoint[] };
  breakdowns: {
    projects: DashboardBreakdownPoint[];
    models: DashboardBreakdownPoint[];
    sources: DashboardBreakdownPoint[];
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

function formatUsd(value: number | null): string {
  if (value === null) return 'Não disponível';
  return `US$ ${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}`;
}

function lastImportedLabel(snapshot: ExtensionSnapshot): string {
  const freshness = snapshot.freshness;
  if (!freshness?.last_imported_at) return 'Última coleta: não disponível';
  const raw = freshness.last_imported_at;
  const normalized = raw.includes('T') ? raw : `${raw.replace(' ', 'T')}Z`;
  const parsed = new Date(normalized);
  const formatted = Number.isNaN(parsed.getTime())
    ? raw
    : new Intl.DateTimeFormat('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short',
      }).format(parsed);
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

export function toDashboardViewModel(
  snapshot: ExtensionSnapshot,
  filters: SnapshotFilters,
): DashboardViewModel {
  return {
    generatedAt: snapshot.generated_at,
    database: snapshot.database,
    lastImportedLabel: lastImportedLabel(snapshot),
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
      estimatedCost: metric(
        formatUsd(snapshot.summary.estimated_cost_usd),
        snapshot.availability.estimated_cost,
      ),
      estimatedSavings: metric(
        formatUsd(snapshot.summary.estimated_savings_usd),
        snapshot.availability.estimated_savings,
      ),
    },
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
      })),
      sources: snapshot.breakdowns.sources.map((row) => ({
        label: row.source,
        sessions: row.sessions,
        totalTokens: row.total_tokens,
      })),
    },
  };
}
