import {
  Period,
  SnapshotDimensions,
  SnapshotFilters,
} from '../contracts/snapshot';

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

export function reconcileDimensionFilters(
  filters: SnapshotFilters,
  dimensions: SnapshotDimensions,
): SnapshotFilters {
  return {
    ...filters,
    project: filters.project && dimensions.projects.includes(filters.project)
      ? filters.project : null,
    model: filters.model && dimensions.models.includes(filters.model)
      ? filters.model : null,
    source: filters.source && dimensions.sources.includes(filters.source)
      ? filters.source : null,
    user: filters.user && dimensions.users.includes(filters.user)
      ? filters.user : null,
    machine: filters.machine && dimensions.machines.includes(filters.machine)
      ? filters.machine : null,
  };
}

export function resetFilters(_state: SnapshotFilters, period: Period): SnapshotFilters {
  return { period };
}
