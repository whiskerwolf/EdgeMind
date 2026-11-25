import {
  AnalysisCategorySummary,
  AnalysisReport,
  AnalysisSessionItem,
  CoverageGapItem,
  EdgeMindCandidate,
  PersistedReportDocument,
  ReportFinding,
  SessionAnalysisRecord,
} from '../types/api';

export type HistoryRecordSource = 'database' | 'session';

export interface NormalizedHistoryEntry {
  id: string;
  sessionId: string;
  source: HistoryRecordSource;
  title: string;
  filename: string | null;
  projectName: string | null;
  problemSlug: string | null;
  platform: string | null;
  language: string;
  analysisMode: string;
  status: string;
  storageStatus: string;
  score: number | null;
  totalErrors: number | null;
  totalWarnings: number | null;
  gapsDetected: number | null;
  candidatesGenerated: number | null;
  durationMs: number | null;
  createdAt: string | null;
  summary: AnalysisCategorySummary | null;
  errors: ReportFinding[];
  warnings: ReportFinding[];
  coverageGaps: CoverageGapItem[];
  generatedCandidates: EdgeMindCandidate[];
  recommendations: string[];
  rawSnapshot: unknown;
  sourceCodeNote: string;
  hasDetailedReport: boolean;
}

export type HistorySortOption = 'newest' | 'oldest' | 'score-desc' | 'score-asc';
export type HistoryDateFilter = 'all' | 'today' | '7d' | '30d';
export type HistoryScoreFilter = 'all' | '90plus' | '70plus' | 'below70';

export interface HistoryFilters {
  search: string;
  status: string;
  dateRange: HistoryDateFilter;
  scoreRange: HistoryScoreFilter;
  sort: HistorySortOption;
}

export const DEFAULT_HISTORY_FILTERS: HistoryFilters = {
  search: '',
  status: 'all',
  dateRange: 'all',
  scoreRange: 'all',
  sort: 'newest',
};

function freezeSnapshot<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalizeSummary(raw: unknown): AnalysisCategorySummary | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  if (!obj.syntax && !obj.runtime && !obj.logic && !obj.quality && !obj.complexity) {
    return null;
  }
  return {
    syntax: String(obj.syntax || 'UNKNOWN'),
    runtime: String(obj.runtime || 'SKIPPED'),
    logic: String(obj.logic || 'UNKNOWN'),
    quality: String(obj.quality || 'UNKNOWN'),
    complexity: String(obj.complexity || 'UNKNOWN'),
  };
}

function collectRecommendations(
  errors: ReportFinding[],
  warnings: ReportFinding[],
  explanations?: { limitations?: string[]; warnings?: string[] }
): string[] {
  const recs: string[] = [];
  for (const item of [...errors, ...warnings]) {
    const fix = (item.fix || item.suggested_fix || '').trim();
    if (fix && !recs.includes(fix)) {
      recs.push(fix);
    }
  }
  for (const msg of explanations?.warnings || []) {
    const cleaned = String(msg || '').trim();
    if (cleaned && !recs.includes(cleaned)) {
      recs.push(cleaned);
    }
  }
  for (const lim of explanations?.limitations || []) {
    const cleaned = String(lim || '').trim();
    if (cleaned && !recs.includes(cleaned)) {
      recs.push(cleaned);
    }
  }
  return recs;
}

/**
 * Converts an in-memory SessionAnalysisRecord into an immutable NormalizedHistoryEntry.
 */
