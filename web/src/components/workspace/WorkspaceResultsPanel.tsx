import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Code2,
  Play,
  Terminal,
  WifiOff,
} from 'lucide-react';
import { AnalysisReport, ApiError, HealthStatus } from '../../types/api';
import { extractExplorerFindings } from '../../utils/findingsHelpers';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { Skeleton } from '../ui/Skeleton';
import { WorkspaceFindingItem } from './WorkspaceFindingItem';
import { cn } from '../../utils/cn';

type FindingFilter = 'all' | 'error' | 'warning';

export interface WorkspaceResultsPanelProps {
  report: AnalysisReport | null;
  durationMs: number | null;
  isAnalyzing: boolean;
  error: ApiError | null;
  healthStatus: HealthStatus;
  hasCode: boolean;
  isSupportedLanguage: boolean;
  hasUnanalyzedChanges: boolean;
  activeFindingKey: string | null;
  onSelectFinding: (key: string, line: number) => void;
  onInspectInFindings?: (findingId: string) => void;
  onRetryAnalyze: () => void;
  onInsertDefaultSample: () => void;
}

function getStatusVariant(status: string): 'success' | 'warning' | 'error' | 'neutral' {
  const upper = status.toUpperCase();
  if (upper === 'PASS') return 'success';
  if (upper.includes('WARNING')) return 'warning';
  if (upper === 'FAIL') return 'error';
  return 'neutral';
}

function getScoreBarColor(score: number): string {
  if (score >= 90) return 'bg-em-status-success';
  if (score >= 70) return 'bg-em-status-warning';
  return 'bg-em-status-error';
}

