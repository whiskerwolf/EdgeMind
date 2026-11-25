import * as vscode from 'vscode';
import { ApiClient } from '../api/client';
import { Logger } from '../utils/logger';
import { validateEditorSelection } from '../utils/editorValidator';
import { formatReportOutput, formatSummaryNotification } from '../utils/reportFormatter';
import { updateDocumentDiagnostics } from '../utils/diagnosticMapper';
import { ResultsPanel } from '../ui/results/resultsPanel';
import { validateSelectionBounds } from '../ui/results/resultsProvider';
import { getBackendUrl } from '../utils/configuration';

export interface ReanalyzeSelectionParams {
  documentUri: string;
  startLine: number;
  endLine: number;
  displayFilename?: string;
}

/**
 * Command handler for "EdgeMind: Analyze Selection" (edgemind.analyzeSelection).
 * Reads the active editor's selected Python code snippet, performs client validation,
 * sends static analysis request to the EdgeMind backend, and presents results.
 * Supports re-analysis without requiring active editor focus.
 */
export async function analyzeSelection(
  apiClient: ApiClient,
  logger: Logger,
  diagnosticCollection?: vscode.DiagnosticCollection,
  extensionUri?: vscode.Uri,
  reanalyzeParams?: ReanalyzeSelectionParams
): Promise<void> {
  let document: vscode.TextDocument;
  let startLine: number;
  let endLine: number;
  let selectedText: string;
  let hasSelection: boolean;
  let selectionRange: vscode.Range | vscode.Selection | undefined;

  if (reanalyzeParams) {
    try {
      const uri = vscode.Uri.parse(reanalyzeParams.documentUri);
      document = await vscode.workspace.openTextDocument(uri);
    } catch (err) {
      logger.error(`Re-analysis failed: could not open document '${reanalyzeParams.documentUri}'`, err);
      vscode.window.showErrorMessage(
        'EdgeMind re-analysis failed: Could not open document. The file may have moved or been closed.'
      );
      return;
    }

    const boundsValidation = validateSelectionBounds(
      reanalyzeParams.startLine,
      reanalyzeParams.endLine,
      document.lineCount
    );

    if (!boundsValidation.isValid || boundsValidation.effectiveEndLine === undefined) {
      const errMsg = boundsValidation.error || 'Invalid selection line bounds.';
      logger.warn(`Re-analysis bounds invalid: ${errMsg}`);
      vscode.window.showErrorMessage(`EdgeMind re-analysis failed: ${errMsg}`);
      return;
    }

    startLine = reanalyzeParams.startLine;
    endLine = boundsValidation.effectiveEndLine;

    const startPos = new vscode.Position(startLine - 1, 0);
    const endLineObj = document.lineAt(endLine - 1);
    selectionRange = new vscode.Range(startPos, endLineObj.range.end);
    selectedText = document.getText(selectionRange);
    hasSelection = selectedText.trim().length > 0;
  } else {
    const editor = vscode.window.activeTextEditor;

    if (!editor) {
      vscode.window.showWarningMessage('No active editor found. Please open a Python file and select code to analyze.');
      logger.warn('Analyze Selection invoked without an active editor.');
      return;
    }

    document = editor.document;
    const selection = editor.selection;
    selectionRange = selection;
    hasSelection = !selection.isEmpty;
    selectedText = hasSelection ? document.getText(selection) : '';
    startLine = selection.start.line + 1; // 1-based
    endLine = selection.end.line + 1;     // 1-based
  }

  const validation = validateEditorSelection(
    document.fileName,
    document.languageId,
    hasSelection,
    selectedText,
    startLine,
    endLine
  );

  if (!validation.isValid) {
    vscode.window.showWarningMessage(validation.errorMessage);
    logger.warn(`Selection validation failed: ${validation.errorMessage}`);
    return;
  }

  // Ensure client baseUrl matches current configuration
  const currentUrl = getBackendUrl();
  apiClient.setBaseUrl(currentUrl);

  logger.info(
    `Starting static analysis for selected code in '${validation.displayFilename}' ` +
    `(${validation.scopeLabel}, ${validation.sizeBytes} bytes) at ${currentUrl}`
  );

  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: `EdgeMind: Analyzing ${validation.displayFilename} (${validation.scopeLabel})...`,
      cancellable: true,
    },
    async (_progress, token) => {
      const abortController = new AbortController();
      token.onCancellationRequested(() => {
        abortController.abort();
        logger.info(`Analysis cancelled by user for '${validation.displayFilename}' (${validation.scopeLabel}).`);
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
        vscode.window.showInformationMessage(
          `Analysis cancelled for '${validation.displayFilename}' (${validation.scopeLabel}).`
        );
        return;
      }

      if (response.success && response.data) {
        const report = response.data;
        const formattedReport = formatReportOutput(report, response.durationMs, validation.scopeLabel);

        // Update VS Code native Diagnostics for the selection range
        if (diagnosticCollection && document) {
          updateDocumentDiagnostics(diagnosticCollection, document, report, selectionRange);
        }

        // Show/Update Interactive Results Webview Panel with selection context
        if (extensionUri) {
          ResultsPanel.render(
            extensionUri,
            logger,
            report,
            {
              scope: 'selection',
              documentUri: document.uri.toString(),
              documentPath: document.fileName,
              displayFilename: validation.displayFilename,
              selectionStartLine: startLine,
              selectionEndLine: endLine,
              timestamp: new Date().toLocaleTimeString(),
            },
            () =>
              analyzeSelection(apiClient, logger, diagnosticCollection, extensionUri, {
                documentUri: document.uri.toString(),
                startLine,
                endLine,
                displayFilename: validation.displayFilename,
              }),
            () => {
              if (diagnosticCollection && document) {
                updateDocumentDiagnostics(
                  diagnosticCollection,
                  document,
                  { ...report, errors: [], warnings: [] },
                  selectionRange
                );
              }
            }
          );
        }

        // Print full formatted report to EdgeMind OutputChannel
        logger.getChannel().appendLine(formattedReport);
        logger.info(
          `Analysis completed for '${validation.displayFilename}' (${validation.scopeLabel}): ` +
          `Score=${report.score}/100, Status=${report.overall_status}, ` +
          `Errors=${report.total_errors}, Warnings=${report.total_warnings} (${response.durationMs}ms)`
        );

        // Display summary notification with Interactive Results action
        const summary = formatSummaryNotification(report, validation.scopeLabel);
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
                scope: 'selection',
                documentUri: document.uri.toString(),
                documentPath: document.fileName,
                displayFilename: validation.displayFilename,
                selectionStartLine: startLine,
                selectionEndLine: endLine,
                timestamp: new Date().toLocaleTimeString(),
              },
              () =>
                analyzeSelection(apiClient, logger, diagnosticCollection, extensionUri, {
                  documentUri: document.uri.toString(),
                  startLine,
                  endLine,
                  displayFilename: validation.displayFilename,
                })
            );
          }
        } else if (selectedAction === outputChannelAction) {
          logger.show(true);
        }
      } else {
        logger.warn(
          `Analysis failed for '${validation.displayFilename}' (${validation.scopeLabel}): ${response.error}`
        );
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