export function normalizeSessionRecord(record: SessionAnalysisRecord): NormalizedHistoryEntry {
  const report: AnalysisReport = freezeSnapshot(record.report);
  const errors = Array.isArray(report.errors) ? report.errors : [];
  const warnings = Array.isArray(report.warnings) ? report.warnings : [];

  return {
    id: record.id,
    sessionId: record.id,
    source: 'session',
    title: record.filename || report.file || 'snippet.py',
    filename: record.filename || report.file || 'snippet.py',
    projectName: null,
    problemSlug: null,
    platform: null,
    language: 'python',
    analysisMode: 'STATIC_AST',
    status: record.overall_status || report.overall_status || report.status || 'UNKNOWN',
    storageStatus: 'IN_MEMORY_SESSION',
    score: typeof record.score === 'number' ? record.score : null,
    totalErrors: typeof record.total_errors === 'number' ? record.total_errors : errors.length,
    totalWarnings:
      typeof record.total_warnings === 'number' ? record.total_warnings : warnings.length,
    gapsDetected: null,
    candidatesGenerated: null,
    durationMs: typeof record.durationMs === 'number' ? record.durationMs : null,
    createdAt: record.executedAt || null,
    summary: normalizeSummary(report.summary),
    errors,
    warnings,
    coverageGaps: [],
    generatedCandidates: [],
    recommendations: collectRecommendations(errors, warnings),
    rawSnapshot: report,
    sourceCodeNote:
      'Source code is not attached to historical snapshots to preserve workspace separation and privacy.',
    hasDetailedReport: true,
  };
}

/**
 * Converts a persisted JSONB AnalysisReport document (and optional joined session metadata)
 * into an immutable NormalizedHistoryEntry without fabricating missing score or findings fields.
 */
export function normalizePersistedReportDoc(
  doc: PersistedReportDocument,
  joinedMeta?: AnalysisSessionItem
): NormalizedHistoryEntry {
  const snapshot = freezeSnapshot(doc);
  const meta = snapshot.analysis_metadata || {};
  const metaAny = meta as Record<string, unknown>;
  const codeSnapshot =
    metaAny.code_analysis && typeof metaAny.code_analysis === 'object'
      ? (metaAny.code_analysis as Record<string, unknown>)
      : null;

  const rawScore =
    typeof metaAny.score === 'number'
      ? metaAny.score
      : codeSnapshot && typeof codeSnapshot.score === 'number'
        ? codeSnapshot.score
        : null;

  const rawErrors = Array.isArray(metaAny.errors)
    ? (metaAny.errors as ReportFinding[])
    : codeSnapshot && Array.isArray(codeSnapshot.errors)
      ? (codeSnapshot.errors as ReportFinding[])
      : [];

  const rawWarnings = Array.isArray(metaAny.warnings)
    ? (metaAny.warnings as ReportFinding[])
    : codeSnapshot && Array.isArray(codeSnapshot.warnings)
      ? (codeSnapshot.warnings as ReportFinding[])
      : [];

  const totalErrors =
    typeof metaAny.total_errors === 'number'
      ? metaAny.total_errors
      : codeSnapshot && typeof codeSnapshot.total_errors === 'number'
        ? codeSnapshot.total_errors
        : rawErrors.length > 0
          ? rawErrors.length
          : null;

  const totalWarnings =
    typeof metaAny.total_warnings === 'number'
      ? metaAny.total_warnings
      : codeSnapshot && typeof codeSnapshot.total_warnings === 'number'
        ? codeSnapshot.total_warnings
        : rawWarnings.length > 0
          ? rawWarnings.length
          : null;

  const filename =
    (typeof metaAny.filename === 'string' && metaAny.filename) ||
    (typeof codeSnapshot?.file === 'string' && codeSnapshot.file) ||
    null;

  const sessionId = snapshot.analysis_session_id || snapshot.id || joinedMeta?.id || 'unknown';
  const title =
    snapshot.problem?.title ||
    joinedMeta?.problem_title ||
    joinedMeta?.project_name ||
    filename ||
    snapshot.problem_slug ||
    joinedMeta?.problem_slug ||
    `Session ${sessionId.slice(0, 8)}`;

  const summary =
    normalizeSummary(meta.code_summary) || normalizeSummary(codeSnapshot?.summary);

  return {
    id: sessionId,
    sessionId,
    source: 'database',
    title,
    filename,
    projectName: joinedMeta?.project_name ?? null,
    problemSlug: snapshot.problem_slug || joinedMeta?.problem_slug || null,
    platform: snapshot.platform || snapshot.problem?.platform || joinedMeta?.platform || null,
    language: snapshot.language || joinedMeta?.language || 'python',
    analysisMode: snapshot.analysis_mode || joinedMeta?.analysis_mode || 'BASELINE_DRIVEN',
    status: snapshot.analysis_status || joinedMeta?.analysis_status || 'SUCCESS',
    storageStatus: joinedMeta?.report_storage_status || 'STORED',
    score: rawScore,
    totalErrors,
    totalWarnings,
    gapsDetected:
      typeof meta.gaps_detected === 'number'
        ? meta.gaps_detected
        : typeof joinedMeta?.gaps_detected === 'number'
          ? joinedMeta.gaps_detected
          : Array.isArray(snapshot.coverage_gaps)
            ? snapshot.coverage_gaps.length
            : null,
    candidatesGenerated:
      typeof meta.candidates_generated === 'number'
        ? meta.candidates_generated
        : typeof joinedMeta?.candidates_generated === 'number'
          ? joinedMeta.candidates_generated
          : Array.isArray(snapshot.generated_candidates)
            ? snapshot.generated_candidates.length
            : null,
    durationMs:
      typeof meta.duration_ms === 'number'
        ? meta.duration_ms
        : typeof joinedMeta?.duration_ms === 'number'
          ? joinedMeta.duration_ms
          : null,
    createdAt: snapshot.created_at || joinedMeta?.created_at || null,
    summary,
    errors: rawErrors,
    warnings: rawWarnings,
    coverageGaps: Array.isArray(snapshot.coverage_gaps) ? snapshot.coverage_gaps : [],
    generatedCandidates: Array.isArray(snapshot.generated_candidates)
      ? snapshot.generated_candidates
      : [],
    recommendations: collectRecommendations(rawErrors, rawWarnings, snapshot.explanations),
    rawSnapshot: snapshot,
    sourceCodeNote:
      'Raw source code is permanently excluded from PostgreSQL JSONB reports by EdgeMind security policy.',
    hasDetailedReport: true,
  };
}

