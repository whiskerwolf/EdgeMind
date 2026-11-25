import React from 'react';
import { Clock, Database, Eye, GitCompare, HardDrive, Trash2 } from 'lucide-react';
import { cn } from '../../utils/cn';
import { NormalizedHistoryEntry } from '../../utils/historyHelpers';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export interface HistoryItemProps {
  entry: NormalizedHistoryEntry;
  isSelected: boolean;
  compareRole: 'A' | 'B' | null;
  onInspect: (entry: NormalizedHistoryEntry) => void;
  onSelectCompare: (role: 'A' | 'B', id: string) => void;
  onRequestDelete?: (entry: NormalizedHistoryEntry) => void;
  isDeleting?: boolean;
}

function getStatusVariant(status: string): 'success' | 'warning' | 'error' | 'info' | 'neutral' {
  const upper = status.toUpperCase();
  if (upper === 'PASS' || upper === 'SUCCESS') return 'success';
  if (upper.includes('WARNING') || upper === 'INSUFFICIENT_CONTEXT') return 'warning';
  if (upper === 'FAIL' || upper === 'FAILED' || upper === 'ERROR') return 'error';
  return 'info';
}

export function formatHistoryTimestamp(iso: string | null): string {
  if (!iso) return 'Timestamp unavailable';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export const HistoryItem: React.FC<HistoryItemProps> = ({
  entry,
  isSelected,
  compareRole,
  onInspect,
  onSelectCompare,
  onRequestDelete,
  isDeleting = false,
}) => {
  const isDeletedReport = entry.storageStatus === 'DELETED';

  return (
    <article
      className={cn(
        'rounded-lg border p-3.5 transition-colors bg-em-card',
        isSelected
          ? 'border-em-accent-primary/70 bg-em-elevated/80'
          : 'border-em-border-default hover:border-em-border-strong'
      )}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={getStatusVariant(entry.status)} size="sm">
              {entry.status}
            </Badge>

            {entry.source === 'database' ? (
              <Badge variant="info" size="sm">
                <Database className="w-3 h-3" />
                DB Stored
              </Badge>
            ) : (
              <Badge variant="neutral" size="sm">
                <HardDrive className="w-3 h-3" />
                In-Memory Session
              </Badge>
            )}

            {isDeletedReport && (
              <Badge variant="warning" size="sm">
                Report Deleted
              </Badge>
            )}

            {compareRole && (
              <Badge variant="info" size="sm">
                <GitCompare className="w-3 h-3" />
                Compare {compareRole === 'A' ? 'Baseline (A)' : 'Target (B)'}
              </Badge>
            )}

            <span className="text-[11px] font-mono text-em-text-dim">{entry.analysisMode}</span>
          </div>

          <div className="flex flex-wrap items-baseline gap-2">
            <h3 className="text-sm font-semibold text-em-text-primary font-mono truncate">
              {entry.title}
            </h3>
            {entry.projectName && entry.projectName !== entry.title && (
              <span className="text-xs text-em-text-muted truncate">
                Project: {entry.projectName}
              </span>
            )}
            {entry.platform && (
              <span className="text-[11px] font-mono text-em-text-dim">{entry.platform}</span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] font-mono text-em-text-muted">
            <span>
              Score:{' '}
              <strong className="text-em-text-primary">
                {entry.score !== null ? `${entry.score}/100` : 'N/A'}
              </strong>
            </span>
            <span>
              Errors:{' '}
              <strong className="text-em-text-primary">
                {entry.totalErrors !== null ? entry.totalErrors : 'N/A'}
              </strong>
            </span>
            <span>
              Warnings:{' '}
              <strong className="text-em-text-primary">
                {entry.totalWarnings !== null ? entry.totalWarnings : 'N/A'}
              </strong>
            </span>
            {entry.gapsDetected !== null && (
              <span>
                Gaps: <strong className="text-em-text-primary">{entry.gapsDetected}</strong>
              </span>
            )}
            <span>
              Duration:{' '}
              <strong className="text-em-text-primary">
                {entry.durationMs !== null ? `${entry.durationMs} ms` : 'N/A'}
              </strong>
            </span>
            <span className="inline-flex items-center gap-1 text-em-text-dim" title={entry.createdAt || undefined}>
              <Clock className="w-3 h-3" />
              {formatHistoryTimestamp(entry.createdAt)}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5 shrink-0">
          <Button
            type="button"
            variant={isSelected ? 'primary' : 'outline'}
            size="sm"
            leftIcon={<Eye className="w-3.5 h-3.5" />}
            onClick={() => onInspect(entry)}
          >
            {isSelected ? 'Inspecting' : 'View Report'}
          </Button>

          <Button
            type="button"
            variant={compareRole === 'A' ? 'primary' : 'outline'}
            size="sm"
            onClick={() => onSelectCompare('A', entry.id)}
            aria-pressed={compareRole === 'A'}
            title="Set as Baseline run (A) for comparison"
          >
            Set A
          </Button>

          <Button
            type="button"
            variant={compareRole === 'B' ? 'primary' : 'outline'}
            size="sm"
            onClick={() => onSelectCompare('B', entry.id)}
            aria-pressed={compareRole === 'B'}
            title="Set as Target run (B) for comparison"
          >
            Set B
          </Button>

          {onRequestDelete && !isDeletedReport && (
            <Button
              type="button"
              variant="danger"
              size="sm"
              leftIcon={<Trash2 className="w-3.5 h-3.5" />}
              isLoading={isDeleting}
              onClick={() => onRequestDelete(entry)}
              aria-label={`Delete ${entry.title}`}
              title={
                entry.source === 'database'
                  ? 'Delete stored JSONB report'
                  : 'Remove from in-memory session history'
              }
            >
              Delete
            </Button>
          )}
        </div>
      </div>
    </article>
  );
};
