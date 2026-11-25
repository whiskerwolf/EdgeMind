import React from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, CheckCircle2, ArrowRight } from 'lucide-react';
import { AnalysisReport, HealthStatus } from '../../types/api';
import { Badge } from '../ui/Badge';
import { Skeleton } from '../ui/Skeleton';

export interface SeverityDistributionSectionProps {
  report: AnalysisReport | null;
  healthStatus: HealthStatus;
  isAnalyzing: boolean;
}

export const SeverityDistributionSection: React.FC<SeverityDistributionSectionProps> = ({
  report,
  healthStatus,
  isAnalyzing,
}) => {
  const totalFindings = report ? report.total_errors + report.total_warnings : 0;
  const errorPct =
    report && totalFindings > 0 ? Math.round((report.total_errors / totalFindings) * 100) : 0;
  const warningPct = report && totalFindings > 0 ? 100 - errorPct : 0;

  const previewFindings = report
    ? [
        ...report.errors.map((f) => ({ ...f, severity: 'error' as const })),
        ...report.warnings.map((f) => ({ ...f, severity: 'warning' as const })),
      ].slice(0, 3)
    : [];

  return (
    <section
      aria-labelledby="severity-distribution-heading"
      className="rounded-lg border border-em-border-default bg-em-surface-card p-4 flex flex-col justify-between"
    >
      <div>
        <div className="flex items-center justify-between gap-2 pb-3 border-b border-em-border-hairline">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-em-text-muted shrink-0" />
            <h3
              id="severity-distribution-heading"
              className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
            >
              Severity Distribution
            </h3>
          </div>

          {report && (
            <span className="text-[11px] font-mono tabular-nums text-em-text-muted">
              Total: {totalFindings}
            </span>
          )}
        </div>

        {isAnalyzing && (
          <div className="space-y-3 pt-4">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        )}

        {!isAnalyzing && !report && (
          <div className="py-6 text-center">
            <p className="text-xs text-em-text-muted">
              {healthStatus === 'disconnected'
                ? 'Severity metrics are unavailable while the backend is disconnected.'
                : 'No analysis performed yet. Severity breakdown requires a completed analysis report.'}
            </p>
            <p className="mt-2 text-xs font-mono text-em-text-dim">Errors: — · Warnings: —</p>
          </div>
        )}

        {!isAnalyzing && report && totalFindings === 0 && (
          <div className="py-5 px-3 flex flex-col items-center text-center">
            <CheckCircle2 className="w-6 h-6 text-em-status-success mb-2" />
            <p className="text-xs font-semibold text-em-text-primary">
              Zero Findings Detected
            </p>
            <p className="text-xs text-em-text-muted mt-1">
              0 errors and 0 warnings reported across all static checks for <code className="text-em-text-secondary">{report.file}</code>.
            </p>
          </div>
        )}

        {!isAnalyzing && report && totalFindings > 0 && (
          <div className="pt-3 space-y-3">
            {/* Compact Segmented Distribution Bar */}
            <div>
              <div
                className="h-2.5 w-full rounded-sm bg-white/[0.05] overflow-hidden flex"
                role="img"
                aria-label={`Severity distribution: ${report.total_errors} errors (${errorPct}%), ${report.total_warnings} warnings (${warningPct}%)`}
              >
                {report.total_errors > 0 && (
                  <div
                    className="h-full bg-em-status-error transition-all duration-200"
                    style={{ width: `${errorPct}%` }}
                  />
                )}
                {report.total_warnings > 0 && (
                  <div
                    className="h-full bg-em-status-warning transition-all duration-200"
                    style={{ width: `${warningPct}%` }}
                  />
                )}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 mt-2 text-xs font-mono tabular-nums">
                <div className="flex items-center gap-1.5 text-em-text-secondary">
                  <span className="w-2 h-2 rounded-full bg-em-status-error" />
                  <span>Errors: {report.total_errors}</span>
                  <span className="text-em-text-dim">({errorPct}%)</span>
                </div>
                <div className="flex items-center gap-1.5 text-em-text-secondary">
                  <span className="w-2 h-2 rounded-full bg-em-status-warning" />
                  <span>Warnings: {report.total_warnings}</span>
                  <span className="text-em-text-dim">({warningPct}%)</span>
                </div>
              </div>
            </div>

            {/* Compact Preview of Top Findings */}
            <div className="space-y-1.5 pt-2 border-t border-em-border-hairline">
              {previewFindings.map((finding, idx) => (
                <div
                  key={`${finding.type}-${finding.line}-${idx}`}
                  className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded bg-em-surface-workspace border border-em-border-hairline text-xs"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <Badge variant={finding.severity === 'error' ? 'error' : 'warning'}>
                      {finding.type}
                    </Badge>
                    <span className="text-em-text-secondary truncate">{finding.message}</span>
                  </div>
                  <span className="text-[11px] font-mono tabular-nums text-em-text-dim shrink-0">
                    L{finding.line || finding.line_number || 0}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {report && (
        <div className="pt-3 mt-3 border-t border-em-border-hairline flex justify-end">
          <Link
            to="/findings"
            className="inline-flex items-center gap-1 text-xs font-medium text-em-accent-primary hover:underline"
          >
            <span>View Findings Explorer</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}
    </section>
  );
};
