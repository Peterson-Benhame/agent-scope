import * as crypto from 'crypto';
import * as vscode from 'vscode';

import { ExtensionSnapshot, Period, SnapshotFilters } from '../contracts/snapshot';
import { DashboardViewModel, toDashboardViewModel } from './dashboardViewModel';

export type DashboardMessageHandler = (message: unknown) => void | Promise<void>;

export class DashboardViewProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private handler?: DashboardMessageHandler;

  constructor(private readonly extensionUri: vscode.Uri) {}

  setMessageHandler(handler: DashboardMessageHandler): void {
    this.handler = handler;
  }

  resolveWebviewView(webviewView: vscode.WebviewView): void {
    this.view = webviewView;
    const webview = webviewView.webview;
    webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };
    webview.html = this.html(webview);
    webview.onDidReceiveMessage(async (message) => {
      if (this.handler) {
        await this.handler(message);
      }
    });
    void this.handler?.({ type: 'refresh' });
  }

  setLoading(): void {
    void this.view?.webview.postMessage({ type: 'loading' });
  }

  update(snapshot: ExtensionSnapshot, filters: SnapshotFilters): void {
    const payload: DashboardViewModel = toDashboardViewModel(snapshot, filters);
    void this.view?.webview.postMessage({ type: 'snapshot', payload });
  }

  showError(code: string, message: string): void {
    void this.view?.webview.postMessage({ type: 'error', code, message });
  }

  private html(webview: vscode.Webview): string {
    const nonce = crypto.randomBytes(16).toString('base64');
    const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, 'media', 'dashboard.js'));
    const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, 'media', 'dashboard.css'));
    const csp = [
      "default-src 'none'",
      `img-src ${webview.cspSource} data:`,
      `style-src ${webview.cspSource}`,
      `script-src 'nonce-${nonce}'`,
    ].join('; ');

    return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <link rel="stylesheet" href="${styleUri}">
  <title>AgentScope</title>
</head>
<body>
  <header class="toolbar">
    <strong>AgentScope</strong>
    <div class="toolbar-actions">
      <button id="select-database">Banco</button>
      <button id="refresh">Atualizar</button>
    </div>
  </header>
  <section id="filters" class="filters" aria-label="Filtros"></section>
  <section id="status" class="status">Carregando...</section>
  <section id="cards" class="cards" aria-live="polite"></section>
  <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
  }
}

export interface DashboardFilterMessage {
  type: 'setFilter';
  patch: Partial<SnapshotFilters>;
}

export interface DashboardPeriodMessage {
  type: 'setPeriod';
  period: Period;
}
