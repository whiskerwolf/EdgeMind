import React from 'react';
import { Sparkles } from 'lucide-react';
import { FindingDiagnosisState } from '../../context/AnalysisContext';
import { ExplorerFinding } from '../../utils/findingsHelpers';
import { SeverityBadge } from './SeverityBadge';
import { CategoryBadge } from './CategoryBadge';
import { Badge } from '../ui/Badge';
import { cn } from '../../utils/cn';

export interface FindingListItemProps {
  finding: ExplorerFinding;
  isSelected: boolean;
  diagnosisState?: FindingDiagnosisState;
  onSelect: (finding: ExplorerFinding) => void;
}

export const FindingListItem: React.FC<FindingListItemProps> = ({
  finding,
  isSelected,
  diagnosisState,
  onSelect,
}) => {
  const hasAiOutput =
    diagnosisState &&
    (diagnosisState.status === 'streaming' || diagnosisState.status === 'completed');

  return (
    <button
      type="button"
      onClick={() => onSelect(finding)}
      aria-pressed={isSelected}
      className={cn(
        'w-full text-left p-3.5 border-b border-em-border-hairline last:border-b-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-em-border-focus',
        isSelected
          ? 'bg-em-elevated border-l-2 border-l-em-accent-primary'
          : 'bg-em-card hover:bg-em-workspace border-l-2 border-l-transparent'
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 min-w-0">
          <SeverityBadge severity={finding.severity} />
          <span className="text-xs font-semibold font-mono text-em-text-primary truncate">
            {finding.type}
          </span>
        </div>

        <span className="text-[11px] font-mono tabular-nums text-em-text-dim shrink-0">
          {finding.line !== null ? `Line ${finding.line}` : 'Module'}
        </span>
      </div>

      <p className="mt-2 text-xs text-em-text-secondary leading-relaxed line-clamp-2 break-words">
        {finding.message}
      </p>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 min-w-0">
          <CategoryBadge category={finding.concept} />
          {hasAiOutput && (
            <Badge variant="info">
              <Sparkles className="w-2.5 h-2.5" aria-hidden="true" />
              <span>{diagnosisState?.status === 'streaming' ? 'AI Streaming' : 'AI Diagnosed'}</span>
            </Badge>
          )}
        </div>

        <span className="text-[10px] font-mono text-em-text-dim truncate max-w-[140px]">
          {finding.filename}
        </span>
      </div>
    </button>
  );
};
