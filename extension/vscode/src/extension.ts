import * as vscode from 'vscode';
import { ApiClient } from './api/client';
import { Logger } from './utils/logger';
import { StatusBarManager } from './ui/statusBar';
import { analyzeCurrentFile } from './commands/analyzeCurrentFile';
import { analyzeSelection } from './commands/analyzeSelection';
import { clearDiagnostics } from './commands/clearDiagnostics';
import {
  CONFIG_SECTION,
  CONFIG_BACKEND_URL,
  getBackendUrl,
  validateBackendUrl,
} from './utils/configuration';

let apiClient: ApiClient;
let statusBar: StatusBarManager;

/**
 * EdgeMind Extension Activation.
 * Initializes OutputChannel, API Client, Status Bar, and registers commands.
 */
export function activate(context: vscode.ExtensionContext): void {
  const logger = Logger.getInstance();
  logger.info('EdgeMind VS Code Extension activated.');

  // Initialize API client with configured URL
  const backendUrl = getBackendUrl();
  apiClient = new ApiClient({
    baseUrl: backendUrl,
    logger,
  });
  logger.info(`Configured backend URL: ${backendUrl}`);

  // Initialize status bar item
  statusBar = new StatusBarManager();

  // Initialize native Diagnostic Collection for EdgeMind
  const diagnosticCollection = vscode.languages.createDiagnosticCollection('EdgeMind');

  // Command: edgemind.hello
  const helloCommand = vscode.commands.registerCommand('edgemind.hello', () => {
    logger.info('Command edgemind.hello executed.');
    vscode.window.showInformationMessage('EdgeMind is running inside VS Code!');
  });

  // Command: edgemind.showOutput
  const showOutputCommand = vscode.commands.registerCommand('edgemind.showOutput', () => {
    logger.info('Command edgemind.showOutput executed.');
    logger.show(true);
  });

  // Command: edgemind.checkBackend
  const checkBackendCommand = vscode.commands.registerCommand('edgemind.checkBackend', async () => {
    const currentUrl = getBackendUrl();
    apiClient.setBaseUrl(currentUrl);

    logger.info(`Manual backend health check triggered for: ${currentUrl}`);
    statusBar.setStatus('checking', `Checking backend at ${currentUrl}...`);

    await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: 'EdgeMind: Checking backend status...',
        cancellable: false,
      },
      async () => {
        const result = await apiClient.checkHealth();
        if (result.success && result.data) {
          statusBar.setStatus(
            'online',
            `EdgeMind: Online (${result.data.service} - ${result.durationMs}ms)\n${currentUrl}`
          );
          logger.info(
            `Backend health check PASSED: Service=${result.data.service}, Status=${result.data.status} (${result.durationMs}ms)`
          );
          vscode.window.showInformationMessage(
            `EdgeMind backend is Online (${result.data.service}) at ${currentUrl} [${result.durationMs}ms]`
          );
        } else {
          statusBar.setStatus(
            'offline',
            `EdgeMind: Offline\n${result.error || 'Connection failed'}\n${currentUrl}`
          );
          logger.warn(`Backend health check FAILED (${result.durationMs}ms): ${result.error}`);
          const selection = await vscode.window.showErrorMessage(
            `EdgeMind backend is Offline at ${currentUrl}. ${result.error}`,
            'View Output Channel',
            'Settings'
          );
          if (selection === 'View Output Channel') {
            logger.show(true);
          } else if (selection === 'Settings') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'edgemind.backendUrl');
          }
        }
      }
    );
  });

  // Command: edgemind.analyzeCurrentFile
  const analyzeCurrentFileCommand = vscode.commands.registerCommand(
    'edgemind.analyzeCurrentFile',
    () => analyzeCurrentFile(apiClient, logger, diagnosticCollection)
  );

  // Command: edgemind.analyzeSelection
  const analyzeSelectionCommand = vscode.commands.registerCommand(
    'edgemind.analyzeSelection',
    () => analyzeSelection(apiClient, logger, diagnosticCollection)
  );

  // Command: edgemind.clearDiagnostics
  const clearDiagnosticsCommand = vscode.commands.registerCommand(
    'edgemind.clearDiagnostics',
    () => clearDiagnostics(diagnosticCollection, logger)
  );

  // Clear diagnostics when a text document is closed
  const closeDocListener = vscode.workspace.onDidCloseTextDocument((document) => {
    diagnosticCollection.delete(document.uri);
    logger.info(`Cleared EdgeMind diagnostics for closed document: ${document.fileName}`);
  });

  // Listen for configuration changes
  const configListener = vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration(`${CONFIG_SECTION}.${CONFIG_BACKEND_URL}`)) {
      const newUrl = getBackendUrl();
      const validation = validateBackendUrl(newUrl);
      if (validation.valid && validation.normalized) {
        apiClient.setBaseUrl(validation.normalized);
        logger.info(`Backend URL updated in settings: ${validation.normalized}`);
        // Run silent health check to update status bar
        apiClient.checkHealth(3000).then((res) => {
          if (res.success && res.data) {
            statusBar.setStatus(
              'online',
              `EdgeMind: Online (${res.data.service} - ${res.durationMs}ms)\n${validation.normalized}`
            );
          } else {
            statusBar.setStatus(
              'offline',
              `EdgeMind: Offline (${res.error})\n${validation.normalized}`
            );
          }
        });
      } else {
        logger.warn(`Invalid backend URL configured: ${validation.error}`);
        vscode.window.showWarningMessage(`EdgeMind: ${validation.error}`);
        statusBar.setStatus('offline', `Invalid backend URL: ${validation.error}`);
      }
    }
  });

  // Perform initial silent health check on activation to populate status bar
  apiClient.checkHealth(3000).then((res) => {
    if (res.success && res.data) {
      statusBar.setStatus(
        'online',
        `EdgeMind: Online (${res.data.service} - ${res.durationMs}ms)\n${backendUrl}`
      );
      logger.info(`Initial backend health check: Online (${res.data.service}) [${res.durationMs}ms]`);
    } else {
      statusBar.setStatus(
        'offline',
        `EdgeMind: Offline (${res.error})\n${backendUrl}`
      );
      logger.info(`Initial backend health check: Offline (${res.error})`);
    }
  });

  // Register disposables
  context.subscriptions.push(
    { dispose: () => logger.dispose() },
    statusBar,
    helloCommand,
    showOutputCommand,
    checkBackendCommand,
    analyzeCurrentFileCommand,
    analyzeSelectionCommand,
    clearDiagnosticsCommand,
    diagnosticCollection,
    closeDocListener,
    configListener
  );
}

/**
 * EdgeMind Extension Deactivation.
 */
export function deactivate(): void {
  const logger = Logger.getInstance();
  logger.info('EdgeMind VS Code Extension deactivated.');
}
