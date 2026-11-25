import React from 'react';
import { Link } from 'react-router-dom';
import { Code2 } from 'lucide-react';
import { AnalysisReport, HealthStatus } from '../../types/api';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export interface FindingsHeaderProps {
  report: AnalysisReport | null;
  totalFindings: number;
  errorCount: number;
  warningCount: number;
  healthStatus: HealthStatus;
  hasUnanalyzedChanges: boolean;
}

function getReportVariant(status: string): 'success' | 'warning' | 'error' | 'neutral' {
  const upper = status.toUpperCase();
  if (upper === 'PASS') return 'success';
  if (upper.includes('WARNING')) return 'warning';
  if (upper === 'FAIL') return 'error';
  return 'neutral';
}

export const FindingsHeader: React.FC<FindingsHeaderProps> = ({
  report,
  totalFindings,
  errorCount,
  warningCount,
  healthStatus,
  hasUnanalyzedChanges,
}) => {
  const isBackendOffline = healthStatus === 'disconnected' || healthStatus === 'error';

  return (
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-em-border-default pb-4">
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">
            Findings Explorer
          </h2>

          {report ? (
            <Badge variant={getReportVariant(report.overall_status)}>
              {report.overall_status} ({report.score}/100)
            </Badge>
          ) : (
            <Badge variant="neutral">No Active Analysis</Badge>
          )}

          {hasUnanalyzedChanges && <Badge variant="warning">Workspace Modified</Badge>}
          {isBackendOffline && <Badge variant="error">Backend Offline</Badge>}
        </div>

        <p className="text-xs text-em-text-muted leading-relaxed">
          Inspect, filter, and prioritize static analyzer findings, jump to source lines in Workspace, or request optional streaming AI explanations.
        </p>

        {report && (
          <div className="flex flex-wrap items-center gap-3 pt-0.5 text-[11px] font-mono tabular-nums text-em-text-muted">
            <span>
              File: <strong className="text-em-text-primary font-medium">{report.file || report.file_path}</strong>
            </span>
            <span className="text-em-text-dim">•</span>
            <span>
              Total: <strong className="text-em-text-primary">{totalFindings}</strong>
            </span>
            <span>
              Errors: <strong className="text-em-status-error">{errorCount}</strong>
            </span>
            <span>
              Warnings: <strong className="text-em-status-warning">{warningCount}</strong>
            </span>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <Link to="/workspace">
          <Button variant="secondary" size="sm" leftIcon={<Code2 className="w-3.5 h-3.5" />}>
            {report ? 'Back to Workspace' : 'Open Workspace'}
          </Button>
        </Link>
      </div>
    </div>
  );
};
