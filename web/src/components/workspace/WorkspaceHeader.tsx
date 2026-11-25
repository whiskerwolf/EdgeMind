import React from 'react';
import { Play } from 'lucide-react';
import { AnalysisReport, HealthStatus } from '../../types/api';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export interface WorkspaceHeaderProps {
  healthStatus: HealthStatus;
  hasCode: boolean;
  isSupportedLanguage: boolean;
  isAnalyzing: boolean;
  hasUnanalyzedChanges: boolean;
  hasValidationError: boolean;
  report: AnalysisReport | null;
  onAnalyze: () => void;
}

export const WorkspaceHeader: React.FC<WorkspaceHeaderProps> = ({
  healthStatus,
  hasCode,
  isSupportedLanguage,
  isAnalyzing,
  hasUnanalyzedChanges,
  hasValidationError,
  report,
  onAnalyze,
}) => {
  const isBackendOffline = healthStatus === 'disconnected' || healthStatus === 'error';
  const canAnalyze = hasCode && isSupportedLanguage && !isAnalyzing && !isBackendOffline && !hasValidationError;

  let statusBadge: { label: string; variant: 'neutral' | 'info' | 'success' | 'warning' | 'error' } = {
    label: 'Empty',
    variant: 'neutral',
  };

  if (isBackendOffline) {
    statusBadge = { label: 'Backend Offline', variant: 'error' };
  } else if (!isSupportedLanguage) {
    statusBadge = { label: 'Unsupported Language', variant: 'warning' };
  } else if (isAnalyzing) {
    statusBadge = { label: 'Analyzing...', variant: 'info' };
  } else if (!hasCode) {
    statusBadge = { label: 'Empty', variant: 'neutral' };
  } else if (hasUnanalyzedChanges) {
    statusBadge = { label: 'Unanalyzed Changes', variant: 'neutral' };
  } else if (report) {
    const upper = report.overall_status.toUpperCase();
    statusBadge = {
      label: `${report.overall_status} (${report.score}/100)`,
      variant: upper === 'PASS' ? 'success' : upper.includes('WARNING') ? 'warning' : 'error',
    };
  } else {
    statusBadge = { label: 'Ready to Analyze', variant: 'info' };
  }

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-em-border-default pb-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">Code Workspace</h2>
          <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
        </div>
        <p className="text-xs text-em-text-muted mt-1">
          Write, paste, or upload Python code to execute static syntax, logic, quality, and complexity checks.
        </p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant="primary"
          size="md"
          isLoading={isAnalyzing}
          disabled={!canAnalyze}
          leftIcon={<Play className="w-3.5 h-3.5 fill-current" />}
          onClick={onAnalyze}
          title="Run static analysis (⌘↵)"
        >
          <span>{isAnalyzing ? 'Analyzing...' : 'Analyze Code'}</span>
          <span className="text-[10px] font-mono opacity-80 hidden md:inline ml-1">⌘↵</span>
        </Button>
      </div>
    </div>
  );
};
