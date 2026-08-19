import { Period, SnapshotFilters } from '../contracts/snapshot';

export function createDefaultFilterState(period: Period): SnapshotFilters {
  return { period };
}

export function applyPeriod(state: SnapshotFilters, period: Period): SnapshotFilters {
  return { ...state, period, from: null, to: null };
}

export function applyCustomRange(
  state: SnapshotFilters,
  from: string | null,
  to: string | null,
): SnapshotFilters {
  return { ...state, period: null, from, to };
}

export function applyFilterPatch(
  state: SnapshotFilters,
  patch: Partial<SnapshotFilters>,
): SnapshotFilters {
  return { ...state, ...patch };
}

export function resetFilters(_state: SnapshotFilters, period: Period): SnapshotFilters {
  return { period };
}
