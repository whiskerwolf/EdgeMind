import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useHealthContext } from '../context/HealthContext';
import { useAnalysisContext } from '../context/AnalysisContext';
import { useOptionalSettings } from '../context/SettingsContext';
import { WorkspaceHeader } from '../components/workspace/WorkspaceHeader';
import { AnalysisControls } from '../components/workspace/AnalysisControls';
import { CodeEditorPanel } from '../components/workspace/CodeEditorPanel';
import { WorkspaceResultsPanel } from '../components/workspace/WorkspaceResultsPanel';
import type { WorkspaceFindingDecoration } from '../components/workspace/MonacoEditorAdapter';
import {
  formatByteSize,
  getUtf8ByteLength,
  inferLanguageFromFilename,
  isSupportedLanguage,
  MAX_SOURCE_CODE_BYTES,
  validateWorkspaceFilename,
  WORKSPACE_SAMPLES,
  WorkspaceSample,
} from '../utils/workspaceConfig';
import { cn } from '../utils/cn';

type MobileTab = 'editor' | 'results';

export const WorkspacePage: React.FC = () => {
  const navigate = useNavigate();
  const { status: healthStatus } = useHealthContext();
  const settings = useOptionalSettings();
  const {
    latestReport,
    latestDurationMs,
    isAnalyzing,
    analysisError,
    runAnalysis,
    workspaceCode,
    workspaceFilename,
    workspaceLanguage,
    hasUnanalyzedChanges,
    setWorkspaceCode,
    setWorkspaceFilename,
    setWorkspaceLanguage,
    clearWorkspaceResult,
    setSelectedFindingId,
    pendingWorkspaceNavigation,
    clearPendingWorkspaceNavigation,
  } = useAnalysisContext();

  const [mobileTab, setMobileTab] = useState<MobileTab>('editor');
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [activeFindingKey, setActiveFindingKey] = useState<string | null>(null);
  const [navigationTarget, setNavigationTarget] = useState<{ line: number; seq: number } | null>(
    null
  );

  useEffect(() => {
    if (!pendingWorkspaceNavigation) return;
    const target = pendingWorkspaceNavigation;
    clearPendingWorkspaceNavigation();

    setActiveFindingKey(target.findingId);
    if (target.line !== null && target.line >= 1) {
      const totalLines = Math.max(1, workspaceCode ? workspaceCode.split('\n').length : 1);
      const boundedLine = Math.min(target.line, totalLines);
      setNavigationTarget((prev) => ({ line: boundedLine, seq: (prev?.seq ?? 0) + 1 }));
      if (typeof window !== 'undefined' && window.innerWidth < 768) {
        setMobileTab('editor');
      }
    }
  }, [pendingWorkspaceNavigation, clearPendingWorkspaceNavigation, workspaceCode]);

  const hasCode = workspaceCode.trim().length > 0;
  const codeBytes = useMemo(() => getUtf8ByteLength(workspaceCode), [workspaceCode]);
  const filenameError = useMemo(
    () => validateWorkspaceFilename(workspaceFilename),
    [workspaceFilename]
  );
  const sizeExceeded = codeBytes > MAX_SOURCE_CODE_BYTES;
  const languageSupported = isSupportedLanguage(workspaceLanguage);
  const hasValidationError = Boolean(filenameError || sizeExceeded || uploadError);

  // Only show editor decorations when report matches current code & filename
  const activeDecorations = useMemo<WorkspaceFindingDecoration[]>(() => {
    if (!latestReport || hasUnanalyzedChanges) return [];
    return [
      ...(latestReport.errors || []).map((f) => ({ ...f, severity: 'error' as const })),
      ...(latestReport.warnings || []).map((f) => ({ ...f, severity: 'warning' as const })),
    ];
  }, [latestReport, hasUnanalyzedChanges]);

  const findingsTotal = latestReport
    ? latestReport.total_errors + latestReport.total_warnings
    : null;

  const handleAnalyze = async () => {
    if (!hasCode || !languageSupported || isAnalyzing || hasValidationError) return;
    if (healthStatus === 'disconnected' || healthStatus === 'error') return;

    setUploadError(null);
    setActiveFindingKey(null);
    const result = await runAnalysis({
      code: workspaceCode,
      filename: workspaceFilename.trim() || 'snippet.py',
      static_only: true,
    });
    if (result && typeof window !== 'undefined' && window.innerWidth < 768) {
      setMobileTab('results');
    }
  };

  const handleInsertSample = (sample: WorkspaceSample) => {
    setUploadError(null);
    setActiveFindingKey(null);
    setNavigationTarget(null);
    setWorkspaceCode(sample.code);
    setWorkspaceFilename(sample.filename);
    setWorkspaceLanguage(sample.language);
  };

  const handleUploadFile = async (file: File) => {
    setUploadError(null);
    if (file.size > MAX_SOURCE_CODE_BYTES) {
      setUploadError(
        `File '${file.name}' (${formatByteSize(file.size)}) exceeds the 64 KiB static analysis limit.`
      );
      return;
    }

    try {
      const content = await file.text();
      if (getUtf8ByteLength(content) > MAX_SOURCE_CODE_BYTES) {
        setUploadError(
          `Decoded file '${file.name}' exceeds the 64 KiB static analysis limit.`
        );
        return;
      }
      const cleanName = file.name.replace(/^.*[\\/]/, '') || 'snippet.py';
      setWorkspaceCode(content);
      setWorkspaceFilename(cleanName);
      setWorkspaceLanguage(inferLanguageFromFilename(cleanName));
      setActiveFindingKey(null);
      setNavigationTarget(null);
    } catch {
      setUploadError(`Failed to read file '${file.name}'.`);
    }
  };

  const handleClear = () => {
    setUploadError(null);
    setActiveFindingKey(null);
    setNavigationTarget(null);
    setWorkspaceCode('');
    setWorkspaceFilename(settings.defaultFilename || 'snippet.py');
    setWorkspaceLanguage('python');
    clearWorkspaceResult();
  };

  const handleSelectFinding = (key: string, line: number) => {
    setActiveFindingKey(key);
    setNavigationTarget((prev) => ({ line, seq: (prev?.seq ?? 0) + 1 }));
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setMobileTab('editor');
    }
  };

  return (
    <div className="space-y-4">
      <WorkspaceHeader
        healthStatus={healthStatus}
        hasCode={hasCode}
        isSupportedLanguage={languageSupported}
        isAnalyzing={isAnalyzing}
        hasUnanalyzedChanges={hasUnanalyzedChanges}
        hasValidationError={hasValidationError}
        report={latestReport}
        onAnalyze={() => {
          void handleAnalyze();
        }}
      />

      {/* Mobile Tabbed Workbench Switcher (< 768px) */}
      <div
        className="md:hidden flex rounded-md border border-em-border-default bg-em-surface-card p-1 gap-1"
        role="tablist"
        aria-label="Mobile workspace sections"
      >
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === 'editor'}
          onClick={() => setMobileTab('editor')}
          className={cn(
            'flex-1 py-2 text-xs font-medium rounded transition-colors',
            mobileTab === 'editor'
              ? 'bg-em-surface-elevated text-em-text-primary'
              : 'text-em-text-muted hover:text-em-text-primary'
          )}
        >
          Code Editor
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mobileTab === 'results'}
          onClick={() => setMobileTab('results')}
          className={cn(
            'flex-1 py-2 text-xs font-medium rounded transition-colors',
            mobileTab === 'results'
              ? 'bg-em-surface-elevated text-em-text-primary'
              : 'text-em-text-muted hover:text-em-text-primary'
          )}
        >
          Results {findingsTotal !== null ? `(${findingsTotal})` : ''}
        </button>
      </div>

      {/* Inline File / Size Validation Banner */}
      {(uploadError || sizeExceeded) && (
        <div
          role="alert"
          className="p-3 rounded-md border border-em-status-error/30 bg-em-status-error/5 text-xs text-em-status-error flex items-center justify-between gap-2"
        >
          <span>
            {uploadError ||
              `Source code (${formatByteSize(codeBytes)}) exceeds the maximum 64 KiB limit.`}
          </span>
          {uploadError && (
            <button
              type="button"
              onClick={() => setUploadError(null)}
              className="text-xs underline shrink-0"
            >
              Dismiss
            </button>
          )}
        </div>
      )}

      {/* Split Desktop / Stacked Tablet / Tabbed Mobile Workbench */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        <div
          className={cn(
            'lg:col-span-7 space-y-3',
            mobileTab !== 'editor' && 'hidden md:block'
          )}
        >
          <AnalysisControls
            filename={workspaceFilename}
            filenameError={filenameError}
            language={workspaceLanguage}
            codeBytes={codeBytes}
            isAnalyzing={isAnalyzing}
            hasCode={hasCode}
            onFilenameChange={(val) => {
              setUploadError(null);
              setWorkspaceFilename(val);
            }}
            onLanguageChange={(lang) => {
              setUploadError(null);
              setWorkspaceLanguage(lang);
            }}
            onInsertSample={handleInsertSample}
            onUploadFile={(f) => {
              void handleUploadFile(f);
            }}
            onClear={handleClear}
          />

          <CodeEditorPanel
            value={workspaceCode}
            language={workspaceLanguage}
            filename={workspaceFilename}
            findings={activeDecorations}
            navigationTarget={navigationTarget}
            onChange={(val) => {
              if (uploadError) setUploadError(null);
              setWorkspaceCode(val);
            }}
            onFileDrop={(f) => {
              void handleUploadFile(f);
            }}
            onAnalyzeShortcut={() => {
              void handleAnalyze();
            }}
          />
        </div>

        <div
          className={cn(
            'lg:col-span-5',
            mobileTab !== 'results' && 'hidden md:block'
          )}
        >
          <WorkspaceResultsPanel
            report={latestReport}
            durationMs={latestDurationMs}
            isAnalyzing={isAnalyzing}
            error={analysisError}
            healthStatus={healthStatus}
            hasCode={hasCode}
            isSupportedLanguage={languageSupported}
            hasUnanalyzedChanges={hasUnanalyzedChanges}
            activeFindingKey={activeFindingKey}
            onSelectFinding={handleSelectFinding}
            onInspectInFindings={(findingId) => {
              setSelectedFindingId(findingId);
              navigate('/findings');
            }}
            onRetryAnalyze={() => {
              void handleAnalyze();
            }}
            onInsertDefaultSample={() => handleInsertSample(WORKSPACE_SAMPLES[0])}
          />
        </div>
      </div>
    </div>
  );
};
