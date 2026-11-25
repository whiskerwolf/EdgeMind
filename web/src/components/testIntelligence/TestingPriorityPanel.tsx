import React from 'react';
import { AlertCircle, ArrowUpRight, Target } from 'lucide-react';
import { TestingPriorityItem } from '../../utils/testIntelligenceHelpers';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';

export interface TestingPriorityPanelProps {
  priorityItems: TestingPriorityItem[];
  hasFindingsReport: boolean;
  onInspectLineInWorkspace: (filename: string, line: number | null) => void;
  onOpenFindings: () => void;
}

function getTierVariant(tier: TestingPriorityItem['tier']): 'error' | 'warning' | 'neutral' {
  if (tier === 'High') return 'error';
  if (tier === 'Medium') return 'warning';
  return 'neutral';
}

export const TestingPriorityPanel: React.FC<TestingPriorityPanelProps> = ({
  priorityItems,
  hasFindingsReport,
  onInspectLineInWorkspace,
  onOpenFindings,
}) => {
  return (
    <section
      aria-labelledby="testing-priority-heading"
      className="flex flex-col rounded-lg border border-em-border-default bg-em-card overflow-hidden"
    >
      <div className="px-4 py-2.5 border-b border-em-border-hairline flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-em-accent-primary shrink-0" aria-hidden="true" />
          <h3
            id="testing-priority-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Risk-Based Testing Priority
          </h3>
        </div>

        {hasFindingsReport && (
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<AlertCircle className="w-3 h-3" />}
            onClick={onOpenFindings}
          >
            Inspect Findings
          </Button>
        )}
      </div>

      <div className="p-4 space-y-3 max-h-[540px] overflow-y-auto">
        {priorityItems.length === 0 ? (
          <EmptyState
            icon={Target}
            title="No Source Code Target Available"
            description="Write or load Python source code in Code Workspace (or upload a .py module) to compute deterministic testing priority heuristics."
            className="my-0 border-em-border-hairline"
          />
        ) : (
          <>
            <p className="text-[11px] text-em-text-muted leading-relaxed">
              Deterministic testing priority index based on static analyzer errors (+30), warnings (+10), control-flow branching/nesting (+up to 25), absent static test references (+25 when tests supplied), and backend domain gaps. This is a transparent triage heuristic, not a runtime failure probability.
            </p>

            <div className="space-y-2.5">
              {priorityItems.map((item) => (
                <article
                  key={item.id}
                  className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-2"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={getTierVariant(item.tier)}>{item.tier} Priority</Badge>
                        <span className="text-xs font-mono font-semibold text-em-text-primary truncate">
                          {item.targetName}
                        </span>
                        <span className="text-[11px] font-mono text-em-text-dim">
                          · Heuristic Index: {item.priorityScore}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-em-text-dim">
                        <span>{item.filename}</span>
                        {item.line !== null && <span>Line {item.line}</span>}
                        <span>•</span>
                        <span>
                          Branches: {item.branchCount} · Max Depth: {item.maxNesting}
                        </span>
                      </div>
                    </div>

                    <Button
                      variant="outline"
                      size="sm"
                      rightIcon={<ArrowUpRight className="w-3 h-3" />}
                      onClick={() => onInspectLineInWorkspace(item.filename, item.line)}
                    >
                      {item.line !== null ? `Workspace Line ${item.line}` : 'Open in Workspace'}
                    </Button>
                  </div>

                  <p className="text-[11px] text-em-text-secondary leading-relaxed">
                    {item.rationale}
                  </p>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
};
