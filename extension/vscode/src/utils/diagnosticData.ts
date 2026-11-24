import { AnalysisReport, ReportFinding } from '../types/api';

/**
 * Diagnostic severity matching VS Code's DiagnosticSeverity enum values.
 * Defined independently to allow pure unit testing in Node without vscode runtime.
 */
export enum EdgeMindDiagnosticSeverity {
  Error = 0,
  Warning = 1,
  Information = 2,
  Hint = 3,
}

export interface DiagnosticRange {
  startLine: number; // 0-based
  startChar: number; // 0-based
  endLine: number;   // 0-based
  endChar: number;   // 0-based
}

export interface EdgeMindDiagnostic {
  range: DiagnosticRange;
  message: string;
  severity: EdgeMindDiagnosticSeverity;
  source: string;
  code: string;
}

export interface DiagnosticMappingOptions {
  selectionStartLine?: number; // 1-based start line of selection in document
  maxLineIndex?: number;       // 0-based maximum line index in document (lineCount - 1)
  getLineText?: (line0: number) => string;
}

/**
 * Resolves severity from finding attributes and default report group.
 */
export function mapFindingSeverity(
  finding: ReportFinding,
  defaultSeverity: EdgeMindDiagnosticSeverity
): EdgeMindDiagnosticSeverity {
  const explicitSeverity = finding.severity?.toLowerCase();
  if (explicitSeverity === 'error') {
    return EdgeMindDiagnosticSeverity.Error;
  }
  if (explicitSeverity === 'warning' || explicitSeverity === 'warn') {
    return EdgeMindDiagnosticSeverity.Warning;
  }
  if (explicitSeverity === 'info' || explicitSeverity === 'information') {
    return EdgeMindDiagnosticSeverity.Information;
  }

  const typeLower = (finding.type || '').toLowerCase();
  if (typeLower.includes('info') || typeLower.includes('hint')) {
    return EdgeMindDiagnosticSeverity.Information;
  }

  return defaultSeverity;
}

/**
 * Formats a descriptive multi-line diagnostic message with finding explanation and remediation.
 */
export function formatDiagnosticMessage(finding: ReportFinding): string {
  const parts: string[] = [];
  const primaryMsg = finding.message || finding.type || 'EdgeMind finding';
  parts.push(primaryMsg);

  const why = finding.why || finding.explanation;
  if (why && why.trim() && why.trim() !== primaryMsg.trim()) {
    parts.push(`Why: ${why.trim()}`);
  }

  const fix = finding.fix || finding.suggested_fix;
  if (fix && fix.trim()) {
    parts.push(`Fix: ${fix.trim()}`);
  }

  if (finding.concept && finding.concept.trim() && finding.concept !== 'General') {
    parts.push(`Concept: ${finding.concept.trim()}`);
  }

  return parts.join('\n');
}

/**
 * Calculates absolute 0-based document line from backend 1-based finding line number.
 * Handles missing, 0, negative, and out-of-range line numbers safely.
 */
export function calculateAbsoluteLine(
  rawLine: number | undefined | null,
  selectionStartLine1?: number,
  maxLineIndex?: number
): number {
  // If line number is missing, invalid, or 0, fallback to snippet or document start
  let lineOffset = 0;
  if (rawLine !== undefined && rawLine !== null && !isNaN(rawLine)) {
    const parsed = Math.floor(rawLine);
    if (parsed > 0) {
      lineOffset = parsed - 1; // 1-based to 0-based offset
    }
  }

  let baseLine0 = 0;
  if (selectionStartLine1 !== undefined && selectionStartLine1 > 0) {
    baseLine0 = selectionStartLine1 - 1; // 1-based to 0-based base
  }

  let targetLine = baseLine0 + lineOffset;

  if (targetLine < 0) {
    targetLine = 0;
  }

  if (maxLineIndex !== undefined && maxLineIndex >= 0) {
    targetLine = Math.min(targetLine, maxLineIndex);
  }

  return targetLine;
}

/**
 * Computes range for a diagnostic on a target line, trimming leading whitespace squiggles.
 */
export function calculateDiagnosticRange(
  targetLine0: number,
  getLineText?: (line0: number) => string
): DiagnosticRange {
  let startChar = 0;
  let endChar = 80;

  if (getLineText) {
    const text = getLineText(targetLine0) ?? '';
    const firstNonWs = text.search(/\S/);
    startChar = firstNonWs >= 0 ? firstNonWs : 0;
    endChar = Math.max(startChar + 1, text.length);
  }

  return {
    startLine: targetLine0,
    startChar,
    endLine: targetLine0,
    endChar,
  };
}

/**
 * Maps a single finding into an EdgeMindDiagnostic.
 */
export function mapFindingToDiagnostic(
  finding: ReportFinding,
  defaultSeverity: EdgeMindDiagnosticSeverity,
  options?: DiagnosticMappingOptions
): EdgeMindDiagnostic {
  const rawLine = finding.line ?? finding.line_number;
  const targetLine = calculateAbsoluteLine(
    rawLine,
    options?.selectionStartLine,
    options?.maxLineIndex
  );

  const range = calculateDiagnosticRange(targetLine, options?.getLineText);
  const severity = mapFindingSeverity(finding, defaultSeverity);
  const message = formatDiagnosticMessage(finding);
  const code = finding.type || 'Finding';

  return {
    range,
    message,
    severity,
    source: 'EdgeMind',
    code,
  };
}

/**
 * Maps all errors and warnings in an AnalysisReport into a list of EdgeMindDiagnostics.
 */
export function mapReportToDiagnostics(
  report: AnalysisReport,
  options?: DiagnosticMappingOptions
): EdgeMindDiagnostic[] {
  const diagnostics: EdgeMindDiagnostic[] = [];

  const errors = report.errors || report.detailed_errors || [];
  for (const err of errors) {
    diagnostics.push(mapFindingToDiagnostic(err, EdgeMindDiagnosticSeverity.Error, options));
  }

  const warnings = report.warnings || report.detailed_warnings || [];
  for (const warn of warnings) {
    diagnostics.push(mapFindingToDiagnostic(warn, EdgeMindDiagnosticSeverity.Warning, options));
  }

  return diagnostics;
}

/**
 * Merges new selection diagnostics into existing document diagnostics.
 * Replaces diagnostics in [selectionStartLine0, selectionEndLine0] while preserving
 * findings outside that range.
 */
export function mergeSelectionDiagnostics(
  existing: EdgeMindDiagnostic[],
  newDiagnostics: EdgeMindDiagnostic[],
  selectionStartLine0: number,
  selectionEndLine0: number
): EdgeMindDiagnostic[] {
  const preserved = existing.filter((d) => {
    const line = d.range.startLine;
    return line < selectionStartLine0 || line > selectionEndLine0;
  });

  return [...preserved, ...newDiagnostics];
}
