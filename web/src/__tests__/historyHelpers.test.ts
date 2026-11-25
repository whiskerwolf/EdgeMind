import { describe, it, expect } from 'vitest';
import {
  extractAvailableHistoryStatuses,
  filterAndSortHistory,
  DEFAULT_HISTORY_FILTERS,
  NormalizedHistoryEntry,
  normalizePersistedReportDoc,
  normalizeSessionJoinItem,
  normalizeSessionRecord,
} from '../utils/historyHelpers';
import {
  compareHistoryReports,
  computeFindingBaseSignature,
} from '../utils/reportComparison';
import {
  buildReportExportCsv,
  buildReportExportJson,
  escapeCsvCell,
} from '../utils/reportExport';
import {
  CoverageGapItem,
  PersistedReportDocument,
  ReportFinding,
  SessionAnalysisRecord,
} from '../types/api';

const makeFinding = (
  overrides: Partial<ReportFinding> & Pick<ReportFinding, 'type' | 'message'>
): ReportFinding => ({
  line: overrides.line ?? 1,
  line_number: overrides.line_number ?? overrides.line ?? 1,
  why: overrides.why ?? '',
  explanation: overrides.explanation ?? overrides.why ?? '',
  fix: overrides.fix ?? '',
  suggested_fix: overrides.suggested_fix ?? overrides.fix ?? '',
  concept: overrides.concept ?? 'GENERAL',
  ...overrides,
});

const makeGap = (
  overrides: Partial<CoverageGapItem> & Pick<CoverageGapItem, 'category' | 'severity' | 'rationale'>
): CoverageGapItem => ({
  constraint_validity: overrides.constraint_validity ?? 'VALID',
  relevance_score: overrides.relevance_score ?? 85,
  risk_explained: overrides.risk_explained ?? overrides.rationale,
  suggested_action: overrides.suggested_action ?? 'Add edge case coverage.',
  ...overrides,
});

const makeSessionRun = (overrides: Partial<SessionAnalysisRecord> = {}): SessionAnalysisRecord => ({
  id: 'session-100',
  filename: 'solver.py',
  score: 82,
  overall_status: 'WARNING',
  total_errors: 1,
  total_warnings: 1,
  durationMs: 28,
  executedAt: '2026-11-24T10:00:00.000Z',
  report: {
    file_path: 'solver.py',
    file: 'solver.py',
    overall_status: 'WARNING',
    status: 'WARNING',
    score: 82,
    total_errors: 1,
    total_warnings: 1,
    syntax_status: 'PASS',
    runtime_status: 'SKIPPED',
    logic_status: 'FAIL',
    quality_status: 'WARNING',
    complexity_status: 'PASS',
    errors: [
      makeFinding({
        type: 'ZeroDivisionError',
        line: 5,
        message: 'Division by zero detected',
        concept: 'SAFETY',
        why: 'Denominator can be 0.',
        fix: 'Guard against zero.',
      }),
    ],
    warnings: [
      makeFinding({
        type: 'UnusedVariable',
        line: 2,
        message: 'Variable tmp is unused',
        concept: 'CLEANLINESS',
      }),
    ],
    summary: {
      syntax: 'PASS',
      runtime: 'SKIPPED',
      logic: 'FAIL',
      quality: 'WARNING',
      complexity: 'PASS',
    },
  },
  ...overrides,
});

