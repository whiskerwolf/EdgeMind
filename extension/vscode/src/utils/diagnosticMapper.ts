import * as vscode from 'vscode';
import { AnalysisReport } from '../types/api';
import {
  mapReportToDiagnostics,
  EdgeMindDiagnostic,
} from './diagnosticData';

/**
 * Converts pure EdgeMindDiagnostic objects to native VS Code Diagnostic instances.
 */
export function toVsCodeDiagnostic(d: EdgeMindDiagnostic): vscode.Diagnostic {
  const range = new vscode.Range(
    d.range.startLine,
    d.range.startChar,
    d.range.endLine,
    d.range.endChar
  );

  let severity: vscode.DiagnosticSeverity;
  switch (d.severity) {
    case 0:
      severity = vscode.DiagnosticSeverity.Error;
      break;
    case 1:
      severity = vscode.DiagnosticSeverity.Warning;
      break;
    case 2:
      severity = vscode.DiagnosticSeverity.Information;
      break;
    case 3:
      severity = vscode.DiagnosticSeverity.Hint;
      break;
    default:
      severity = vscode.DiagnosticSeverity.Warning;
      break;
  }

  const diagnostic = new vscode.Diagnostic(range, d.message, severity);
  diagnostic.source = d.source;
  diagnostic.code = d.code;
  return diagnostic;
}

/**
 * Creates VS Code Diagnostic objects from an EdgeMind AnalysisReport for the given document.
 */
export function createDocumentDiagnostics(
  report: AnalysisReport,
  document: vscode.TextDocument,
  selectionRange?: vscode.Range
): vscode.Diagnostic[] {
  const maxLineIndex = Math.max(0, document.lineCount - 1);
  const selectionStartLine1 = selectionRange ? selectionRange.start.line + 1 : undefined;

  const pureDiagnostics = mapReportToDiagnostics(report, {
    selectionStartLine: selectionStartLine1,
    maxLineIndex,
    getLineText: (line0: number) => {
      if (line0 >= 0 && line0 < document.lineCount) {
        return document.lineAt(line0).text;
      }
      return '';
    },
  });

  return pureDiagnostics.map(toVsCodeDiagnostic);
}

/**
 * Updates a DiagnosticCollection with findings from an AnalysisReport.
 * For full-file analysis: replaces all diagnostics for document.uri.
 * For selection analysis: replaces diagnostics within the selection range,
 * preserving findings outside that range.
 */
export function updateDocumentDiagnostics(
  collection: vscode.DiagnosticCollection,
  document: vscode.TextDocument,
  report: AnalysisReport,
  selectionRange?: vscode.Range
): void {
  const newDiagnostics = createDocumentDiagnostics(report, document, selectionRange);

  if (!selectionRange) {
    // Full-file analysis: completely replace document diagnostics
    collection.set(document.uri, newDiagnostics);
  } else {
    // Selection analysis: preserve diagnostics outside selection range
    const startLine0 = selectionRange.start.line;
    const endLine0 = selectionRange.end.line;

    const existingDiagnostics = collection.get(document.uri) || [];
    const preservedDiagnostics = existingDiagnostics.filter((d) => {
      const line = d.range.start.line;
      return line < startLine0 || line > endLine0;
    });

    const combined = [...preservedDiagnostics, ...newDiagnostics];
    collection.set(document.uri, combined);
  }
}
