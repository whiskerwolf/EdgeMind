import React, { useState } from 'react';
import { Clock, Lock, LogOut, Shield, Trash2 } from 'lucide-react';
import { HistorySortOption } from '../../utils/historyHelpers';
import {
  AppSettings,
  EDGEMIND_SETTINGS_STORAGE_KEY,
  SETTINGS_LIMITS,
  SettingsValidationErrors,
} from '../../utils/settingsConfig';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

export interface HistorySecuritySectionProps {
  draft: AppSettings;
  errors: SettingsValidationErrors;
  sessionRunCount: number;
  authSessionEmail: string | null;
  onChangeDraft: (partial: Partial<AppSettings>) => void;
  onClearSessionHistory: () => void;
  onLogoutBackend: () => void;
}

const SELECT_CLASS =
  'w-full h-9 px-2.5 rounded-md border border-em-border-default bg-em-workspace text-xs font-mono text-em-text-primary focus:outline-none focus:border-em-accent-primary focus:ring-1 focus:ring-em-accent-primary';

export const HistorySecuritySection: React.FC<HistorySecuritySectionProps> = ({
  draft,
  errors,
  sessionRunCount,
  authSessionEmail,
  onChangeDraft,
  onClearSessionHistory,
  onLogoutBackend,
}) => {
  const [confirmClearSession, setConfirmClearSession] = useState(false);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      {/* HISTORY PREFERENCES */}
      <section
        aria-labelledby="settings-history-heading"
        className="lg:col-span-6 rounded-lg border border-em-border-default bg-em-card p-4 space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-em-border-hairline">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-em-accent-primary" />
            <h3
              id="settings-history-heading"
              className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
            >
              History &amp; Retention
            </h3>
          </div>
          <Badge variant="neutral" size="sm">
            Requires Save
          </Badge>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <label
              htmlFor="settings-history-sort"
              className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
            >
              Default History Sort
            </label>
            <select
              id="settings-history-sort"
              value={draft.historyDefaultSort}
              onChange={(e) =>
                onChangeDraft({ historyDefaultSort: e.target.value as HistorySortOption })
              }
              className={SELECT_CLASS}
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
              <option value="score-desc">Highest Score</option>
              <option value="score-asc">Lowest Score</option>
            </select>
          </div>

          <div className="space-y-1.5">
            <label
              htmlFor="settings-history-page-size"
              className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
            >
              PostgreSQL Page Size
            </label>
            <select
              id="settings-history-page-size"
              value={draft.historyPageSize}
              onChange={(e) =>
                onChangeDraft({ historyPageSize: Number(e.target.value) as 10 | 20 | 50 })
              }
              className={SELECT_CLASS}
            >
              {SETTINGS_LIMITS.historyPageSizes.map((size) => (
                <option key={size} value={size}>
                  {size} reports per page
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="settings-session-history-limit"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            In-Memory Session Run Limit ({SETTINGS_LIMITS.minSessionHistoryLimit}-
            {SETTINGS_LIMITS.maxSessionHistoryLimit})
          </label>
          <Input
            id="settings-session-history-limit"
            type="number"
            min={SETTINGS_LIMITS.minSessionHistoryLimit}
            max={SETTINGS_LIMITS.maxSessionHistoryLimit}
            value={draft.sessionHistoryLimit}
            onChange={(e) => onChangeDraft({ sessionHistoryLimit: Number(e.target.value) })}
            error={errors.sessionHistoryLimit}
          />
          <p className="text-[11px] text-em-text-muted">
            Caps snapshot retention inside browser tab memory; PostgreSQL retention is managed
            per-report via delete actions (automatic database TTL pruning is not supported).
          </p>
        </div>

        <div className="rounded-md border border-em-border-default bg-em-workspace p-3 flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs">
            <span className="font-medium text-em-text-primary block">
              In-Memory Session Snapshots ({sessionRunCount} stored)
            </span>
            <span className="text-[11px] text-em-text-muted">
              Clears temporary tab history only; Workspace code and PostgreSQL records stay intact.
            </span>
          </div>

          {!confirmClearSession ? (
            <Button
              type="button"
              variant="danger"
              size="sm"
              disabled={sessionRunCount === 0}
              leftIcon={<Trash2 className="w-3.5 h-3.5" />}
              onClick={() => setConfirmClearSession(true)}
            >
              Clear Session Runs
            </Button>
          ) : (
            <div className="flex items-center gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setConfirmClearSession(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => {
                  onClearSessionHistory();
                  setConfirmClearSession(false);
                }}
              >
                Confirm Clear
              </Button>
            </div>
          )}
        </div>
      </section>

      {/* SECURITY & SESSION PRIVACY */}
      <section
        aria-labelledby="settings-security-heading"
        className="lg:col-span-6 rounded-lg border border-em-border-default bg-em-card p-4 space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-em-border-hairline">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-em-accent-primary" />
            <h3
              id="settings-security-heading"
              className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
            >
              Security &amp; Privacy Boundaries
            </h3>
          </div>
          <Badge variant="success" size="sm">
            <Lock className="w-3 h-3" />
            Zero Secrets Stored
          </Badge>
        </div>

        <div className="space-y-2.5 text-xs">
          <div className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-em-text-secondary">
                Backend Authentication Session
              </span>
              {authSessionEmail ? (
                <Badge variant="success" size="sm">
                  Active In-Memory JWT
                </Badge>
              ) : (
                <Badge variant="neutral" size="sm">
                  Not Signed In
                </Badge>
              )}
            </div>
            {authSessionEmail ? (
              <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                <span className="text-[11px] font-mono text-em-text-muted">
                  Signed in as <strong className="text-em-text-primary">{authSessionEmail}</strong>{' '}
                  (token redacted &amp; never stored to disk)
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  leftIcon={<LogOut className="w-3.5 h-3.5" />}
                  onClick={onLogoutBackend}
                >
                  Sign Out
                </Button>
              </div>
            ) : (
              <p className="text-[11px] text-em-text-muted">
                Database JWT tokens are held strictly in browser memory and never written to{' '}
                <span className="font-mono">localStorage</span> or{' '}
                <span className="font-mono">sessionStorage</span>.
              </p>
            )}
          </div>

          <div className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-1.5">
            <span className="font-semibold text-em-text-secondary block">
              Local Persistence Scope
            </span>
            <p className="text-[11px] text-em-text-muted leading-relaxed">
              Only non-sensitive UI, editor, polling, timeout, and base URL preferences are saved
              under <span className="font-mono text-em-text-secondary">{EDGEMIND_SETTINGS_STORAGE_KEY}</span>.
              URLs containing embedded credentials are rejected.
            </p>
          </div>

          <div className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-1.5">
            <span className="font-semibold text-em-text-secondary block">
              Execution &amp; Data Protection Guarantees
            </span>
            <ul className="list-disc list-inside space-y-1 text-[11px] text-em-text-muted">
              <li>Static AST analysis only (<span className="font-mono">static_only=true</span>)</li>
              <li>Source code omitted from PostgreSQL JSONB reports and JSON/CSV exports</li>
              <li>CSV exports neutralize spreadsheet formula prefixes (<span className="font-mono">= + - @</span>)</li>
              <li>AI streaming redacts credential patterns server- and client-side</li>
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
};
