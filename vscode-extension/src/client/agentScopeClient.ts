import { execFile } from 'child_process';

import {
  ExtensionSnapshot,
  parseExtensionSnapshot,
  SnapshotContractError,
  SnapshotFilters,
} from '../contracts/snapshot';

export type SnapshotClientErrorCode =
  | 'AGENTSCOPE_NOT_FOUND'
  | 'DATABASE_NOT_FOUND'
  | 'SNAPSHOT_TIMEOUT'
  | 'SNAPSHOT_PROCESS_ERROR'
  | 'SNAPSHOT_INVALID_JSON'
  | 'SNAPSHOT_UNSUPPORTED_VERSION';

export class SnapshotClientError extends Error {
  constructor(
    public readonly code: SnapshotClientErrorCode,
    message: string,
  ) {
    super(message);
    this.name = 'SnapshotClientError';
  }
}

export interface ProcessResult {
  stdout: string;
  stderr: string;
  exitCode: number;
}

export interface ProcessRunner {
  run(executable: string, args: readonly string[], timeoutMs: number): Promise<ProcessResult>;
}

export class ExecFileProcessRunner implements ProcessRunner {
  run(executable: string, args: readonly string[], timeoutMs: number): Promise<ProcessResult> {
    return new Promise((resolve, reject) => {
      execFile(
        executable,
        [...args],
        {
          encoding: 'utf8',
          shell: false,
          timeout: timeoutMs,
          maxBuffer: 2 * 1024 * 1024,
        },
        (error, stdout, stderr) => {
          if (error) {
            const enriched = error as NodeJS.ErrnoException & { killed?: boolean; code?: string | number };
            if (enriched.killed) {
              reject(new SnapshotClientError('SNAPSHOT_TIMEOUT', 'AgentScope snapshot timed out.'));
              return;
            }
            if (enriched.code === 'ENOENT') {
              reject(new SnapshotClientError('AGENTSCOPE_NOT_FOUND', 'AgentScope executable was not found.'));
              return;
            }
            resolve({
              stdout: stdout ?? '',
              stderr: stderr ?? '',
              exitCode: typeof enriched.code === 'number' ? enriched.code : 1,
            });
            return;
          }
          resolve({ stdout: stdout ?? '', stderr: stderr ?? '', exitCode: 0 });
        },
      );
    });
  }
}

export interface AgentScopeClientOptions {
  executablePath?: string;
  databasePath?: string;
  timeoutMs?: number;
  runner?: ProcessRunner;
}

export function buildSnapshotArgs(
  filters: SnapshotFilters,
  databasePath = '',
): string[] {
  const args = ['extension', 'snapshot', '--json'];
  if (databasePath) {
    args.push('--database', databasePath);
  }
  if (filters.from) {
    args.push('--from', filters.from);
  }
  if (filters.to) {
    args.push('--to', filters.to);
  }
  if (!filters.from && !filters.to && filters.period) {
    args.push('--period', filters.period);
  }
  for (const key of ['project', 'model', 'source', 'user', 'machine'] as const) {
    const value = filters[key];
    if (value) {
      args.push(`--${key}`, value);
    }
  }
  return args;
}

export class AgentScopeClient {
  private readonly executablePath: string;
  private readonly databasePath: string;
  private readonly timeoutMs: number;
  private readonly runner: ProcessRunner;

  constructor(options: AgentScopeClientOptions = {}) {
    this.executablePath = options.executablePath || 'agentscope';
    this.databasePath = options.databasePath || '';
    this.timeoutMs = options.timeoutMs ?? 15_000;
    this.runner = options.runner ?? new ExecFileProcessRunner();
  }

  async snapshot(filters: SnapshotFilters): Promise<ExtensionSnapshot> {
    let result: ProcessResult;
    try {
      result = await this.runner.run(
        this.executablePath,
        buildSnapshotArgs(filters, this.databasePath),
        this.timeoutMs,
      );
    } catch (error) {
      if (error instanceof SnapshotClientError) {
        throw error;
      }
      const candidate = error as NodeJS.ErrnoException & { killed?: boolean };
      if (candidate?.code === 'ENOENT') {
        throw new SnapshotClientError('AGENTSCOPE_NOT_FOUND', 'AgentScope executable was not found.');
      }
      if (candidate?.killed) {
        throw new SnapshotClientError('SNAPSHOT_TIMEOUT', 'AgentScope snapshot timed out.');
      }
      throw new SnapshotClientError('SNAPSHOT_PROCESS_ERROR', 'AgentScope snapshot process failed.');
    }

    if (result.exitCode !== 0) {
      if (result.stderr.toLowerCase().includes('database not found:')) {
        throw new SnapshotClientError('DATABASE_NOT_FOUND', 'AgentScope database was not found.');
      }
      throw new SnapshotClientError('SNAPSHOT_PROCESS_ERROR', 'AgentScope snapshot process returned an error.');
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(result.stdout);
    } catch {
      throw new SnapshotClientError('SNAPSHOT_INVALID_JSON', 'AgentScope returned invalid snapshot JSON.');
    }

    try {
      return parseExtensionSnapshot(parsed);
    } catch (error) {
      if (error instanceof SnapshotContractError) {
        throw new SnapshotClientError(error.code, error.message);
      }
      throw new SnapshotClientError('SNAPSHOT_INVALID_JSON', 'AgentScope returned an invalid snapshot.');
    }
  }
}
