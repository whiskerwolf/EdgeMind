import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { apiClient } from '../api/client';
import { useHealthContext } from '../context/HealthContext';
import { useAnalysisContext } from '../context/AnalysisContext';
import { useOverviewHistory } from '../hooks/useOverviewHistory';
import { StatusIndicator } from '../components/ui/StatusIndicator';
import { Button } from '../components/ui/Button';
import { SystemStatusSection } from '../components/overview/SystemStatusSection';
import { AnalysisOverviewSection } from '../components/overview/AnalysisOverviewSection';
import { SeverityDistributionSection } from '../components/overview/SeverityDistributionSection';
import { RecentActivitySection } from '../components/overview/RecentActivitySection';
import { QuickActionsSection } from '../components/overview/QuickActionsSection';

const SAMPLE_VERIFICATION_CODE = `def calculate_ratio(total: int, count: int) -> float:
    unused_flag = True
    return total / 0
`;

export const OverviewPage: React.FC = () => {
  const health = useHealthContext();
  const {
    latestReport,
    latestDurationMs,
    sessionRuns,
    isAnalyzing,
    analysisError,
    runAnalysis,
    clearError,
  } = useAnalysisContext();

  const history = useOverviewHistory(health.status, 5);

  const handleRunSampleVerification = () => {
    void runAnalysis({
      code: SAMPLE_VERIFICATION_CODE,
      filename: 'sample_check.py',
      static_only: true,
    });
  };

  return (
    <div className="space-y-4">
      {/* 1. Dashboard Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-em-border-default pb-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">Overview</h2>
            <StatusIndicator
              status={health.status}
              label={
                health.status === 'connected'
                  ? 'Backend Online'
                  : health.status === 'connecting'
                    ? 'Connecting'
                    : health.status === 'disconnected'
                      ? 'Backend Offline'
                      : 'Health Error'
              }
            />
          </div>
          <p className="text-xs text-em-text-muted mt-1">
            Backend telemetry, active static analysis summary, and quick developer workflows.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Link to="/workspace">
            <Button variant="primary" size="sm" rightIcon={<ArrowRight className="w-3.5 h-3.5" />}>
              Go to Workspace
            </Button>
          </Link>
        </div>
      </div>

      {/* 2. System Status */}
      <SystemStatusSection
        health={health}
        baseUrl={apiClient.getBaseUrl()}
        unavailableReason={history.unavailableReason}
        onRefresh={() => {
          void health.checkHealth();
        }}
      />

      {/* 3. Analysis Overview */}
      <AnalysisOverviewSection
        report={latestReport}
        durationMs={latestDurationMs}
        healthStatus={health.status}
        isAnalyzing={isAnalyzing}
        error={analysisError}
        onRunSampleAnalysis={handleRunSampleVerification}
        onClearError={clearError}
      />

      {/* 4. Severity Distribution & 5. Recent Activity */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
        <div className="xl:col-span-5 flex flex-col">
          <SeverityDistributionSection
            report={latestReport}
            healthStatus={health.status}
            isAnalyzing={isAnalyzing}
          />
        </div>
        <div className="xl:col-span-7">
          <RecentActivitySection history={history} sessionRuns={sessionRuns} />
        </div>
      </div>

      {/* 6. Quick Actions */}
      <QuickActionsSection report={latestReport} />
    </div>
  );
};
