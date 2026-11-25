import React from 'react';
import { Link } from 'react-router-dom';
import {
  Code2,
  Database,
  GitCompare,
  History,
  KeyRound,
  LogOut,
  RefreshCw,
  ShieldAlert,
} from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export type HistoryBackendStatus =
  | 'loading'
  | 'ready'
  | 'unavailable'
  | 'disconnected'
  | 'error';

export interface HistoryHeaderProps {
  totalShown: number;
  totalRecords: number;
  dbStatus: HistoryBackendStatus;
  unavailableReason: 'auth_required' | 'database_offline' | null;
  authSessionEmail: string | null;
  isAuthDrawerOpen: boolean;
  onToggleAuthDrawer: () => void;
  onLogout: () => void;
  onRefresh: () => void;
  isRefreshing: boolean;
  isCompareMode: boolean;
  onToggleCompareMode: () => void;
  canCompare: boolean;
}

export const HistoryHeader: React.FC<HistoryHeaderProps> = ({
  totalShown,
  totalRecords,
  dbStatus,
  unavailableReason,
  authSessionEmail,
  isAuthDrawerOpen,
  onToggleAuthDrawer,
  onLogout,
  onRefresh,
  isRefreshing,
  isCompareMode,
  onToggleCompareMode,
  canCompare,
}) => {
  const renderBackendBadge = () => {
    if (dbStatus === 'ready') {
      return (
        <Badge variant="success" size="sm">
          <Database className="w-3 h-3" />
          PostgreSQL Synced
        </Badge>
      );
    }
    if (dbStatus === 'unavailable' && unavailableReason === 'auth_required') {
      return (
        <Badge variant="info" size="sm">
          <ShieldAlert className="w-3 h-3" />
          DB History Locked (Sign In)
        </Badge>
      );
    }
    if (dbStatus === 'unavailable' && unavailableReason === 'database_offline') {
      return (
        <Badge variant="warning" size="sm">
          <Database className="w-3 h-3" />
          Stateless Session Mode
        </Badge>
      );
    }
    if (dbStatus === 'disconnected') {
      return (
        <Badge variant="neutral" size="sm">
          Backend Offline
        </Badge>
      );
    }
    if (dbStatus === 'error') {
      return (
        <Badge variant="error" size="sm">
          DB Query Error
        </Badge>
      );
    }
    return (
      <Badge variant="neutral" size="sm">
        Checking Persistence...
      </Badge>
    );
  };

  return (
    <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between pb-4 border-b border-em-border-hairline">
      <div className="space-y-1.5 min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-em-card border border-em-border-default flex items-center justify-center text-em-accent-primary shrink-0">
            <History className="w-4 h-4" />
          </div>
          <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">
            Analysis History
          </h2>
          {renderBackendBadge()}
          <Badge variant="neutral" size="sm">
            {totalShown === totalRecords
              ? `${totalRecords} ${totalRecords === 1 ? 'run' : 'runs'}`
              : `${totalShown} of ${totalRecords} shown`}
          </Badge>
        </div>
        <p className="text-xs text-em-text-muted max-w-3xl leading-relaxed">
          Inspect immutable analysis snapshots, audit stored findings, compare baseline vs.
          current runs, and export JSON or CSV reports without modifying active Workspace code.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 shrink-0">
        {authSessionEmail ? (
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md border border-em-border-default bg-em-card text-xs">
            <span className="text-em-text-muted truncate max-w-[160px]" title={authSessionEmail}>
              {authSessionEmail}
            </span>
            <button
              type="button"
              onClick={onLogout}
              className="inline-flex items-center gap-1 text-em-text-secondary hover:text-em-text-primary transition-colors"
              aria-label="Sign out of backend history"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        ) : (
          <Button
            type="button"
            variant={unavailableReason === 'auth_required' ? 'primary' : 'outline'}
            size="sm"
            leftIcon={<KeyRound className="w-3.5 h-3.5" />}
            onClick={onToggleAuthDrawer}
            aria-expanded={isAuthDrawerOpen}
          >
            {isAuthDrawerOpen ? 'Hide Sign In' : 'Sign In for DB'}
          </Button>
        )}

        <Button
          type="button"
          variant={isCompareMode ? 'primary' : 'secondary'}
          size="sm"
          leftIcon={<GitCompare className="w-3.5 h-3.5" />}
          onClick={onToggleCompareMode}
          disabled={!canCompare && !isCompareMode}
          title={
            canCompare
              ? 'Compare two analysis runs side-by-side'
              : 'Requires at least two history runs to compare'
          }
          className={
            !isCompareMode
              ? 'bg-em-card border-em-border-default hover:bg-em-elevated'
              : undefined
          }
        >
          {isCompareMode ? 'Close Compare' : 'Compare Runs'}
        </Button>

        <Button
          type="button"
          variant="outline"
          size="sm"
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          isLoading={isRefreshing}
          onClick={onRefresh}
        >
          Refresh
        </Button>

        <Link
          to="/workspace"
          className="inline-flex items-center gap-1.5 h-9 sm:h-7 px-3 sm:px-2.5 text-xs font-medium rounded-sm border border-em-border-default bg-em-card text-em-text-primary hover:bg-em-elevated hover:border-em-border-strong transition-colors"
        >
          <Code2 className="w-3.5 h-3.5 text-em-accent-primary" />
          Workspace
        </Link>
      </div>
    </header>
  );
};
