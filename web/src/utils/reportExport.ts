import { ReportFinding } from '../types/api';
import { NormalizedHistoryEntry } from './historyHelpers';

function sanitizeFilenameSlug(value: string): string {
  const cleaned = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return cleaned || 'edgemind-report';
}

function serializeFindingForExport(finding: ReportFinding, severity: 'error' | 'warning') {
  return {
    severity,
    type: finding.type || '',
    category: finding.concept || '',
    line: finding.line || finding.line_number || null,
    message: finding.message || '',
    explanation: finding.why || finding.explanation || null,
    suggested_fix: finding.fix || finding.suggested_fix || null,
  };
}

/**
 * Produces sanitized JSON export string excluding raw user source code or credentials.
 */
export function buildReportExportJson(entry: NormalizedHistoryEntry): string {
  const payload = {
    schema_version: '1.0.0',
    exported_at: new Date().toISOString(),
    source_type: entry.source,
    session_id: entry.sessionId,
    target: {
      title: entry.title,
      filename: entry.filename,
      project_name: entry.projectName,
      problem_slug: entry.problemSlug,
      platform: entry.platform,
      language: entry.language,
    },
    analysis: {
      mode: entry.analysisMode,
      status: entry.status,
      storage_status: entry.storageStatus,
      score: entry.score,
      total_errors: entry.totalErrors,
      total_warnings: entry.totalWarnings,
      gaps_detected: entry.gapsDetected,
      candidates_generated: entry.candidatesGenerated,
      duration_ms: entry.durationMs,
      created_at: entry.createdAt,
      summary: entry.summary,
    },
    errors: (entry.errors || []).map((e) => serializeFindingForExport(e, 'error')),
    warnings: (entry.warnings || []).map((w) => serializeFindingForExport(w, 'warning')),
    coverage_gaps: entry.coverageGaps || [],
    recommendations: entry.recommendations || [],
    source_code_included: false,
  };

  return JSON.stringify(payload, null, 2);
}

/**
 * Escapes CSV fields safely and defends against spreadsheet formula injection (=, +, -, @, tab, cr).
 */
export function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return '""';
  let text = String(value).replace(/\r\n/g, ' ').replace(/[\r\n]/g, ' ');
  if (/^[=+\-@\t]/.test(text)) {
    text = `'${text}`;
  }
  return `"${text.replace(/"/g, '""')}"`;
}

/**
 * Produces RFC 4180 CSV summary + findings export string.
 */
export function buildReportExportCsv(entry: NormalizedHistoryEntry): string {
  const headers = [
    'record_type',
    'session_id',
    'title',
    'filename',
    'project_name',
    'status',
    'score',
    'created_at',
    'severity',
    'rule_or_category',
    'line',
    'message',
    'recommendation',
  ];

  const rows: string[][] = [];

  rows.push([
    'METADATA',
    entry.sessionId,
    entry.title,
    entry.filename ?? '',
    entry.projectName ?? '',
    entry.status,
    entry.score !== null ? String(entry.score) : '',
    entry.createdAt ?? '',
    '',
    entry.analysisMode,
    '',
    `Errors: ${entry.totalErrors ?? 'N/A'}, Warnings: ${entry.totalWarnings ?? 'N/A'}`,
    entry.recommendations[0] ?? '',
  ]);

  for (const err of entry.errors || []) {
    rows.push([
      'FINDING',
      entry.sessionId,
      entry.title,
      entry.filename ?? '',
      entry.projectName ?? '',
      entry.status,
      entry.score !== null ? String(entry.score) : '',
      entry.createdAt ?? '',
      'error',
      err.type,
      String(err.line || err.line_number || ''),
      err.message,
      err.fix || err.suggested_fix || '',
    ]);
  }

  for (const warn of entry.warnings || []) {
    rows.push([
      'FINDING',
      entry.sessionId,
      entry.title,
      entry.filename ?? '',
      entry.projectName ?? '',
      entry.status,
      entry.score !== null ? String(entry.score) : '',
      entry.createdAt ?? '',
      'warning',
      warn.type,
      String(warn.line || warn.line_number || ''),
      warn.message,
      warn.fix || warn.suggested_fix || '',
    ]);
  }

  for (const gap of entry.coverageGaps || []) {
    rows.push([
      'COVERAGE_GAP',
      entry.sessionId,
      entry.title,
      entry.filename ?? '',
      entry.projectName ?? '',
      entry.status,
      entry.score !== null ? String(entry.score) : '',
      entry.createdAt ?? '',
      gap.severity,
      gap.category,
      '',
      gap.rationale,
      gap.suggested_action || '',
    ]);
  }

  const lines = [
    headers.map(escapeCsvCell).join(','),
    ...rows.map((row) => row.map(escapeCsvCell).join(',')),
  ];

  return lines.join('\n');
}

export function triggerBrowserDownload(
  content: string,
  filename: string,
  mimeType: string
): boolean {
  if (typeof document === 'undefined' || typeof URL.createObjectURL !== 'function') {
    return false;
  }
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
  return true;
}

export function getExportFilename(entry: NormalizedHistoryEntry, ext: 'json' | 'csv'): string {
  const base = sanitizeFilenameSlug(entry.filename || entry.title || 'analysis');
  const shortId = sanitizeFilenameSlug(entry.sessionId.slice(0, 8));
  return `edgemind-${base}-${shortId}.${ext}`;
}
