import React, { useState } from 'react';
import { ArrowUpRight, ChevronDown, ChevronRight, CornerDownRight } from 'lucide-react';
import { ReportFinding } from '../../types/api';
import { Badge } from '../ui/Badge';
import { cn } from '../../utils/cn';

export interface WorkspaceFindingItemProps {
  finding: ReportFinding;
  severity: 'error' | 'warning';
  isSelected: boolean;
  onNavigateToLine: (line: number) => void;
  onOpenInFindings?: () => void;
}

export const WorkspaceFindingItem: React.FC<WorkspaceFindingItemProps> = ({
  finding,
  severity,
  isSelected,
  onNavigateToLine,
  onOpenInFindings,
}) => {
  const [expanded, setExpanded] = useState(false);

  const lineNumber = finding.line || finding.line_number || 0;
  const explanation = finding.why || finding.explanation || '';
  const remediation = finding.fix || finding.suggested_fix || '';
  const hasDetails = Boolean(explanation || remediation);

  return (
    <article
      className={cn(
        'rounded-md border p-3 transition-colors bg-em-surface-workspace',
        isSelected
          ? 'border-em-accent-primary/60 bg-em-surface-elevated/60'
          : 'border-em-border-default hover:border-em-border-strong'
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 min-w-0">
          <Badge variant={severity === 'error' ? 'error' : 'warning'}>
            {severity}
          </Badge>
          <span className="text-xs font-semibold font-mono text-em-text-primary">
            {finding.type}
          </span>
          {finding.concept && finding.concept !== 'General' && (
            <Badge variant="neutral">{finding.concept}</Badge>
          )}
        </div>

        {lineNumber > 0 ? (
          <button
            type="button"
            onClick={() => onNavigateToLine(lineNumber)}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/[0.04] hover:bg-em-accent-primary/15 border border-white/[0.08] hover:border-em-accent-primary/40 text-[11px] font-mono tabular-nums text-em-accent-primary shrink-0 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus"
            title={`Jump to line ${lineNumber} in editor`}
          >
            <CornerDownRight className="w-3 h-3" />
            <span>Line {lineNumber}</span>
          </button>
        ) : (
          <span className="text-[11px] font-mono text-em-text-dim shrink-0">Module</span>
        )}
      </div>

      <p className="mt-2 text-xs text-em-text-secondary leading-relaxed break-words">
        {finding.message}
      </p>

      {(hasDetails || onOpenInFindings) && (
        <div className="mt-2.5 pt-2 border-t border-em-border-hairline">
          <div className="flex flex-wrap items-center justify-between gap-2">
            {hasDetails ? (
              <button
                type="button"
                onClick={() => setExpanded((prev) => !prev)}
                aria-expanded={expanded}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-em-text-muted hover:text-em-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus rounded"
              >
                {expanded ? (
                  <ChevronDown className="w-3.5 h-3.5" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5" />
                )}
                <span>{expanded ? 'Hide Details' : 'View Explanation & Fix'}</span>
              </button>
            ) : (
              <span />
            )}

            {onOpenInFindings && (
              <button
                type="button"
                onClick={onOpenInFindings}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-em-accent-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus rounded"
              >
                <span>Open in Findings</span>
                <ArrowUpRight className="w-3 h-3" aria-hidden="true" />
              </button>
            )}
          </div>

          {hasDetails && expanded && (
            <div className="mt-2 space-y-2 text-xs">
              {explanation && (
                <div className="p-2 rounded bg-em-surface-card border border-em-border-hairline">
                  <span className="block text-[10px] font-mono uppercase text-em-text-dim mb-0.5">
                    Why This Happens
                  </span>
                  <p className="text-em-text-secondary leading-relaxed">{explanation}</p>
                </div>
              )}
              {remediation && (
                <div className="p-2 rounded bg-em-surface-card border border-em-border-hairline">
                  <span className="block text-[10px] font-mono uppercase text-em-text-dim mb-0.5">
                    Suggested Fix
                  </span>
                  <p className="text-em-text-secondary leading-relaxed">{remediation}</p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </article>
  );
};
