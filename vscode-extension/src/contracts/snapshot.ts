export type Period = 'today' | '7d' | '30d' | 'month';

export interface SnapshotFilters {
  from?: string | null;
  to?: string | null;
  period?: Period | null;
  project?: string | null;
  model?: string | null;
  source?: string | null;
  user?: string | null;
  machine?: string | null;
}

export interface SnapshotSummary {
  sessions: number;
  total_tokens: number;
  tokens_saved: number;
  cache_ratio: number | null;
  observed_cost_usd: number | null;
  estimated_savings_usd: number | null;
}

export interface SnapshotDimensions {
  projects: string[];
  models: string[];
  sources: string[];
  users: string[];
  machines: string[];
}

export interface SnapshotQuality {
  import_errors: number;
  tokens_without_model: number;
  identity_confidence: Record<string, number>;
  correlation_confidence: Record<string, number>;
}

export interface ExtensionSnapshot {
  schema: 'agentscope-extension-snapshot';
  version: 1;
  generated_at: string;
  database: string;
  filters: SnapshotFilters;
  summary: SnapshotSummary;
  dimensions: SnapshotDimensions;
  quality: SnapshotQuality;
}

export type SnapshotContractErrorCode =
  | 'SNAPSHOT_INVALID_JSON'
  | 'SNAPSHOT_UNSUPPORTED_VERSION';

export class SnapshotContractError extends Error {
  constructor(
    public readonly code: SnapshotContractErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'SnapshotContractError';
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNumberOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value));
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isNumberRecord(value: unknown): value is Record<string, number> {
  return isRecord(value) && Object.values(value).every(
    (item) => typeof item === 'number' && Number.isFinite(item),
  );
}

function invalid(message: string): never {
  throw new SnapshotContractError('SNAPSHOT_INVALID_JSON', message);
}

export function parseExtensionSnapshot(value: unknown): ExtensionSnapshot {
  if (!isRecord(value)) {
    return invalid('Snapshot must be an object.');
  }
  if (value.schema !== 'agentscope-extension-snapshot') {
    return invalid('Unexpected snapshot schema.');
  }
  if (value.version !== 1) {
    throw new SnapshotContractError(
      'SNAPSHOT_UNSUPPORTED_VERSION',
      `Unsupported snapshot version: ${String(value.version)}`,
    );
  }
  if (typeof value.generated_at !== 'string' || typeof value.database !== 'string') {
    return invalid('Snapshot metadata is invalid.');
  }
  if (!isRecord(value.filters) || !isRecord(value.summary) || !isRecord(value.dimensions) || !isRecord(value.quality)) {
    return invalid('Snapshot sections are invalid.');
  }

  const summary = value.summary;
  if (
    typeof summary.sessions !== 'number' ||
    typeof summary.total_tokens !== 'number' ||
    typeof summary.tokens_saved !== 'number' ||
    !isNumberOrNull(summary.cache_ratio) ||
    !isNumberOrNull(summary.observed_cost_usd) ||
    !isNumberOrNull(summary.estimated_savings_usd)
  ) {
    return invalid('Snapshot summary is invalid.');
  }

  const dimensions = value.dimensions;
  if (
    !isStringArray(dimensions.projects) ||
    !isStringArray(dimensions.models) ||
    !isStringArray(dimensions.sources) ||
    !isStringArray(dimensions.users) ||
    !isStringArray(dimensions.machines)
  ) {
    return invalid('Snapshot dimensions are invalid.');
  }

  const quality = value.quality;
  if (
    typeof quality.import_errors !== 'number' ||
    typeof quality.tokens_without_model !== 'number' ||
    !isNumberRecord(quality.identity_confidence) ||
    !isNumberRecord(quality.correlation_confidence)
  ) {
    return invalid('Snapshot quality section is invalid.');
  }

  const allowedPeriods = new Set(['today', '7d', '30d', 'month']);
  for (const key of ['from', 'to', 'project', 'model', 'source', 'user', 'machine'] as const) {
    const filterValue = value.filters[key];
    if (filterValue !== undefined && filterValue !== null && typeof filterValue !== 'string') {
      return invalid(`Invalid filter: ${key}`);
    }
  }
  const period = value.filters.period;
  if (period !== undefined && period !== null && !allowedPeriods.has(String(period))) {
    return invalid('Invalid period filter.');
  }

  return value as unknown as ExtensionSnapshot;
}
