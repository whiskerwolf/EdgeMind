import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Database,
  FileCode2,
  HardDrive,
  Info,
  Lock,
  ShieldCheck,
  X,
} from 'lucide-react';
import { ApiError, ReportFinding } from '../../types/api';
import { cn } from '../../utils/cn';
import { NormalizedHistoryEntry } from '../../utils/historyHelpers';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import { formatHistoryTimestamp } from './HistoryItem';
import { ReportExport } from './ReportExport';

export interface HistoricalReportViewProps {
  entry: NormalizedHistoryEntry;
  isHydrating?: boolean;
  hydrationError?: ApiError | null;
  onClose: () => void;
}

function getSummaryVariant(value: string): 'success' | 'warning' | 'error' | 'info' | 'neutral' {
  const upper = value.toUpperCase();
  if (upper === 'PASS' || upper === 'VALID' || upper === 'OK') return 'success';
  if (upper.includes('WARN') || upper === 'MEDIUM' || upper === 'HIGH') return 'warning';
  if (upper === 'FAIL' || upper === 'ERROR' || upper === 'CRITICAL') return 'error';
  if (upper === 'SKIPPED' || upper === 'UNKNOWN') return 'neutral';
  return 'info';
}

const FindingReadOnlyCard: React.FC<{
  finding: ReportFinding;
  severity: 'error' | 'warning';
}> = ({ finding, severity }) => {
  const line = finding.line ?? finding.line_number ?? null;
  const why = finding.why || finding.explanation;
  const fix = finding.fix || finding.suggested_fix;

  return (
    <div className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={severity === 'error' ? 'error' : 'warning'} size="sm">
            {severity === 'error' ? (
              <AlertCircle className="w-3 h-3" />
            ) : (
              <AlertTriangle className="w-3 h-3" />
            )}
            {severity}
          </Badge>
          <span className="text-xs font-mono font-semibold text-em-text-primary">
            {finding.type || 'DiagnosticRule'}
          </span>
          {finding.concept && (
            <span className="text-[11px] font-mono text-em-text-dim">{finding.concept}</span>
          )}
        </div>
        <span className="text-[11px] font-mono text-em-text-muted">
          {line ? `Line ${line}` : 'File-level'}
        </span>
      </div>

      <p className="text-xs text-em-text-secondary leading-relaxed">{finding.message}</p>

      {why && (
        <p className="text-[11px] text-em-text-muted leading-relaxed">
          <span className="font-semibold text-em-text-secondary">Why:</span> {why}
        </p>
      )}
      {fix && (
        <p className="text-[11px] text-em-accent-primary/90 leading-relaxed">
          <span className="font-semibold">Fix:</span> {fix}
        </p>
      )}
    </div>
  );
};

