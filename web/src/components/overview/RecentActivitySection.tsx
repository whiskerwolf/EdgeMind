import React from 'react';
import { Clock, Database, RefreshCw, ShieldAlert } from 'lucide-react';
import { OverviewHistoryState } from '../../hooks/useOverviewHistory';
import { SessionAnalysisRecord } from '../../types/api';
import { Badge } from '../ui/Badge';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { IconButton } from '../ui/IconButton';
import { Skeleton } from '../ui/Skeleton';

export interface RecentActivitySectionProps {
  history: OverviewHistoryState;
  sessionRuns: SessionAnalysisRecord[];
}

function getSessionStatusBadge(status: string): 'success' | 'warning' | 'error' | 'info' | 'neutral' {
  const upper = status.toUpperCase();
  if (upper === 'PASS' || upper === 'SUCCESS') return 'success';
  if (upper.includes('WARNING') || upper === 'INSUFFICIENT_CONTEXT') return 'warning';
  if (upper === 'FAIL' || upper === 'FAILED' || upper === 'ERROR') return 'error';
  return 'info';
}

export const RecentActivitySection: React.FC<RecentActivitySectionProps> = ({
  history,
  sessionRuns,
}) => {
  const { status, items, unavailableReason, message, error, refresh } = history;

  return (
    <section
      aria-labelledby="recent-activity-heading"
      className="rounded-lg border border-em-border-default bg-em-surface-card p-4"
    >
      <div className="flex items-center justify-between gap-2 pb-3 border-b border-em-border-hairline">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-em-text-muted shrink-0" />
          <h3
            id="recent-activity-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Recent Analysis Activity
          </h3>
        </div>

        <IconButton
          size="sm"
          variant="ghost"
          aria-label="Refresh persisted history"
          title="Refresh persisted history"
          onClick={refresh}
          disabled={status === 'disconnected' || status === 'loading'}
          isLoading={status === 'loading'}
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </IconButton>
      </div>

      {/* Loading State */}
      {status === 'loading' && (
        <div className="space-y-2 pt-3" aria-label="Loading recent analyses">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
        </div>
      )}

      {/* Backend Disconnected State */}
      {status === 'disconnected' && (
        <div className="py-5 px-3 text-center">
          <p className="text-xs font-semibold text-em-text-primary">Backend Disconnected</p>
          <p className="text-xs text-em-text-muted mt-1">
            {message || 'Cannot retrieve persisted history while the EdgeMind API is unreachable.'}
          </p>
        </div>
      )}

      {/* API Error State */}
      {status === 'error' && (
        <ErrorState
          title="Failed to Load History"
          message={
            error?.detail || message || 'An unexpected error occurred while querying analysis history.'
          }
          onRetry={refresh}
          className="my-3"
        />
      )}

      {/* Data Unavailable State (401 Auth Required or 503 Database Offline) */}
      {status === 'unavailable' && (
        <div className="mt-3 p-3 rounded-md border border-em-border-default bg-em-surface-workspace flex items-start gap-3">
          {unavailableReason === 'auth_required' ? (
            <ShieldAlert className="w-4 h-4 text-em-status-info shrink-0 mt-0.5" />
          ) : (
            <Database className="w-4 h-4 text-em-status-warning shrink-0 mt-0.5" />
          )}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-em-text-primary">
                Persisted History Unavailable
              </span>
              <Badge variant={unavailableReason === 'auth_required' ? 'info' : 'warning'}>
                {unavailableReason === 'auth_required'
                  ? 'Auth Required'
                  : unavailableReason === 'database_offline'
                    ? 'Database Offline'
                    : 'Unavailable'}
              </Badge>
            </div>
            <p className="text-xs text-em-text-muted mt-1 leading-relaxed">{message}</p>
          </div>
        </div>
      )}

      {/* Honest Empty State when DB + Auth returned [] */}
      {status === 'empty' && (
        <EmptyState
          icon={Clock}
          title="No Persisted Analyses Found"
          description="The backend database is connected and returned zero stored analysis sessions."
          className="my-3 py-5"
        />
      )}

      {/* Ready State: Verified Persisted Backend Sessions */}
      {status === 'ready' && items.length > 0 && (
        <div className="pt-3">
          {/* Desktop / Tablet Table */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-em-border-hairline text-[11px] font-mono uppercase text-em-text-dim">
                  <th className="py-2 pr-3 font-medium">Target</th>
                  <th className="py-2 px-3 font-medium">Mode</th>
                  <th className="py-2 px-3 font-medium">Status</th>
                  <th className="py-2 px-3 font-medium text-right">Gaps / Cands</th>
                  <th className="py-2 px-3 font-medium text-right">Duration</th>
                  <th className="py-2 pl-3 font-medium text-right">Recorded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-em-border-hairline text-xs">
                {items.map((item) => (
                  <tr key={item.id} className="hover:bg-em-surface-elevated/60 transition-colors">
                    <td className="py-2.5 pr-3 font-mono text-em-text-primary">
                      {item.problem_title || item.project_name || item.problem_slug || item.id.slice(0, 8)}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-em-text-muted">
                      {item.analysis_mode}
                    </td>
                    <td className="py-2.5 px-3">
                      <Badge variant={getSessionStatusBadge(item.analysis_status)}>
                        {item.analysis_status}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3 font-mono tabular-nums text-right text-em-text-secondary">
                      {item.gaps_detected} / {item.candidates_generated}
                    </td>
                    <td className="py-2.5 px-3 font-mono tabular-nums text-right text-em-text-muted">
                      {item.duration_ms.toFixed(1)}ms
                    </td>
                    <td className="py-2.5 pl-3 font-mono tabular-nums text-right text-em-text-dim">
                      {item.created_at ? new Date(item.created_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile Card Layout (375px / 430px) */}
          <div className="sm:hidden space-y-2">
            {items.map((item) => (
              <div
                key={item.id}
                className="p-3 rounded-md bg-em-surface-workspace border border-em-border-hairline space-y-1.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-mono font-medium text-em-text-primary truncate">
                    {item.problem_title || item.project_name || item.problem_slug || item.id.slice(0, 8)}
                  </span>
                  <Badge variant={getSessionStatusBadge(item.analysis_status)}>
                    {item.analysis_status}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-[11px] font-mono text-em-text-muted">
                  <span>{item.analysis_mode}</span>
                  <span className="tabular-nums">{item.duration_ms.toFixed(1)}ms</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Optional Current Browser Session Runs (Only when user ran static analysis in this browser session) */}
      {sessionRuns.length > 0 && (
        <div className="mt-4 pt-3 border-t border-em-border-hairline">
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-[11px] font-mono uppercase text-em-text-dim">
              Current Browser Session (In-Memory)
            </span>
            <span className="text-[11px] font-mono tabular-nums text-em-text-dim">
              {sessionRuns.length} run{sessionRuns.length === 1 ? '' : 's'}
            </span>
          </div>
          <div className="space-y-1.5">
            {sessionRuns.slice(0, 5).map((run) => (
              <div
                key={run.id}
                className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded bg-em-surface-workspace border border-em-border-hairline text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-mono text-em-text-primary truncate">{run.filename}</span>
                  <Badge variant={getSessionStatusBadge(run.overall_status)}>
                    {run.overall_status}
                  </Badge>
                </div>
                <div className="flex items-center gap-3 font-mono tabular-nums text-[11px] text-em-text-muted">
                  <span>Score: {run.score}</span>
                  <span>
                    E:{run.total_errors} W:{run.total_warnings}
                  </span>
                  <span>{run.durationMs}ms</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
