import * as vscode from 'vscode';

import { Period, SnapshotFilters } from './contracts/snapshot';
import { readSettings, setDatabasePath } from './config/settings';
import { DashboardCoordinator } from './services/dashboardCoordinator';
import { DashboardViewProvider } from './views/dashboardViewProvider';
import { ProjectsViewProvider } from './views/projectsViewProvider';
import { SourcesViewProvider } from './views/sourcesViewProvider';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isPeriod(value: unknown): value is Period {
  return value === 'today' || value === '7d' || value === '30d' || value === 'month';
}

function safeFilterPatch(value: unknown): Partial<SnapshotFilters> {
  if (!isRecord(value)) {
    return {};
  }
  const result: Partial<SnapshotFilters> = {};
  for (const key of ['project', 'model', 'source', 'user', 'machine'] as const) {
    const candidate = value[key];
    if (candidate === null || typeof candidate === 'string') {
      result[key] = candidate;
    }
  }
  return result;
}

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel('AgentScope');
  const dashboard = new DashboardViewProvider(context.extensionUri);
  const sources = new SourcesViewProvider();
  const projects = new ProjectsViewProvider();
  const coordinator = new DashboardCoordinator(
    readSettings,
    dashboard,
    sources,
    projects,
    output,
  );

  dashboard.setMessageHandler(async (message) => {
    if (!isRecord(message) || typeof message.type !== 'string') {
      return;
    }
    switch (message.type) {
      case 'load':
        await coordinator.refresh();
        return;
      case 'refresh':
        await coordinator.refreshDerived();
        return;
      case 'syncCodex':
        await coordinator.syncCodex();
        return;
      case 'selectDatabase':
        await vscode.commands.executeCommand('agentscope.selectDatabase');
        return;
      case 'setFilter':
        await coordinator.setFilter(safeFilterPatch(message.patch));
        return;
      case 'setPeriod':
        if (isPeriod(message.period)) {
          await coordinator.setPeriod(message.period);
        }
        return;
      case 'setCustomRange': {
        const from = message.from === null || typeof message.from === 'string' ? message.from : null;
        const to = message.to === null || typeof message.to === 'string' ? message.to : null;
        await coordinator.setCustomRange(from, to);
        return;
      }
      case 'resetFilters':
        await coordinator.resetFilters();
        return;
      default:
        return;
    }
  });

  context.subscriptions.push(
    output,
    sources,
    projects,
    vscode.window.registerWebviewViewProvider('agentscope.dashboard', dashboard),
    vscode.window.registerTreeDataProvider('agentscope.sources', sources),
    vscode.window.registerTreeDataProvider('agentscope.projects', projects),
    vscode.commands.registerCommand('agentscope.openDashboard', async () => {
      await vscode.commands.executeCommand('workbench.view.extension.agentscope');
      await vscode.commands.executeCommand('agentscope.dashboard.focus');
    }),
    vscode.commands.registerCommand('agentscope.refreshDashboard', async () => {
      await coordinator.refreshDerived();
    }),
    vscode.commands.registerCommand('agentscope.selectDatabase', async () => {
      const selected = await vscode.window.showOpenDialog({
        canSelectFiles: true,
        canSelectFolders: false,
        canSelectMany: false,
        filters: { 'SQLite database': ['db', 'sqlite', 'sqlite3'] },
        openLabel: 'Selecionar banco AgentScope',
      });
      if (!selected?.length) {
        return;
      }
      await setDatabasePath(selected[0].fsPath);
      await coordinator.refresh();
    }),
    vscode.commands.registerCommand('agentscope.filterBySource', async (source: string) => {
      await coordinator.setFilter({ source });
    }),
    vscode.commands.registerCommand('agentscope.filterByProject', async (project: string) => {
      await coordinator.setFilter({ project });
    }),
  );
}

export function deactivate(): void {}
