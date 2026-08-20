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
  estimated_cost_usd: number | null;
  estimated_savings_usd: number | null;
}

export type BillingMode = 'api' | 'chatgpt_codex_plan' | 'unknown' | 'mixed';
export type BillingConfidence = 'explicit' | 'unknown' | 'mixed';
export type EstimatedCostBasis = 'openai_api_estimate' | 'openai_api_equivalent';

export interface SnapshotBilling {
  mode: BillingMode;
  confidence: BillingConfidence;
  estimated_cost_basis: EstimatedCostBasis;
  is_observed_spend: boolean;
}

export interface SnapshotFreshness {
  last_imported_at: string | null;
  artifacts_tracked: number;
}

export type AvailabilityReason =
  | 'source_does_not_report_cost'
  | 'insufficient_pricing_data'
  | 'no_optimization_data';

export interface AvailabilityItem {
  available: boolean;
  reason: AvailabilityReason | null;
}

export interface SnapshotAvailability {
  observed_cost: AvailabilityItem;
  estimated_cost: AvailabilityItem;
  estimated_savings: AvailabilityItem;
}

export interface DailySeriesPoint {
  date: string;
  sessions: number;
  total_tokens: number;
  cache_ratio: number | null;
  observed_cost_usd: number | null;
  estimated_cost_usd: number | null;
  estimated_savings_usd: number | null;
}

export interface ProjectBreakdown {
  project: string;
  sessions: number;
  total_tokens: number;
}

export interface ModelBreakdown {
  model: string;
  sessions: number;
  total_tokens: number;
  estimated_cost_usd: number | null;
  cost_events_total: number;
  cost_events_priced: number;
  cost_complete: boolean;
}

export interface SourceBreakdown {
  source: string;
  sessions: number;
  total_tokens: number;
}

export interface ClientBreakdown {
  client: string;
  sessions: number;
  total_tokens: number;
  share: number;
}

export interface SnapshotSeries {
  daily: DailySeriesPoint[];
}