export const HistoricalReportView: React.FC<HistoricalReportViewProps> = ({
  entry,
  isHydrating = false,
  hydrationError = null,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'findings' | 'coverage' | 'raw'>('findings');

  useEffect(() => {
    setActiveTab('findings');
  }, [entry.id]);

  const totalFindings = entry.errors.length + entry.warnings.length;

  return (
    <section
      aria-label={`Historical report for ${entry.title}`}
      className="rounded-lg border border-em-border-strong bg-em-card overflow-hidden"
    >
      {/* Top Immutable Snapshot Header */}
      <div className="p-4 border-b border-em-border-hairline bg-em-elevated/60 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-1.5 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="info" size="sm">
              <Lock className="w-3 h-3" />
              Immutable Historical Snapshot
            </Badge>
            <Badge variant={entry.source === 'database' ? 'info' : 'neutral'} size="sm">
              {entry.source === 'database' ? (
                <>
                  <Database className="w-3 h-3" />
                  DB Stored
                </>
              ) : (
                <>
                  <HardDrive className="w-3 h-3" />
                  In-Memory Session
                </>
              )}
            </Badge>
            <Badge variant="neutral" size="sm">
              {entry.status}
            </Badge>
          </div>
          <h3 className="text-base font-semibold text-em-text-primary font-mono truncate">
            {entry.title}
          </h3>
          <p className="text-[11px] font-mono text-em-text-dim">
            Session ID: {entry.sessionId} • Recorded: {formatHistoryTimestamp(entry.createdAt)}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <ReportExport entry={entry} />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label="Close report view"
          >
            <X className="w-4 h-4" />
            Close
          </Button>
        </div>
      </div>

      {/* Source Code Exclusion Notice (Never fabricates source code) */}
      <div className="px-4 py-2.5 border-b border-em-border-hairline bg-em-workspace flex items-start gap-2.5 text-xs text-em-text-muted">
        <FileCode2 className="w-4 h-4 text-em-text-dim shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold text-em-text-secondary">
            Source code is unavailable in this view.
          </span>{' '}
          <span>{entry.sourceCodeNote}</span>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {isHydrating && (
          <div className="space-y-2" aria-label="Loading report details">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-16 w-full" />
          </div>
        )}

        {hydrationError && (
          <div
            role="alert"
            className="rounded-md border border-em-status-warning/30 bg-em-status-warning/10 p-3 text-xs text-em-status-warning"
          >
            Could not fetch full JSONB report body ({hydrationError.detail}). Showing recorded
            session metadata only.
          </div>
        )}

        {/* Metrics Summary */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5">
          <div className="rounded-md border border-em-border-default bg-em-workspace p-2.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              Score
            </div>
            <div className="text-sm font-semibold font-mono text-em-text-primary mt-0.5">
              {entry.score !== null ? `${entry.score} / 100` : 'Not Recorded'}
            </div>
          </div>

          <div className="rounded-md border border-em-border-default bg-em-workspace p-2.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              Errors
            </div>
            <div className="text-sm font-semibold font-mono text-em-text-primary mt-0.5">
              {entry.totalErrors !== null ? entry.totalErrors : 'Not Recorded'}
            </div>
          </div>

          <div className="rounded-md border border-em-border-default bg-em-workspace p-2.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              Warnings
            </div>
            <div className="text-sm font-semibold font-mono text-em-text-primary mt-0.5">
              {entry.totalWarnings !== null ? entry.totalWarnings : 'Not Recorded'}
            </div>
          </div>

          <div className="rounded-md border border-em-border-default bg-em-workspace p-2.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              Coverage Gaps
            </div>
            <div className="text-sm font-semibold font-mono text-em-text-primary mt-0.5">
              {entry.gapsDetected !== null ? entry.gapsDetected : 'N/A'}
            </div>
          </div>

          <div className="rounded-md border border-em-border-default bg-em-workspace p-2.5">
            <div className="text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              Duration
            </div>
            <div className="text-sm font-semibold font-mono text-em-text-primary mt-0.5">
              {entry.durationMs !== null ? `${entry.durationMs} ms` : 'N/A'}
            </div>
          </div>
        </div>

        {/* Target & Run Metadata */}
        <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 rounded-md border border-em-border-default bg-em-workspace p-3 text-xs">
          <div>
            <dt className="text-[10px] font-mono uppercase text-em-text-dim">Filename</dt>
            <dd className="font-mono text-em-text-primary mt-0.5 truncate">
              {entry.filename || 'N/A'}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] font-mono uppercase text-em-text-dim">Project</dt>
            <dd className="text-em-text-primary mt-0.5 truncate">{entry.projectName || 'N/A'}</dd>
          </div>
          <div>
            <dt className="text-[10px] font-mono uppercase text-em-text-dim">Language / Mode</dt>
            <dd className="font-mono text-em-text-primary mt-0.5">
              {entry.language} • {entry.analysisMode}
            </dd>
          </div>
          <div>
            <dt className="text-[10px] font-mono uppercase text-em-text-dim">Storage Status</dt>
            <dd className="font-mono text-em-text-primary mt-0.5">{entry.storageStatus}</dd>
          </div>
        </dl>

        {/* Category Summary */}
        {entry.summary && (
          <div className="space-y-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary">
              Category Summary
            </h4>
            <div className="flex flex-wrap gap-2">
              {Object.entries(entry.summary).map(([category, status]) => (
                <div
                  key={category}
                  className="inline-flex items-center gap-2 rounded-md border border-em-border-default bg-em-workspace px-2.5 py-1.5 text-xs"
                >
                  <span className="font-mono uppercase text-em-text-dim">{category}:</span>
                  <Badge variant={getSummaryVariant(String(status))} size="sm">
                    {String(status)}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Section Tabs */}
        <div
          role="tablist"
          aria-label="Historical report sections"
          className="flex flex-wrap items-center gap-1 border-b border-em-border-hairline pb-2"
        >
          {[
            { id: 'findings' as const, label: `Findings (${totalFindings})` },
            {
              id: 'coverage' as const,
              label: `Test Gaps & Recommendations (${entry.coverageGaps.length + entry.recommendations.length})`,
            },
            { id: 'raw' as const, label: 'Raw JSON Snapshot' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
                activeTab === tab.id
                  ? 'bg-em-accent-subtle text-em-accent-primary border border-em-accent-primary/30'
                  : 'text-em-text-muted hover:text-em-text-primary hover:bg-white/[0.04]'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Panels */}
        {activeTab === 'findings' && (
          <div className="space-y-2.5" role="tabpanel">
            {totalFindings === 0 ? (
              <div className="rounded-md border border-em-border-default bg-em-workspace p-4 text-xs text-em-text-muted flex items-start gap-2.5">
                {entry.storageStatus === 'DELETED' ? (
                  <>
                    <Info className="w-4 h-4 text-em-status-warning shrink-0 mt-0.5" />
                    <span>
                      Detailed JSONB report contents were deleted; only session audit metadata
                      remains.
                    </span>
                  </>
                ) : entry.source === 'database' &&
                  entry.totalErrors === null &&
                  entry.totalWarnings === null ? (
                  <>
                    <Info className="w-4 h-4 text-em-status-info shrink-0 mt-0.5" />
                    <span>
                      Static code findings were not serialized in this stored JSONB test-intelligence
                      report. Switch to the Test Gaps &amp; Recommendations tab or Raw JSON Snapshot.
                    </span>
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-4 h-4 text-em-status-success shrink-0 mt-0.5" />
                    <span>Zero errors or warnings were recorded in this snapshot.</span>
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
                {entry.errors.map((err, idx) => (
                  <FindingReadOnlyCard
                    key={`hist-err-${idx}-${err.type}-${err.line ?? 0}`}
                    finding={err}
                    severity="error"
                  />
                ))}
                {entry.warnings.map((warn, idx) => (
                  <FindingReadOnlyCard
                    key={`hist-warn-${idx}-${warn.type}-${warn.line ?? 0}`}
                    finding={warn}
                    severity="warning"
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'coverage' && (
          <div className="space-y-3" role="tabpanel">
            {entry.coverageGaps.length > 0 ? (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary">
                  Detected Coverage Gaps ({entry.coverageGaps.length})
                </h4>
                <div className="space-y-2 max-h-[260px] overflow-y-auto pr-1">
                  {entry.coverageGaps.map((gap, idx) => (
                    <div
                      key={`${gap.category}-${gap.param_name || 'param'}-${idx}`}
                      className="rounded-md border border-em-border-default bg-em-workspace p-3 text-xs space-y-1"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant="warning" size="sm">
                          {gap.severity || 'GAP'}
                        </Badge>
                        <span className="font-mono font-semibold text-em-text-primary">
                          {gap.category}
                        </span>
                        {gap.param_name && (
                          <span className="font-mono text-em-text-dim">
                            param: {gap.param_name}
                          </span>
                        )}
                      </div>
                      <p className="text-em-text-muted leading-relaxed">{gap.rationale}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-em-text-muted">
                No adaptive coverage gaps recorded in this snapshot.
              </p>
            )}

            {entry.generatedCandidates.length > 0 && (
              <p className="text-xs font-mono text-em-text-secondary">
                Generated test candidates preserved: {entry.generatedCandidates.length}
              </p>
            )}

            {entry.recommendations.length > 0 && (
              <div className="space-y-1.5">
                <h4 className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary">
                  Recommendations &amp; Caveats
                </h4>
                <ul className="list-disc list-inside space-y-1 text-xs text-em-text-muted">
                  {entry.recommendations.map((rec, idx) => (
                    <li key={idx}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {activeTab === 'raw' && (
          <div role="tabpanel">
            <pre className="rounded-md border border-em-border-default bg-em-canvas p-3 text-[11px] font-mono text-em-text-secondary max-h-[340px] overflow-auto">
              {JSON.stringify(entry.rawSnapshot, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </section>
  );
};
