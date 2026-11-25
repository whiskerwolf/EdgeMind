import React from 'react';
import { Activity, Globe, PlugZap, RefreshCw } from 'lucide-react';
import { ConnectionProbeResult } from '../../context/SettingsContext';
import { HealthResponse, HealthStatus } from '../../types/api';
import { SETTINGS_LIMITS } from '../../utils/settingsConfig';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

export interface ConnectionSettingsSectionProps {
  apiBaseUrl: string;
  apiBaseUrlError?: string;
  healthPollingIntervalMs: number;
  healthStatus: HealthStatus;
  healthData: HealthResponse | null;
  healthLatencyMs: number | null;
  healthError: string | null;
  isProbing: boolean;
  probeResult: ConnectionProbeResult | null;
  onChangeUrl: (nextUrl: string) => void;
  onChangePolling: (ms: number) => void;
  onTestConnection: () => void;
  onRefreshGlobalHealth: () => void;
}

const SELECT_CLASS =
  'w-full h-9 px-2.5 rounded-md border border-em-border-default bg-em-workspace text-xs font-mono text-em-text-primary focus:outline-none focus:border-em-accent-primary focus:ring-1 focus:ring-em-accent-primary';

export const ConnectionSettingsSection: React.FC<ConnectionSettingsSectionProps> = ({
  apiBaseUrl,
  apiBaseUrlError,
  healthPollingIntervalMs,
  healthStatus,
  healthData,
  healthLatencyMs,
  healthError,
  isProbing,
  probeResult,
  onChangeUrl,
  onChangePolling,
  onTestConnection,
  onRefreshGlobalHealth,
}) => {
  const renderHealthBadge = () => {
    if (healthStatus === 'connected') {
      return (
        <Badge variant="success" size="sm">
          Online {healthLatencyMs !== null ? `(${healthLatencyMs}ms)` : ''}
        </Badge>
      );
    }
    if (healthStatus === 'connecting') {
      return (
        <Badge variant="info" size="sm">
          Checking...
        </Badge>
      );
    }
    if (healthStatus === 'error') {
      return (
        <Badge variant="error" size="sm">
          API Error
        </Badge>
      );
    }
    return (
      <Badge variant="neutral" size="sm">
        Disconnected
      </Badge>
    );
  };

  return (
    <section
      aria-labelledby="settings-connection-heading"
      className="rounded-lg border border-em-border-default bg-em-card p-4 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-em-border-hairline">
        <div className="flex items-center gap-2">
          <PlugZap className="w-4 h-4 text-em-accent-primary" />
          <h3
            id="settings-connection-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Connection &amp; Backend API
          </h3>
        </div>
        <div className="flex items-center gap-2">
          {renderHealthBadge()}
          <Badge variant="neutral" size="sm">
            Requires Save
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        <div className="lg:col-span-7 space-y-1.5">
          <label
            htmlFor="settings-api-base-url"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            EdgeMind API Base URL
          </label>
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Input
                id="settings-api-base-url"
                type="url"
                value={apiBaseUrl}
                onChange={(e) => onChangeUrl(e.target.value)}
                placeholder="http://127.0.0.1:8000"
                error={apiBaseUrlError}
                leftIcon={<Globe className="w-3.5 h-3.5" />}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="md"
              isLoading={isProbing}
              disabled={Boolean(apiBaseUrlError)}
              onClick={onTestConnection}
              className="shrink-0"
            >
              Test Connection
            </Button>
          </div>
          <p className="text-[11px] text-em-text-muted">
            Targets FastAPI REST &amp; SSE endpoints (<span className="font-mono">/health</span>,{' '}
            <span className="font-mono">/api/v1/*</span>). Click Save Settings to apply URL changes
            globally.
          </p>
        </div>

        <div className="lg:col-span-5 space-y-1.5">
          <label
            htmlFor="settings-polling-interval"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            Health Check Polling Interval
          </label>
          <div className="flex items-center gap-2">
            <select
              id="settings-polling-interval"
              value={healthPollingIntervalMs}
              onChange={(e) => onChangePolling(Number(e.target.value))}
              className={SELECT_CLASS}
            >
              {SETTINGS_LIMITS.healthPollingOptions.map((ms) => (
                <option key={ms} value={ms}>
                  Every {ms / 1000} seconds ({ms} ms)
                </option>
              ))}
            </select>
            <Button
              type="button"
              variant="outline"
              size="md"
              onClick={onRefreshGlobalHealth}
              leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
              title="Run immediate health check against saved endpoint"
              className="shrink-0"
            >
              Ping
            </Button>
          </div>
          <p className="text-[11px] text-em-text-muted">
            Active service:{' '}
            <span className="font-mono text-em-text-secondary">
              {healthData?.service || (healthError ? `Unreachable (${healthError})` : 'Checking...')}
            </span>
          </p>
        </div>
      </div>

      {probeResult && (
        <div
          role="status"
          className={
            probeResult.ok
              ? 'rounded-md border border-em-status-success/30 bg-em-status-success/10 p-3 text-xs text-em-status-success flex items-center gap-2 font-mono'
              : 'rounded-md border border-em-status-error/30 bg-em-status-error/10 p-3 text-xs text-em-status-error flex items-center gap-2 font-mono'
          }
        >
          <Activity className="w-4 h-4 shrink-0" />
          <span>
            {probeResult.ok
              ? `Connected to ${probeResult.url} (${probeResult.service || 'EdgeMind'} · ${probeResult.latencyMs}ms)`
              : `Connection probe failed for ${probeResult.url}: ${probeResult.errorDetail}`}
          </span>
        </div>
      )}
    </section>
  );
};
