import React from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle, ArrowRight, Code2, Cpu } from 'lucide-react';
import { AnalysisReport } from '../../types/api';
import { Badge } from '../ui/Badge';

export interface QuickActionsSectionProps {
  report: AnalysisReport | null;
}

export const QuickActionsSection: React.FC<QuickActionsSectionProps> = ({ report }) => {
  const totalFindings = report ? report.total_errors + report.total_warnings : null;

  return (
    <section
      aria-labelledby="quick-actions-heading"
      className="rounded-lg border border-em-border-default bg-em-surface-card p-4"
    >
      <div className="pb-3 border-b border-em-border-hairline">
        <h3
          id="quick-actions-heading"
          className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
        >
          Quick Navigation
        </h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-3">
        <Link
          to="/workspace"
          className="group p-3.5 rounded-md border border-em-border-default bg-em-surface-workspace hover:bg-em-surface-elevated hover:border-em-border-strong transition-colors flex flex-col justify-between gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Code2 className="w-4 h-4 text-em-accent-primary shrink-0" />
              <span className="text-xs font-semibold text-em-text-primary">Code Workspace</span>
            </div>
            <ArrowRight className="w-3.5 h-3.5 text-em-text-dim group-hover:text-em-text-primary transition-colors" />
          </div>
          <p className="text-xs text-em-text-muted leading-relaxed">
            Submit Python source code for deterministic AST quality, logic, and complexity checks.
          </p>
        </Link>

        <Link
          to="/findings"
          className="group p-3.5 rounded-md border border-em-border-default bg-em-surface-workspace hover:bg-em-surface-elevated hover:border-em-border-strong transition-colors flex flex-col justify-between gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-em-accent-primary shrink-0" />
              <span className="text-xs font-semibold text-em-text-primary">Findings Explorer</span>
              {totalFindings !== null && (
                <Badge variant={totalFindings > 0 ? 'warning' : 'success'}>
                  {totalFindings}
                </Badge>
              )}
            </div>
            <ArrowRight className="w-3.5 h-3.5 text-em-text-dim group-hover:text-em-text-primary transition-colors" />
          </div>
          <p className="text-xs text-em-text-muted leading-relaxed">
            Filter diagnostic issues by severity and trigger finding-level streaming AI diagnosis.
          </p>
        </Link>

        <Link
          to="/test-intelligence"
          className="group p-3.5 rounded-md border border-em-border-default bg-em-surface-workspace hover:bg-em-surface-elevated hover:border-em-border-strong transition-colors flex flex-col justify-between gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Cpu className="w-4 h-4 text-em-accent-primary shrink-0" />
              <span className="text-xs font-semibold text-em-text-primary">Test Intelligence</span>
            </div>
            <ArrowRight className="w-3.5 h-3.5 text-em-text-dim group-hover:text-em-text-primary transition-colors" />
          </div>
          <p className="text-xs text-em-text-muted leading-relaxed">
            Evaluate input domain coverage gaps and inspect synthesized boundary test candidates.
          </p>
        </Link>
      </div>
    </section>
  );
};
