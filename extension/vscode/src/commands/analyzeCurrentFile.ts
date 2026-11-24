import * as vscode from 'vscode';
import { ApiClient } from '../api/client';
import { Logger } from '../utils/logger';
import { validateEditorDocument } from '../utils/editorValidator';
import { formatReportOutput, formatSummaryNotification } from '../utils/reportFormatter';
import { updateDocumentDiagnostics } from '../utils/diagnosticMapper';
import { getBackendUrl } from '../utils/configuration';

/**
 * Command handler for "EdgeMind: Analyze Current File" (edgemind.analyzeCurrentFile).
 * Reads the active editor's Python source code, performs client validation,
 * sends static analysis request to the EdgeMind backend, and presents results.
 */
export async function analyzeCurrentFile(
  apiClient: ApiClient,
  logger: Logger,
  diagnosticCollection?: vscode.DiagnosticCollection
): Promise<void> {
  const editor = vscode.window.activeTextEditor;

  if (!editor) {
    vscode.window.showWarningMessage('No active editor found. Please open a Python file to analyze.');
    logger.warn('Analyze Current File invoked without an active editor.');
    return;
  }

  const validation = validateEditorDocument(
    editor.document.fileName,
    editor.document.languageId,
    editor.document.getText()
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
        if (diagnosticCollection && editor.document) {
          updateDocumentDiagnostics(diagnosticCollection, editor.document, report);
        }

        // Print full formatted report to EdgeMind OutputChannel
        logger.getChannel().appendLine(formattedReport);
        logger.info(
          `Analysis completed for '${validation.displayFilename}': Score=${report.score}/100, ` +
          `Status=${report.overall_status}, Errors=${report.total_errors}, Warnings=${report.total_warnings} (${response.durationMs}ms)`
        );

        // Display summary notification
        const summary = formatSummaryNotification(report);
        const actionButton = 'View Full Report';

        let selectedAction: string | undefined;
        if (report.total_errors > 0) {
          selectedAction = await vscode.window.showErrorMessage(summary, actionButton);
        } else if (report.total_warnings > 0) {
          selectedAction = await vscode.window.showWarningMessage(summary, actionButton);
        } else {
          selectedAction = await vscode.window.showInformationMessage(summary, actionButton);
        }

        if (selectedAction === actionButton) {
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
