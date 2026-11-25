import React from 'react';
import { ArrowLeftRight, X } from 'lucide-react';
import { NormalizedHistoryEntry } from '../../utils/historyHelpers';
import { Button } from '../ui/Button';

export interface ComparisonSelectorProps {
  entries: NormalizedHistoryEntry[];
  baselineId: string | null;
  targetId: string | null;
  onChangeBaseline: (id: string) => void;
  onChangeTarget: (id: string) => void;
  onSwap: () => void;
  onClose: () => void;
}

const SELECT_CLASS =
  'w-full h-9 px-2.5 rounded-md border border-em-border-default bg-em-workspace text-xs font-mono text-em-text-primary focus:outline-none focus:border-em-accent-primary focus:ring-1 focus:ring-em-accent-primary';

function formatOptionLabel(entry: NormalizedHistoryEntry): string {
  const scoreLabel = entry.score !== null ? `${entry.score}/100` : 'N/A';
  const shortId = entry.sessionId.replace(/^session-/, '').slice(0, 8);
  return `${entry.title} [${entry.status} • Score: ${scoreLabel}] (${shortId})`;
}

export const ComparisonSelector: React.FC<ComparisonSelectorProps> = ({
  entries,
  baselineId,
  targetId,
  onChangeBaseline,
  onChangeTarget,
  onSwap,
  onClose,
}) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
      <div className="md:col-span-5 space-y-1">
        <label
          htmlFor="compare-baseline-select"
          className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
        >
          Baseline Run (A - Previous)
        </label>
        <select
          id="compare-baseline-select"
          aria-label="Baseline Run (A)"
          value={baselineId || ''}
          onChange={(e) => onChangeBaseline(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="" disabled>
            Select baseline run...
          </option>
          {entries.map((entry) => (
            <option key={`base-${entry.id}`} value={entry.id}>
              {formatOptionLabel(entry)}
            </option>
          ))}
        </select>
      </div>

      <div className="md:col-span-1 flex justify-center">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onSwap}
          disabled={!baselineId || !targetId}
          aria-label="Swap baseline and target runs"
          title="Swap Baseline (A) and Target (B)"
        >
          <ArrowLeftRight className="w-3.5 h-3.5" />
        </Button>
      </div>

      <div className="md:col-span-5 space-y-1">
        <label
          htmlFor="compare-target-select"
          className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
        >
          Target Run (B - Comparison)
        </label>
        <select
          id="compare-target-select"
          aria-label="Target Run (B)"
          value={targetId || ''}
          onChange={(e) => onChangeTarget(e.target.value)}
          className={SELECT_CLASS}
        >
          <option value="" disabled>
            Select target run...
          </option>
          {entries.map((entry) => (
            <option key={`target-${entry.id}`} value={entry.id}>
              {formatOptionLabel(entry)}
            </option>
          ))}
        </select>
      </div>

      <div className="md:col-span-1 flex justify-end">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={onClose}
          aria-label="Close comparison"
        >
          <X className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
};
