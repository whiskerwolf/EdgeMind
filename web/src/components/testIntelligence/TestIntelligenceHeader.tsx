import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Play, ShieldCheck } from 'lucide-react';
import { HealthStatus } from '../../types/api';
import { WorkspaceLanguage } from '../../utils/workspaceConfig';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export interface TestIntelligenceHeaderProps {
  workspaceFilename: string;
  hasWorkspaceCode: boolean;
  workspaceLanguage: WorkspaceLanguage;
  healthStatus: HealthStatus;
  isAnalyzing: boolean;
  canRunAdaptive: boolean;
  suppliedTestFileCount: number;
  onRunAdaptive: () => void;
}

export const TestIntelligenceHeader: React.FC<TestIntelligenceHeaderProps> = ({
  workspaceFilename,
  hasWorkspaceCode,
  workspaceLanguage,
  healthStatus,
  isAnalyzing,
  canRunAdaptive,
  suppliedTestFileCount,
  onRunAdaptive,
}) => {
  const isBackendOffline = healthStatus === 'disconnected' || healthStatus === 'error';
  const isUnsupportedLanguage = workspaceLanguage !== 'python';

  return (
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-em-border-default pb-4">
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">
            Adaptive Test Intelligence
          </h2>

          <Badge variant="neutral">
            <ShieldCheck className="w-3 h-3" aria-hidden="true" />
            <span>Static-Only · Zero Execution</span>
          </Badge>

          {isBackendOffline ? (
            <Badge variant="error">Backend Offline</Badge>
          ) : (
            <Badge variant="info">
              {hasWorkspaceCode ? `Target: ${workspaceFilename}` : 'No Code Target'}
            </Badge>
          )}

          {isUnsupportedLanguage && (
            <Badge variant="warning">Unsupported Language: {workspaceLanguage}</Badge>
          )}

          {suppliedTestFileCount > 0 && (
            <Badge variant="success">{suppliedTestFileCount} Test File(s) Loaded</Badge>
          )}
        </div>

        <p className="text-xs text-em-text-muted leading-relaxed">
          Evaluate black-box input-domain partitions, parse supplied Python test suites statically, map test-to-code references, and inspect heuristic testing priorities.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 shrink-0">
        <Link to="/workspace">
          <Button variant="secondary" size="sm" rightIcon={<ArrowRight className="w-3.5 h-3.5" />}>
            Open Workspace
          </Button>
        </Link>

        <Button
          variant="primary"
          size="sm"
          isLoading={isAnalyzing}
          disabled={!canRunAdaptive}
          leftIcon={<Play className="w-3.5 h-3.5 fill-current" />}
          onClick={onRunAdaptive}
          title="Run POST /api/v1/edgemind/analyze on target Python code"
        >
          {isAnalyzing ? 'Analyzing...' : 'Run Adaptive Analysis'}
        </Button>
      </div>
    </div>
  );
};
