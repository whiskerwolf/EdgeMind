import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  GitCompare,
  Info,
  MinusCircle,
  PlusCircle,
} from 'lucide-react';
import { cn } from '../../utils/cn';
import { NormalizedHistoryEntry } from '../../utils/historyHelpers';
import { compareHistoryReports } from '../../utils/reportComparison';
import { Badge } from '../ui/Badge';
import { ComparisonSelector } from './ComparisonSelector';

export interface ReportComparisonProps {
  entries: NormalizedHistoryEntry[];
  baselineId: string | null;
  targetId: string | null;
  onChangeBaseline: (id: string) => void;
  onChangeTarget: (id: string) => void;
  onSwap: () => void;
  onClose: () => void;
}

export const ReportComparison: React.FC<ReportComparisonProps> = ({
  entries,
  baselineId,
  targetId,
  onChangeBaseline,
  onChangeTarget,
  onSwap,
  onClose,
}) => {
  const [diffTab, setDiffTab] = useState<'added' | 'resolved' | 'persistent' | 'gaps'>('added');

  const baseline = useMemo(
    () => entries.find((item) => item.id === baselineId) ?? null,
    [entries, baselineId]
  );
  const target = useMemo(
    () => entries.find((item) => item.id === targetId) ?? null,
    [entries, targetId]
  );

  const comparison = useMemo(() => {
    if (!baseline || !target) return null;
    return compareHistoryReports(baseline, target);
  }, [baseline, target]);

  const formatDelta = (delta: number | null): string => {
    if (delta === null) return 'Unavailable';
    if (delta > 0) return `+${delta}`;
    return String(delta);
  };

  return (
    <section
      aria-label="Run comparison"
      className="rounded-lg border border-em-border-strong bg-em-card p-4 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-em-border-hairline">
        <div className="flex items-center gap-2">
          <GitCompare className="w-4 h-4 text-em-accent-primary" />
          <h3 className="text-sm font-semibold text-em-text-primary">
            Compare Historical Snapshots
          </h3>
        </div>
        <span className="text-[11px] font-mono text-em-text-dim">
          Deterministic non-index matching (type + concept + message)
        </span>
      </div>

      <ComparisonSelector
        entries={entries}
        baselineId={baselineId}
        targetId={targetId}
        onChangeBaseline={onChangeBaseline}
        onChangeTarget={onChangeTarget}
        onSwap={onSwap}
        onClose={onClose}
      />

      {!comparison ? (
        <div className="rounded-md border border-em-border-default bg-em-workspace p-4 text-xs text-em-text-muted">
          Select both a Baseline Run (A) and a Target Run (B) to view score deltas and finding
          changes.
        </div>
      ) : (
        <div className="space-y-4">
          {baselineId === targetId && (
            <div className="rounded-md border border-em-status-info/30 bg-em-status-info/10 p-2.5 text-xs text-em-status-info flex items-center gap-2">
              <Info className="w-4 h-4 shrink-0" />
              <span>Comparing the exact same snapshot against itself (delta is zero).</span>
            </div>
          )}

          {comparison.differentFiles && (
            <div className="rounded-md border border-em-status-warning/30 bg-em-status-warning/10 p-2.5 text-xs text-em-status-warning flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              <span>
                Target mismatch notice: comparing <strong>{comparison.baselineTitle}</strong>{' '}
                against <strong>{comparison.targetTitle}</strong>. Finding deltas may reflect
                different files or problems.
              </span>
            </div>
          )}

          {/* Top Diff Summary Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-2.5">
            <div className="rounded-md border border-em-border-default bg-em-workspace p-3">
              <div className="text-[10px] font-mono uppercase text-em-text-dim">Score Change</div>
              <div className="mt-1 flex items-center gap-1.5 text-sm font-mono font-semibold text-em-text-primary">
                <span>{comparison.previousScore ?? 'N/A'}</span>
                <ArrowRight className="w-3.5 h-3.5 text-em-text-dim" />
                <span>{comparison.newScore ?? 'N/A'}</span>
              </div>
              <div
                className={cn(
                  'text-[11px] font-mono mt-0.5',
                  comparison.scoreDelta === null
                    ? 'text-em-text-dim'
                    : comparison.scoreDelta > 0
                      ? 'text-em-status-success'
                      : comparison.scoreDelta < 0
                        ? 'text-em-status-error'
                        : 'text-em-text-muted'
                )}
              >
                Delta: {formatDelta(comparison.scoreDelta)}
              </div>
            </div>

            <div className="rounded-md border border-em-border-default bg-em-workspace p-3">
              <div className="text-[10px] font-mono uppercase text-em-text-dim">Added Findings</div>
              <div className="text-lg font-mono font-semibold text-em-status-error mt-0.5">
                +{comparison.addedFindings.length}
              </div>
            </div>

            <div className="rounded-md border border-em-border-default bg-em-workspace p-3">
              <div className="text-[10px] font-mono uppercase text-em-text-dim">
                Resolved Findings
              </div>
              <div className="text-lg font-mono font-semibold text-em-status-success mt-0.5">
                -{comparison.resolvedFindings.length}
              </div>
            </div>

            <div className="rounded-md border border-em-border-default bg-em-workspace p-3">
              <div className="text-[10px] font-mono uppercase text-em-text-dim">
                Persistent Findings
              </div>
              <div className="text-lg font-mono font-semibold text-em-text-primary mt-0.5">
                {comparison.persistentFindings.length}
              </div>
            </div>

            <div className="rounded-md border border-em-border-default bg-em-workspace p-3">
              <div className="text-[10px] font-mono uppercase text-em-text-dim">
                Severity Shifts
              </div>
              <div className="text-lg font-mono font-semibold text-em-status-warning mt-0.5">
                {comparison.severityChanges.length}
              </div>
            </div>
          </div>

          {comparison.areIdentical && (
            <div className="rounded-md border border-em-status-success/30 bg-em-status-success/10 p-3 text-xs text-em-status-success flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>
                No finding, score, or coverage gap changes detected between Baseline (A) and Target
                (B).
              </span>
            </div>
          )}

          {/* Diff Tabs */}
          <div
            role="tablist"
            aria-label="Comparison details"
            className="flex flex-wrap items-center gap-1 border-b border-em-border-hairline pb-2"
          >
            {[
              { id: 'added' as const, label: `Added (${comparison.addedFindings.length})` },
              { id: 'resolved' as const, label: `Resolved (${comparison.resolvedFindings.length})` },
              {
                id: 'persistent' as const,
                label: `Persistent (${comparison.persistentFindings.length})`,
              },
              {
                id: 'gaps' as const,
                label: `Coverage Gaps Diff (${comparison.addedGaps.length + comparison.resolvedGaps.length})`,
              },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={diffTab === tab.id}
                onClick={() => setDiffTab(tab.id)}
                className={cn(
                  'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                  diffTab === tab.id
                    ? 'bg-em-accent-subtle text-em-accent-primary border border-em-accent-primary/30'
                    : 'text-em-text-muted hover:text-em-text-primary hover:bg-white/[0.04]'
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Diff Panel Content */}
          {diffTab === 'added' && (
            <div className="space-y-2" role="tabpanel">
              {comparison.addedFindings.length === 0 ? (
                <p className="text-xs text-em-text-muted">No new findings introduced in Target B.</p>
              ) : (
                comparison.addedFindings.map((item) => (
                  <div
                    key={`add-${item.occurrenceKey}`}
                    className="rounded-md border border-em-border-default bg-em-workspace p-3 text-xs space-y-1"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <PlusCircle className="w-3.5 h-3.5 text-em-status-error shrink-0" />
                      <Badge variant={item.severity === 'error' ? 'error' : 'warning'} size="sm">
                        {item.severity}
                      </Badge>
                      <span className="font-mono font-semibold text-em-text-primary">
                        {item.type}
                      </span>
                      <span className="font-mono text-em-text-dim">
                        {item.line ? `Line ${item.line}` : 'File-level'}
                      </span>
                    </div>
                    <p className="text-em-text-secondary">{item.message}</p>
                  </div>
                ))
              )}
            </div>
          )}

          {diffTab === 'resolved' && (
            <div className="space-y-2" role="tabpanel">
              {comparison.resolvedFindings.length === 0 ? (
                <p className="text-xs text-em-text-muted">No findings resolved in Target B.</p>
              ) : (
                comparison.resolvedFindings.map((item) => (
                  <div
                    key={`res-${item.occurrenceKey}`}
                    className="rounded-md border border-em-border-default bg-em-workspace p-3 text-xs space-y-1"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <MinusCircle className="w-3.5 h-3.5 text-em-status-success shrink-0" />
                      <Badge variant="success" size="sm">
                        resolved ({item.severity})
                      </Badge>
                      <span className="font-mono font-semibold text-em-text-primary">
                        {item.type}
                      </span>
                      <span className="font-mono text-em-text-dim">
                        {item.line ? `Line ${item.line}` : 'File-level'}
                      </span>
                    </div>
                    <p className="text-em-text-secondary">{item.message}</p>
                  </div>
                ))
              )}
            </div>
          )}

          {diffTab === 'persistent' && (
            <div className="space-y-2" role="tabpanel">
              {comparison.persistentFindings.length === 0 ? (
                <p className="text-xs text-em-text-muted">
                  No persistent findings shared between runs.
                </p>
              ) : (
                comparison.persistentFindings.map((item) => (
                  <div
                    key={`pers-${item.occurrenceKey}`}
                    className="rounded-md border border-em-border-default bg-em-workspace p-3 text-xs space-y-1"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="neutral" size="sm">
                        persistent
                      </Badge>
                      {item.severityChanged ? (
                        <Badge variant="warning" size="sm">
                          {item.previousSeverity} -&gt; {item.newSeverity}
                        </Badge>
                      ) : (
                        <Badge
                          variant={item.newSeverity === 'error' ? 'error' : 'warning'}
                          size="sm"
                        >
                          {item.newSeverity}
                        </Badge>
                      )}
                      <span className="font-mono font-semibold text-em-text-primary">
                        {item.type}
                      </span>
                      <span className="font-mono text-em-text-dim">
                        {item.previousLine !== item.newLine
                          ? `Line ${item.previousLine ?? '?'} -> ${item.newLine ?? '?'}`
                          : item.newLine
                            ? `Line ${item.newLine}`
                            : 'File-level'}
                      </span>
                    </div>
                    <p className="text-em-text-secondary">{item.message}</p>
                  </div>
                ))
              )}
            </div>
          )}

          {diffTab === 'gaps' && (
            <div className="space-y-2 text-xs" role="tabpanel">
              {comparison.addedGaps.length === 0 && comparison.resolvedGaps.length === 0 ? (
                <p className="text-em-text-muted">
                  No coverage gap differences ({comparison.persistentGapsCount} persistent).
                </p>
              ) : (
                <>
                  {comparison.addedGaps.map((g, i) => (
                    <div
                      key={`ag-${i}`}
                      className="rounded-md border border-em-border-default bg-em-workspace p-2.5"
                    >
                      <Badge variant="error" size="sm">
                        + Added Gap
                      </Badge>{' '}
                      <span className="font-mono font-semibold text-em-text-primary">
                        {g.category}
                      </span>
                      {g.paramName && (
                        <span className="font-mono text-em-text-dim"> ({g.paramName})</span>
                      )}
                      <p className="text-em-text-muted mt-1">{g.rationale}</p>
                    </div>
                  ))}
                  {comparison.resolvedGaps.map((g, i) => (
                    <div
                      key={`rg-${i}`}
                      className="rounded-md border border-em-border-default bg-em-workspace p-2.5"
                    >
                      <Badge variant="success" size="sm">
                        - Resolved Gap
                      </Badge>{' '}
                      <span className="font-mono font-semibold text-em-text-primary">
                        {g.category}
                      </span>
                      {g.paramName && (
                        <span className="font-mono text-em-text-dim"> ({g.paramName})</span>
                      )}
                      <p className="text-em-text-muted mt-1">{g.rationale}</p>
                    </div>
                  ))}
                </>
              )}
            </div>
          )}

          <p className="text-[11px] font-mono text-em-text-dim pt-2 border-t border-em-border-hairline">
            {comparison.matchingMethodology}
          </p>
        </div>
      )}
    </section>
  );
};
