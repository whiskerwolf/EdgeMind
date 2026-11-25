import React from 'react';
import { RotateCcw, Search, SlidersHorizontal } from 'lucide-react';
import {
  DEFAULT_HISTORY_FILTERS,
  HistoryDateFilter,
  HistoryFilters,
  HistoryScoreFilter,
  HistorySortOption,
} from '../../utils/historyHelpers';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

export interface HistoryToolbarProps {
  filters: HistoryFilters;
  availableStatuses: string[];
  onChange: (next: HistoryFilters) => void;
  onClear: () => void;
}

const SELECT_CLASS =
  'h-9 px-2.5 rounded-md border border-em-border-default bg-em-card text-xs text-em-text-primary focus:outline-none focus:border-em-accent-primary focus:ring-1 focus:ring-em-accent-primary transition-colors';

export const HistoryToolbar: React.FC<HistoryToolbarProps> = ({
  filters,
  availableStatuses,
  onChange,
  onClear,
}) => {
  const activeCount =
    (filters.search.trim() ? 1 : 0) +
    (filters.status !== DEFAULT_HISTORY_FILTERS.status ? 1 : 0) +
    (filters.scoreRange !== DEFAULT_HISTORY_FILTERS.scoreRange ? 1 : 0) +
    (filters.dateRange !== DEFAULT_HISTORY_FILTERS.dateRange ? 1 : 0) +
    (filters.sort !== DEFAULT_HISTORY_FILTERS.sort ? 1 : 0);

  return (
    <section
      aria-label="History search and filters"
      className="rounded-lg border border-em-border-default bg-em-workspace p-3"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-12 gap-2.5 items-center">
        <div className="sm:col-span-2 lg:col-span-4">
          <Input
            type="search"
            value={filters.search}
            onChange={(e) => onChange({ ...filters, search: e.target.value })}
            placeholder="Search filename, title, project, mode, session ID..."
            aria-label="Search history"
            leftIcon={<Search className="w-3.5 h-3.5" />}
          />
        </div>

        <div className="lg:col-span-2">
          <label className="sr-only" htmlFor="history-status-filter">
            Status filter
          </label>
          <select
            id="history-status-filter"
            aria-label="Filter by status"
            value={filters.status}
            onChange={(e) => onChange({ ...filters, status: e.target.value })}
            className={`${SELECT_CLASS} w-full`}
          >
            <option value="all">Status: All</option>
            {availableStatuses.map((st) => (
              <option key={st} value={st}>
                Status: {st}
              </option>
            ))}
          </select>
        </div>

        <div className="lg:col-span-2">
          <label className="sr-only" htmlFor="history-score-filter">
            Score range filter
          </label>
          <select
            id="history-score-filter"
            aria-label="Filter by score"
            value={filters.scoreRange}
            onChange={(e) =>
              onChange({ ...filters, scoreRange: e.target.value as HistoryScoreFilter })
            }
            className={`${SELECT_CLASS} w-full`}
          >
            <option value="all">Score: Any</option>
            <option value="90plus">Score: 90 - 100</option>
            <option value="70plus">Score: 70+</option>
            <option value="below70">Score: Below 70</option>
          </select>
        </div>

        <div className="lg:col-span-2">
          <label className="sr-only" htmlFor="history-date-filter">
            Date range filter
          </label>
          <select
            id="history-date-filter"
            aria-label="Filter by date"
            value={filters.dateRange}
            onChange={(e) =>
              onChange({ ...filters, dateRange: e.target.value as HistoryDateFilter })
            }
            className={`${SELECT_CLASS} w-full`}
          >
            <option value="all">Time: All</option>
            <option value="today">Time: Last 24h</option>
            <option value="7d">Time: Last 7 days</option>
            <option value="30d">Time: Last 30 days</option>
          </select>
        </div>

        <div className="lg:col-span-2 flex items-center gap-1.5">
          <label className="sr-only" htmlFor="history-sort-select">
            Sort order
          </label>
          <select
            id="history-sort-select"
            aria-label="Sort history"
            value={filters.sort}
            onChange={(e) =>
              onChange({ ...filters, sort: e.target.value as HistorySortOption })
            }
            className={`${SELECT_CLASS} w-full`}
          >
            <option value="newest">Sort: Newest</option>
            <option value="oldest">Sort: Oldest</option>
            <option value="score-desc">Sort: Highest Score</option>
            <option value="score-asc">Sort: Lowest Score</option>
          </select>

          {activeCount > 0 && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClear}
              title={`Clear ${activeCount} active filters`}
              aria-label="Clear filters"
              className="shrink-0 px-2"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </Button>
          )}
        </div>
      </div>

      {activeCount > 0 && (
        <div className="mt-2 pt-2 border-t border-em-border-hairline flex items-center justify-between text-[11px] text-em-text-muted">
          <span className="inline-flex items-center gap-1.5">
            <SlidersHorizontal className="w-3 h-3 text-em-accent-primary" />
            {activeCount} {activeCount === 1 ? 'filter' : 'filters'} active
          </span>
          <button
            type="button"
            onClick={onClear}
            className="text-em-accent-primary hover:underline font-medium"
          >
            Reset all filters
          </button>
        </div>
      )}
    </section>
  );
};
