import React from 'react';
import { EdgeMindAnalyzeResponse } from '../../types/api';
import { cn } from '../../utils/cn';

export interface TestSummaryProps {
  discoveredTestFilesCount: number | null;
  discoveredTestCasesCount: number | null;
  backendReport: EdgeMindAnalyzeResponse | null;
  staticGapsCount: number | null;
}

interface SummaryCardItem {
  id: string;
  label: string;
  value: string;
  caption: string;
  tone: 'default' | 'accent' | 'warning' | 'muted';
}

export const TestSummary: React.FC<TestSummaryProps> = ({
  discoveredTestFilesCount,
  discoveredTestCasesCount,
  backendReport,
  staticGapsCount,
}) => {
  const domainGapsCount = backendReport ? backendReport.test_intelligence.total_gaps : null;
  const synthesizedCount = backendReport
    ? backendReport.test_intelligence.ranked_candidates.length
    : null;
  const baselineAnalyzed = backendReport
    ? backendReport.test_intelligence.existing_tests_analyzed
    : null;

  const combinedTestCasesValue =
    discoveredTestCasesCount !== null || baselineAnalyzed !== null
      ? String((discoveredTestCasesCount ?? 0) + (baselineAnalyzed ?? 0))
      : 'None Supplied';

  const cards: SummaryCardItem[] = [
    {
      id: 'test-files',
      label: 'Test Files',
      value:
        discoveredTestFilesCount !== null && discoveredTestFilesCount > 0
          ? String(discoveredTestFilesCount)
          : 'None Loaded',
      caption:
        discoveredTestFilesCount !== null && discoveredTestFilesCount > 0
          ? 'User-supplied .py parsed locally'
          : 'No server directory scanner',
      tone: discoveredTestFilesCount && discoveredTestFilesCount > 0 ? 'accent' : 'muted',
    },
    {
      id: 'test-cases',
      label: 'Tests / Baselines',
      value: combinedTestCasesValue,
      caption:
        baselineAnalyzed !== null
          ? `${discoveredTestCasesCount ?? 0} parsed · ${baselineAnalyzed} baseline`
          : 'Parsed test_* defs + baselines',
      tone:
        (discoveredTestCasesCount ?? 0) + (baselineAnalyzed ?? 0) > 0 ? 'default' : 'muted',
    },
    {
      id: 'domain-gaps',
      label: 'Coverage Gaps',
      value:
        domainGapsCount !== null || staticGapsCount !== null
          ? String((domainGapsCount ?? 0) + (staticGapsCount ?? 0))
          : 'Pending',
      caption:
        domainGapsCount !== null
          ? `${domainGapsCount} domain · ${staticGapsCount ?? 0} static ref`
          : 'Run analysis or load tests',
      tone:
        (domainGapsCount ?? 0) + (staticGapsCount ?? 0) > 0 ? 'warning' : 'muted',
    },
    {
      id: 'candidates',
      label: 'Edge Candidates',
      value: synthesizedCount !== null ? String(synthesizedCount) : 'Pending',
      caption:
        backendReport
          ? `${backendReport.analysis_mode.replace('_', ' ')} (unverified)`
          : 'Synthesized by EdgeMind API',
      tone: synthesizedCount !== null && synthesizedCount > 0 ? 'accent' : 'muted',
    },
    {
      id: 'execution',
      label: 'Execution Status',
      value: 'Unavailable',
      caption: 'Pass / Fail / Skip disabled (static_only)',
      tone: 'muted',
    },
    {
      id: 'coverage',
      label: 'Measured Coverage',
      value: 'Not Measured',
      caption: 'No runtime line/branch instrumentation',
      tone: 'muted',
    },
  ];

  return (
    <section
      aria-label="Test intelligence availability summary"
      className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3"
    >
      {cards.map((card) => (
        <div
          key={card.id}
          className="rounded-lg border border-em-border-default bg-em-card p-3 space-y-1 min-w-0"
        >
          <span className="block text-[10px] font-mono uppercase tracking-wider text-em-text-dim truncate">
            {card.label}
          </span>
          <div
            className={cn(
              'text-sm font-semibold font-mono tabular-nums truncate',
              card.tone === 'accent'
                ? 'text-em-accent-primary'
                : card.tone === 'warning'
                  ? 'text-em-status-warning'
                  : card.tone === 'muted'
                    ? 'text-em-text-muted'
                    : 'text-em-text-primary'
            )}
          >
            {card.value}
          </div>
          <span className="block text-[10px] text-em-text-dim leading-snug truncate" title={card.caption}>
            {card.caption}
          </span>
        </div>
      ))}
    </section>
  );
};
