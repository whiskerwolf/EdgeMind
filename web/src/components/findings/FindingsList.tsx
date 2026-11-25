import React from 'react';
import { FilterX } from 'lucide-react';
import { FindingDiagnosisState } from '../../context/AnalysisContext';
import { ExplorerFinding } from '../../utils/findingsHelpers';
import { FindingListItem } from './FindingListItem';
import { EmptyState } from '../ui/EmptyState';
import { Button } from '../ui/Button';

export interface FindingsListProps {
  findings: ExplorerFinding[];
  selectedFindingId: string | null;
  diagnosisByFinding: Record<string, FindingDiagnosisState>;
  onSelectFinding: (finding: ExplorerFinding) => void;
  onClearFilters: () => void;
}

export const FindingsList: React.FC<FindingsListProps> = ({
  findings,
  selectedFindingId,
  diagnosisByFinding,
  onSelectFinding,
  onClearFilters,
}) => {
  return (
    <section
      aria-label="Findings list"
      className="flex flex-col rounded-lg border border-em-border-default bg-em-card overflow-hidden lg:h-[640px]"
    >
      <div className="px-4 py-2.5 border-b border-em-border-hairline bg-em-card flex items-center justify-between gap-2 shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-em-text-secondary">
          Reported Issues
        </span>
        <span className="text-[11px] font-mono tabular-nums text-em-text-dim">
          {findings.length} {findings.length === 1 ? 'item' : 'items'}
        </span>
      </div>

      <div className="flex-1 overflow-y-auto">
        {findings.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={FilterX}
              title="No Findings Match Filters"
              description="Try clearing the search query or relaxing the severity and category filters."
              action={
                <Button variant="secondary" size="sm" onClick={onClearFilters}>
                  Clear Filters
                </Button>
              }
              className="my-0 border-em-border-hairline"
            />
          </div>
        ) : (
          <div role="list">
            {findings.map((finding) => (
              <div key={finding.id} role="listitem">
                <FindingListItem
                  finding={finding}
                  isSelected={finding.id === selectedFindingId}
                  diagnosisState={diagnosisByFinding[finding.id]}
                  onSelect={onSelectFinding}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
};
