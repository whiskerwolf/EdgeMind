import * as vscode from 'vscode';
import { BackendStatus } from '../types/api';

/**
 * Manages the EdgeMind Status Bar item in the bottom right of the VS Code window.
 * Shows online/offline status with theme-appropriate icons and color tokens.
 */
export class StatusBarManager {
  private item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.item.command = 'edgemind.checkBackend';
    this.setStatus('checking', 'Initializing EdgeMind backend connection...');
    this.item.show();
  }

  public setStatus(status: BackendStatus, tooltipInfo?: string): void {
    switch (status) {
      case 'online':
        this.item.text = '$(circle-filled) EdgeMind: Online';
        this.item.color = new vscode.ThemeColor('testing.iconPassed');
        this.item.tooltip = tooltipInfo || 'EdgeMind backend is connected and healthy.\nClick to re-check.';
        break;
      case 'offline':
        this.item.text = '$(circle-outline) EdgeMind: Offline';
        this.item.color = new vscode.ThemeColor('testing.iconFailed');
        this.item.tooltip = tooltipInfo || 'EdgeMind backend is unreachable.\nClick to re-check.';
        break;
      case 'checking':
        this.item.text = '$(sync~spin) EdgeMind: Checking...';
        this.item.color = undefined;
        this.item.tooltip = tooltipInfo || 'Verifying EdgeMind backend connectivity...';
        break;
    }
  }

  public dispose(): void {
    this.item.dispose();
  }
}
