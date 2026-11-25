import * as vscode from 'vscode';
import { ApiClient } from '../api/client';
import { Logger } from '../utils/logger';
import { validateEditorDocument } from '../utils/editorValidator';
import { formatReportOutput, formatSummaryNotification } from '../utils/reportFormatter';
import { updateDocumentDiagnostics } from '../utils/diagnosticMapper';
import { ResultsPanel } from '../ui/results/resultsPanel';
import { getBackendUrl } from '../utils/configuration';

/**
 * Command handler for "EdgeMind: Analyze Current File" (edgemind.analyzeCurrentFile).
 * Reads the active editor's Python source code, performs client validation,
 * sends static analysis request to the EdgeMind backend, and presents results.
 */
export async function analyzeCurrentFile(
  apiClient: ApiClient,
  logger: Logger,
  diagnosticCollection?: vscode.DiagnosticCollection,
  extensionUri?: vscode.Uri,
  reanalyzeDocumentUri?: string
): Promise<void> {
  let document: vscode.TextDocument;

  if (reanalyzeDocumentUri) {
    try {
      const uri = vscode.Uri.parse(reanalyzeDocumentUri);
      document = await vscode.workspace.openTextDocument(uri);
    } catch (err) {
      logger.error(`Re-analysis failed: could not open document '${reanalyzeDocumentUri}'`, err);
      vscode.window.showErrorMessage('EdgeMind re-analysis failed: Could not open document.');
      return;
    }
  } else {
    const editor = vscode.window.activeTextEditor;

    if (!editor) {
      vscode.window.showWarningMessage('No active editor found. Please open a Python file to analyze.');
      logger.warn('Analyze Current File invoked without an active editor.');
      return;
    }
    document = editor.document;
  }

  const validation = validateEditorDocument(
    document.fileName,
    document.languageId,
    document.getText()
  );

  if (!validation.isValid) {
    vscode.window.showWarningMessage(validation.errorMessage);
    logger.warn(`Editor validation failed: ${validation.errorMessage}`);
    return;
  }

  // Ensure client baseUrl matches current configuration
  const currentUrl = getBackendUrl();
  apiClient.setBaseUrl(currentUrl);

  logger.info(`Starting static analysis for '${validation.displayFilename}' (${validation.sizeBytes} bytes) at ${currentUrl}`);

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `EdgeMind: Analyzing ${validation.displayFilename}...`,
      cancellable: true,
    },
    async (_progress, token) => {
      const abortController = new AbortController();
      token.onCancellationRequested(() => {
        abortController.abort();
        logger.info(`Analysis cancelled by user for '${validation.displayFilename}'.`);
      });

      const response = await apiClient.analyzeCode(
        {
          code: validation.code,
          filename: validation.displayFilename,
          static_only: true,
        },
        { signal: abortController.signal }
      );

      if (token.isCancellationRequested) {
        vscode.window.showInformationMessage(`Analysis cancelled for '${validation.displayFilename}'.`);
        return;
      }

      if (response.success && response.data) {
        const report = response.data;
        const formattedReport = formatReportOutput(report, response.durationMs);

        // Update VS Code native Diagnostics
        if (diagnosticCollection && document) {
          updateDocumentDiagnostics(diagnosticCollection, document, report);
        }

        // Show/Update Interactive Results Webview Panel
        if (extensionUri) {
          ResultsPanel.render(
            extensionUri,
            logger,
            report,
            {
              scope: 'full',
              documentUri: document.uri.toString(),
              documentPath: document.fileName,
              displayFilename: validation.displayFilename,
              timestamp: new Date().toLocaleTimeString(),
            },
            () => analyzeCurrentFile(apiClient, logger, diagnosticCollection, extensionUri, document.uri.toString()),
            () => {
              if (diagnosticCollection && document) {
                diagnosticCollection.delete(document.uri);
              }
            }
          );
        }

        // Print full formatted report to EdgeMind OutputChannel
        logger.getChannel().appendLine(formattedReport);
        logger.info(
          `Analysis completed for '${validation.displayFilename}': Score=${report.score}/100, ` +
          `Status=${report.overall_status}, Errors=${report.total_errors}, Warnings=${report.total_warnings} (${response.durationMs}ms)`
        );

        // Display summary notification with Interactive Results action
        const summary = formatSummaryNotification(report);
        const actionButton = 'View Results';
        const outputChannelAction = 'Output Channel';

        let selectedAction: string | undefined;
        if (report.total_errors > 0) {
          selectedAction = await vscode.window.showErrorMessage(summary, actionButton, outputChannelAction);
        } else if (report.total_warnings > 0) {
          selectedAction = await vscode.window.showWarningMessage(summary, actionButton, outputChannelAction);
        } else {
          selectedAction = await vscode.window.showInformationMessage(summary, actionButton, outputChannelAction);
        }

        if (selectedAction === actionButton) {
          if (ResultsPanel.currentPanel) {
            ResultsPanel.currentPanel.reveal();
          } else if (extensionUri) {
            ResultsPanel.render(
              extensionUri,
              logger,
              report,
              {
                scope: 'full',
                documentUri: document.uri.toString(),
                documentPath: document.fileName,
                displayFilename: validation.displayFilename,
                timestamp: new Date().toLocaleTimeString(),
              },
              () => analyzeCurrentFile(apiClient, logger, diagnosticCollection, extensionUri, document.uri.toString())
            );
          }
        } else if (selectedAction === outputChannelAction) {
          logger.show(true);
        }
      } else {
        logger.warn(`Analysis failed for '${validation.displayFilename}': ${response.error}`);
        const selected = await vscode.window.showErrorMessage(
          `EdgeMind analysis failed: ${response.error}`,
          'View Output Channel',
          'Check Backend'
        );

        if (selected === 'View Output Channel') {
          logger.show(true);
        } else if (selected === 'Check Backend') {
          vscode.commands.executeCommand('edgemind.checkBackend');
        }
      }
    }
  );
}
