import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';

describe('Dashboard manual refresh routing', () => {
  it('uses a derived-data refresh message for the toolbar button', () => {
    const mediaPath = path.resolve(__dirname, '../../../media/dashboard.js');
    const source = fs.readFileSync(mediaPath, 'utf8');

    assert.ok(source.includes("refreshDerived"));
    assert.ok(source.includes("vscode.postMessage({ type: 'refreshDerived' })"));
  });

  it('keeps initial dashboard loading on the lightweight refresh path', () => {
    const providerPath = path.resolve(__dirname, '../../views/dashboardViewProvider.js');
    const source = fs.readFileSync(providerPath, 'utf8');

    assert.ok(source.includes("this.handler?.({ type: 'refresh' })"));
  });

  it('routes the manual refresh message to derived-data recalculation', () => {
    const extensionPath = path.resolve(__dirname, '../../extension.js');
    const source = fs.readFileSync(extensionPath, 'utf8');

    assert.ok(source.includes("case 'refreshDerived':"));
    assert.ok(source.includes('await coordinator.refreshDerived();'));
  });
});
