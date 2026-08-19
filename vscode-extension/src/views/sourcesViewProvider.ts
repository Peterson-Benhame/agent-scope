import * as vscode from 'vscode';

export class SourcesViewProvider implements vscode.TreeDataProvider<string> {
  private readonly changed = new vscode.EventEmitter<string | undefined | void>();
  readonly onDidChangeTreeData = this.changed.event;
  private items: string[] = [];

  setItems(values: readonly string[]): void {
    this.items = [...values];
    this.changed.fire();
  }

  getTreeItem(element: string): vscode.TreeItem {
    const item = new vscode.TreeItem(element, vscode.TreeItemCollapsibleState.None);
    item.iconPath = new vscode.ThemeIcon('plug');
    item.command = {
      command: 'agentscope.filterBySource',
      title: 'Filtrar por fonte',
      arguments: [element],
    };
    return item;
  }

  getChildren(): string[] {
    return this.items;
  }

  dispose(): void {
    this.changed.dispose();
  }
}
