import { Period } from '../contracts/snapshot';

export interface AgentScopeSettings {
  executablePath: string;
  databasePath: string;
  defaultPeriod: Period;
  autoRefresh: boolean;
  autoRefreshIntervalSeconds: number;
}

const periods = new Set<Period>(['today', '7d', '30d', 'month']);

export function normalizeSettings(values: Partial<AgentScopeSettings>): AgentScopeSettings {
  const period = values.defaultPeriod && periods.has(values.defaultPeriod)
    ? values.defaultPeriod
    : '7d';
  const interval = Math.max(10, values.autoRefreshIntervalSeconds ?? 60);
  return {
    executablePath: values.executablePath?.trim() || 'agentscope',
    databasePath: values.databasePath?.trim() || '',
    defaultPeriod: period,
    autoRefresh: values.autoRefresh ?? false,
    autoRefreshIntervalSeconds: interval,
  };
}

export function readSettings(): AgentScopeSettings {
  const vscode = require('vscode') as typeof import('vscode');
  const config = vscode.workspace.getConfiguration('agentscope');
  return normalizeSettings({
    executablePath: config.get<string>('executablePath'),
    databasePath: config.get<string>('databasePath'),
    defaultPeriod: config.get<Period>('defaultPeriod'),
    autoRefresh: config.get<boolean>('autoRefresh'),
    autoRefreshIntervalSeconds: config.get<number>('autoRefreshIntervalSeconds'),
  });
}

export async function setDatabasePath(path: string): Promise<void> {
  const vscode = require('vscode') as typeof import('vscode');
  await vscode.workspace
    .getConfiguration('agentscope')
    .update('databasePath', path, vscode.ConfigurationTarget.Global);
}