describe('historyHelpers', () => {
  it('normalizes session records as immutable snapshots without shared mutation', () => {
    const original = makeSessionRun();
    const entry = normalizeSessionRecord(original);

    // Mutate source object after normalization
    original.report.errors[0].message = 'MUTATED';
    original.report.score = 0;

    expect(entry.source).toBe('session');
    expect(entry.score).toBe(82);
    expect(entry.errors[0].message).toBe('Division by zero detected');
    expect(entry.summary?.logic).toBe('FAIL');
    expect(entry.recommendations).toContain('Guard against zero.');
  });

  it('normalizes persisted JSONB report docs without fabricating missing scores', () => {
    const doc: PersistedReportDocument = {
      id: 'rep-1',
      analysis_session_id: 'sess-db-1',
      problem: { title: 'Two Sum', slug: 'two-sum', platform: 'LeetCode' },
      problem_slug: 'two-sum',
      platform: 'LeetCode',
      language: 'python',
      analysis_mode: 'BASELINE_DRIVEN',
      analysis_status: 'SUCCESS',
      coverage_gaps: [
        makeGap({
          category: 'BOUNDARY_VALUE',
          param_name: 'nums',
          severity: 'HIGH',
          rationale: 'Missing empty array case',
        }),
      ],
      generated_candidates: [],
      explanations: { warnings: ['Static analysis only'] },
      analysis_metadata: {
        duration_ms: 45,
        gaps_detected: 1,
        candidates_generated: 4,
      },
      created_at: '2026-11-23T09:00:00.000Z',
    };

    const normalized = normalizePersistedReportDoc(doc, {
      id: 'sess-db-1',
      project_name: 'Interview Prep',
      problem_title: 'Two Sum',
      problem_slug: 'two-sum',
      platform: 'LeetCode',
      language: 'python',
      analysis_mode: 'BASELINE_DRIVEN',
      analysis_status: 'SUCCESS',
      report_storage_status: 'STORED',
      gaps_detected: 1,
      candidates_generated: 4,
      duration_ms: 45,
      created_at: '2026-11-23T09:00:00.000Z',
    });

    expect(normalized.source).toBe('database');
    expect(normalized.projectName).toBe('Interview Prep');
    expect(normalized.score).toBeNull();
    expect(normalized.totalErrors).toBeNull();
    expect(normalized.gapsDetected).toBe(1);
    expect(normalized.candidatesGenerated).toBe(4);
    expect(normalized.durationMs).toBe(45);
    expect(normalized.sourceCodeNote.toLowerCase()).toContain('excluded');
  });

  it('handles deleted DB session metadata rows honestly', () => {
    const row = normalizeSessionJoinItem({
      id: 'sess-del-1',
      project_name: 'Core',
      problem_title: 'Binary Search',
      problem_slug: 'binary-search',
      platform: 'Internal',
      language: 'python',
      analysis_mode: 'CONTEXT_BASED',
      analysis_status: 'SUCCESS',
      report_storage_status: 'DELETED',
      gaps_detected: 2,
      candidates_generated: 0,
      duration_ms: 19,
      created_at: '2026-11-22T08:00:00.000Z',
    });

    expect(row.storageStatus).toBe('DELETED');
    expect(row.hasDetailedReport).toBe(false);
    expect(row.score).toBeNull();
    expect(row.sourceCodeNote.toLowerCase()).toContain('deleted');
  });

  it('filters by search, status, score range, and date range without mutating input array', () => {
    const nowMs = Date.parse('2026-11-25T12:00:00.000Z');
    const a = normalizeSessionRecord(
      makeSessionRun({
        id: 'a',
        filename: 'alpha.py',
        score: 95,
        overall_status: 'PASS',
        executedAt: '2026-11-25T10:00:00.000Z',
      })
    );
    const b = normalizeSessionRecord(
      makeSessionRun({
        id: 'b',
        filename: 'beta.py',
        score: 62,
        overall_status: 'FAIL',
        executedAt: '2026-11-20T10:00:00.000Z',
      })
    );
    const c = normalizePersistedReportDoc({
      analysis_session_id: 'c',
      problem_slug: 'gamma-check',
      analysis_status: 'SUCCESS',
      created_at: '2026-10-01T10:00:00.000Z',
    });

    const input: NormalizedHistoryEntry[] = [a, b, c];
    const snapshotOrder = input.map((i) => i.id);

    expect(extractAvailableHistoryStatuses(input)).toEqual(['FAIL', 'PASS', 'SUCCESS']);

    // Score filter excludes null score (never treats null as 0)
    const below70 = filterAndSortHistory(
      input,
      { ...DEFAULT_HISTORY_FILTERS, scoreRange: 'below70' },
      nowMs
    );
    expect(below70.map((x) => x.id)).toEqual(['b']);

    const todayOnly = filterAndSortHistory(
      input,
      { ...DEFAULT_HISTORY_FILTERS, dateRange: 'today' },
      nowMs
    );
    expect(todayOnly.map((x) => x.id)).toEqual(['a']);

    const searchGamma = filterAndSortHistory(
      input,
      { ...DEFAULT_HISTORY_FILTERS, search: 'gamma' },
      nowMs
    );
    expect(searchGamma.map((x) => x.id)).toEqual(['c']);

    const sortedScoreDesc = filterAndSortHistory(
      input,
      { ...DEFAULT_HISTORY_FILTERS, sort: 'score-desc' },
      nowMs
    );
    expect(sortedScoreDesc.map((x) => x.id)).toEqual(['a', 'b', 'c']);

    expect(input.map((i) => i.id)).toEqual(snapshotOrder);
  });
});

