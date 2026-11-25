import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { NormalizedHistoryEntry } from '../../utils/historyHelpers';
import { Button } from '../ui/Button';
import { HistoryItem } from './HistoryItem';

export interface HistoryListProps {
  items: NormalizedHistoryEntry[];
  selectedId: string | null;
  baselineId: string | null;
  targetId: string | null;
  onInspect: (entry: NormalizedHistoryEntry) => void;
  onSelectCompare: (role: 'A' | 'B', id: string) => void;
  onRequestDelete: (entry: NormalizedHistoryEntry) => void;
  deletingId: string | null;
  showDbPagination: boolean;
  dbTotal: number;
  dbSkip: number;
  dbLimit: number;
  onPrevPage: () => void;
  onNextPage: () => void;
}

export const HistoryList: React.FC<HistoryListProps> = ({
  items,
  selectedId,
  baselineId,
  targetId,
  onInspect,
  onSelectCompare,
  onRequestDelete,
  deletingId,
  showDbPagination,
  dbTotal,
  dbSkip,
  dbLimit,
  onPrevPage,
  onNextPage,
}) => {
  const canPrev = dbSkip > 0;
  const canNext = dbSkip + dbLimit < dbTotal;
  const pageStart = dbTotal === 0 ? 0 : dbSkip + 1;
  const pageEnd = Math.min(dbTotal, dbSkip + dbLimit);

  return (
    <div className="space-y-3">
      <div className="space-y-2.5" role="list" aria-label="Analysis history entries">
        {items.map((entry) => {
          const compareRole =
            baselineId === entry.id ? 'A' : targetId === entry.id ? 'B' : null;
          return (
            <div key={entry.id} role="listitem">
              <HistoryItem
                entry={entry}
                isSelected={selectedId === entry.id}
                compareRole={compareRole}
                onInspect={onInspect}
                onSelectCompare={onSelectCompare}
                onRequestDelete={onRequestDelete}
                isDeleting={deletingId === entry.id}
              />
            </div>
          );
        })}
      </div>

      {showDbPagination && dbTotal > dbLimit && (
        <nav
          aria-label="Persisted history pagination"
          className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-em-border-hairline text-xs text-em-text-muted"
        >
          <span className="font-mono">
            Database records {pageStart}-{pageEnd} of {dbTotal}
          </span>
          <div className="inline-flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              leftIcon={<ChevronLeft className="w-3.5 h-3.5" />}
              disabled={!canPrev}
              onClick={onPrevPage}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              rightIcon={<ChevronRight className="w-3.5 h-3.5" />}
              disabled={!canNext}
              onClick={onNextPage}
            >
              Next
            </Button>
          </div>
        </nav>
      )}
    </div>
  );
};
