import React, { useState } from 'react';
import { AlertTriangle, Check, Copy, Layers, ShieldAlert } from 'lucide-react';
import { ApiError, EdgeMindAnalyzeResponse } from '../../types/api';
import { StaticTestingGap } from '../../utils/testIntelligenceHelpers';
import { Badge } from '../ui/Badge';
import { ErrorState } from '../ui/ErrorState';
import { Skeleton } from '../ui/Skeleton';

export interface TestingGapsPanelProps {
  backendReport: EdgeMindAnalyzeResponse | null;
  isLoading: boolean;
  error: ApiError | null;
  staticGaps: StaticTestingGap[];
  hasSuppliedTestFiles: boolean;
  onRetryAnalyze?: () => void;
}

function getSeverityBadgeVariant(sev: string): 'error' | 'warning' | 'neutral' {
  if (sev === 'HIGH') return 'error';
  if (sev === 'MEDIUM') return 'warning';
  return 'neutral';
}

export const TestingGapsPanel: React.FC<TestingGapsPanelProps> = ({
  backendReport,
  isLoading,
  error,
  staticGaps,
  hasSuppliedTestFiles,
  onRetryAnalyze,
}) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopyJson = async (id: string, inputData: Record<string, unknown>) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(inputData, null, 2));
      setCopiedId(id);
      setTimeout(() => setCopiedId((prev) => (prev === id ? null : prev)), 1500);
    } catch {
      // Clipboard unavailable in constrained browsers/tests
    }
  };

  const backendGaps = backendReport?.test_intelligence.coverage_gaps ?? [];
  const rankedCandidates = backendReport?.test_intelligence.ranked_candidates ?? [];

  return (
    <section
      aria-labelledby="testing-gaps-heading"
      className="flex flex-col rounded-lg border border-em-border-default bg-em-card overflow-hidden"
    >
      <div className="px-4 py-2.5 border-b border-em-border-hairline flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-em-accent-primary shrink-0" aria-hidden="true" />
          <h3
            id="testing-gaps-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Testing Gaps & Synthesized Candidates
          </h3>
        </div>
        {backendReport && (
          <Badge variant="info">
            {backendReport.analysis_mode === 'BASELINE_DRIVEN' ? 'Baseline-Driven' : 'Context-Based'}
          </Badge>
        )}
      </div>

      <div className="p-4 space-y-4 max-h-[540px] overflow-y-auto">
        {isLoading && (
          <div className="space-y-2.5" aria-label="Running EdgeMind adaptive test intelligence">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}

        {!isLoading && error && (
          <ErrorState
            title="Adaptive Test Intelligence Request Failed"
            message={`${error.detail}${error.request_id ? ` (Request ID: ${error.request_id})` : ''}`}
            onRetry={onRetryAnalyze}
            className="my-0"
          />
        )}

        {/* Section A: Backend Domain Partitions & Candidates */}
        {!isLoading && !error && backendReport && (
          <div className="space-y-3">
            {/* Parameter & Constraint Context Banner */}
            <div className="p-3 rounded-md border border-em-border-hairline bg-em-workspace space-y-1.5">
              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono">
                <span className="text-em-text-dim uppercase">Backend Analysis Context</span>
                <span className="text-em-text-secondary">
                  Constraints: {backendReport.parsed_constraints.status}
                </span>
              </div>

              {backendReport.identified_parameters.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-0.5">
                  {backendReport.identified_parameters.map((param) => (
                    <Badge key={param.name} variant={param.is_ambiguous ? 'warning' : 'neutral'}>
                      {param.name}: {param.param_type} ({param.structure})
                    </Badge>
                  ))}
                </div>
              )}

              {backendReport.warnings.map((w, idx) => (
                <p key={idx} className="text-[11px] text-em-status-warning leading-relaxed pt-1">
                  {w}
                </p>
              ))}
            </div>

            {/* Black-box Domain Coverage Gaps */}
            {backendGaps.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-[11px] font-mono uppercase tracking-wider text-em-text-dim">
                  Input-Domain Coverage Gaps ({backendGaps.length})
                </h4>
                {backendGaps.map((gap, idx) => (
                  <article
                    key={`${gap.category}-${gap.param_name || 'all'}-${idx}`}
                    className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-1.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={getSeverityBadgeVariant(gap.severity)}>{gap.severity}</Badge>
                        <span className="text-xs font-mono font-semibold text-em-text-primary">
                          {gap.category}
                        </span>
                        {gap.param_name && <Badge variant="neutral">{gap.param_name}</Badge>}
                      </div>
                      <Badge variant="neutral">{gap.constraint_validity}</Badge>
                    </div>
                    <p className="text-xs text-em-text-secondary leading-relaxed">{gap.rationale}</p>
                    {gap.risk_explained && (
                      <p className="text-[11px] text-em-text-muted leading-relaxed">
                        Risk: {gap.risk_explained}
                      </p>
                    )}
                  </article>
                ))}
              </div>
            )}

            {/* Synthesized Candidates */}
            {rankedCandidates.length > 0 && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-[11px] font-mono uppercase tracking-wider text-em-text-dim">
                    Synthesized Candidates ({rankedCandidates.length})
                  </h4>
                  <span className="text-[10px] font-mono text-em-text-dim">
                    GENERATED_TEST · expected_output: null
                  </span>
                </div>
                {rankedCandidates.map((item) => {
                  const cand = item.candidate;
                  return (
                    <article
                      key={cand.id || `cand-${item.rank}`}
                      className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-2"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant="info">Rank #{item.rank}</Badge>
                          <Badge variant="neutral">{cand.classification}</Badge>
                          {cand.target_gap && <Badge variant="warning">{cand.target_gap}</Badge>}
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            void handleCopyJson(cand.id, cand.input_data);
                          }}
                          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-mono text-em-text-muted hover:text-em-text-primary hover:bg-white/[0.04] border border-em-border-hairline transition-colors"
                        >
                          {copiedId === cand.id ? (
                            <>
                              <Check className="w-3 h-3 text-em-status-success" />
                              <span>Copied</span>
                            </>
                          ) : (
                            <>
                              <Copy className="w-3 h-3" />
                              <span>Copy Input</span>
                            </>
                          )}
                        </button>
                      </div>

                      <pre className="p-2 rounded bg-em-canvas border border-em-border-hairline text-[11px] font-mono text-em-text-primary overflow-x-auto">
                        {JSON.stringify(cand.input_data)}
                      </pre>
                      <p className="text-[11px] text-em-text-secondary leading-relaxed">
                        {cand.rationale}
                      </p>
                      <p className="text-[10px] font-mono text-em-text-dim">
                        Expected Output: null (Unverified; static-only mode)
                      </p>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Section B: Deterministic Static Function / File Gaps */}
        <div className="space-y-2 pt-1 border-t border-em-border-hairline">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-[11px] font-mono uppercase tracking-wider text-em-text-dim">
              Static Reference Gap Heuristics
            </h4>
            <Badge variant="neutral">Heuristic Inference</Badge>
          </div>

          {!hasSuppliedTestFiles ? (
            <p className="text-xs text-em-text-muted leading-relaxed">
              No Python test files supplied yet. Source files cannot be evaluated for missing static test references without supplied test files.
            </p>
          ) : staticGaps.length === 0 ? (
            <p className="text-xs text-em-status-success leading-relaxed">
              All parsed functions in loaded Python source modules have at least one static call or import reference in the supplied test files.
            </p>
          ) : (
            <div className="space-y-2">
              {staticGaps.map((gap) => (
                <article
                  key={gap.id}
                  className="rounded-md border border-em-status-warning/30 bg-em-status-warning/5 p-3 space-y-1"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <AlertTriangle className="w-3.5 h-3.5 text-em-status-warning shrink-0" aria-hidden="true" />
                      <span className="text-xs font-mono font-semibold text-em-text-primary truncate">
                        {gap.name}
                      </span>
                    </div>
                    <Badge variant="warning">
                      {gap.scope === 'unmapped-test'
                        ? 'Unmapped Test'
                        : gap.scope === 'file'
                          ? 'Unmapped File'
                          : 'No Static Call Ref'}
                    </Badge>
                  </div>
                  <p className="text-xs text-em-text-secondary leading-relaxed">{gap.evidence}</p>
                  <p className="text-[10px] text-em-text-muted flex items-start gap-1">
                    <ShieldAlert className="w-3 h-3 shrink-0 mt-0.5 text-em-text-dim" aria-hidden="true" />
                    <span>{gap.caveat}</span>
                  </p>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
};