describe('reportComparison', () => {
  it('computes base signatures independent of whitespace, case, and line numbers', () => {
    const s1 = computeFindingBaseSignature('ZeroDivisionError', 'SAFETY', 'Division   by zero');
    const s2 = computeFindingBaseSignature('zerodivisionerror', 'safety', ' division by zero ');
    expect(s1).toBe(s2);
  });

  it('detects added, resolved, persistent, severity-changed findings and reordered arrays', () => {
    const baseline = normalizeSessionRecord(
      makeSessionRun({
        id: 'base',
        filename: 'app.py',
        score: 70,
        report: {
          file_path: 'app.py',
          file: 'app.py',
          overall_status: 'FAIL',
          status: 'FAIL',
          score: 70,
          total_errors: 2,
          total_warnings: 1,
          syntax_status: 'PASS',
          runtime_status: 'SKIPPED',
          logic_status: 'FAIL',
          quality_status: 'WARNING',
          complexity_status: 'PASS',
          errors: [
            makeFinding({ type: 'OldErr', line: 10, message: 'Old bug removed later', concept: 'LOGIC' }),
            makeFinding({ type: 'ShiftedErr', line: 12, message: 'Keep checking null input', concept: 'SAFETY' }),
          ],
          warnings: [
            makeFinding({ type: 'EscalatedRule', line: 20, message: 'Mutable default arg', concept: 'PITFALL' }),
          ],
          summary: {
            syntax: 'PASS',
            runtime: 'SKIPPED',
            logic: 'FAIL',
            quality: 'WARNING',
            complexity: 'PASS',
          },
        },
      })
    );

    const target = normalizeSessionRecord(
      makeSessionRun({
        id: 'target',
        filename: 'app.py',
        score: 85,
        report: {
          file_path: 'app.py',
          file: 'app.py',
          overall_status: 'WARNING',
          status: 'WARNING',
          score: 85,
          total_errors: 2,
          total_warnings: 1,
          syntax_status: 'PASS',
          runtime_status: 'SKIPPED',
          logic_status: 'PASS',
          quality_status: 'WARNING',
          complexity_status: 'PASS',
          errors: [
            // Escalated from warning -> error
            makeFinding({ type: 'EscalatedRule', line: 20, message: 'Mutable default arg', concept: 'PITFALL' }),
            // Reordered + shifted line
            makeFinding({ type: 'ShiftedErr', line: 18, message: 'Keep checking null input', concept: 'SAFETY' }),
          ],
          warnings: [
            makeFinding({ type: 'NewWarn', line: 3, message: 'Broad except clause', concept: 'QUALITY' }),
          ],
          summary: {
            syntax: 'PASS',
            runtime: 'SKIPPED',
            logic: 'PASS',
            quality: 'WARNING',
            complexity: 'PASS',
          },
        },
      })
    );

    const result = compareHistoryReports(baseline, target);

    expect(result.differentFiles).toBe(false);
    expect(result.previousScore).toBe(70);
    expect(result.newScore).toBe(85);
    expect(result.scoreDelta).toBe(15);
    expect(result.addedFindings.map((f) => f.type)).toEqual(['NewWarn']);
    expect(result.resolvedFindings.map((f) => f.type)).toEqual(['OldErr']);
    expect(result.persistentFindings.length).toBe(2);
    expect(result.severityChanges.length).toBe(1);
    expect(result.severityChanges[0].previousSeverity).toBe('warning');
    expect(result.severityChanges[0].newSeverity).toBe('error');
    expect(result.areIdentical).toBe(false);
  });

  it('flags identical reports and missing scores accurately', () => {
    const dbA = normalizePersistedReportDoc({
      analysis_session_id: 'db-1',
      problem_slug: 'prob-a',
      coverage_gaps: [makeGap({ category: 'NULL_HANDLING', severity: 'HIGH', rationale: 'Check None' })],
    });
    const dbB = normalizePersistedReportDoc({
      analysis_session_id: 'db-2',
      problem_slug: 'prob-b',
      coverage_gaps: [makeGap({ category: 'NULL_HANDLING', severity: 'HIGH', rationale: 'Check None' })],
    });

    const diff = compareHistoryReports(dbA, dbB);
    expect(diff.differentFiles).toBe(true);
    expect(diff.scoreDelta).toBeNull();
    expect(diff.addedGaps).toEqual([]);
    expect(diff.resolvedGaps).toEqual([]);
    expect(diff.areIdentical).toBe(true);
  });
});

describe('reportExport', () => {
  it('neutralizes CSV formula injection and serializes JSON cleanly without source code', () => {
    expect(escapeCsvCell('=CMD("calc")')).toBe('"\'=CMD(""calc"")"');
    expect(escapeCsvCell('+1+1')).toBe('"\'+1+1"');
    expect(escapeCsvCell('@SUM(A1)')).toBe('"\'@SUM(A1)"');

    const entry = normalizeSessionRecord(
      makeSessionRun({
        filename: 'calc.py',
        report: {
          ...makeSessionRun().report,
          errors: [
            makeFinding({
              type: 'InjectionTest',
              line: 4,
              message: '=malicious("cell")',
              fix: '+use guard',
              concept: 'SECURITY',
            }),
          ],
          warnings: [],
        },
      })
    );

    const json = buildReportExportJson(entry);
    const parsed = JSON.parse(json);
    expect(parsed.source_code_included).toBe(false);
    expect(parsed.code).toBeUndefined();
    expect(parsed.errors[0].type).toBe('InjectionTest');

    const csv = buildReportExportCsv(entry);
    expect(csv).toContain('METADATA');
    expect(csv).toContain('"\'=malicious(""cell"")"');
    expect(csv).toContain('"\'+use guard"');
  });
});
