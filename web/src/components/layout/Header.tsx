import React from 'react';
import { useLocation } from 'react-router-dom';
import { Menu, Play } from 'lucide-react';
import { StatusIndicator, StatusIndicatorType } from '../ui/StatusIndicator';
import { Button } from '../ui/Button';
import { Tooltip } from '../ui/Tooltip';
import { NAV_ITEMS } from './Sidebar';

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

  const currentItem = NAV_ITEMS.find((item) =>
    item.path === '/'
      ? location.pathname === '/'
      : location.pathname.startsWith(item.path)
  );

  const routeTitle = currentItem ? currentItem.label : 'Overview';

  return (
    <header className="h-13 bg-em-sidebar border-b border-em-border-default px-4 flex items-center justify-between z-20 shrink-0">
      {/* Left: Mobile hamburger + Breadcrumb Title */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobileMenu}
          className="md:hidden p-1.5 text-em-text-secondary hover:text-em-text-primary hover:bg-white/[0.06] rounded"
          aria-label="Open Navigation Menu"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2">
          <span className="text-xs font-mono uppercase text-em-text-dim hidden sm:inline">Workspace</span>
          <span className="text-em-text-dim text-xs hidden sm:inline">/</span>
          <h1 className="text-sm font-semibold text-em-text-primary tracking-tight">{routeTitle}</h1>
        </div>
      </div>

      {/* Right: Real Backend Health Indicator + Run Analysis CTA */}
      <div className="flex items-center gap-3">
        {/* Real Backend Status Indicator */}
        <Tooltip
          content={
            <div className="text-[11px] font-mono">
              <div>API: http://127.0.0.1:8000</div>
              {durationMs !== null && <div>Latency: {durationMs}ms</div>}
              <div>Status: {healthStatus.toUpperCase()}</div>
            </div>
          }
          position="bottom"
        >
          <div className="px-2.5 py-1 bg-em-surface-card border border-em-border-default rounded-md flex items-center gap-2 cursor-default">
            <StatusIndicator
              status={healthStatus}
              label={healthStatus === 'connected' ? `API: 8000 (${durationMs ?? 0}ms)` : undefined}
            />
          </div>
        </Tooltip>

        {/* Global Action CTA */}
        <Button
          variant="primary"
          size="sm"
          leftIcon={<Play className="w-3.5 h-3.5 fill-current" />}
          onClick={onRunAnalysis}
          title="Run Static Analysis (⌘↵)"
        >
          <span className="hidden sm:inline">Run Analysis</span>
          <span className="text-[10px] font-mono opacity-80 hidden md:inline ml-1">⌘↵</span>
        </Button>
      </div>
    </header>
  );
};
