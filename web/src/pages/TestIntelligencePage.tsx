import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Code2,
  Play,
  SlidersHorizontal,
  WifiOff,
} from 'lucide-react';
import { useHealthContext } from '../context/HealthContext';
import { useAnalysisContext } from '../context/AnalysisContext';
import { useOptionalSettings } from '../context/SettingsContext';
import {
  computeTestingPriority,
  detectStaticTestingGaps,
  mapTestsToSources,
  parseBaselineTestInputs,
  parseSuppliedFile,
  ParsedTestFile,
  SAMPLE_TEST_INTELLIGENCE_SUITE,
} from '../utils/testIntelligenceHelpers';
import { TestIntelligenceHeader } from '../components/testIntelligence/TestIntelligenceHeader';
import { TestSummary } from '../components/testIntelligence/TestSummary';
import { TestExplorer } from '../components/testIntelligence/TestExplorer';
import { TestRelationshipPanel } from '../components/testIntelligence/TestRelationshipPanel';
import { TestingGapsPanel } from '../components/testIntelligence/TestingGapsPanel';
import { TestingPriorityPanel } from '../components/testIntelligence/TestingPriorityPanel';
import { TestExecutionPanel } from '../components/testIntelligence/TestExecutionPanel';
import { Button } from '../components/ui/Button';

