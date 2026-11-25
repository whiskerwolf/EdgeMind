import React from 'react';
import { RefreshCw, Server, WifiOff, AlertTriangle } from 'lucide-react';
import { HealthState } from '../../types/api';
import { UnavailableReason } from '../../hooks/useOverviewHistory';
import { Badge } from '../ui/Badge';
import { IconButton } from '../ui/IconButton';
import { Skeleton } from '../ui/Skeleton';
import { StatusIndicator } from '../ui/StatusIndicator';
import { Button } from '../ui/Button';

export interface SystemStatusSectionProps {
  health: HealthState;
  baseUrl: string;
  unavailableReason: UnavailableReason;
  onRefresh: () => void;
}

export const SystemStatusSection: React.FC<SystemStatusSectionProps> = ({
  health,
  baseUrl,
  unavailableReason,
  onRefresh,
}) => {
  const { status, data, error, durationMs, lastChecked } = health;

  const isConnecting = status === 'connecting' && !data && !error;
  const isDisconnected = status === 'disconnected';
  const isError = status === 'error';
  const isConnected = status === 'connected';

  const databaseLabel = data?.database
    ? data.database
    : unavailableReason === 'database_offline'
      ? 'Offline / Unconfigured'
      : 'Not reported by /health';

  return (
    <section
      aria-labelledby="system-status-heading"
      className="rounded-lg border border-em-border-default bg-em-surface-card p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-em-border-hairline">
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 text-em-text-muted shrink-0" />
          <h3 id="system-status-heading" className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary">
            System Status
          </h3>
        </div>

        <div className="flex items-center gap-2">
          <StatusIndicator status={status} />
          <IconButton
            size="sm"
            variant="ghost"
            aria-label="Refresh backend status"
            title="Refresh backend status"
            onClick={onRefresh}
            isLoading={status === 'connecting'}
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </IconButton>
        </div>
      </div>

      {isConnecting ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-3" aria-label="Loading system status">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : (
        <>
          {(isDisconnected || isError) && (
            <div
              role="alert"
              className="mt-3 p-3 rounded-md border border-em-status-error/30 bg-em-status-error/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
            >
              <div className="flex items-start gap-2.5 min-w-0">
                {isDisconnected ? (
                  <WifiOff className="w-4 h-4 text-em-status-error shrink-0 mt-0.5" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-em-status-error shrink-0 mt-0.5" />
                )}
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-em-text-primary">
                    {isDisconnected ? 'Backend Disconnected' : 'Backend Health Error'}
                  </p>
                  <p className="text-xs text-em-text-muted font-mono break-words mt-0.5">
                    {error || `Unable to reach ${baseUrl}/health`}
                  </p>
                </div>
              </div>
              <Button variant="outline" size="sm" onClick={onRefresh} className="shrink-0 self-start sm:self-center">
                Retry Check
              </Button>
            </div>
          )}

          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 pt-3">
            <div className="p-2.5 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <dt className="text-[11px] font-mono uppercase text-em-text-dim">Service</dt>
              <dd className="mt-1 flex items-center gap-2 text-xs font-mono text-em-text-primary">
                <span>{isConnected && data?.service ? data.service : 'Unavailable'}</span>
                {isConnected && data?.status && <Badge variant="success">{data.status}</Badge>}
              </dd>
            </div>

            <div className="p-2.5 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <dt className="text-[11px] font-mono uppercase text-em-text-dim">API Endpoint</dt>
              <dd className="mt-1 text-xs font-mono text-em-text-secondary truncate" title={baseUrl}>
                {baseUrl}
              </dd>
            </div>

            <div className="p-2.5 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <dt className="text-[11px] font-mono uppercase text-em-text-dim">Response Latency</dt>
              <dd className="mt-1 text-xs font-mono tabular-nums text-em-text-primary">
                {isConnected && durationMs !== null ? `${durationMs}ms` : '—'}
              </dd>
            </div>

            <div className="p-2.5 rounded-md bg-em-surface-workspace border border-em-border-hairline">
              <dt className="text-[11px] font-mono uppercase text-em-text-dim">Persistence / Checked</dt>
              <dd className="mt-1 text-xs font-mono text-em-text-secondary truncate" title={databaseLabel}>
                {isConnected ? databaseLabel : '—'}
                {lastChecked && (
                  <span className="block text-[10px] text-em-text-dim mt-0.5">
                    Checked {lastChecked.toLocaleTimeString()}
                  </span>
                )}
              </dd>
            </div>
          </dl>
        </>
      )}
    </section>
  );
};
