import { FindingSeverity, ReportFinding } from '../types/api';
import { NormalizedHistoryEntry } from './historyHelpers';

export interface IndexedFinding {
  baseSignature: string;
  occurrenceKey: string;
  severity: FindingSeverity;
  type: string;
  concept: string;
  message: string;
  line: number | null;
}

export interface PersistentFindingMatch {
  occurrenceKey: string;
  type: string;
  concept: string;
  message: string;
  previousSeverity: FindingSeverity;
  newSeverity: FindingSeverity;
  severityChanged: boolean;
  previousLine: number | null;
  newLine: number | null;
}

export interface GapDiffItem {
  category: string;
  paramName: string | null;
  severity: string;
  rationale: string;
}

export interface ReportComparisonResult {
  baselineId: string;
  targetId: string;
  baselineTitle: string;
  targetTitle: string;
  differentFiles: boolean;
  previousScore: number | null;
  newScore: number | null;
  scoreDelta: number | null;
  addedFindings: IndexedFinding[];
  resolvedFindings: IndexedFinding[];
  persistentFindings: PersistentFindingMatch[];
  severityChanges: PersistentFindingMatch[];
  addedGaps: GapDiffItem[];
  resolvedGaps: GapDiffItem[];
  persistentGapsCount: number;
  areIdentical: boolean;
  matchingMethodology: string;
}