/**
 * Converts a session-only JOIN row (when detailed JSONB report was not loaded or deleted)
 * without fabricating detailed findings or scores.
 */
export function normalizeSessionJoinItem(item: AnalysisSessionItem): NormalizedHistoryEntry {
  const snapshot = freezeSnapshot(item);
  const title =
    snapshot.problem_title ||
    snapshot.project_name ||
    snapshot.problem_slug ||
    `Session ${snapshot.id.slice(0, 8)}`;

  return {
    id: snapshot.id,
    sessionId: snapshot.id,
    source: 'database',
    title,
    filename: null,
    projectName: snapshot.project_name ?? null,
    problemSlug: snapshot.problem_slug ?? null,
    platform: snapshot.platform ?? null,
    language: snapshot.language || 'python',
    analysisMode: snapshot.analysis_mode || 'BASELINE_DRIVEN',
    status: snapshot.analysis_status || 'UNKNOWN',
    storageStatus: snapshot.report_storage_status || 'STORED',
    score: null,
    totalErrors: null,
    totalWarnings: null,
    gapsDetected: typeof snapshot.gaps_detected === 'number' ? snapshot.gaps_detected : null,
    candidatesGenerated:
      typeof snapshot.candidates_generated === 'number' ? snapshot.candidates_generated : null,
    durationMs: typeof snapshot.duration_ms === 'number' ? snapshot.duration_ms : null,
    createdAt: snapshot.created_at || null,
    summary: null,
    errors: [],
    warnings: [],
    coverageGaps: [],
    generatedCandidates: [],
    recommendations: [],
    rawSnapshot: snapshot,
    sourceCodeNote:
      snapshot.report_storage_status === 'DELETED'
        ? 'The JSONB report document for this session was deleted; audit metadata remains.'
        : 'Source code is excluded from stored backend records.',
    hasDetailedReport: snapshot.report_storage_status !== 'DELETED',
  };
}

