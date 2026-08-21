import * as vscode from 'vscode';

import { AgentScopeClient, SnapshotClientError } from '../client/agentScopeClient';
import { Period, SnapshotFilters } from '../contracts/snapshot';
import { AgentScopeSettings } from '../config/settings';
import {
  applyCustomRange,
  applyFilterPatch,
  applyPeriod,
  createDefaultFilterState,
  reconcileDimensionFilters,
  resetFilters,
} from '../state/filterState';
import { DashboardViewProvider } from '../views/dashboardViewProvider';
import { ProjectsViewProvider } from '../views/projectsViewProvider';
import { SourcesViewProvider } from '../views/sourcesViewProvider';

export type SettingsReader = () => AgentScopeSettings;

export class DashboardCoordinator {
  private filters: SnapshotFilters;
  private requestSequence = 0;

  constructor(
    private readonly readSettings: SettingsReader,
    private readonly dashboard: DashboardViewProvider,
    private readonly sources: SourcesViewProvider,
    private readonly projects: ProjectsViewProvider,
    private readonly output: vscode.OutputChannel,
  ) {
    this.filters = createDefaultFilterState(readSettings().defaultPeriod);
  }

  get currentFilters(): SnapshotFilters {
    return { ...this.filters };
  }

  private client(): AgentScopeClient {
    const settings = this.readSettings();
    return new AgentScopeClient({
      executablePath: settings.executablePath,
      databasePath: settings.databasePath,
    });
  }

  async refresh(): Promise<void> {
    const sequence = ++this.requestSequence;
    this.dashboard.setLoading();
    const client = this.client();

    try {
      const snapshot = await client.snapshot(this.filters);
      if (sequence !== this.requestSequence) return;
      this.filters = reconcileDimensionFilters(this.filters, snapshot.dimensions);
      this.sources.setItems(snapshot.dimensions.sources);
      this.projects.setItems(snapshot.dimensions.projects);
      this.dashboard.update(snapshot, this.filters);
    } catch (error) {
      if (sequence !== this.requestSequence) return;
      const mapped = this.mapError(error);
      this.output.appendLine(`[${mapped.code}] ${mapped.detail}`);
      this.dashboard.showError(mapped.code, mapped.message);
    }
  }

  async refreshDerived(): Promise<void> {
    this.dashboard.setLoading();
    try {
      const result = await this.client().refreshDerivedData();
      this.output.appendLine(
        `[DERIVED_REFRESH] context_updated=${String(result.context.sessions_updated ?? 'unknown')} ` +
        `events_priced=${String(result.costs.events_priced ?? 'unknown')} ` +
        `events_unpriced=${String(result.costs.events_unpriced ?? 'unknown')}`,
      );
      await this.refresh();
    } catch (error) {
      const mapped = this.mapError(error);
      this.output.appendLine(`[${mapped.code}] ${mapped.detail}`);
      this.dashboard.showError(mapped.code, mapped.message);
    }
  }

  async syncCodex(): Promise<void> {
    this.dashboard.setCodexSyncing();
    try {
      const result = await this.client().syncCodexAndRecalculate();
      this.output.appendLine(
        `[CODEX_SYNC] account=${String(result.account.status ?? 'unknown')} ` +
        `context_updated=${String(result.context.sessions_updated ?? 'unknown')} ` +
        `events_priced=${String(result.costs.events_priced ?? 'unknown')} ` +
        `events_unpriced=${String(result.costs.events_unpriced ?? 'unknown')}`,
      );
      await this.refresh();
    } catch (error) {
      const mapped = this.mapError(error);
      this.output.appendLine(`[${mapped.code}] ${mapped.detail}`);
      this.dashboard.showCodexSyncError(mapped.message);
    }
  }

  async setFilter(patch: Partial<SnapshotFilters>): Promise<void> {
    this.filters = applyFilterPatch(this.filters, patch);
    await this.refresh();
  }

  async setPeriod(period: Period): Promise<void> {
    this.filters = applyPeriod(this.filters, period);
    await this.refresh();
  }

  async setCustomRange(from: string | null, to: string | null): Promise<void> {
    this.filters = applyCustomRange(this.filters, from, to);
    await this.refresh();
  }

  async resetFilters(): Promise<void> {
    this.filters = resetFilters(this.filters, this.readSettings().defaultPeriod);
    await this.refresh();
  }

  private mapError(error: unknown): { code: string; message: string; detail: string } {
    if (error instanceof SnapshotClientError) {
      const messages: Record<string, string> = {
        AGENTSCOPE_NOT_FOUND: 'AgentScope não foi encontrado. Configure agentscope.executablePath.',
        DATABASE_NOT_FOUND: 'Banco AgentScope não encontrado. Selecione um arquivo de banco válido.',
        SNAPSHOT_TIMEOUT: 'A operação do AgentScope excedeu o tempo limite.',
        SNAPSHOT_PROCESS_ERROR: 'O AgentScope não conseguiu concluir a operação.',
        SNAPSHOT_INVALID_JSON: 'O AgentScope retornou dados inválidos para a extensão.',
        SNAPSHOT_UNSUPPORTED_VERSION: 'A versão do AgentScope não é compatível com esta extensão.',
      };
      return {
        code: error.code,
        message: messages[error.code] ?? 'Falha ao carregar o AgentScope.',
        detail: error.message,
      };
    }
    return {
      code: 'SNAPSHOT_PROCESS_ERROR',
      message: 'Falha ao carregar o AgentScope.',
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}