function normalizeText(value: unknown): string {
  return String(value ?? '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}

function normalizeConcept(value: unknown): string {
  const cleaned = normalizeText(value);
  return cleaned === 'general' ? '' : cleaned;
}

function normalizeLine(finding: ReportFinding): number | null {
  const candidate =
    typeof finding.line === 'number' && finding.line >= 1
      ? finding.line
      : typeof finding.line_number === 'number' && finding.line_number >= 1
        ? finding.line_number
        : null;
  return candidate !== null ? Math.floor(candidate) : null;
}

/**
 * Computes a deterministic base identity for a finding independent of array order:
 * normalized type + normalized category + normalized message.
 * Line number is intentionally kept as supporting location metadata so simple line shifts
 * or array re-orderings preserve finding identity.
 */
export function computeFindingBaseSignature(
  type: unknown,
  concept: unknown,
  message: unknown
): string {
  return `${normalizeText(type) || 'unknownrule'}||${normalizeConcept(concept)}||${normalizeText(message)}`;
}

function indexEntryFindings(entry: NormalizedHistoryEntry): IndexedFinding[] {
  const combined: Array<{ raw: ReportFinding; severity: FindingSeverity }> = [
    ...(entry.errors || []).map((raw) => ({ raw, severity: 'error' as const })),
    ...(entry.warnings || []).map((raw) => ({ raw, severity: 'warning' as const })),
  ];

  // Canonical sort within identical base signatures by (line ?? MAX, severity) so array ordering never alters identity
  const prelim = combined.map(({ raw, severity }) => {
    const type = (raw.type || 'UnknownRule').trim() || 'UnknownRule';
    const concept = (raw.concept || '').trim();
    const message = (raw.message || '').trim() || 'No diagnostic message reported.';
    const line = normalizeLine(raw);
    const baseSignature = computeFindingBaseSignature(type, concept, message);
    return { baseSignature, severity, type, concept, message, line };
  });

  prelim.sort((a, b) => {
    const sigCmp = a.baseSignature.localeCompare(b.baseSignature);
    if (sigCmp !== 0) return sigCmp;
    const lineA = a.line ?? Number.MAX_SAFE_INTEGER;
    const lineB = b.line ?? Number.MAX_SAFE_INTEGER;
    if (lineA !== lineB) return lineA - lineB;
    return a.severity.localeCompare(b.severity);
  });

  const seenCount = new Map<string, number>();
  return prelim.map((item) => {
    const count = (seenCount.get(item.baseSignature) ?? 0) + 1;
    seenCount.set(item.baseSignature, count);
    return {
      ...item,
      occurrenceKey: `${item.baseSignature}#${count}`,
    };
  });
}

function buildGapKey(category: unknown, paramName: unknown): string {
  return `${normalizeText(category)}||${normalizeText(paramName)}`;
}

/**
 * Deterministically compares two immutable historical reports.
 */
export function compareHistoryReports(
  baseline: NormalizedHistoryEntry,
  target: NormalizedHistoryEntry
): ReportComparisonResult {
  const baselineIndexed = indexEntryFindings(baseline);
  const targetIndexed = indexEntryFindings(target);

  const baselineMap = new Map<string, IndexedFinding>();
  baselineIndexed.forEach((item) => baselineMap.set(item.occurrenceKey, item));

  const targetMap = new Map<string, IndexedFinding>();
  targetIndexed.forEach((item) => targetMap.set(item.occurrenceKey, item));

  const addedFindings: IndexedFinding[] = [];
  const resolvedFindings: IndexedFinding[] = [];
  const persistentFindings: PersistentFindingMatch[] = [];
  const severityChanges: PersistentFindingMatch[] = [];

  for (const baseItem of baselineIndexed) {
    const matched = targetMap.get(baseItem.occurrenceKey);
    if (!matched) {
      resolvedFindings.push(baseItem);
    } else {
      const severityChanged = baseItem.severity !== matched.severity;
      const matchRecord: PersistentFindingMatch = {
        occurrenceKey: baseItem.occurrenceKey,
        type: matched.type,
        concept: matched.concept || baseItem.concept,
        message: matched.message,
        previousSeverity: baseItem.severity,
        newSeverity: matched.severity,
        severityChanged,
        previousLine: baseItem.line,
        newLine: matched.line,
      };
      persistentFindings.push(matchRecord);
      if (severityChanged) {
        severityChanges.push(matchRecord);
      }
    }
  }

  for (const targetItem of targetIndexed) {
    if (!baselineMap.has(targetItem.occurrenceKey)) {
      addedFindings.push(targetItem);
    }
  }

  // Compare backend coverage_gaps if present on EdgeMind persisted reports
  const baseGaps = new Map<string, GapDiffItem>();
  for (const g of baseline.coverageGaps || []) {
    baseGaps.set(buildGapKey(g.category, g.param_name), {
      category: g.category,
      paramName: g.param_name ?? null,
      severity: g.severity,
      rationale: g.rationale,
    });
  }
  const targetGaps = new Map<string, GapDiffItem>();
  for (const g of target.coverageGaps || []) {
    targetGaps.set(buildGapKey(g.category, g.param_name), {
      category: g.category,
      paramName: g.param_name ?? null,
      severity: g.severity,
      rationale: g.rationale,
    });
  }

  const addedGaps: GapDiffItem[] = [];
  const resolvedGaps: GapDiffItem[] = [];
  let persistentGapsCount = 0;

  baseGaps.forEach((val, key) => {
    if (targetGaps.has(key)) {
      persistentGapsCount += 1;
    } else {
      resolvedGaps.push(val);
    }
  });
  targetGaps.forEach((val, key) => {
    if (!baseGaps.has(key)) {
      addedGaps.push(val);
    }
  });

  const previousScore = baseline.score;
  const newScore = target.score;
  const scoreDelta =
    previousScore !== null && newScore !== null ? newScore - previousScore : null;

  const baseName = (baseline.filename || baseline.title).trim().toLowerCase();
  const targetName = (target.filename || target.title).trim().toLowerCase();
  const differentFiles = Boolean(baseName && targetName && baseName !== targetName);

  const areIdentical =
    addedFindings.length === 0 &&
    resolvedFindings.length === 0 &&
    severityChanges.length === 0 &&
    addedGaps.length === 0 &&
    resolvedGaps.length === 0 &&
    (scoreDelta === null || scoreDelta === 0) &&
    baseline.status === target.status;

  return {
    baselineId: baseline.id,
    targetId: target.id,
    baselineTitle: baseline.title,
    targetTitle: target.title,
    differentFiles,
    previousScore,
    newScore,
    scoreDelta,
    addedFindings,
    resolvedFindings,
    persistentFindings,
    severityChanges,
    addedGaps,
    resolvedGaps,
    persistentGapsCount,
    areIdentical,
    matchingMethodology:
      'Findings are matched deterministically using normalized rule type, category, and message regardless of array ordering; line numbers serve as supporting metadata.',
  };
}