export interface SnapshotBreakdowns {
  projects: ProjectBreakdown[];
  models: ModelBreakdown[];
  sources: SourceBreakdown[];
  clients?: ClientBreakdown[];
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
  version: 2;
  generated_at: string;
  database: string;
  freshness?: SnapshotFreshness;
  filters: SnapshotFilters;
  summary: SnapshotSummary;
  billing: SnapshotBilling;
  availability: SnapshotAvailability;
  series: SnapshotSeries;
  breakdowns: SnapshotBreakdowns;
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

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isNumberOrNull(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function isNumberRecord(value: unknown): value is Record<string, number> {
  return isRecord(value) && Object.values(value).every(isFiniteNumber);
}

function invalid(message: string): never {
  throw new SnapshotContractError('SNAPSHOT_INVALID_JSON', message);
}

function validateAvailabilityItem(value: unknown): void {
  const reasons = new Set([
    'source_does_not_report_cost',
    'insufficient_pricing_data',
    'no_optimization_data',
  ]);
  if (!isRecord(value) || typeof value.available !== 'boolean') {
    invalid('Snapshot availability item is invalid.');
  }
  if (value.reason !== null && !reasons.has(String(value.reason))) {
    invalid('Snapshot availability reason is invalid.');
  }
}

function validateBilling(value: unknown): void {
  if (!isRecord(value)) invalid('Snapshot billing section is invalid.');
  const modes = new Set(['api', 'chatgpt_codex_plan', 'unknown', 'mixed']);
  const confidences = new Set(['explicit', 'unknown', 'mixed']);
  const bases = new Set(['openai_api_estimate', 'openai_api_equivalent']);
  if (
    !modes.has(String(value.mode)) ||
    !confidences.has(String(value.confidence)) ||
    !bases.has(String(value.estimated_cost_basis)) ||
    typeof value.is_observed_spend !== 'boolean'
  ) {
    invalid('Snapshot billing section is invalid.');
  }
}

function validateDaily(value: unknown): void {
  if (!Array.isArray(value)) invalid('Snapshot daily series is invalid.');
  for (const item of value) {
    if (
      !isRecord(item) ||
      typeof item.date !== 'string' ||
      !isFiniteNumber(item.sessions) ||
      !isFiniteNumber(item.total_tokens) ||
      !isNumberOrNull(item.cache_ratio) ||
      !isNumberOrNull(item.observed_cost_usd) ||
      !isNumberOrNull(item.estimated_cost_usd) ||
      !isNumberOrNull(item.estimated_savings_usd)
    ) {
      invalid('Snapshot daily series item is invalid.');
    }
  }
}

function validateBreakdown(value: unknown, labelKey: string): void {
  if (!Array.isArray(value)) invalid('Snapshot breakdown is invalid.');
  for (const item of value) {
    if (
      !isRecord(item) ||
      typeof item[labelKey] !== 'string' ||
      !isFiniteNumber(item.sessions) ||
      !isFiniteNumber(item.total_tokens)
    ) {
      invalid(`Snapshot ${labelKey} breakdown is invalid.`);
    }
  }
}

function validateModelBreakdown(value: unknown): void {
  if (!Array.isArray(value)) invalid('Snapshot model breakdown is invalid.');
  for (const item of value) {
    if (
      !isRecord(item) ||
      typeof item.model !== 'string' ||
      !isFiniteNumber(item.sessions) ||
      !isFiniteNumber(item.total_tokens) ||
      !isNumberOrNull(item.estimated_cost_usd) ||
      !isFiniteNumber(item.cost_events_total) ||
      !isFiniteNumber(item.cost_events_priced) ||
      typeof item.cost_complete !== 'boolean'
    ) {
      invalid('Snapshot model breakdown is invalid.');
    }
    if (
      item.cost_events_total < 0 ||
      item.cost_events_priced < 0 ||
      item.cost_events_priced > item.cost_events_total
    ) {
      invalid('Snapshot model cost coverage is invalid.');
    }
  }
}

function validateClientBreakdown(value: unknown): void {
  if (!Array.isArray(value)) invalid('Snapshot client breakdown is invalid.');
  for (const item of value) {
    if (
      !isRecord(item) ||
      typeof item.client !== 'string' ||
      !isFiniteNumber(item.sessions) ||
      !isFiniteNumber(item.total_tokens) ||
      !isFiniteNumber(item.share) ||
      item.share < 0 ||
      item.share > 1
    ) {
      invalid('Snapshot client breakdown is invalid.');
    }
  }
}

function validateFreshness(value: unknown): void {
  if (!isRecord(value)) invalid('Snapshot freshness is invalid.');
  if (
    value.last_imported_at !== null &&
    typeof value.last_imported_at !== 'string'
  ) {
    invalid('Snapshot last import timestamp is invalid.');
  }
  if (!isFiniteNumber(value.artifacts_tracked)) {
    invalid('Snapshot tracked artifact count is invalid.');
  }
}

export function parseExtensionSnapshot(value: unknown): ExtensionSnapshot {
  if (!isRecord(value)) return invalid('Snapshot must be an object.');
  if (value.schema !== 'agentscope-extension-snapshot') return invalid('Unexpected snapshot schema.');
  if (value.version !== 2) {
    throw new SnapshotContractError(
      'SNAPSHOT_UNSUPPORTED_VERSION',
      `Unsupported snapshot version: ${String(value.version)}`,
    );
  }
  if (typeof value.generated_at !== 'string' || typeof value.database !== 'string') {
    return invalid('Snapshot metadata is invalid.');
  }
  if (value.freshness !== undefined) validateFreshness(value.freshness);
  if (
    !isRecord(value.filters) || !isRecord(value.summary) ||
    !isRecord(value.billing) || !isRecord(value.availability) || !isRecord(value.series) ||
    !isRecord(value.breakdowns) || !isRecord(value.dimensions) ||
    !isRecord(value.quality)
  ) {
    return invalid('Snapshot sections are invalid.');
  }

  const summary = value.summary;
  if (
    !isFiniteNumber(summary.sessions) ||
    !isFiniteNumber(summary.total_tokens) ||
    !isFiniteNumber(summary.tokens_saved) ||
    !isNumberOrNull(summary.cache_ratio) ||
    !isNumberOrNull(summary.observed_cost_usd) ||
    !isNumberOrNull(summary.estimated_cost_usd) ||
    !isNumberOrNull(summary.estimated_savings_usd)
  ) {
    return invalid('Snapshot summary is invalid.');
  }

  validateBilling(value.billing);
  validateAvailabilityItem(value.availability.observed_cost);
  validateAvailabilityItem(value.availability.estimated_cost);
  validateAvailabilityItem(value.availability.estimated_savings);
  validateDaily(value.series.daily);
  validateBreakdown(value.breakdowns.projects, 'project');
  validateModelBreakdown(value.breakdowns.models);
  validateBreakdown(value.breakdowns.sources, 'source');
  if (value.breakdowns.clients !== undefined) {
    validateClientBreakdown(value.breakdowns.clients);
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
    !isFiniteNumber(quality.import_errors) ||
    !isFiniteNumber(quality.tokens_without_model) ||
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
