import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Menu, Play } from 'lucide-react';
import { StatusIndicator, StatusIndicatorType } from '../ui/StatusIndicator';
import { Button } from '../ui/Button';
import { Tooltip } from '../ui/Tooltip';
import { NAV_ITEMS } from './Sidebar';
import { apiClient } from '../../api/client';
import { useOptionalSettings } from '../../context/SettingsContext';

export interface HeaderProps {
  onOpenMobileMenu: () => void;
  healthStatus: StatusIndicatorType;
  durationMs: number | null;
  onRunAnalysis?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  onOpenMobileMenu,
  healthStatus,
  durationMs,
  onRunAnalysis,
}) => {
  const location = useLocation();
  const navigate = useNavigate();

  const currentItem = NAV_ITEMS.find((item) =>
    item.path === '/'
      ? location.pathname === '/'
      : location.pathname.startsWith(item.path)
  );

  const routeTitle = currentItem ? currentItem.label : 'Overview';
  const isWorkspaceRoute = location.pathname.startsWith('/workspace');

  const settings = useOptionalSettings();
  const baseUrl = apiClient.getBaseUrl?.() || settings.apiBaseUrl;
  let endpointBadge = '8000';
  try {
    const parsed = new URL(baseUrl);
    endpointBadge = parsed.port || parsed.hostname;
  } catch {
    endpointBadge = baseUrl;
  }

  const handleActionClick = () => {
    if (onRunAnalysis) {
      onRunAnalysis();
      return;
    }
    navigate('/workspace');
  };

  return (
    <header className="h-[52px] bg-em-sidebar border-b border-em-border-default px-4 flex items-center justify-between z-20 shrink-0">
      {/* Left: Mobile hamburger + Breadcrumb Title */}
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onOpenMobileMenu}
          className="md:hidden p-1.5 text-em-text-secondary hover:text-em-text-primary hover:bg-white/[0.06] rounded"
          aria-label="Open Navigation Menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-mono uppercase text-em-text-dim hidden sm:inline">Workspace</span>
          <span className="text-em-text-dim text-xs hidden sm:inline">/</span>
          <h1 className="text-sm font-semibold text-em-text-primary tracking-tight truncate">{routeTitle}</h1>
        </div>
      </div>

      {/* Right: Real Backend Health Indicator + Workspace Action CTA */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        {/* Real Backend Status Indicator */}
        <Tooltip
          content={
            <div className="text-[11px] font-mono">
              <div>API: {baseUrl}</div>
              {durationMs !== null && <div>Latency: {durationMs}ms</div>}
              <div>Status: {healthStatus.toUpperCase()}</div>
            </div>
          }
          position="bottom"
        >
          <div className="px-2 sm:px-2.5 py-1 bg-em-surface-card border border-em-border-default rounded-md flex items-center gap-2 cursor-default">
            <StatusIndicator
              status={healthStatus}
              label={
                healthStatus === 'connected'
                  ? `API: ${endpointBadge} (${durationMs ?? 0}ms)`
                  : undefined
              }
            />
          </div>
        </Tooltip>

        {/* Global Action CTA (Hidden on Workspace since WorkspaceHeader provides primary Analyze CTA) */}
        {(!isWorkspaceRoute || onRunAnalysis) && (
          <Button
            variant={onRunAnalysis ? 'primary' : 'secondary'}
            size="sm"
            leftIcon={<Play className="w-3.5 h-3.5 fill-current" />}
            onClick={handleActionClick}
            title={onRunAnalysis ? 'Run Static Analysis (⌘↵)' : 'Open Code Workspace'}
          >
            <span className="hidden sm:inline">
              {onRunAnalysis ? 'Run Analysis' : 'Open Workspace'}
            </span>
          </Button>
        )}
      </div>
    </header>
  );
};
