import { AnalysisReport } from '../types/api';

/**
 * Formats a concise one-line summary string for VS Code notification toast.
 */
export function formatSummaryNotification(
  report: AnalysisReport,
  scopeLabel?: string
): string {
  const file = report.file || report.file_path || 'snippet.py';
  const targetLabel = scopeLabel ? `'${file}' (${scopeLabel})` : `'${file}'`;
  const errors = report.total_errors ?? (report.errors ? report.errors.length : 0);
  const warnings = report.total_warnings ?? (report.warnings ? report.warnings.length : 0);
  return `EdgeMind Analysis for ${targetLabel}: ${report.overall_status} (Score: ${report.score}/100) — ${errors} error(s), ${warnings} warning(s).`;
}

/**
 * Formats an AnalysisReport into a human-readable text document for the EdgeMind Output Channel.
 */
export function formatReportOutput(
  report: AnalysisReport,
  durationMs?: number,
  scopeLabel?: string
): string {
  const divider = '='.repeat(70);
  const subDivider = '-'.repeat(70);
  const lines: string[] = [];

  const file = report.file || report.file_path || 'snippet.py';
  const errors = report.errors || report.detailed_errors || [];
  const warnings = report.warnings || report.detailed_warnings || [];
  const summary = report.summary || {
    syntax: report.syntax_status || 'PASS',
    runtime: report.runtime_status || 'SKIPPED',
    logic: report.logic_status || 'PASS',
    quality: report.quality_status || 'PASS',
    complexity: report.complexity_status || 'PASS',
  };

  lines.push('');
  lines.push(divider);
  lines.push('EDGEMIND STATIC CODE ANALYSIS REPORT');
  lines.push(divider);
  lines.push(`File:             ${file}`);
  if (scopeLabel) {
    lines.push(`Scope:            ${scopeLabel}`);
  }
  lines.push(`Overall Status:   ${report.overall_status || report.status || 'PASS'}`);
  lines.push(`Score:            ${report.score}/100`);
  if (durationMs !== undefined) {
    lines.push(`Latency:          ${durationMs}ms`);
  }
  lines.push(`Total Errors:     ${report.total_errors ?? errors.length}`);
  lines.push(`Total Warnings:   ${report.total_warnings ?? warnings.length}`);
  lines.push('');

  lines.push(subDivider);
  lines.push('Category Summary:');
  lines.push(subDivider);
  lines.push(`  • Syntax:         ${summary.syntax}`);
  lines.push(`  • Runtime Checks: ${summary.runtime} (Static-only mode enforced)`);
  lines.push(`  • Logic:          ${summary.logic}`);
  lines.push(`  • Code Quality:   ${summary.quality}`);
  lines.push(`  • Complexity:     ${summary.complexity}`);
  lines.push('');

  if (errors.length > 0) {
    lines.push(subDivider);
    lines.push(`ERRORS (${errors.length}):`);
    lines.push(subDivider);
    errors.forEach((err, idx) => {
      const lineNum = err.line || err.line_number || 0;
      lines.push(`[${idx + 1}] Line ${lineNum}: ${err.type} — ${err.message}`);
      if (err.why || err.explanation) {
        lines.push(`    Why:     ${err.why || err.explanation}`);
      }
      if (err.fix || err.suggested_fix) {
        lines.push(`    Fix:     ${err.fix || err.suggested_fix}`);
      }
      if (err.concept) {
        lines.push(`    Concept: ${err.concept}`);
      }
      lines.push('');
    });
  }

  if (warnings.length > 0) {
    lines.push(subDivider);
    lines.push(`WARNINGS (${warnings.length}):`);
    lines.push(subDivider);
    warnings.forEach((warn, idx) => {
      const lineNum = warn.line || warn.line_number || 0;
      lines.push(`[${idx + 1}] Line ${lineNum}: ${warn.type} — ${warn.message}`);
      if (warn.why || warn.explanation) {
        lines.push(`    Why:     ${warn.why || warn.explanation}`);
      }
      if (warn.fix || warn.suggested_fix) {
        lines.push(`    Fix:     ${warn.fix || warn.suggested_fix}`);
      }
      if (warn.concept) {
        lines.push(`    Concept: ${warn.concept}`);
      }
      lines.push('');
    });
  }

  if (errors.length === 0 && warnings.length === 0) {
    lines.push(subDivider);
    lines.push('FINDINGS:');
    lines.push(subDivider);
    lines.push('No errors or warnings detected. Clean static code hygiene!');
    lines.push('');
  }

  lines.push(divider);
  lines.push('');
  return lines.join('\n');
}
