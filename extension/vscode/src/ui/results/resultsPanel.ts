import * as vscode from 'vscode';
import * as crypto from 'crypto';
import { AnalysisReport } from '../../types/api';
import { Logger } from '../../utils/logger';
import { getBackendUrl } from '../../utils/configuration';
import { DiagnosisClient } from '../../api/diagnosisClient';
import { DiagnoseFindingRequest } from '../../types/diagnosis';
import {
  AnalysisContext,
  AnalysisResultsViewModel,
  transformReportToViewModel,
  validateWebviewMessage,
} from './resultsProvider';
import {
  renderResultsHtml,
  renderEmptyStateHtml,
} from './resultsRenderer';
import {
  extractDiagnosisContext,
  ExtractedDiagnosisContext,
} from './contextExtractor';
import { renderSafeMarkdown } from './markdownRenderer';

/**
 * Generates a cryptographically strong 16-byte base64 nonce for CSP script authorization.
 */
export function generateNonce(): string {
  return crypto.randomBytes(16).toString('base64');
}

/**
 * Manages the lifecycle and message passing of the EdgeMind Interactive Results Webview Panel.
 */
export class ResultsPanel {
  public static currentPanel: ResultsPanel | undefined;
  public static readonly viewType = 'edgemind.results';
  public static readonly MAX_CONCURRENT_DIAGNOSES = 3;

  private readonly panel: vscode.WebviewPanel;
  private readonly extensionUri: vscode.Uri;
  private readonly logger: Logger;
  private disposables: vscode.Disposable[] = [];
  private isDisposed: boolean = false;

  private currentReport?: AnalysisReport;
  private currentContext?: AnalysisContext;
  private currentViewModel?: AnalysisResultsViewModel;
  private onAnalyzeAgainCallback?: () => Promise<void> | void;
  private onClearResultsCallback?: () => void;

