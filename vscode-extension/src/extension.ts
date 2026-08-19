import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand('agentscope.openDashboard', async () => {
      await vscode.commands.executeCommand('agentscope.dashboard.focus');
    }),
    vscode.commands.registerCommand('agentscope.refreshDashboard', () => undefined),
    vscode.commands.registerCommand('agentscope.selectDatabase', () => undefined),
  );
}

export function deactivate(): void {}
