import React from 'react';
import { cn } from '../../utils/cn';

export type StatusIndicatorType = 'connected' | 'connecting' | 'disconnected' | 'error';

export interface StatusIndicatorProps {
  status: StatusIndicatorType;
  label?: string;
  className?: string;
  showDot?: boolean;
}

export const StatusIndicator: React.FC<StatusIndicatorProps> = ({
  status,
  label,
  className,
  showDot = true,
}) => {
  const statusStyles: Record<StatusIndicatorType, { dot: string; text: string; defaultLabel: string }> = {
    connected: {
      dot: 'bg-em-status-success shadow-[0_0_8px_rgba(16,185,129,0.5)]',
      text: 'text-em-status-success',
      defaultLabel: 'Connected',
    },
    connecting: {
      dot: 'bg-em-status-warning animate-pulse shadow-[0_0_8px_rgba(245,158,11,0.5)]',
      text: 'text-em-status-warning',
      defaultLabel: 'Connecting',
    },
    disconnected: {
      dot: 'bg-em-status-error shadow-[0_0_8px_rgba(239,68,68,0.5)]',
      text: 'text-em-status-error',
      defaultLabel: 'Disconnected',
    },
    error: {
      dot: 'bg-em-status-error shadow-[0_0_8px_rgba(239,68,68,0.5)]',
      text: 'text-em-status-error',
      defaultLabel: 'Error',
    },
  };

  const current = statusStyles[status];

  return (
    <div
      className={cn('inline-flex items-center gap-1.5 select-none text-xs font-mono', className)}
      role="status"
    >
      {showDot && (
        <span className={cn('w-2 h-2 rounded-full inline-block shrink-0', current.dot)} />
      )}
      <span className={cn('font-medium', current.text)}>{label || current.defaultLabel}</span>
    </div>
  );
};