  private diagnosisClient: DiagnosisClient;
  private activeDiagnoses = new Map<string, { findingId: string; controller: AbortController }>();
  private diagnosisGenerations = new Map<string, number>();

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    logger: Logger,
    diagnosisClient?: DiagnosisClient
  ) {
    this.panel = panel;
    this.extensionUri = extensionUri;
    this.logger = logger;
    this.diagnosisClient =
      diagnosisClient ||
      new DiagnosisClient({
        baseUrl: getBackendUrl(),
        logger: this.logger,
      });

    // Set panel icon if available
    this.panel.iconPath = {
      light: vscode.Uri.joinPath(this.extensionUri, 'resources', 'icon.svg'),
      dark: vscode.Uri.joinPath(this.extensionUri, 'resources', 'icon.svg'),
    };

    // Handle panel closure
    this.panel.onDidDispose(() => this.dispose(), null, this.disposables);

    // Listen for messages from the Webview
    this.panel.webview.onDidReceiveMessage(
      async (rawMessage) => {
        await this.handleWebviewMessage(rawMessage);
      },
      null,
      this.disposables
    );
  }

  /**
   * Creates or reveals the ResultsPanel singleton with new analysis findings.
   */
  public static render(
    extensionUri: vscode.Uri,
    logger: Logger,
    report: AnalysisReport,
    context: AnalysisContext,
    onAnalyzeAgain?: () => Promise<void> | void,
    onClearResults?: () => void,
    diagnosisClient?: DiagnosisClient
  ): ResultsPanel {
    const column = vscode.window.activeTextEditor
      ? vscode.ViewColumn.Beside
      : vscode.ViewColumn.One;

    if (ResultsPanel.currentPanel) {
      if (!ResultsPanel.currentPanel.isDisposed) {
        if (diagnosisClient) {
          ResultsPanel.currentPanel.setDiagnosisClient(diagnosisClient);
        }
        ResultsPanel.currentPanel.panel.reveal(column, true);
        ResultsPanel.currentPanel.update(report, context, onAnalyzeAgain, onClearResults);
        return ResultsPanel.currentPanel;
      }
      ResultsPanel.currentPanel = undefined;
    }

    const panel = vscode.window.createWebviewPanel(
      ResultsPanel.viewType,
      'EdgeMind: Analysis Results',
      { viewColumn: column, preserveFocus: true },
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [extensionUri],
      }
    );

    ResultsPanel.currentPanel = new ResultsPanel(panel, extensionUri, logger, diagnosisClient);
    ResultsPanel.currentPanel.update(report, context, onAnalyzeAgain, onClearResults);
    return ResultsPanel.currentPanel;
  }

  /**
   * Sets or replaces the DiagnosisClient instance (useful for testing and configuration updates).
   */
  public setDiagnosisClient(client: DiagnosisClient): void {
    this.diagnosisClient = client;
  }

  /**
   * Checks whether a diagnosis stream is currently active for a given finding ID.
   */
  public isDiagnosisActive(findingId: string): boolean {
    return this.activeDiagnoses.has(findingId);
  }

  /**
   * Returns the count of actively streaming diagnoses.
   */
  public getActiveDiagnosesCount(): number {
    return this.activeDiagnoses.size;
  }

  /**
   * Reveals the panel in the specified column or beside.
   */
  public reveal(viewColumn?: vscode.ViewColumn, preserveFocus: boolean = true): void {
    this.panel.reveal(viewColumn || vscode.ViewColumn.Beside, preserveFocus);
  }

  /**
   * Returns whether the panel has been disposed.
   */
  public get disposed(): boolean {
    return this.isDisposed;
  }

  /**
   * Returns the current analysis report if available.
   */
  public getReport(): AnalysisReport | undefined {
    return this.currentReport;
  }

  /**
   * Updates panel content with a new analysis report and context.
   * Any active diagnosis streams from previous reports are safely aborted.
   */
  public update(
    report: AnalysisReport,
    context: AnalysisContext,
    onAnalyzeAgain?: () => Promise<void> | void,
    onClearResults?: () => void
  ): void {
    this.abortAllDiagnoses();
    this.currentReport = report;
    this.currentContext = context;
    if (onAnalyzeAgain) {
      this.onAnalyzeAgainCallback = onAnalyzeAgain;
    }
    if (onClearResults) {
      this.onClearResultsCallback = onClearResults;
    }

    const titleFilename = context.displayFilename || report.file || 'Results';
    this.panel.title = `EdgeMind: ${titleFilename}`;

    const viewModel = transformReportToViewModel(report, context);
    this.currentViewModel = viewModel;
    const nonce = generateNonce();
    this.panel.webview.html = renderResultsHtml(viewModel, this.panel.webview.cspSource, nonce);
    this.logger.info(`Results Webview updated for '${titleFilename}' with ${viewModel.findings.length} findings.`);
  }

  /**
   * Displays the empty/idle state when results are cleared.
   * Any active diagnosis streams are safely aborted.
   */
  public showEmptyState(): void {
    this.abortAllDiagnoses();
    this.currentReport = undefined;
    this.currentViewModel = undefined;
    this.panel.title = 'EdgeMind: Analysis Results';
    const nonce = generateNonce();
    this.panel.webview.html = renderEmptyStateHtml(this.panel.webview.cspSource, nonce);
  }

  /**
   * Dispatches and handles messages received from the untrusted Webview environment.
   */
  private async handleWebviewMessage(rawMessage: unknown): Promise<void> {
    if (this.isDisposed) {
      return;
    }

    const expectedUri = this.currentContext?.documentUri;
    const validation = validateWebviewMessage(rawMessage, expectedUri);
    if (!validation.isValid || !validation.message) {
      this.logger.warn(`Rejected invalid Webview message: ${validation.error}`);
      return;
    }

    const msg = validation.message;
    switch (msg.type) {
      case 'navigateToLine':
        if (msg.line) {
          await this.navigateToSourceLine(msg.line);
        }
        break;

      case 'analyzeAgain':
        this.logger.info('Analyze Again triggered from Results Webview.');
        if (this.onAnalyzeAgainCallback) {
          try {
            await this.onAnalyzeAgainCallback();
          } catch (err) {
            this.logger.error('Error running Re-analysis from Results Webview', err);
            vscode.window.showErrorMessage(`EdgeMind re-analysis failed: ${err instanceof Error ? err.message : String(err)}`);
          }
        } else {
          vscode.commands.executeCommand('edgemind.analyzeCurrentFile');
        }
        break;

      case 'clearResults':
        this.logger.info('Clear Results triggered from Results Webview.');
        if (this.onClearResultsCallback) {
          this.onClearResultsCallback();
        }
        this.showEmptyState();
        break;

      case 'explainFinding':
        if (msg.findingId) {
          await this.handleExplainFinding(msg.findingId);
        }
        break;

      case 'cancelDiagnosis':
        if (msg.findingId) {
          this.handleCancelDiagnosis(msg.findingId);
        }
        break;

      case 'retryDiagnosis':
        if (msg.findingId) {
          await this.handleRetryDiagnosis(msg.findingId);
        }
        break;
    }
  }

  /**
   * Handles user request to cancel an ongoing AI diagnosis for a specific finding.
   * Idempotent: ignores requests if diagnosis is not actively in-flight.
   */
  private handleCancelDiagnosis(findingId: string): void {
    const active = this.activeDiagnoses.get(findingId);
    if (!active) {
      this.logger.info(`Cancel diagnosis ignored for finding '${findingId}': no active diagnosis session in progress.`);
      return;
    }

    try {
      active.controller.abort();
    } catch {
      // ignore
    }
    this.activeDiagnoses.delete(findingId);
    this.diagnosisGenerations.delete(findingId);

    this.postWebviewMessage({
      type: 'diagnosisStateChange',
      findingId,
      state: 'cancelled',
    });
    this.logger.info(`Diagnosis cancelled for finding '${findingId}'.`);
  }

  /**
   * Handles user request to retry AI diagnosis for a specific finding.
   * Cancels any prior active operation without emitting intermediate cancellation flicker,
   * then launches a fresh diagnosis using current editor context.
   */
  private async handleRetryDiagnosis(findingId: string): Promise<void> {
    const active = this.activeDiagnoses.get(findingId);
    if (active) {
      try {
        active.controller.abort();
      } catch {
        // ignore
      }
      this.activeDiagnoses.delete(findingId);
    }
    this.logger.info(`Retry diagnosis initiated for finding '${findingId}'.`);
    await this.handleExplainFinding(findingId);
  }

  /**
   * Initiates finding-level AI diagnosis streaming.
   *
   * Flow:
   * 1. Validates document context and active state
   * 2. Checks concurrency limit to prevent resource exhaustion
   * 3. Extracts bounded code context (±15 lines) from editor document
   * 4. Streams SSE events from EdgeMind backend
   * 5. Converts token chunks to sanitized HTML and posts to Webview
   * 6. Preserves partial output if stream is interrupted prematurely
   */
  private async handleExplainFinding(findingId: string): Promise<void> {
    if (this.isDisposed) {
      return;
    }

    if (!this.currentContext?.documentUri) {
      this.logger.warn(`Explain finding rejected: no document URI in analysis context for finding '${findingId}'.`);
      this.postWebviewMessage({
        type: 'diagnosisStateChange',
        findingId,
        state: 'error',
        error: 'No target document URI available in analysis context.',
        retryable: false,
      });
      return;
    }

    if (this.activeDiagnoses.has(findingId)) {
      this.logger.info(`Diagnosis already in progress for finding '${findingId}'; ignoring duplicate request.`);
      return;
    }

    // Check concurrency cap to avoid exhausting backend connection pool / rate limits
    if (this.activeDiagnoses.size >= ResultsPanel.MAX_CONCURRENT_DIAGNOSES) {
      this.logger.warn(
        `Explain finding rejected for '${findingId}': maximum concurrent diagnoses (${ResultsPanel.MAX_CONCURRENT_DIAGNOSES}) reached.`
      );
      this.postWebviewMessage({
        type: 'diagnosisStateChange',
        findingId,
        state: 'error',
        error: `Maximum concurrent diagnoses (${ResultsPanel.MAX_CONCURRENT_DIAGNOSES}) reached. Please wait for an active diagnosis to complete or cancel one.`,
        retryable: true,
      });
      return;
    }

    const finding = this.currentViewModel?.findings.find((f) => f.id === findingId);
    if (!finding) {
      this.logger.warn(`Explain finding rejected: finding '${findingId}' not found in active report.`);
      this.postWebviewMessage({
        type: 'diagnosisStateChange',
        findingId,
        state: 'error',
        error: `Finding '${findingId}' not found in current analysis report.`,
        retryable: false,
      });
      return;
    }

    this.postWebviewMessage({
      type: 'diagnosisStateChange',
      findingId,
      state: 'loading',
    });

    const controller = new AbortController();
    this.activeDiagnoses.set(findingId, { findingId, controller });
    const currentGeneration = (this.diagnosisGenerations.get(findingId) || 0) + 1;
    this.diagnosisGenerations.set(findingId, currentGeneration);

    let extracted: ExtractedDiagnosisContext;
    try {
      extracted = await extractDiagnosisContext(
        this.currentContext.documentUri,
        finding.line,
        this.currentContext.displayFilename
      );
    } catch (err) {
      this.activeDiagnoses.delete(findingId);
      const errMsg = this.formatUserDiagnosisError(err);
      this.logger.error(`Context extraction failed for finding '${findingId}': ${errMsg}`);
      this.postWebviewMessage({
        type: 'diagnosisStateChange',
        findingId,
        state: 'error',
        error: errMsg,
        retryable: true,
      });
      return;
    }

    if (controller.signal.aborted || this.diagnosisGenerations.get(findingId) !== currentGeneration) {
      this.activeDiagnoses.delete(findingId);
      return;
    }

    const request: DiagnoseFindingRequest = {
      finding: {
        finding_id: finding.id,
        type: finding.type,
        severity: finding.severity,
        message: finding.message,
        line: finding.line ?? null,
        static_why: finding.why ?? null,
        static_fix: finding.fix ?? null,
      },
      code_context: extracted.codeContext,
      context_start_line: extracted.contextStartLine,
      context_end_line: extracted.contextEndLine,
      filename: extracted.filename,
      language: extracted.language,
    };

    let accumulated = '';
    try {
      const stream = this.diagnosisClient.streamDiagnosis(request, {
        signal: controller.signal,
      });

      for await (const event of stream) {
        if (controller.signal.aborted || this.diagnosisGenerations.get(findingId) !== currentGeneration) {
          break;
        }

        if (event.event === 'response_chunk') {
          accumulated += event.chunk;
          const html = renderSafeMarkdown(accumulated);
          this.postWebviewMessage({
            type: 'diagnosisChunk',
            findingId,
            chunk: event.chunk,
            fullText: accumulated,
            html,
          });
        } else if (event.event === 'completed') {
          const html = renderSafeMarkdown(accumulated);
          this.postWebviewMessage({
            type: 'diagnosisStateChange',
            findingId,
            state: 'completed',
            fullText: accumulated,
            html,
            durationMs: event.duration_ms,
          });
        } else if (event.event === 'error') {
          this.postWebviewMessage({
            type: 'diagnosisStateChange',
            findingId,
            state: 'error',
            error: event.message,
            retryable: event.retryable,
            partialText: accumulated || undefined,
            partialHtml: accumulated ? renderSafeMarkdown(accumulated) : undefined,
          });
        }
      }
    } catch (err) {
      if (controller.signal.aborted || this.diagnosisGenerations.get(findingId) !== currentGeneration) {
        return;
      }
      const errMsg = this.formatUserDiagnosisError(err);
      this.logger.error(`Diagnosis stream failed for finding '${findingId}': ${errMsg}`);
      this.postWebviewMessage({
        type: 'diagnosisStateChange',
        findingId,
        state: 'error',
        error: errMsg,
        retryable: true,
        partialText: accumulated || undefined,
        partialHtml: accumulated ? renderSafeMarkdown(accumulated) : undefined,
      });
    } finally {
      if (this.diagnosisGenerations.get(findingId) === currentGeneration) {
        this.activeDiagnoses.delete(findingId);
      }
    }
  }

  /**
   * Translates internal and transport errors into helpful, user-friendly messages
   * while rigorously redacting API keys, passwords, and sensitive server paths.
   */
  private formatUserDiagnosisError(err: unknown): string {
    if (!err) {
      return 'An unexpected error occurred during AI diagnosis.';
    }
    const rawMessage = err instanceof Error ? err.message : String(err);
    const lower = rawMessage.toLowerCase();

    // Connection refused / unreachable
    if (lower.includes('econnrefused') || lower.includes('failed to fetch') || lower.includes('fetch failed')) {
      return 'EdgeMind backend service is unreachable. Verify that the backend is running at http://127.0.0.1:8000.';
    }
    // 401 Unauthorized
    if (lower.includes('401') || lower.includes('unauthorized')) {
      return 'Authentication failed. Check your EdgeMind backend credentials in settings.';
    }
    // 429 Rate limit
    if (lower.includes('429') || lower.includes('rate limit')) {
      return 'AI provider rate limit reached. Please wait a moment before retrying.';
    }
    // Timeout
    if (lower.includes('timeout') || lower.includes('timed out')) {
      return 'Diagnosis request timed out. The AI provider may be overloaded or responding slowly.';
    }
    // Premature stream termination
    if (lower.includes('terminated prematurely') || lower.includes('unexpected eof')) {
      return 'Diagnosis stream was interrupted before completion. Click Retry to generate a fresh diagnosis.';
    }
    // Document modified
    if (lower.includes('exceeds document length') || lower.includes('modified since analysis')) {
      return 'The source document was modified since analysis was performed. Re-run analysis to update finding line references.';
    }

    // Redact any sensitive substrings (tokens, passwords, paths)
    return rawMessage
      .replace(/Bearer\s+[A-Za-z0-9\-_\.]+/gi, 'Bearer [REDACTED]')
      .replace(/(?:sk-(?:proj-)?[a-zA-Z0-9_\-]{20,}|AIza[0-9A-Za-z\-_]{30,})/g, '[REDACTED]')
      .replace(/(?:password|secret_key|api_key)=([^\s&]+)/gi, '$1=[REDACTED]')
      .replace(/([a-zA-Z]:\\[^:\s\n]+\\)([^:\s\n]+)/g, '$2');
  }

  /**
   * Safely posts a message to the active Webview if not disposed.
   */
  private postWebviewMessage(message: unknown): void {
    if (!this.isDisposed && this.panel) {
      try {
        this.panel.webview.postMessage(message);
      } catch (err) {
        this.logger.warn(`Failed to post message to Webview: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
  }

  /**
   * Safely aborts all actively streaming diagnosis requests and clears generations.
   */
  private abortAllDiagnoses(): void {
    for (const active of this.activeDiagnoses.values()) {
      try {
        active.controller.abort();
      } catch {
        // ignore
      }
    }
    this.activeDiagnoses.clear();
    this.diagnosisGenerations.clear();
  }

  /**
   * Navigates to the specified document and line in the editor safely.
   * Navigation is strictly bound to the originally analyzed document context;
   * foreign URIs or arbitrary filesystem paths from the Webview are ignored.
   */
  private async navigateToSourceLine(line1: number): Promise<void> {
    const targetUriStr = this.currentContext?.documentUri;
    if (!targetUriStr) {
      this.logger.warn(`Source navigation rejected: no target URI available in analysis context for line ${line1}`);
      return;
    }

    try {
      const uri = vscode.Uri.parse(targetUriStr);
      // Strictly restrict navigation to file and untitled schemes
      if (uri.scheme !== 'file' && uri.scheme !== 'untitled') {
        this.logger.warn(`Source navigation rejected for disallowed scheme '${uri.scheme}': ${targetUriStr}`);
        vscode.window.showWarningMessage(`Cannot navigate to disallowed URI scheme: ${uri.scheme}`);
        return;
      }

      const document = await vscode.workspace.openTextDocument(uri);
      const totalLines = document.lineCount;
      if (totalLines <= 0) {
        this.logger.warn(`Source navigation aborted: document '${document.fileName}' has 0 lines.`);
        return;
      }

      // Safely clamp line number to document range [0, totalLines - 1]
      const line0 = Math.max(0, Math.min(line1 - 1, totalLines - 1));

      const editor = await vscode.window.showTextDocument(document, {
        viewColumn: vscode.ViewColumn.One,
        preserveFocus: false,
        preview: true,
      });

      const lineRange = document.lineAt(line0).range;
      editor.selection = new vscode.Selection(lineRange.start, lineRange.end);
      editor.revealRange(lineRange, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
      this.logger.info(`Navigated to '${document.fileName}', line ${line0 + 1}`);
    } catch (err) {
      this.logger.error(`Source navigation failed for '${targetUriStr}' at line ${line1}`, err);
      vscode.window.showWarningMessage(`Could not navigate to source line ${line1}. File may have moved or been closed.`);
    }
  }

  public dispose(): void {
    if (this.isDisposed) {
      return;
    }
    this.isDisposed = true;

    this.abortAllDiagnoses();

    if (ResultsPanel.currentPanel === this) {
      ResultsPanel.currentPanel = undefined;
    }

    while (this.disposables.length) {
      const disposable = this.disposables.pop();
      if (disposable) {
        try {
          disposable.dispose();
        } catch {
          // ignore disposable error
        }
      }
    }

    try {
      this.panel.dispose();
    } catch {
      // panel was already disposed by user closing the tab
    }

    this.logger.info('EdgeMind Results Webview disposed.');
  }
}
