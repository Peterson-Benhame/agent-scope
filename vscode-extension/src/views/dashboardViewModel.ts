import { ExtensionSnapshot, SnapshotFilters } from '../contracts/snapshot';

export interface DashboardCards {
  sessions: string;
  totalTokens: string;
  tokensSaved: string;
  cacheRatio: string;
  observedCost: string;
  estimatedSavings: string;
}

export interface DashboardViewModel {
  generatedAt: string;
  database: string;
  filters: SnapshotFilters;
  isEmpty: boolean;
  cards: DashboardCards;
  dimensions: ExtensionSnapshot['dimensions'];
  quality: ExtensionSnapshot['quality'];
}

function formatInteger(value: number): string {
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 }).format(value);
}

function formatPercent(value: number | null): string {
  if (value === null) {
    return 'Não disponível';
  }
  return `${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value * 100)}%`;
}

function formatUsd(value: number | null): string {
  if (value === null) {
    return 'Não disponível';
  }
  return `US$ ${new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}`;
}

export function toDashboardViewModel(
  snapshot: ExtensionSnapshot,
  filters: SnapshotFilters,
): DashboardViewModel {
  return {
    generatedAt: snapshot.generated_at,
    database: snapshot.database,
    filters,
    isEmpty: snapshot.summary.sessions === 0,
    cards: {
      sessions: formatInteger(snapshot.summary.sessions),
      totalTokens: formatInteger(snapshot.summary.total_tokens),
      tokensSaved: formatInteger(snapshot.summary.tokens_saved),
      cacheRatio: formatPercent(snapshot.summary.cache_ratio),
      observedCost: formatUsd(snapshot.summary.observed_cost_usd),
      estimatedSavings: formatUsd(snapshot.summary.estimated_savings_usd),
    },
    dimensions: snapshot.dimensions,
    quality: snapshot.quality,
  };
}
