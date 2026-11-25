import React from 'react';
import { Search, X, RotateCcw } from 'lucide-react';
import { FindingSeverity } from '../../types/api';
import {
  DEFAULT_FINDING_FILTERS,
  FindingFilters,
  FindingSortOption,
} from '../../utils/findingsHelpers';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { cn } from '../../utils/cn';

export interface FindingsToolbarProps {
  filters: FindingFilters;
  availableCategories: string[];
  totalCount: number;
  filteredCount: number;
  errorCount: number;
  warningCount: number;
  onFiltersChange: (next: FindingFilters) => void;
  onClearFilters: () => void;
}

export const FindingsToolbar: React.FC<FindingsToolbarProps> = ({
  filters,
  availableCategories,
  totalCount,
  filteredCount,
  errorCount,
  warningCount,
  onFiltersChange,
  onClearFilters,
}) => {
  const hasActiveFilters =
    filters.search.trim().length > 0 ||
    filters.severity !== DEFAULT_FINDING_FILTERS.severity ||
    filters.category !== DEFAULT_FINDING_FILTERS.category ||
    filters.sort !== DEFAULT_FINDING_FILTERS.sort;

  const setSeverity = (severity: 'all' | FindingSeverity) => {
    onFiltersChange({ ...filters, severity });
  };

  return (
    <div className="rounded-lg border border-em-border-default bg-em-card p-3 space-y-3">
      {/* Primary Controls Row */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-2.5 items-center">
        {/* Search */}
        <div className="md:col-span-12 lg:col-span-5">
          <Input
            type="text"
            aria-label="Search findings"
            placeholder="Search rule, message, category, or line..."
            value={filters.search}
            onChange={(e) => onFiltersChange({ ...filters, search: e.target.value })}
            leftIcon={<Search className="w-3.5 h-3.5" />}
            rightIcon={
              filters.search ? (
                <button
                  type="button"
                  onClick={() => onFiltersChange({ ...filters, search: '' })}
                  className="p-0.5 text-em-text-dim hover:text-em-text-primary rounded focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-em-border-focus"
                  aria-label="Clear search query"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              ) : undefined
            }
          />
        </div>

        {/* Category Dropdown */}
        <div className="md:col-span-6 lg:col-span-4">
          <select
            aria-label="Filter by category"
            value={filters.category}
            onChange={(e) => onFiltersChange({ ...filters, category: e.target.value })}
            disabled={availableCategories.length === 0}
            className="w-full h-9 rounded-md border border-em-border-default bg-em-workspace px-2.5 text-xs font-mono text-em-text-primary focus:outline-none focus:border-em-accent-primary focus:ring-1 focus:ring-em-accent-primary disabled:opacity-50"
          >
            <option value="all">All Categories ({availableCategories.length})</option>
            {availableCategories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </div>

        {/* Sort Select */}
        <div className="md:col-span-6 lg:col-span-3">
          <select
            aria-label="Sort findings"
            value={filters.sort}
            onChange={(e) =>
              onFiltersChange({ ...filters, sort: e.target.value as FindingSortOption })
            }
            className="w-full h-9 rounded-md border border-em-border-default bg-em-workspace px-2.5 text-xs font-mono text-em-text-primary focus:outline-none focus:border-em-accent-primary focus:ring-1 focus:ring-em-accent-primary"
          >
            <option value="default">Sort: Default Order</option>
            <option value="severity-desc">Sort: Errors First</option>
            <option value="line-asc">Sort: Line Asc</option>
            <option value="line-desc">Sort: Line Desc</option>
          </select>
        </div>
      </div>

      {/* Severity Filter Pills + Active Indicators */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-em-border-hairline">
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Severity filter">
          {(
            [
              { id: 'all', label: `All (${totalCount})` },
              { id: 'error', label: `Errors (${errorCount})` },
              { id: 'warning', label: `Warnings (${warningCount})` },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSeverity(item.id)}
              aria-pressed={filters.severity === item.id}
              className={cn(
                'px-2.5 py-1.5 rounded text-[11px] font-mono tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus',
                filters.severity === item.id
                  ? 'bg-em-accent-subtle text-em-accent-primary font-semibold border border-em-accent-primary/35'
                  : 'text-em-text-muted hover:text-em-text-primary hover:bg-white/[0.04] border border-em-border-hairline'
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono text-em-text-muted">
          <span className="tabular-nums">
            Showing <strong className="text-em-text-primary">{filteredCount}</strong> of{' '}
            <strong className="text-em-text-primary">{totalCount}</strong>
          </span>

          {hasActiveFilters && (
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<RotateCcw className="w-3 h-3" />}
              onClick={onClearFilters}
            >
              Clear Filters
            </Button>
          )}
        </div>
      </div>

      {/* Active Filter Chips */}
      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[10px] font-mono">
          <span className="uppercase tracking-wider text-em-text-dim mr-1">Active:</span>
          {filters.search.trim() && (
            <span className="px-1.5 py-0.5 rounded bg-em-workspace border border-em-border-default text-em-text-secondary">
              search: &quot;{filters.search.trim()}&quot;
            </span>
          )}
          {filters.severity !== 'all' && (
            <span className="px-1.5 py-0.5 rounded bg-em-workspace border border-em-border-default text-em-text-secondary">
              severity: {filters.severity}
            </span>
          )}
          {filters.category !== 'all' && (
            <span className="px-1.5 py-0.5 rounded bg-em-workspace border border-em-border-default text-em-text-secondary">
              category: {filters.category}
            </span>
          )}
          {filters.sort !== 'default' && (
            <span className="px-1.5 py-0.5 rounded bg-em-workspace border border-em-border-default text-em-text-secondary">
              sort: {filters.sort}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
