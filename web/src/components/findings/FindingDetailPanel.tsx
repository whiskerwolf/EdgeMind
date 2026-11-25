import React, { useMemo } from 'react';
import { ArrowUpRight, FileCode2, Info } from 'lucide-react';
import { FindingDiagnosisState } from '../../context/AnalysisContext';
import { HealthStatus } from '../../types/api';
import { ExplorerFinding, getCodePreviewLines } from '../../utils/findingsHelpers';
import { WorkspaceLanguage } from '../../utils/workspaceConfig';
import { SeverityBadge } from './SeverityBadge';
import { CategoryBadge } from './CategoryBadge';
import { DiagnosisPanel } from './DiagnosisPanel';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { cn } from '../../utils/cn';

export interface FindingDetailPanelProps {
  finding: ExplorerFinding | null;
  sourceCode: string | null;
  sourceLanguage: WorkspaceLanguage;
  healthStatus: HealthStatus;
  hasUnanalyzedChanges: boolean;
  diagnosis?: FindingDiagnosisState;
  onInspectInWorkspace: (finding: ExplorerFinding) => void;
  onStartDiagnosis: (finding: ExplorerFinding) => void;
  onCancelDiagnosis: (findingId: string) => void;
}

export const FindingDetailPanel: React.FC<FindingDetailPanelProps> = ({
  finding,
  sourceCode,
  sourceLanguage,
  healthStatus,
  hasUnanalyzedChanges,
  diagnosis,
  onInspectInWorkspace,
  onStartDiagnosis,
  onCancelDiagnosis,
}) => {
  const previewLines = useMemo(() => {
    if (!finding) return null;
    return getCodePreviewLines(sourceCode, finding.line, 3);
  }, [finding, sourceCode]);

  if (!finding) {
    return (
      <section
        aria-label="Finding details"
        className="rounded-lg border border-em-border-default bg-em-card p-6 lg:h-[640px] flex items-center justify-center"
      >
        <EmptyState
          icon={FileCode2}
          title="Select a Finding to Inspect"
          description="Choose any finding from the list to review rule details, remediation guidance, source location, and optional AI diagnosis."
          className="my-0 border-none bg-transparent"
        />
      </section>
    );
  }

  return (
    <section
      aria-labelledby="finding-detail-heading"
      className="flex flex-col rounded-lg border border-em-border-default bg-em-card overflow-hidden lg:h-[640px]"
    >
      {/* Detail Header */}
      <div className="px-4 py-3 border-b border-em-border-hairline bg-em-card flex flex-wrap items-start justify-between gap-3 shrink-0">
        <div className="space-y-1.5 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <SeverityBadge severity={finding.severity} />
            <h3
              id="finding-detail-heading"
              className="text-sm font-semibold font-mono text-em-text-primary break-all"
            >
              {finding.type}
            </h3>
            <CategoryBadge category={finding.concept} />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[11px] font-mono tabular-nums text-em-text-muted">
            <span>File: {finding.filename}</span>
            <span className="text-em-text-dim">•</span>
            <span>
              {finding.line !== null
                ? `Line ${finding.line}`
                : 'Location: Module-level (no specific line)'}
            </span>
          </div>
        </div>

        <Button
          variant="primary"
          size="sm"
          rightIcon={<ArrowUpRight className="w-3.5 h-3.5" />}
          onClick={() => onInspectInWorkspace(finding)}
        >
          {finding.line !== null ? 'Inspect in Workspace' : 'Open File in Workspace'}
        </Button>
      </div>

      {/* Scrollable Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Deterministic Message */}
        <div className="rounded-md border border-em-border-hairline bg-em-workspace p-3.5 space-y-1.5">
          <span className="block text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
            Diagnostic Message (Deterministic Analyzer)
          </span>
          <p className="text-xs text-em-text-primary leading-relaxed break-words">
            {finding.message}
          </p>
        </div>

        {/* Static Explanation & Fix (Strictly only if present) */}
        {(finding.explanation || finding.suggestedFix) ? (
          <div className="grid grid-cols-1 gap-3">
            {finding.explanation && (
              <div className="rounded-md border border-em-border-hairline bg-em-workspace p-3.5 space-y-1">
                <span className="block text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
                  Why This Happens
                </span>
                <p className="text-xs text-em-text-secondary leading-relaxed break-words">
                  {finding.explanation}
                </p>
              </div>
            )}
            {finding.suggestedFix && (
              <div className="rounded-md border border-em-border-hairline bg-em-workspace p-3.5 space-y-1">
                <span className="block text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
                  Suggested Fix
                </span>
                <p className="text-xs text-em-text-secondary leading-relaxed break-words">
                  {finding.suggestedFix}
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-md border border-em-border-hairline bg-em-workspace p-3 flex items-start gap-2 text-xs text-em-text-muted">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-em-text-dim" aria-hidden="true" />
            <span>
              No pre-computed explanation or suggested fix metadata was returned for this finding.
            </span>
          </div>
        )}

        {/* Bounded Real Code Context Preview */}
        {previewLines && (
          <div className="rounded-md border border-em-border-default bg-em-canvas overflow-hidden">
            <div className="px-3 py-1.5 border-b border-em-border-hairline bg-em-workspace flex items-center justify-between text-[10px] font-mono text-em-text-dim">
              <span>Analyzed Source Preview · {finding.filename}</span>
              <span>{finding.line !== null ? `Target Line ${finding.line}` : 'Top of File'}</span>
            </div>
            <div className="py-1.5 overflow-x-auto font-mono text-[11px] leading-5">
              {previewLines.map((lineObj) => (
                <div
                  key={lineObj.lineNumber}
                  className={cn(
                    'flex px-3 min-w-max',
                    lineObj.isHighlighted &&
                      (finding.severity === 'error'
                        ? 'bg-em-status-error/15 border-l-2 border-l-em-status-error'
                        : 'bg-em-status-warning/15 border-l-2 border-l-em-status-warning')
                  )}
                >
                  <span className="w-8 shrink-0 select-none text-right pr-3 text-em-text-dim tabular-nums">
                    {lineObj.lineNumber}
                  </span>
                  <span className="text-em-text-primary whitespace-pre">
                    {lineObj.text || ' '}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* AI Diagnosis Streaming Integration */}
        <DiagnosisPanel
          finding={finding}
          diagnosis={diagnosis}
          sourceCode={sourceCode}
          sourceLanguage={sourceLanguage}
          healthStatus={healthStatus}
          hasUnanalyzedChanges={hasUnanalyzedChanges}
          onStartDiagnosis={() => onStartDiagnosis(finding)}
          onCancelDiagnosis={() => onCancelDiagnosis(finding.id)}
        />
      </div>
    </section>
  );
};
