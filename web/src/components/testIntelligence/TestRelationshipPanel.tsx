import React from 'react';
import { ArrowUpRight, GitBranch } from 'lucide-react';
import { TestToCodeRelationship } from '../../utils/testIntelligenceHelpers';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';

export interface TestRelationshipPanelProps {
  relationships: TestToCodeRelationship[];
  hasSuppliedTestFiles: boolean;
  onOpenSourceInWorkspace: (sourceFilename: string) => void;
}

function getConfidenceVariant(
  confidence: TestToCodeRelationship['confidence']
): 'success' | 'warning' | 'neutral' {
  if (confidence === 'high') return 'success';
  if (confidence === 'medium') return 'warning';
  return 'neutral';
}

function getConfidenceLabel(confidence: TestToCodeRelationship['confidence']): string {
  if (confidence === 'high') return 'HIGH CONFIDENCE (INFERRED)';
  if (confidence === 'medium') return 'MEDIUM CONFIDENCE (INFERRED)';
  return 'UNMAPPED';
}

export const TestRelationshipPanel: React.FC<TestRelationshipPanelProps> = ({
  relationships,
  hasSuppliedTestFiles,
  onOpenSourceInWorkspace,
}) => {
  return (
    <section
      aria-labelledby="relationships-heading"
      className="flex flex-col rounded-lg border border-em-border-default bg-em-card overflow-hidden"
    >
      <div className="px-4 py-2.5 border-b border-em-border-hairline flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <GitBranch className="w-4 h-4 text-em-accent-primary shrink-0" aria-hidden="true" />
          <h3
            id="relationships-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Test-to-Code Relationships
          </h3>
        </div>
        <Badge variant="neutral">Static Reference Inference</Badge>
      </div>

      <div className="p-4 space-y-3 max-h-[420px] overflow-y-auto">
        {!hasSuppliedTestFiles ? (
          <EmptyState
            icon={GitBranch}
            title="No Test-to-Code Mapping Yet"
            description="Load or paste Python test files in Supplied Test Explorer to trace import statements, filename conventions, and symbol calls against source code."
            className="my-0 border-em-border-hairline"
          />
        ) : relationships.length === 0 ? (
          <p className="text-xs text-em-text-muted">
            No mappable Python test files available yet.
          </p>
        ) : (
          <>
            <p className="text-[11px] text-em-text-muted leading-relaxed">
              Derived from static imports, naming patterns, and direct function call matching. Inferred relationships do not measure runtime execution coverage.
            </p>
            <div className="space-y-2.5">
              {relationships.map((rel) => (
                <article
                  key={rel.id}
                  className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-2"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="space-y-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
                        <span className="font-semibold text-em-text-primary truncate">
                          {rel.testFilename}
                        </span>
                        <span className="text-em-text-dim">→</span>
                        <span className="text-em-accent-primary truncate">
                          {rel.sourceFilename}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={getConfidenceVariant(rel.confidence)}>
                          {getConfidenceLabel(rel.confidence)}
                        </Badge>
                        {rel.isWorkspaceTarget && (
                          <Badge variant="info">Active Workspace Target</Badge>
                        )}
                      </div>
                    </div>

                    {rel.confidence !== 'unmapped' && (
                      <Button
                        variant="outline"
                        size="sm"
                        rightIcon={<ArrowUpRight className="w-3 h-3" />}
                        onClick={() => onOpenSourceInWorkspace(rel.sourceFilename)}
                      >
                        Open in Workspace
                      </Button>
                    )}
                  </div>

                  {rel.matchedSymbols.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
                      <span className="text-em-text-dim uppercase">Referenced Symbols:</span>
                      {rel.matchedSymbols.map((sym) => (
                        <span
                          key={sym}
                          className="px-1.5 py-0.5 rounded bg-em-card border border-em-border-hairline text-em-text-secondary"
                        >
                          {sym}()
                        </span>
                      ))}
                    </div>
                  )}

                  <ul className="space-y-0.5 text-[11px] text-em-text-secondary list-disc pl-4">
                    {rel.evidence.map((ev, idx) => (
                      <li key={idx}>{ev}</li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
};
