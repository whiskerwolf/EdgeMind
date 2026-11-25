import React from 'react';
import { Link } from 'react-router-dom';
import { Activity, ArrowRight, FileCode2, Play } from 'lucide-react';
import { AnalysisReport, ApiError, HealthStatus } from '../../types/api';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { ErrorState } from '../ui/ErrorState';
import { Skeleton } from '../ui/Skeleton';

export interface AnalysisOverviewSectionProps {
  report: AnalysisReport | null;
  durationMs: number | null;
  healthStatus: HealthStatus;
  isAnalyzing: boolean;
  error: ApiError | null;
  onRunSampleAnalysis: () => void;
  onClearError: () => void;
}

function getStatusBadgeVariant(status: string): 'success' | 'warning' | 'error' | 'neutral' {
  const upper = status.toUpperCase();
  if (upper === 'PASS') return 'success';
  if (upper === 'PASS WITH WARNINGS' || upper === 'WARNING') return 'warning';
  if (upper === 'FAIL') return 'error';
  return 'neutral';
}

function getScoreBarColor(score: number): string {
  if (score >= 90) return 'bg-em-status-success';
  if (score >= 70) return 'bg-em-status-warning';
  return 'bg-em-status-error';
}

export const AnalysisOverviewSection: React.FC<AnalysisOverviewSectionProps> = ({
  report,
  durationMs,
  healthStatus,
  isAnalyzing,
  error,
  onRunSampleAnalysis,
  onClearError,
}) => {
  const backendOffline = healthStatus === 'disconnected' || healthStatus === 'error';

  return (
    <section
      aria-labelledby="analysis-overview-heading"
      className="rounded-lg border border-em-border-default bg-em-surface-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-em-border-hairline">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-em-accent-primary shrink-0" />
          <h3
            id="analysis-overview-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Latest Static Analysis
          </h3>
        </div>

        {report && (
          <div className="flex items-center gap-2">
            <Badge variant={getStatusBadgeVariant(report.overall_status)}>
              {report.overall_status}
            </Badge>
          </div>
        )}
      </div>

      {isAnalyzing && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-4" aria-label="Running static analysis">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      )}

      {!isAnalyzing && error && (
        <ErrorState
          title="Static Analysis Failed"
          message={`${error.detail}${error.request_id ? ` (Request ID: ${error.request_id})` : ''}`}
          onRetry={onClearError}
          className="my-3"
        />
      )}

      {!isAnalyzing && !error && !report && (
        <div className="py-6 px-4 text-center flex flex-col items-center">
          <div className="w-10 h-10 rounded-full bg-white/[0.04] border border-white/[0.08] flex items-center justify-center mb-3">
            <FileCode2 className="w-5 h-5 text-em-text-muted" />
          </div>
          <h4 className="text-sm font-semibold text-em-text-primary mb-1">
            No Analysis Performed Yet
          </h4>
          <p className="text-xs text-em-text-muted max-w-md mb-4 leading-relaxed">
            {backendOffline
              ? 'Reconnect to the EdgeMind backend to run deterministic AST analysis on Python source code.'
              : 'Run your first static code analysis to inspect quality score, rule category checks, and finding severity metrics.'}
          </p>
          <div className="flex flex-wrap items-center justify-center gap-2.5">
            <Link to="/workspace">
              <Button variant="primary" size="sm" rightIcon={<ArrowRight className="w-3.5 h-3.5" />}>
                Open Workspace
              </Button>
            </Link>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Play className="w-3.5 h-3.5" />}
              onClick={onRunSampleAnalysis}
              disabled={backendOffline}
              title={
                backendOffline
                  ? 'Backend must be connected to run analysis'
                  : 'Execute real POST /api/v1/analyze on sample Python snippet'
              }
            >
              Run Sample Verification
            </Button>
          </div>
        </div>
      )}

      {!isAnalyzing && !error && report && (
        <div className="pt-3 space-y-3">
          {/* 4-Metric Precision Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="p-3 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <div className="flex items-center justify-between text-[11px] font-mono uppercase text-em-text-dim">
                <span>Code Score</span>
                <span className="tabular-nums text-em-text-primary font-semibold">
                  {report.score} / 100
                </span>
              </div>
              <div
                className="mt-2 h-1.5 w-full rounded-full bg-white/[0.06] overflow-hidden"
                role="progressbar"
                aria-valuenow={report.score}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Static analysis code score"
              >
                <div
                  className={`h-full transition-all duration-200 ${getScoreBarColor(report.score)}`}
                  style={{ width: `${Math.max(0, Math.min(100, report.score))}%` }}
                />
              </div>
              <p className="mt-2 text-[11px] font-mono text-em-text-muted truncate">
                Status: {report.overall_status}
              </p>
            </div>

            <div className="p-3 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <div className="text-[11px] font-mono uppercase text-em-text-dim">Analyzed Target</div>
              <div className="mt-1.5 text-xs font-mono text-em-text-primary truncate" title={report.file}>
                {report.file}
              </div>
              <div className="mt-1.5 text-[11px] font-mono tabular-nums text-em-text-muted">
                {durationMs !== null ? `Completed in ${durationMs}ms` : 'Static AST only'}
              </div>
            </div>

            <div className="p-3 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <div className="text-[11px] font-mono uppercase text-em-text-dim">Critical Errors</div>
              <div className="mt-1 text-xl font-semibold font-mono tabular-nums text-em-text-primary">
                {report.total_errors}
              </div>
              <div className="mt-1 text-[11px] font-mono text-em-text-muted">
                {report.total_errors === 0 ? 'No syntax or runtime errors' : `Score impact: -${report.total_errors * 20} pts`}
              </div>
            </div>

            <div className="p-3 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <div className="text-[11px] font-mono uppercase text-em-text-dim">Quality Warnings</div>
              <div className="mt-1 text-xl font-semibold font-mono tabular-nums text-em-text-primary">
                {report.total_warnings}
              </div>
              <div className="mt-1 text-[11px] font-mono text-em-text-muted">
                {report.total_warnings === 0 ? 'No quality or complexity smells' : `Score impact: -${report.total_warnings * 5} pts`}
              </div>
            </div>
          </div>

          {/* Deterministic Category Check Breakdown */}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-em-border-hairline">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-mono uppercase text-em-text-dim mr-1">Checks:</span>
              {Object.entries(report.summary || {}).map(([category, checkStatus]) => (
                <div
                  key={category}
                  className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-em-surface-workspace border border-em-border-hairline text-[11px] font-mono"
                >
                  <span className="capitalize text-em-text-muted">{category}:</span>
                  <Badge variant={getStatusBadgeVariant(checkStatus)}>{checkStatus}</Badge>
                </div>
              ))}
            </div>
            <Link to="/findings" className="text-xs font-medium text-em-accent-primary hover:underline">
              Inspect Findings
            </Link>
          </div>
        </div>
      )}
    </section>
  );
};