export const WorkspaceResultsPanel: React.FC<WorkspaceResultsPanelProps> = ({
  report,
  durationMs,
  isAnalyzing,
  error,
  healthStatus,
  hasCode,
  isSupportedLanguage,
  hasUnanalyzedChanges,
  activeFindingKey,
  onSelectFinding,
  onInspectInFindings,
  onRetryAnalyze,
  onInsertDefaultSample,
}) => {
  const [filter, setFilter] = useState<FindingFilter>('all');

  const combinedFindings = useMemo(() => {
    return extractExplorerFindings(report).map((item) => ({
      key: item.id,
      finding: item.raw,
      severity: item.severity,
    }));
  }, [report]);

  const filteredFindings = useMemo(() => {
    if (filter === 'all') return combinedFindings;
    return combinedFindings.filter((item) => item.severity === filter);
  }, [combinedFindings, filter]);

  const isBackendOffline = healthStatus === 'disconnected' || healthStatus === 'error';

  return (
    <section
      aria-labelledby="workspace-results-heading"
      className="flex flex-col h-full min-h-[360px] lg:h-[572px] rounded-md border border-em-border-default bg-em-surface-card overflow-hidden"
    >
      {/* Panel Header */}
      <div className="px-4 py-2.5 bg-em-surface-card border-b border-em-border-hairline flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-em-text-muted" />
          <h3
            id="workspace-results-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Analysis Results
          </h3>
        </div>
        {report && !isAnalyzing && (
          <div className="flex items-center gap-2">
            <Link
              to="/findings"
              className="inline-flex items-center gap-1 text-[11px] font-medium text-em-accent-primary hover:underline"
              title="Open Findings Explorer"
            >
              <span>Explorer</span>
              <ArrowUpRight className="w-3 h-3" aria-hidden="true" />
            </Link>
            {hasUnanalyzedChanges && <Badge variant="warning">Modified</Badge>}
            <Badge variant={getStatusVariant(report.overall_status)}>
              {report.overall_status}
            </Badge>
          </div>
        )}
      </div>

      {/* Scrollable Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Unsupported Language Notice */}
        {!isSupportedLanguage && (
          <div
            role="alert"
            className="p-3 rounded-md border border-em-status-warning/30 bg-em-status-warning/5 flex items-start gap-2.5"
          >
            <AlertTriangle className="w-4 h-4 text-em-status-warning shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-semibold text-em-text-primary">
                Unsupported Analysis Language
              </p>
              <p className="text-xs text-em-text-muted mt-0.5 leading-relaxed">
                The EdgeMind backend analyzer currently performs AST static analysis exclusively on Python source code. Select Python 3 to analyze.
              </p>
            </div>
          </div>
        )}

        {/* Backend Disconnected Notice */}
        {isBackendOffline && (
          <div
            role="alert"
            className="p-3 rounded-md border border-em-status-error/30 bg-em-status-error/5 flex items-start gap-2.5"
          >
            <WifiOff className="w-4 h-4 text-em-status-error shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-semibold text-em-text-primary">Backend Disconnected</p>
              <p className="text-xs text-em-text-muted mt-0.5 leading-relaxed">
                Cannot execute static analysis while EdgeMind API is unreachable. Ensure the FastAPI server is running on port 8000.
              </p>
            </div>
          </div>
        )}

        {/* Analyzing State */}
        {isAnalyzing && (
          <div className="space-y-3" aria-label="Analyzing code">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        )}

        {/* API Failure State */}
        {!isAnalyzing && error && (
          <ErrorState
            title="Analysis Request Failed"
            message={`${error.detail}${error.request_id ? ` (Request ID: ${error.request_id})` : ''}`}
            onRetry={isSupportedLanguage && !isBackendOffline ? onRetryAnalyze : undefined}
          />
        )}

        {/* Initial Empty Workspace */}
        {!isAnalyzing && !error && !report && !hasCode && (
          <EmptyState
            icon={Code2}
            title="Ready for Static Analysis"
            description="Write or paste Python source code in the editor, upload a .py file, or load a sample snippet to inspect findings."
            action={
              <Button variant="secondary" size="sm" onClick={onInsertDefaultSample}>
                Load Sample Snippet
              </Button>
            }
          />
        )}

        {/* Code Entered, Not Yet Analyzed */}
        {!isAnalyzing && !error && !report && hasCode && (
          <EmptyState
            icon={Play}
            title="Code Not Yet Analyzed"
            description="Run static analysis to inspect deterministic score, AST checks, and finding details."
            action={
              isSupportedLanguage && !isBackendOffline ? (
                <Button variant="primary" size="sm" onClick={onRetryAnalyze}>
                  Analyze Code
                </Button>
              ) : undefined
            }
          />
        )}

        {/* Verified Backend Analysis Report */}
        {!isAnalyzing && !error && report && (
          <>
            {/* Score & Summary Block */}
            <div className="p-3 rounded-md bg-em-surface-workspace border border-em-border-hairline space-y-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-mono uppercase text-em-text-dim">
                  Static Quality Score
                </span>
                <span className="text-sm font-semibold font-mono tabular-nums text-em-text-primary">
                  {report.score} / 100
                </span>
              </div>
              <div
                className="h-1.5 w-full rounded-full bg-white/[0.06] overflow-hidden"
                role="progressbar"
                aria-valuenow={report.score}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className={cn('h-full transition-all duration-200', getScoreBarColor(report.score))}
                  style={{ width: `${Math.max(0, Math.min(100, report.score))}%` }}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-[11px] font-mono tabular-nums text-em-text-muted">
                <span>
                  Errors: <strong className="text-em-status-error">{report.total_errors}</strong> ·
                  Warnings: <strong className="text-em-status-warning ml-1">{report.total_warnings}</strong>
                </span>
                {durationMs !== null && <span>{durationMs}ms</span>}
              </div>

              {/* Category Statuses directly from report.summary */}
              {report.summary && (
                <div className="flex flex-wrap gap-1.5 pt-2 border-t border-em-border-hairline">
                  {Object.entries(report.summary).map(([category, statusVal]) => (
                    <span
                      key={category}
                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-em-surface-card border border-em-border-hairline text-[10px] font-mono"
                    >
                      <span className="capitalize text-em-text-dim">{category}:</span>
                      <span
                        className={cn(
                          'font-medium',
                          statusVal === 'PASS'
                            ? 'text-em-status-success'
                            : statusVal === 'WARNING'
                              ? 'text-em-status-warning'
                              : statusVal === 'FAIL'
                                ? 'text-em-status-error'
                                : 'text-em-text-muted'
                        )}
                      >
                        {statusVal}
                      </span>
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Zero Findings Confirmed State */}
            {combinedFindings.length === 0 ? (
              <div className="p-6 rounded-md border border-em-status-success/25 bg-em-status-success/5 text-center flex flex-col items-center">
                <CheckCircle2 className="w-6 h-6 text-em-status-success mb-2" />
                <h4 className="text-xs font-semibold text-em-text-primary">
                  Zero Findings Detected
                </h4>
                <p className="text-xs text-em-text-muted mt-1 leading-relaxed">
                  All static checks passed cleanly for <code className="text-em-text-secondary">{report.file}</code>.
                </p>
              </div>
            ) : (
              /* Interactive Filter Tabs & Findings List */
              <div className="space-y-3">
                <div className="flex items-center gap-1.5 border-b border-em-border-hairline pb-2">
                  {(
                    [
                      { id: 'all', label: `All (${combinedFindings.length})` },
                      { id: 'error', label: `Errors (${report.total_errors})` },
                      { id: 'warning', label: `Warnings (${report.total_warnings})` },
                    ] as const
                  ).map((tab) => (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setFilter(tab.id)}
                      className={cn(
                        'px-2.5 py-1 rounded text-[11px] font-mono transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus',
                        filter === tab.id
                          ? 'bg-em-accent-primary/15 text-em-accent-primary font-semibold border border-em-accent-primary/30'
                          : 'text-em-text-muted hover:text-em-text-primary hover:bg-white/[0.04] border border-transparent'
                      )}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>

                <div className="space-y-2.5">
                  {filteredFindings.length === 0 ? (
                    <p className="text-xs text-em-text-muted text-center py-4">
                      No findings match the selected severity filter.
                    </p>
                  ) : (
                    filteredFindings.map((item) => (
                      <WorkspaceFindingItem
                        key={item.key}
                        finding={item.finding}
                        severity={item.severity}
                        isSelected={activeFindingKey === item.key}
                        onNavigateToLine={(line) => onSelectFinding(item.key, line)}
                        onOpenInFindings={
                          onInspectInFindings ? () => onInspectInFindings(item.key) : undefined
                        }
                      />
                    ))
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
};
