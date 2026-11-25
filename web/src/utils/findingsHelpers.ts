import {
  AnalysisReport,
  DiagnoseFindingRequest,
  FindingSeverity,
  ReportFinding,
} from '../types/api';

export const MAX_DIAGNOSIS_CONTEXT_BYTES = 16 * 1024; // 16 KiB matching core/schemas.py

export interface ExplorerFinding {
  id: string;
  severity: FindingSeverity;
  type: string;
  concept: string;
  message: string;
  line: number | null;
  explanation: string;
  suggestedFix: string;
  filename: string;
  originalIndex: number;
  raw: ReportFinding;
}

export type FindingSortOption = 'default' | 'severity-desc' | 'line-asc' | 'line-desc';

export interface FindingFilters {
  search: string;
  severity: 'all' | FindingSeverity;
  category: string;
  sort: FindingSortOption;
}

export const DEFAULT_FINDING_FILTERS: FindingFilters = {
  search: '',
  severity: 'all',
  category: 'all',
  sort: 'default',
};

function sanitizeFindingId(raw: string): string {
  const cleaned = raw.replace(/[^a-zA-Z0-9_-]/g, '-').slice(0, 64);
  return cleaned || 'finding-1';
}

function normalizeFindingLine(finding: ReportFinding): number | null {
  const candidate =
    typeof finding.line === 'number' && finding.line >= 1
      ? finding.line
      : typeof finding.line_number === 'number' && finding.line_number >= 1
        ? finding.line_number
        : null;
  return candidate !== null ? Math.floor(candidate) : null;
}

function mapRawFinding(
  raw: ReportFinding,
  severity: FindingSeverity,
  filename: string,
  originalIndex: number
): ExplorerFinding {
  const line = normalizeFindingLine(raw);
  const type = (raw.type || 'UnknownRule').trim() || 'UnknownRule';
  const concept = (raw.concept || '').trim();
  const message = (raw.message || '').trim() || 'No diagnostic message reported.';
  const explanation = (raw.why || raw.explanation || '').trim();
  const suggestedFix = (raw.fix || raw.suggested_fix || '').trim();
  const id = sanitizeFindingId(`${severity}-${originalIndex + 1}-${type}-${line ?? 0}`);

  return {
    id,
    severity,
    type,
    concept,
    message,
    line,
    explanation,
    suggestedFix,
    filename,
    originalIndex,
    raw,
  };
}

/**
 * Extracts normalized, immutable findings list from an AnalysisReport.
 * Preserves actual reported fields without fabricating missing metadata.
 */
export function extractExplorerFindings(report: AnalysisReport | null): ExplorerFinding[] {
  if (!report) return [];

  const filename = (report.file || report.file_path || 'snippet.py').trim() || 'snippet.py';
  const rawErrors =
    report.errors && report.errors.length > 0
      ? report.errors
      : report.detailed_errors || [];
  const rawWarnings =
    report.warnings && report.warnings.length > 0
      ? report.warnings
      : report.detailed_warnings || [];

  const items: ExplorerFinding[] = [];
  rawErrors.forEach((raw, idx) => {
    items.push(mapRawFinding(raw, 'error', filename, idx));
  });
  rawWarnings.forEach((raw, idx) => {
    items.push(mapRawFinding(raw, 'warning', filename, rawErrors.length + idx));
  });

  return items;
}

/**
 * Returns sorted unique category names actually returned by findings.
 */
export function extractAvailableCategories(findings: ExplorerFinding[]): string[] {
  const seen = new Set<string>();
  for (const f of findings) {
    if (f.concept) {
      seen.add(f.concept);
    }
  }
  return Array.from(seen).sort((a, b) => a.localeCompare(b));
}

function compareLineAscending(a: ExplorerFinding, b: ExplorerFinding): number {
  const aLine = a.line;
  const bLine = b.line;
  if (aLine !== null && bLine !== null) {
    return aLine - bLine;
  }
  if (aLine !== null && bLine === null) return -1;
  if (aLine === null && bLine !== null) return 1;
  return 0;
}

function compareLineDescending(a: ExplorerFinding, b: ExplorerFinding): number {
  const aLine = a.line;
  const bLine = b.line;
  if (aLine !== null && bLine !== null) {
    return bLine - aLine;
  }
  if (aLine !== null && bLine === null) return -1;
  if (aLine === null && bLine !== null) return 1;
  return 0;
}

/**
 * Non-mutating, deterministic filter & sort over ExplorerFindings.
 */
export function filterAndSortFindings(
  findings: readonly ExplorerFinding[],
  filters: FindingFilters
): ExplorerFinding[] {
  const query = filters.search.trim().toLowerCase();

  const filtered = findings.filter((item) => {
    if (filters.severity !== 'all' && item.severity !== filters.severity) {
      return false;
    }
    if (filters.category !== 'all' && item.concept !== filters.category) {
      return false;
    }
    if (query) {
      const lineText = item.line !== null ? `line ${item.line} ${item.line}` : 'module';
      const searchable = [
        item.type,
        item.concept,
        item.message,
        item.explanation,
        item.suggestedFix,
        item.filename,
        item.severity,
        lineText,
      ]
        .join(' ')
        .toLowerCase();
      if (!searchable.includes(query)) {
        return false;
      }
    }
    return true;
  });

  const severityWeight = (s: FindingSeverity) => (s === 'error' ? 0 : 1);

  return filtered.slice().sort((a, b) => {
    switch (filters.sort) {
      case 'severity-desc': {
        const sevDiff = severityWeight(a.severity) - severityWeight(b.severity);
        if (sevDiff !== 0) return sevDiff;
        const lineDiff = compareLineAscending(a, b);
        if (lineDiff !== 0) return lineDiff;
        return a.originalIndex - b.originalIndex;
      }
      case 'line-asc': {
        const lineDiff = compareLineAscending(a, b);
        if (lineDiff !== 0) return lineDiff;
        const sevDiff = severityWeight(a.severity) - severityWeight(b.severity);
        if (sevDiff !== 0) return sevDiff;
        return a.originalIndex - b.originalIndex;
      }
      case 'line-desc': {
        const lineDiff = compareLineDescending(a, b);
        if (lineDiff !== 0) return lineDiff;
        const sevDiff = severityWeight(a.severity) - severityWeight(b.severity);
        if (sevDiff !== 0) return sevDiff;
        return a.originalIndex - b.originalIndex;
      }
      case 'default':
      default: {
        const sevDiff = severityWeight(a.severity) - severityWeight(b.severity);
        if (sevDiff !== 0) return sevDiff;
        const lineDiff = compareLineAscending(a, b);
        if (lineDiff !== 0) return lineDiff;
        return a.originalIndex - b.originalIndex;
      }
    }
  });
}

