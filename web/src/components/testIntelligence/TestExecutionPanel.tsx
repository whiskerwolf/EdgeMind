import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Lock, TerminalSquare } from 'lucide-react';
import {
  CapabilityClassification,
  TEST_INTELLIGENCE_CAPABILITY_MATRIX,
} from '../../utils/testIntelligenceHelpers';
import { Badge } from '../ui/Badge';

function getCapabilityBadgeVariant(
  cls: CapabilityClassification
): 'success' | 'info' | 'warning' | 'neutral' {
  if (cls === 'IMPLEMENTABLE WITH EXISTING DATA') return 'success';
  if (cls === 'IMPLEMENTABLE WITH DETERMINISTIC ANALYSIS') return 'info';
  if (cls === 'REQUIRES BACKEND IMPLEMENTATION') return 'warning';
  return 'neutral';
}

export const TestExecutionPanel: React.FC = () => {
  const [showMatrix, setShowMatrix] = useState(false);

  return (
    <section
      aria-labelledby="execution-status-heading"
      className="rounded-lg border border-em-border-default bg-em-card overflow-hidden"
    >
      <div className="px-4 py-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <div className="p-2 rounded bg-em-workspace border border-em-border-hairline text-em-text-muted shrink-0">
            <TerminalSquare className="w-4 h-4" aria-hidden="true" />
          </div>
          <div className="space-y-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3
                id="execution-status-heading"
                className="text-xs font-semibold text-em-text-primary tracking-tight"
              >
                Test Execution & Line Coverage Results
              </h3>
              <Badge variant="neutral">
                <Lock className="w-2.5 h-2.5" aria-hidden="true" />
                <span>Not Supported (Static-Only API)</span>
              </Badge>
            </div>
            <p className="text-xs text-em-text-muted leading-relaxed">
              EdgeMind permanently disables runtime code execution (<code className="text-em-text-secondary">static_only: true</code>) and does not execute pytest or collect line/branch coverage. Pass, fail, skip, duration, and coverage percentages remain intentionally unavailable rather than reported as zero.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setShowMatrix((prev) => !prev)}
          aria-expanded={showMatrix}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-em-border-default bg-em-workspace hover:bg-em-elevated text-xs font-mono text-em-text-secondary shrink-0 transition-colors"
        >
          {showMatrix ? (
            <ChevronDown className="w-3.5 h-3.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5" />
          )}
          <span>{showMatrix ? 'Hide Capability Matrix' : 'View Capability Matrix'}</span>
        </button>
      </div>

      {showMatrix && (
        <div className="px-4 pb-4 pt-2 border-t border-em-border-hairline bg-em-workspace">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            {TEST_INTELLIGENCE_CAPABILITY_MATRIX.map((item) => (
              <div
                key={item.id}
                className="p-3 rounded-md border border-em-border-default bg-em-card space-y-1.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-1.5">
                  <span className="text-xs font-semibold text-em-text-primary">{item.feature}</span>
                  <Badge variant={getCapabilityBadgeVariant(item.classification)}>
                    {item.classification}
                  </Badge>
                </div>
                <p className="text-[11px] text-em-text-muted leading-relaxed">{item.detail}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
