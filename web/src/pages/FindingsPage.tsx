import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, CheckCircle2, Code2, WifiOff } from 'lucide-react';
import { useAnalysisContext } from '../context/AnalysisContext';
import { useHealthContext } from '../context/HealthContext';
import {
  DEFAULT_FINDING_FILTERS,
  ExplorerFinding,
  extractAvailableCategories,
  extractExplorerFindings,
  filterAndSortFindings,
  FindingFilters,
} from '../utils/findingsHelpers';
import { FindingsHeader } from '../components/findings/FindingsHeader';
import { FindingsToolbar } from '../components/findings/FindingsToolbar';
import { FindingsList } from '../components/findings/FindingsList';
import { FindingDetailPanel } from '../components/findings/FindingDetailPanel';
import { EmptyState } from '../components/ui/EmptyState';
import { Button } from '../components/ui/Button';
import { cn } from '../utils/cn';

type MobileFindingsTab = 'list' | 'detail';

export const FindingsPage: React.FC = () => {
  const navigate = useNavigate();
  const { status: healthStatus } = useHealthContext();
  const {
    latestReport,
    analyzedSnapshot,
    hasUnanalyzedChanges,
    workspaceLanguage,
    selectedFindingId,
    setSelectedFindingId,
    inspectFindingInWorkspace,
    diagnosisByFinding,
    startFindingDiagnosis,
    cancelFindingDiagnosis,
  } = useAnalysisContext();

  const [filters, setFilters] = useState<FindingFilters>(DEFAULT_FINDING_FILTERS);
  const [mobileTab, setMobileTab] = useState<MobileFindingsTab>('list');

  const allFindings = useMemo(
    () => extractExplorerFindings(latestReport),
    [latestReport]
  );

  const errorCount = useMemo(
    () => allFindings.filter((item) => item.severity === 'error').length,
    [allFindings]
  );

  const warningCount = useMemo(
    () => allFindings.filter((item) => item.severity === 'warning').length,
    [allFindings]
  );

  const availableCategories = useMemo(
    () => extractAvailableCategories(allFindings),
    [allFindings]
  );

  const filteredFindings = useMemo(
    () => filterAndSortFindings(allFindings, filters),
    [allFindings, filters]
  );

  // Keep selectedFindingId synchronized with visible filtered findings
  useEffect(() => {
    if (filteredFindings.length === 0) {
      return;
    }
    const stillVisible = filteredFindings.some((f) => f.id === selectedFindingId);
    if (!stillVisible) {
      setSelectedFindingId(filteredFindings[0].id);
    }
  }, [filteredFindings, selectedFindingId, setSelectedFindingId]);

  const selectedFinding = useMemo(
    () => filteredFindings.find((f) => f.id === selectedFindingId) ?? null,
    [filteredFindings, selectedFindingId]
  );

  const isBackendOffline = healthStatus === 'disconnected' || healthStatus === 'error';
  const sourceCode = analyzedSnapshot?.code ?? null;
  const sourceLanguage = analyzedSnapshot?.language ?? workspaceLanguage;

  const handleSelectFinding = (finding: ExplorerFinding) => {
    setSelectedFindingId(finding.id);
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setMobileTab('detail');
    }
  };

  const handleInspectInWorkspace = (finding: ExplorerFinding) => {
    inspectFindingInWorkspace(finding.id, finding.line);
    navigate('/workspace');
  };

  const handleClearFilters = () => {
    setFilters(DEFAULT_FINDING_FILTERS);
  };

  return (
    <div className="space-y-4">
      <FindingsHeader
        report={latestReport}
        totalFindings={allFindings.length}
        errorCount={errorCount}
        warningCount={warningCount}
        healthStatus={healthStatus}
        hasUnanalyzedChanges={hasUnanalyzedChanges}
      />

      {isBackendOffline && !latestReport && (
        <div
          role="alert"
          className="p-3 rounded-md border border-em-status-error/30 bg-em-status-error/5 flex items-start gap-2.5"
        >
          <WifiOff className="w-4 h-4 text-em-status-error shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="text-xs font-semibold text-em-text-primary">Backend Disconnected</p>
            <p className="text-xs text-em-text-muted mt-0.5 leading-relaxed">
              EdgeMind API is unreachable. Start the FastAPI server to run static analysis in Workspace and explore real findings.
            </p>
          </div>
        </div>
      )}

      {/* State 1: No Analysis Performed */}
      {!latestReport && (
        <EmptyState
          icon={Code2}
          title="No Analysis Performed Yet"
          description="Run static code analysis from Code Workspace or trigger Sample Verification on Overview to populate findings here."
          action={
            <Link to="/workspace">
              <Button variant="primary" size="sm" rightIcon={<ArrowRight className="w-3.5 h-3.5" />}>
                Go to Code Workspace
              </Button>
            </Link>
          }
        />
      )}

      {/* State 2: Analysis Passed With Zero Findings */}
      {latestReport && allFindings.length === 0 && (
        <EmptyState
          icon={CheckCircle2}
          title="Zero Findings Detected"
          description={`All static checks passed with no errors or warnings reported for '${latestReport.file || latestReport.file_path}'.`}
          action={
            <Link to="/workspace">
              <Button variant="secondary" size="sm" rightIcon={<ArrowRight className="w-3.5 h-3.5" />}>
                Return to Workspace
              </Button>
            </Link>
          }
        />
      )}

      {/* State 3: Findings Available */}
      {latestReport && allFindings.length > 0 && (
        <>
          <FindingsToolbar
            filters={filters}
            availableCategories={availableCategories}
            totalCount={allFindings.length}
            filteredCount={filteredFindings.length}
            errorCount={errorCount}
            warningCount={warningCount}
            onFiltersChange={setFilters}
            onClearFilters={handleClearFilters}
          />

          {/* Mobile Section Switcher (< 768px) */}
          <div
            className="md:hidden flex rounded-md border border-em-border-default bg-em-card p-1 gap-1"
            role="tablist"
            aria-label="Mobile findings sections"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mobileTab === 'list'}
              onClick={() => setMobileTab('list')}
              className={cn(
                'flex-1 py-2 text-xs font-medium rounded transition-colors',
                mobileTab === 'list'
                  ? 'bg-em-elevated text-em-text-primary'
                  : 'text-em-text-muted hover:text-em-text-primary'
              )}
            >
              Findings List ({filteredFindings.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mobileTab === 'detail'}
              onClick={() => setMobileTab('detail')}
              className={cn(
                'flex-1 py-2 text-xs font-medium rounded transition-colors',
                mobileTab === 'detail'
                  ? 'bg-em-elevated text-em-text-primary'
                  : 'text-em-text-muted hover:text-em-text-primary'
              )}
            >
              Finding Details
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
            <div
              className={cn(
                'lg:col-span-5',
                mobileTab !== 'list' && 'hidden md:block'
              )}
            >
              <FindingsList
                findings={filteredFindings}
                selectedFindingId={selectedFinding?.id ?? null}
                diagnosisByFinding={diagnosisByFinding}
                onSelectFinding={handleSelectFinding}
                onClearFilters={handleClearFilters}
              />
            </div>

            <div
              className={cn(
                'lg:col-span-7',
                mobileTab !== 'detail' && 'hidden md:block'
              )}
            >
              <FindingDetailPanel
                finding={selectedFinding}
                sourceCode={sourceCode}
                sourceLanguage={sourceLanguage}
                healthStatus={healthStatus}
                hasUnanalyzedChanges={hasUnanalyzedChanges}
                diagnosis={
                  selectedFinding ? diagnosisByFinding[selectedFinding.id] : undefined
                }
                onInspectInWorkspace={handleInspectInWorkspace}
                onStartDiagnosis={(f) => {
                  void startFindingDiagnosis(f);
                }}
                onCancelDiagnosis={cancelFindingDiagnosis}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
};
