import { AnalysisReport, ReportFinding } from '../../types/api';

export type AnalysisScopeType = 'full' | 'selection';

export interface AnalysisContext {
  scope: AnalysisScopeType;
  documentUri: string;
  documentPath: string;
  displayFilename: string;
  selectionStartLine?: number; // 1-based start line of selection
  selectionEndLine?: number;   // 1-based end line of selection
  timestamp?: string;
}

export type FindingSeverity = 'error' | 'warning' | 'info';

export interface FindingItem {
  id: string;
  type: string;
  severity: FindingSeverity;
  message: string;
  line?: number;           // Absolute 1-based document line, or undefined if missing
  snippetLine?: number;    // Snippet-relative 1-based line if selection
  why?: string;
  fix?: string;
  concept?: string;
}

export interface AnalysisSummaryData {
  totalFindings: number;
  errorCount: number;
  warningCount: number;
  infoCount: number;
  overallStatus: string;
  score: number;
  syntaxStatus?: string;
  runtimeStatus?: string;
  logicStatus?: string;
  qualityStatus?: string;
  complexityStatus?: string;
}

export interface AnalysisResultsViewModel {
  header: {
    branding: string;
    displayFilename: string;
    documentPath: string;
    documentUri: string;
    timestamp: string;
    scope: AnalysisScopeType;
    scopeLabel: string;
  };
  score: {
    value: number;
    status: string;
    level: 'pass' | 'warn' | 'fail';
  };
  summary: AnalysisSummaryData;
  findings: FindingItem[];
}

export interface WebviewIncomingMessage {
  type:
    | 'navigateToLine'
    | 'analyzeAgain'
    | 'clearResults'
    | 'explainFinding'
    | 'cancelDiagnosis'
    | 'retryDiagnosis';
  line?: number;
  uri?: string;
  findingId?: string;
}

export interface WebviewMessageValidationResult {
  isValid: boolean;
  message?: WebviewIncomingMessage;
  error?: string;
}

/**
 * Normalizes severity classification for a finding.
 */
export function classifyFindingSeverity(
  finding: ReportFinding,
  defaultSeverity: FindingSeverity
): FindingSeverity {
  const explicit = finding.severity?.toLowerCase();
  if (explicit === 'error') {
    return 'error';
  }
  if (explicit === 'warning' || explicit === 'warn') {
    return 'warning';
  }
  if (explicit === 'info' || explicit === 'information') {
    return 'info';
  }

  const typeLower = (finding.type || '').toLowerCase();
  if (typeLower.includes('info') || typeLower.includes('hint')) {
    return 'info';
  }

  return defaultSeverity;
}

/**
 * Calculates absolute 1-based document line from backend finding line.
 * Returns undefined if line is missing, 0, or invalid.
 */
export function calculateAbsoluteLine1(
  rawLine: number | undefined | null,
  selectionStartLine1?: number
): number | undefined {
  if (rawLine === undefined || rawLine === null || isNaN(rawLine)) {
    return undefined;
  }

  const lineNum = Math.floor(rawLine);
  if (lineNum <= 0) {
    return undefined;
  }

  if (selectionStartLine1 !== undefined && selectionStartLine1 > 0) {
    // Snippet line 1 is selectionStartLine1
    return selectionStartLine1 + (lineNum - 1);
  }

  return lineNum;
}

/**
 * Transforms backend ReportFinding into standardized FindingItem.
 */
export function transformFinding(
  finding: ReportFinding,
  index: number,
  defaultSeverity: FindingSeverity,
  selectionStartLine1?: number
): FindingItem {
  const severity = classifyFindingSeverity(finding, defaultSeverity);
  const rawLine = finding.line ?? finding.line_number;
  const absLine = calculateAbsoluteLine1(rawLine, selectionStartLine1);
  const snippetLine = selectionStartLine1 !== undefined && rawLine && rawLine > 0 ? Math.floor(rawLine) : undefined;

  return {
    id: `finding-${index}`,
    type: finding.type || 'Finding',
    severity,
    message: finding.message || finding.type || 'Potential issue detected',
    line: absLine,
    snippetLine,
    why: finding.why || finding.explanation,
    fix: finding.fix || finding.suggested_fix,
    concept: finding.concept && finding.concept !== 'General' ? finding.concept : undefined,
  };
}

/**
 * Determines score level for CSS theming.
 */
export function getScoreLevel(score: number, errorCount: number): 'pass' | 'warn' | 'fail' {
  if (errorCount > 0 || score < 70) {
    return 'fail';
  }
  if (score < 100) {
    return 'warn';
  }
  return 'pass';
}

/**
 * Transforms raw AnalysisReport and AnalysisContext into strongly typed AnalysisResultsViewModel.
 */
