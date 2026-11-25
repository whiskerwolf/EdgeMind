import React, { useMemo } from 'react';
import {
  AlertCircle,
  Loader2,
  RefreshCw,
  Sparkles,
  Square,
  WifiOff,
} from 'lucide-react';
import { FindingDiagnosisState, INITIAL_FINDING_DIAGNOSIS_STATE } from '../../context/AnalysisContext';
import { HealthStatus } from '../../types/api';
import { buildDiagnosisRequest, ExplorerFinding } from '../../utils/findingsHelpers';
import { SafeMarkdown } from '../../utils/safeMarkdown';
import { WorkspaceLanguage } from '../../utils/workspaceConfig';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export interface DiagnosisPanelProps {
  finding: ExplorerFinding;
  diagnosis?: FindingDiagnosisState;
  sourceCode: string | null;
  sourceLanguage: WorkspaceLanguage;
  healthStatus: HealthStatus;
  hasUnanalyzedChanges: boolean;
  onStartDiagnosis: () => void;
  onCancelDiagnosis: () => void;
}

export const DiagnosisPanel: React.FC<DiagnosisPanelProps> = ({
  finding,
  diagnosis = INITIAL_FINDING_DIAGNOSIS_STATE,
  sourceCode,
  sourceLanguage,
  healthStatus,
  hasUnanalyzedChanges,
  onStartDiagnosis,
  onCancelDiagnosis,
}) => {
  const isBackendOffline = healthStatus === 'disconnected' || healthStatus === 'error';
  const contextCheck = useMemo(
    () => buildDiagnosisRequest(finding, sourceCode, sourceLanguage),
    [finding, sourceCode, sourceLanguage]
  );

  const canInvoke = !isBackendOffline && contextCheck.request !== null;
  const isStreaming =
    diagnosis.status === 'connecting' || diagnosis.status === 'streaming';

  return (
    <section
      aria-labelledby="ai-diagnosis-heading"
      className="rounded-md border border-em-border-default bg-em-workspace p-3.5 space-y-3"
    >
      {/* Header & Controls */}
      <div className="flex flex-wrap items-start justify-between gap-2.5">
        <div className="space-y-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-em-accent-primary shrink-0" aria-hidden="true" />
            <h4
              id="ai-diagnosis-heading"
              className="text-xs font-semibold text-em-text-primary tracking-tight"
            >
              AI Diagnosis
            </h4>
            <Badge variant="info">AI-Generated · Unverified</Badge>
            {diagnosis.status === 'completed' && (
              <Badge variant="success">
                Completed
                {diagnosis.durationMs !== null
                  ? ` · ${(diagnosis.durationMs / 1000).toFixed(1)}s`
                  : ''}
              </Badge>
            )}
            {diagnosis.status === 'cancelled' && (
              <Badge variant="warning">Diagnosis Cancelled</Badge>
            )}
            {isStreaming && (
              <Badge variant="info">
                <Loader2 className="w-2.5 h-2.5 animate-spin" aria-hidden="true" />
                <span>{diagnosis.status === 'connecting' ? 'Connecting' : 'Streaming'}</span>
              </Badge>
            )}
          </div>
          <p className="text-[11px] text-em-text-muted leading-relaxed">
            Advisory explanation streamed via SSE. Never alters deterministic severity or static quality score.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {isStreaming ? (
            <Button
              variant="outline"
              size="sm"
              leftIcon={<Square className="w-3 h-3 fill-current" />}
              onClick={onCancelDiagnosis}
            >
              Cancel
            </Button>
          ) : diagnosis.status === 'idle' ? (
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Sparkles className="w-3.5 h-3.5 text-em-accent-primary" />}
              disabled={!canInvoke}
              onClick={onStartDiagnosis}
            >
              Explain with AI
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              leftIcon={<RefreshCw className="w-3 h-3" />}
              disabled={!canInvoke}
              onClick={onStartDiagnosis}
            >
              {diagnosis.status === 'completed' ? 'Regenerate' : 'Retry Diagnosis'}
            </Button>
          )}
        </div>
      </div>

      {/* Snapshot Synchronization Note */}
      {hasUnanalyzedChanges && contextCheck.request && (
        <p className="text-[11px] font-mono text-em-status-warning bg-em-status-warning/5 border border-em-status-warning/25 rounded px-2.5 py-1.5">
          Workspace contains unanalyzed edits; AI diagnosis evaluates the snapshot that generated this report.
        </p>
      )}

      {/* Pre-flight Availability Checks */}
      {isBackendOffline && (
        <div
          role="status"
          className="flex items-start gap-2 text-xs text-em-status-error bg-em-status-error/5 border border-em-status-error/25 rounded p-2.5"
        >
          <WifiOff className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden="true" />
          <span>Backend offline: connect to the EdgeMind server to stream AI diagnosis.</span>
        </div>
      )}

      {!isBackendOffline && contextCheck.unavailableReason && (
        <p className="text-xs text-em-text-muted bg-em-card border border-em-border-hairline rounded p-2.5 leading-relaxed">
          {contextCheck.unavailableReason}
        </p>
      )}

      {/* Streaming Loading Placeholder (before first chunk arrives) */}
      {isStreaming && !diagnosis.content && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 text-xs font-mono text-em-text-muted py-2"
        >
          <Loader2 className="w-3.5 h-3.5 animate-spin text-em-accent-primary" aria-hidden="true" />
          <span>Waiting for streamed diagnosis tokens from /api/v1/diagnose/stream...</span>
        </div>
      )}

      {/* Error Banner */}
      {diagnosis.status === 'error' && diagnosis.errorMessage && (
        <div
          role="alert"
          className="rounded border border-em-status-error/30 bg-em-status-error/5 p-3 flex items-start gap-2 text-xs text-em-status-error"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1 min-w-0">
            <p className="font-medium break-words">{diagnosis.errorMessage}</p>
            {!diagnosis.retryable && (
              <p className="text-[11px] text-em-text-muted">
                Deterministic static findings above remain complete and authoritative.
              </p>
            )}
          </div>
        </div>
      )}

      {/* Streamed / Completed / Partial Cancelled Markdown Output */}
      {diagnosis.content && (
        <div className="rounded border border-em-border-hairline bg-em-card p-3 space-y-2">
          <SafeMarkdown content={diagnosis.content} />
          {diagnosis.sessionId && (
            <div className="pt-2 border-t border-em-border-hairline flex items-center justify-between text-[10px] font-mono text-em-text-dim">
              <span>Session: {diagnosis.sessionId}</span>
              <span>Advisory AI Output</span>
            </div>
          )}
        </div>
      )}
    </section>
  );
};
