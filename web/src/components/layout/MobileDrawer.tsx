import React, { useEffect } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { X } from 'lucide-react';
import { NAV_ITEMS } from './Sidebar';
import { cn } from '../../utils/cn';

export interface MobileDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MobileDrawer: React.FC<MobileDrawerProps> = ({ isOpen, onClose }) => {
  const location = useLocation();

  // Close drawer when route changes
  useEffect(() => {
    if (isOpen) {
      onClose();
    }
  }, [location.pathname]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/70 backdrop-blur-sm transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Container */}
      <div className="fixed inset-y-0 left-0 w-64 bg-em-sidebar border-r border-em-border-default p-4 flex flex-col shadow-xl">
        <div className="flex items-center justify-between pb-3 border-b border-em-border-default">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-gradient-to-br from-em-accent-primary to-em-brand-indigo flex items-center justify-center shrink-0">
              <span className="font-bold text-[12px] text-em-canvas font-mono">EM</span>
            </div>
            <span className="text-xs font-semibold text-em-text-primary">EdgeMind</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-em-text-muted hover:text-em-text-primary rounded-md"
            aria-label="Close navigation"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation list */}
        <nav className="flex-1 py-4 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.id}
                to={item.path}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-medium transition-colors',
                    isActive
                      ? 'bg-em-accent-primary/10 text-em-text-primary font-semibold'
                      : 'text-em-text-secondary hover:text-em-text-primary hover:bg-white/[0.04]'
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      className={cn(
                        'w-4 h-4',
                        isActive ? 'text-em-accent-primary' : 'text-em-text-muted'
                      )}
                    />
                    <span>{item.label}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        <div className="pt-3 border-t border-em-border-default text-[10px] font-mono text-em-text-dim">
          EdgeMind v1.0.0
        </div>
      </div>
    </div>
  );
};