export function transformReportToViewModel(
  report: AnalysisReport,
  context: AnalysisContext
): AnalysisResultsViewModel {
  const errors = report.errors || report.detailed_errors || [];
  const warnings = report.warnings || report.detailed_warnings || [];

  const findings: FindingItem[] = [];
  let currentIndex = 0;

  for (const err of errors) {
    findings.push(transformFinding(err, currentIndex++, 'error', context.selectionStartLine));
  }

  for (const warn of warnings) {
    findings.push(transformFinding(warn, currentIndex++, 'warning', context.selectionStartLine));
  }

  const errorCount = findings.filter((f) => f.severity === 'error').length;
  const warningCount = findings.filter((f) => f.severity === 'warning').length;
  const infoCount = findings.filter((f) => f.severity === 'info').length;

  const scoreVal = typeof report.score === 'number' ? Math.max(0, Math.min(100, Math.round(report.score))) : 100;
  const overallStatus = report.overall_status || report.status || (errorCount > 0 ? 'FAIL' : (warningCount > 0 ? 'WARN' : 'PASS'));
  const scoreLevel = getScoreLevel(scoreVal, errorCount);

  let scopeLabel = 'Full File';
  if (context.scope === 'selection') {
    if (context.selectionStartLine && context.selectionEndLine) {
      scopeLabel = context.selectionStartLine === context.selectionEndLine
        ? `Selected Code (Line ${context.selectionStartLine})`
        : `Selected Code (Lines ${context.selectionStartLine}–${context.selectionEndLine})`;
    } else {
      scopeLabel = 'Selected Code';
    }
  }

  const summary: AnalysisSummaryData = {
    totalFindings: findings.length,
    errorCount,
    warningCount,
    infoCount,
    overallStatus,
    score: scoreVal,
    syntaxStatus: report.summary?.syntax || report.syntax_status,
    runtimeStatus: report.summary?.runtime || report.runtime_status,
    logicStatus: report.summary?.logic || report.logic_status,
    qualityStatus: report.summary?.quality || report.quality_status,
    complexityStatus: report.summary?.complexity || report.complexity_status,
  };

  return {
    header: {
      branding: 'EdgeMind',
      displayFilename: context.displayFilename || report.file || report.file_path || 'snippet.py',
      documentPath: context.documentPath || context.displayFilename,
      documentUri: context.documentUri || '',
      timestamp: context.timestamp || new Date().toLocaleTimeString(),
      scope: context.scope,
      scopeLabel,
    },
    score: {
      value: scoreVal,
      status: overallStatus,
      level: scoreLevel,
    },
    summary,
    findings,
  };
}

/**
 * Filters a list of findings by severity.
 */
export function filterFindings(
  findings: FindingItem[],
  filter: 'all' | 'error' | 'warning' | 'info'
): FindingItem[] {
  if (filter === 'all') {
    return findings;
  }
  return findings.filter((f) => f.severity === filter);
}

/**
 * Validation result for selection line bounds.
 */
export interface SelectionBoundsValidationResult {
  isValid: boolean;
  error?: string;
  effectiveEndLine?: number;
}

/**
 * Validates selection line bounds against current document length.
 * Prevents re-analysis with stale or inverted bounds if the document was edited.
 */
export function validateSelectionBounds(
  startLine: number,
  endLine: number,
  totalLines: number
): SelectionBoundsValidationResult {
  if (totalLines <= 0) {
    return { isValid: false, error: 'Document has no lines.' };
  }

  if (
    !Number.isFinite(startLine) ||
    !Number.isFinite(endLine) ||
    startLine < 1 ||
    endLine < startLine ||
    startLine > totalLines
  ) {
    return {
      isValid: false,
      error: `Stale selection bounds (lines ${startLine}–${endLine}) exceed current document length (${totalLines} lines).`,
    };
  }

  const effectiveEndLine = Math.min(endLine, totalLines);
  return {
    isValid: true,
    effectiveEndLine,
  };
}

/**
 * Validates untrusted messages received from the Webview host.
 * If expectedDocumentUri is supplied, rejects any message attempting to navigate to a foreign URI.
 */
export function validateWebviewMessage(
  raw: unknown,
  expectedDocumentUri?: string
): WebviewMessageValidationResult {
  if (!raw || typeof raw !== 'object') {
    return { isValid: false, error: 'Message must be an object' };
  }

  const msg = raw as Record<string, unknown>;
  const type = msg.type;

  if (type === 'analyzeAgain') {
    return { isValid: true, message: { type: 'analyzeAgain' } };
  }

  if (type === 'clearResults') {
    return { isValid: true, message: { type: 'clearResults' } };
  }

  if (type === 'navigateToLine') {
    const line = msg.line;
    if (
      typeof line !== 'number' ||
      !Number.isFinite(line) ||
      isNaN(line) ||
      line < 1 ||
      Math.floor(line) !== line
    ) {
      return { isValid: false, error: 'Line number must be a finite positive integer' };
    }

    // If a foreign URI is specified in the message, verify against the analyzed document
    if (msg.uri !== undefined) {
      if (typeof msg.uri !== 'string' || !msg.uri.trim()) {
        return { isValid: false, error: 'URI must be a non-empty string when provided' };
      }
      if (expectedDocumentUri && msg.uri.trim() !== expectedDocumentUri) {
        return {
          isValid: false,
          error: `Navigation URI '${msg.uri}' does not match analyzed document URI '${expectedDocumentUri}'`,
        };
      }
    }

    return {
      isValid: true,
      message: {
        type: 'navigateToLine',
        line,
        uri: expectedDocumentUri || (typeof msg.uri === 'string' ? msg.uri.trim() : undefined),
      },
    };
  }

  if (type === 'explainFinding' || type === 'cancelDiagnosis' || type === 'retryDiagnosis') {
    const findingId = msg.findingId;
    if (typeof findingId !== 'string' || !findingId.trim()) {
      return { isValid: false, error: 'findingId must be a non-empty string' };
    }
    const cleanId = findingId.trim();
    if (!/^[a-zA-Z0-9_\-:]{1,128}$/.test(cleanId)) {
      return { isValid: false, error: `Invalid findingId '${cleanId}': must be a safe identifier` };
    }
    return {
      isValid: true,
      message: {
        type,
        findingId: cleanId,
      },
    };
  }

  return { isValid: false, error: `Unknown message type: '${String(type)}'` };
}