export const TestIntelligencePage: React.FC = () => {
  const navigate = useNavigate();
  const { status: healthStatus } = useHealthContext();
  const settings = useOptionalSettings();
  const {
    latestReport,
    workspaceCode,
    workspaceFilename,
    workspaceLanguage,
    setWorkspaceCode,
    setWorkspaceFilename,
    setWorkspaceLanguage,
    edgeMindReport,
    isEdgeMindAnalyzing,
    edgeMindError,
    runEdgeMindAnalysis,
    suppliedFiles,
    addSuppliedFiles,
    removeSuppliedFile,
    clearSuppliedFiles,
    baselineTestsText,
    setBaselineTestsText,
    constraintsText,
    setConstraintsText,
    openCodeInWorkspace,
  } = useAnalysisContext();

  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [showInputsPanel, setShowInputsPanel] = useState(false);

  const isBackendOffline = healthStatus === 'disconnected' || healthStatus === 'error';
  const hasWorkspaceCode = workspaceCode.trim().length > 0;
  const isPythonWorkspace = workspaceLanguage === 'python';

  // Parse user-supplied test/source files deterministically without execution
  const parsedSuppliedFiles = useMemo(
    () => suppliedFiles.map((f) => parseSuppliedFile(f)),
    [suppliedFiles]
  );

  // Separate test files vs additional uploaded source files, plus include active Python Workspace file
  const discoveredTestFiles = useMemo(
    () => parsedSuppliedFiles.filter((f) => f.role === 'test'),
    [parsedSuppliedFiles]
  );

  const sourceModules = useMemo<ParsedTestFile[]>(() => {
    const modules: ParsedTestFile[] = parsedSuppliedFiles.filter((f) => f.role === 'source');
    if (hasWorkspaceCode && isPythonWorkspace) {
      const wsName = (workspaceFilename.trim() || 'snippet.py').split(/[\\/]/).pop() || 'snippet.py';
      const alreadyListed = modules.some((m) => m.filename.toLowerCase() === wsName.toLowerCase());
      if (!alreadyListed) {
        modules.unshift(
          parseSuppliedFile(
            {
              id: 'active-workspace-source',
              filename: wsName,
              content: workspaceCode,
            },
            'source'
          )
        );
      }
    }
    return modules;
  }, [parsedSuppliedFiles, hasWorkspaceCode, isPythonWorkspace, workspaceFilename, workspaceCode]);

  const parsedTestCasesCount = useMemo(() => {
    const supportedTests = discoveredTestFiles.filter((f) => f.isSupported);
    if (supportedTests.length === 0) return null;
    return supportedTests.reduce((sum, f) => sum + f.testCases.length, 0);
  }, [discoveredTestFiles]);

  const supportedTestFilesCount = useMemo(
    () => discoveredTestFiles.filter((f) => f.isSupported).length,
    [discoveredTestFiles]
  );

  const baselineParseResult = useMemo(
    () => parseBaselineTestInputs(baselineTestsText),
    [baselineTestsText]
  );

  const relationships = useMemo(
    () => mapTestsToSources(discoveredTestFiles, sourceModules, workspaceFilename),
    [discoveredTestFiles, sourceModules, workspaceFilename]
  );

  const staticGaps = useMemo(
    () => detectStaticTestingGaps(sourceModules, discoveredTestFiles, relationships),
    [sourceModules, discoveredTestFiles, relationships]
  );

  const priorityItems = useMemo(
    () =>
      computeTestingPriority(
        sourceModules,
        discoveredTestFiles,
        relationships,
        workspaceFilename,
        latestReport,
        edgeMindReport
      ),
    [
      sourceModules,
      discoveredTestFiles,
      relationships,
      workspaceFilename,
      latestReport,
      edgeMindReport,
    ]
  );

  const primaryPythonTarget = useMemo(() => {
    if (hasWorkspaceCode && isPythonWorkspace) {
      return {
        code: workspaceCode,
        filename: workspaceFilename.trim() || 'snippet.py',
      };
    }
    const firstUploadedSource = parsedSuppliedFiles.find((f) => f.isSupported && f.role === 'source');
    if (firstUploadedSource) {
      const raw = suppliedFiles.find((s) => s.id === firstUploadedSource.id);
      if (raw && raw.content.trim()) {
        return { code: raw.content, filename: raw.filename };
      }
    }
    return null;
  }, [hasWorkspaceCode, isPythonWorkspace, workspaceCode, workspaceFilename, parsedSuppliedFiles, suppliedFiles]);

  const canRunAdaptive =
    Boolean(primaryPythonTarget) &&
    !isBackendOffline &&
    !isEdgeMindAnalyzing &&
    !baselineParseResult.error;

  const handleRunAdaptiveAnalysis = async () => {
    if (!primaryPythonTarget || isBackendOffline || isEdgeMindAnalyzing || baselineParseResult.error) {
      return;
    }
    const constraints = constraintsText
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);

    await runEdgeMindAnalysis({
      code: primaryPythonTarget.code,
      filename: primaryPythonTarget.filename,
      problem_context:
        constraints.length > 0 ? { constraints, platform: 'local' } : undefined,
      test_cases: baselineParseResult.testCases,
      max_candidates: settings.defaultMaxCandidates,
      static_only: true,
    });
  };

  const handleLoadSampleSuite = () => {
    if (!hasWorkspaceCode) {
      setWorkspaceCode(SAMPLE_TEST_INTELLIGENCE_SUITE.sourceCode);
      setWorkspaceFilename(SAMPLE_TEST_INTELLIGENCE_SUITE.sourceFilename);
      setWorkspaceLanguage('python');
    } else {
      addSuppliedFiles([
        {
          id: `sample-src-${SAMPLE_TEST_INTELLIGENCE_SUITE.id}`,
          filename: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceFilename,
          content: SAMPLE_TEST_INTELLIGENCE_SUITE.sourceCode,
        },
      ]);
    }
    addSuppliedFiles([
      {
        id: `sample-test-${SAMPLE_TEST_INTELLIGENCE_SUITE.id}`,
        filename: SAMPLE_TEST_INTELLIGENCE_SUITE.testFilename,
        content: SAMPLE_TEST_INTELLIGENCE_SUITE.testCode,
      },
    ]);
    if (!baselineTestsText.trim()) {
      setBaselineTestsText(SAMPLE_TEST_INTELLIGENCE_SUITE.baselineInputsJson);
    }
    if (!constraintsText.trim()) {
      setConstraintsText(SAMPLE_TEST_INTELLIGENCE_SUITE.constraintsText);
    }
  };

  const handleOpenSourceInWorkspace = (sourceFilename: string, line: number | null = null) => {
    const cleanWs = (workspaceFilename || '').split(/[\\/]/).pop()?.toLowerCase();
    if (hasWorkspaceCode && cleanWs === sourceFilename.toLowerCase()) {
      openCodeInWorkspace({ line });
      navigate('/workspace');
      return;
    }

    const supplied = suppliedFiles.find(
      (f) => f.filename.toLowerCase() === sourceFilename.toLowerCase()
    );
    if (supplied) {
      openCodeInWorkspace({
        code: supplied.content,
        filename: supplied.filename,
        language: 'python',
        line,
      });
      navigate('/workspace');
      return;
    }

    openCodeInWorkspace({ line });
    navigate('/workspace');
  };

  const handleSelectExplorerFile = (file: ParsedTestFile) => {
    setSelectedFileId(file.id);
  };

  const handleClearAllFiles = () => {
    setSelectedFileId(null);
    clearSuppliedFiles();
  };

  return (
    <div className="space-y-4">
      <TestIntelligenceHeader
        workspaceFilename={primaryPythonTarget?.filename || workspaceFilename}
        hasWorkspaceCode={Boolean(primaryPythonTarget)}
        workspaceLanguage={workspaceLanguage}
        healthStatus={healthStatus}
        isAnalyzing={isEdgeMindAnalyzing}
        canRunAdaptive={canRunAdaptive}
        suppliedTestFileCount={supportedTestFilesCount}
        onRunAdaptive={() => {
          void handleRunAdaptiveAnalysis();
        }}
      />

      {/* Offline / Unsupported Language Alerts */}
      {isBackendOffline && (
        <div
          role="alert"
          className="p-3 rounded-md border border-em-status-error/30 bg-em-status-error/5 flex items-start gap-2.5"
        >
          <WifiOff className="w-4 h-4 text-em-status-error shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="text-xs font-semibold text-em-text-primary">Backend Disconnected</p>
            <p className="text-xs text-em-text-muted mt-0.5 leading-relaxed">
              EdgeMind API is unreachable. Backend candidate synthesis (/api/v1/edgemind/analyze) is disabled, while client-side test file parsing remains available.
            </p>
          </div>
        </div>
      )}

      {!isPythonWorkspace && (
        <div
          role="alert"
          className="p-3 rounded-md border border-em-status-warning/30 bg-em-status-warning/5 flex items-start gap-2.5"
        >
          <AlertTriangle className="w-4 h-4 text-em-status-warning shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="text-xs font-semibold text-em-text-primary">
              Unsupported Workspace Language ({workspaceLanguage})
            </p>
            <p className="text-xs text-em-text-muted mt-0.5 leading-relaxed">
              EdgeMind static analysis and Adaptive Test Intelligence only support Python source code. Switch Workspace language to Python 3 or upload a Python module to analyze.
            </p>
          </div>
        </div>
      )}

      {/* Honest Metrics & Availability Strip */}
      <TestSummary
        discoveredTestFilesCount={supportedTestFilesCount}
        discoveredTestCasesCount={parsedTestCasesCount}
        backendReport={edgeMindReport}
        staticGapsCount={supportedTestFilesCount > 0 ? staticGaps.length : null}
      />

      {/* Target Code & Optional Baseline Inputs / Constraints Card */}
      <section
        aria-label="Analysis target and baseline inputs"
        className="rounded-lg border border-em-border-default bg-em-card overflow-hidden"
      >
        <div className="px-4 py-2.5 flex flex-wrap items-center justify-between gap-2 bg-em-card">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Code2 className="w-4 h-4 text-em-accent-primary shrink-0" aria-hidden="true" />
            <span className="font-medium text-em-text-primary">
              {primaryPythonTarget
                ? `Active Python Target: ${primaryPythonTarget.filename}`
                : 'No Python Source Code Loaded'}
            </span>
            <span className="text-em-text-muted text-[11px]">
              {primaryPythonTarget
                ? `(${primaryPythonTarget.code.split('\n').length} lines ready for /api/v1/edgemind/analyze)`
                : 'Write Python code in Workspace, upload a .py source file, or load a sample suite.'}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {!primaryPythonTarget && (
              <Button variant="secondary" size="sm" onClick={handleLoadSampleSuite}>
                Load Sample Suite
              </Button>
            )}
            <button
              type="button"
              onClick={() => setShowInputsPanel((prev) => !prev)}
              aria-expanded={showInputsPanel}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded border border-em-border-default bg-em-workspace hover:bg-em-elevated text-xs font-mono text-em-text-secondary transition-colors"
            >
              <SlidersHorizontal className="w-3 h-3" aria-hidden="true" />
              <span>Baseline Inputs & Constraints</span>
              {showInputsPanel ? (
                <ChevronDown className="w-3.5 h-3.5" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>

        {showInputsPanel && (
          <div className="p-4 border-t border-em-border-hairline bg-em-workspace grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label
                htmlFor="ti-baseline-inputs"
                className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
              >
                Optional Baseline Test Inputs (JSON array or STDIN blocks)
              </label>
              <textarea
                id="ti-baseline-inputs"
                rows={4}
                value={baselineTestsText}
                onChange={(e) => setBaselineTestsText(e.target.value)}
                placeholder={'[{"nums": [2, 7, 11, 15], "target": 9}]'}
                className="w-full rounded-md border border-em-border-default bg-em-canvas p-2.5 text-xs font-mono text-em-text-primary placeholder:text-em-text-dim focus:outline-none focus:border-em-accent-primary"
              />
              {baselineParseResult.error && (
                <p className="text-[11px] text-em-status-error">{baselineParseResult.error}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="ti-constraints-input"
                className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
              >
                Optional Constraints (One per line)
              </label>
              <textarea
                id="ti-constraints-input"
                rows={4}
                value={constraintsText}
                onChange={(e) => setConstraintsText(e.target.value)}
                placeholder={'2 <= nums.length <= 10^4\n-10^9 <= nums[i] <= 10^9'}
                className="w-full rounded-md border border-em-border-default bg-em-canvas p-2.5 text-xs font-mono text-em-text-primary placeholder:text-em-text-dim focus:outline-none focus:border-em-accent-primary"
              />
              <div className="flex justify-end pt-1">
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!canRunAdaptive}
                  isLoading={isEdgeMindAnalyzing}
                  leftIcon={<Play className="w-3 h-3 fill-current" />}
                  onClick={() => {
                    void handleRunAdaptiveAnalysis();
                  }}
                >
                  Execute with Supplied Context
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Explorer & Test-to-Code Mapping */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        <div className="lg:col-span-6">
          <TestExplorer
            parsedFiles={parsedSuppliedFiles}
            selectedFileId={selectedFileId}
            onSelectFile={handleSelectExplorerFile}
            onAddFiles={addSuppliedFiles}
            onRemoveFile={removeSuppliedFile}
            onClearAllFiles={handleClearAllFiles}
            onLoadSampleSuite={handleLoadSampleSuite}
          />
        </div>

        <div className="lg:col-span-6">
          <TestRelationshipPanel
            relationships={relationships}
            hasSuppliedTestFiles={discoveredTestFiles.length > 0}
            onOpenSourceInWorkspace={(filename) => handleOpenSourceInWorkspace(filename, null)}
          />
        </div>
      </div>

      {/* Gaps & Risk-Based Priority */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        <div className="lg:col-span-6">
          <TestingGapsPanel
            backendReport={edgeMindReport}
            isLoading={isEdgeMindAnalyzing}
            error={edgeMindError}
            staticGaps={staticGaps}
            hasSuppliedTestFiles={discoveredTestFiles.length > 0}
            onRetryAnalyze={() => {
              void handleRunAdaptiveAnalysis();
            }}
          />
        </div>

        <div className="lg:col-span-6">
          <TestingPriorityPanel
            priorityItems={priorityItems}
            hasFindingsReport={Boolean(latestReport)}
            onInspectLineInWorkspace={(filename, line) => handleOpenSourceInWorkspace(filename, line)}
            onOpenFindings={() => navigate('/findings')}
          />
        </div>
      </div>

      {/* Honest Runtime Execution Unavailable + Capability Matrix */}
      <TestExecutionPanel />
    </div>
  );
};