export interface CodePreviewLine {
  lineNumber: number;
  text: string;
  isHighlighted: boolean;
}

/**
 * Extracts a short line-numbered code preview slice around a finding from real source code.
 * Returns null if source code is unavailable or the target line is out of bounds.
 */
export function getCodePreviewLines(
  sourceCode: string | null | undefined,
  findingLine: number | null,
  radius: number = 3
): CodePreviewLine[] | null {
  if (!sourceCode || !sourceCode.trim()) return null;

  const lines = sourceCode.split('\n');
  if (lines.length === 0) return null;

  if (findingLine === null) {
    const endIdx = Math.min(lines.length, 6);
    return lines.slice(0, endIdx).map((text, idx) => ({
      lineNumber: idx + 1,
      text,
      isHighlighted: false,
    }));
  }

  if (findingLine < 1 || findingLine > lines.length) {
    return null;
  }

  const startLine = Math.max(1, findingLine - radius);
  const endLine = Math.min(lines.length, findingLine + radius);

  const preview: CodePreviewLine[] = [];
  for (let lineNum = startLine; lineNum <= endLine; lineNum++) {
    preview.push({
      lineNumber: lineNum,
      text: lines[lineNum - 1] ?? '',
      isHighlighted: lineNum === findingLine,
    });
  }
  return preview;
}

export interface DiagnosisContextPreparationResult {
  request: DiagnoseFindingRequest | null;
  unavailableReason: string | null;
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).length;
}

/**
 * Extracts bounded source context (±15 lines or first 30 lines for module-level)
 * enforcing POST /api/v1/diagnose/stream invariants from core/schemas.py.
 */
export function buildDiagnosisRequest(
  finding: ExplorerFinding,
  sourceCode: string | null | undefined,
  language: string = 'python',
  contextRadius: number = 15
): DiagnosisContextPreparationResult {
  const normalizedLang = (language || 'python').trim().toLowerCase();
  if (normalizedLang !== 'python') {
    return {
      request: null,
      unavailableReason: `AI diagnosis currently supports Python source code only (selected: ${language}).`,
    };
  }

  if (!sourceCode || !sourceCode.trim()) {
    return {
      request: null,
      unavailableReason:
        'Analyzed source code context is unavailable. Run analysis from Code Workspace to inspect findings with AI.',
    };
  }

  const lines = sourceCode.split('\n');
  const totalLines = lines.length;

  if (finding.line !== null && (finding.line < 1 || finding.line > totalLines)) {
    return {
      request: null,
      unavailableReason: `Finding line ${finding.line} falls outside the available analyzed snapshot (${totalLines} lines).`,
    };
  }

  const boundedRadius = Math.max(5, Math.min(30, Math.round(contextRadius || 15)));
  let startLine = 1;
  let endLine = Math.min(totalLines, boundedRadius * 2);

  if (finding.line !== null) {
    startLine = Math.max(1, finding.line - boundedRadius);
    endLine = Math.min(totalLines, finding.line + boundedRadius);
  }

  let codeContext = lines.slice(startLine - 1, endLine).join('\n') || ' ';
  let byteLen = utf8ByteLength(codeContext);

  while (byteLen > MAX_DIAGNOSIS_CONTEXT_BYTES && endLine > startLine) {
    if (finding.line !== null) {
      if (endLine - finding.line >= finding.line - startLine && endLine > finding.line) {
        endLine--;
      } else if (startLine < finding.line) {
        startLine++;
      } else {
        break;
      }
    } else {
      endLine--;
    }
    codeContext = lines.slice(startLine - 1, endLine).join('\n') || ' ';
    byteLen = utf8ByteLength(codeContext);
  }

  if (!codeContext.trim()) {
    return {
      request: null,
      unavailableReason: 'Extracted code context is empty around the finding line.',
    };
  }

  if (byteLen > MAX_DIAGNOSIS_CONTEXT_BYTES) {
    return {
      request: null,
      unavailableReason: `Source context around line ${finding.line ?? 1} exceeds the 16 KiB diagnosis limit.`,
    };
  }

  const cleanFilename =
    finding.filename.split(/[\\/]/).pop()?.trim() || 'snippet.py';

  return {
    unavailableReason: null,
    request: {
      finding: {
        finding_id: finding.id.slice(0, 64),
        type: finding.type.slice(0, 128),
        severity: finding.severity,
        message: finding.message.slice(0, 1000),
        line: finding.line,
        static_why: finding.explanation ? finding.explanation.slice(0, 1000) : null,
        static_fix: finding.suggestedFix ? finding.suggestedFix.slice(0, 1000) : null,
      },
      code_context: codeContext,
      context_start_line: startLine,
      context_end_line: endLine,
      filename: cleanFilename,
      language: 'python',
    },
  };
}