/**
 * Returns unique sorted status strings actually present in records.
 */
export function extractAvailableHistoryStatuses(records: readonly NormalizedHistoryEntry[]): string[] {
  const seen = new Set<string>();
  for (const r of records) {
    if (r.status) seen.add(r.status);
  }
  return Array.from(seen).sort((a, b) => a.localeCompare(b));
}

function getTimeMs(iso: string | null): number | null {
  if (!iso) return null;
  const parsed = Date.parse(iso);
  return Number.isNaN(parsed) ? null : parsed;
}

/**
 * Non-mutating, deterministic search, filter, and sort over history entries.
 */
export function filterAndSortHistory(
  records: readonly NormalizedHistoryEntry[],
  filters: HistoryFilters,
  nowMs: number = Date.now()
): NormalizedHistoryEntry[] {
  const query = filters.search.trim().toLowerCase();

  const filtered = records.filter((item) => {
    if (filters.status !== 'all' && item.status !== filters.status) {
      return false;
    }

    if (filters.scoreRange !== 'all') {
      if (item.score === null) return false;
      if (filters.scoreRange === '90plus' && item.score < 90) return false;
      if (filters.scoreRange === '70plus' && item.score < 70) return false;
      if (filters.scoreRange === 'below70' && item.score >= 70) return false;
    }

    if (filters.dateRange !== 'all') {
      const ts = getTimeMs(item.createdAt);
      if (ts === null) return false;
      const diffMs = nowMs - ts;
      if (filters.dateRange === 'today' && diffMs > 24 * 60 * 60 * 1000) return false;
      if (filters.dateRange === '7d' && diffMs > 7 * 24 * 60 * 60 * 1000) return false;
      if (filters.dateRange === '30d' && diffMs > 30 * 24 * 60 * 60 * 1000) return false;
    }

    if (query) {
      const haystack = [
        item.title,
        item.filename || '',
        item.projectName || '',
        item.problemSlug || '',
        item.platform || '',
        item.analysisMode,
        item.status,
        item.sessionId,
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(query)) return false;
    }

    return true;
  });

  return filtered.slice().sort((a, b) => {
    switch (filters.sort) {
      case 'oldest': {
        const at = getTimeMs(a.createdAt) ?? Number.POSITIVE_INFINITY;
        const bt = getTimeMs(b.createdAt) ?? Number.POSITIVE_INFINITY;
        if (at !== bt) return at - bt;
        return a.id.localeCompare(b.id);
      }
      case 'score-desc': {
        if (a.score !== null && b.score !== null && a.score !== b.score) {
          return b.score - a.score;
        }
        if (a.score !== null && b.score === null) return -1;
        if (a.score === null && b.score !== null) return 1;
        return (getTimeMs(b.createdAt) ?? 0) - (getTimeMs(a.createdAt) ?? 0);
      }
      case 'score-asc': {
        if (a.score !== null && b.score !== null && a.score !== b.score) {
          return a.score - b.score;
        }
        if (a.score !== null && b.score === null) return -1;
        if (a.score === null && b.score !== null) return 1;
        return (getTimeMs(b.createdAt) ?? 0) - (getTimeMs(a.createdAt) ?? 0);
      }
      case 'newest':
      default: {
        const at = getTimeMs(a.createdAt) ?? Number.NEGATIVE_INFINITY;
        const bt = getTimeMs(b.createdAt) ?? Number.NEGATIVE_INFINITY;
        if (at !== bt) return bt - at;
        return a.id.localeCompare(b.id);
      }
    }
  });
}
