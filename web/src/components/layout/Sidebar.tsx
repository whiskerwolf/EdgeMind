import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Code2,
  AlertCircle,
  Cpu,
  LayoutDashboard,
  Clock,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { NavItem } from '../../types/navigation';
import { Tooltip } from '../ui/Tooltip';
import { cn } from '../../utils/cn';

export interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  className?: string;
}

export const NAV_ITEMS: NavItem[] = [
  {
    id: 'overview',
    label: 'Overview',
    path: '/',
    icon: LayoutDashboard,
    section: 'management',
  },
  {
    id: 'workspace',
    label: 'Workspace',
    path: '/workspace',
    icon: Code2,
    section: 'analysis',
  },
  {
    id: 'findings',
    label: 'Findings',
    path: '/findings',
    icon: AlertCircle,
    section: 'analysis',
  },
  {
    id: 'test-intelligence',
    label: 'Test Intelligence',
    path: '/test-intelligence',
    icon: Cpu,
    section: 'analysis',
  },
  {
    id: 'history',
    label: 'History',
    path: '/history',
    icon: Clock,
    section: 'management',
  },
  {
    id: 'settings',
    label: 'Settings',
    path: '/settings',
    icon: Settings,
    section: 'system',
  },
];

export const Sidebar: React.FC<SidebarProps> = ({ collapsed, onToggle, className }) => {
  return (
    <aside
      className={cn(
        'hidden md:flex flex-col bg-em-sidebar border-r border-em-border-default select-none shrink-0 transition-all duration-200 z-30',
        collapsed ? 'w-16' : 'w-60',
        className
      )}
      role="navigation"
      aria-label="Main Navigation"
    >
      {/* Brand Header */}
      <div
        className={cn(
          'h-[52px] flex items-center border-b border-em-border-default',
          collapsed ? 'px-2 justify-between gap-1' : 'px-4 justify-between'
        )}
      >
        <div className="flex items-center gap-2.5 overflow-hidden">
          {/* Brand Emblem SVG */}
          <div
            className={cn(
              'rounded bg-gradient-to-br from-em-accent-primary to-em-brand-indigo flex items-center justify-center shrink-0 shadow-sm',
              collapsed ? 'w-5 h-5' : 'w-6 h-6'
            )}
          >
            <span
              className={cn(
                'font-bold text-em-canvas font-mono tracking-tighter',
                collapsed ? 'text-[10px]' : 'text-[13px]'
              )}
            >
              EM
            </span>
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span className="text-xs font-semibold text-em-text-primary tracking-tight">EdgeMind</span>
              <span className="text-[9px] font-mono uppercase text-em-text-dim tracking-wider">WORKSPACE</span>
            </div>
          )}
        </div>
        <button
          onClick={onToggle}
          className="p-1 text-em-text-dim hover:text-em-text-primary hover:bg-white/[0.06] rounded transition-colors shrink-0"
          title={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
          aria-label={collapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Nav List */}
      <div className="flex-1 py-3 px-2 space-y-4 overflow-y-auto">
        {/* Analysis Section */}
        <div>
          {!collapsed && (
            <div className="px-2.5 pb-1 text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              Analysis
            </div>
          )}
          <div className="space-y-0.5">
            {NAV_ITEMS.filter((i) => i.section === 'analysis').map((item) => (
              <SidebarLink key={item.id} item={item} collapsed={collapsed} />
            ))}
          </div>
        </div>

        {/* Management Section */}
        <div>
          {!collapsed && (
            <div className="px-2.5 pb-1 text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              Management
            </div>
          )}
          <div className="space-y-0.5">
            {NAV_ITEMS.filter((i) => i.section === 'management').map((item) => (
              <SidebarLink key={item.id} item={item} collapsed={collapsed} />
            ))}
          </div>
        </div>

        {/* System Section */}
        <div>
          {!collapsed && (
            <div className="px-2.5 pb-1 text-[10px] font-mono uppercase tracking-wider text-em-text-dim">
              System
            </div>
          )}
          <div className="space-y-0.5">
            {NAV_ITEMS.filter((i) => i.section === 'system').map((item) => (
              <SidebarLink key={item.id} item={item} collapsed={collapsed} />
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
};

interface SidebarLinkProps {
  item: NavItem;
  collapsed: boolean;
}

const SidebarLink: React.FC<SidebarLinkProps> = ({ item, collapsed }) => {
  const Icon = item.icon;

  const content = (
    <NavLink
      to={item.path}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-3 px-2.5 py-2 rounded-md text-xs font-medium transition-colors duration-150 group relative',
          isActive
            ? 'bg-em-accent-primary/10 text-em-text-primary font-semibold'
            : 'text-em-text-secondary hover:text-em-text-primary hover:bg-white/[0.04]'
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 bg-em-accent-primary rounded-r" />
          )}
          <Icon
            className={cn(
              'w-4 h-4 shrink-0 transition-colors',
              isActive ? 'text-em-accent-primary' : 'text-em-text-muted group-hover:text-em-text-secondary'
            )}
          />
          {!collapsed && <span className="truncate">{item.label}</span>}
        </>
      )}
    </NavLink>
  );

  if (collapsed) {
    return (
      <Tooltip content={item.label} position="right" delayMs={50}>
        {content}
      </Tooltip>
    );
  }

  return content;
};
