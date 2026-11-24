import React from 'react';
import { cn } from '../../utils/cn';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'neutral' | 'info' | 'success' | 'warning' | 'error';
  size?: 'sm' | 'md';
  pill?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  className,
  variant = 'neutral',
  size = 'sm',
  pill = false,
  children,
  ...props
}) => {
  const variants = {
    neutral:
      'bg-white/[0.06] text-em-text-secondary border border-white/[0.08]',
    info:
      'bg-em-status-info/10 text-em-status-info border border-em-status-info/25',
    success:
      'bg-em-status-success/10 text-em-status-success border border-em-status-success/25',
    warning:
      'bg-em-status-warning/10 text-em-status-warning border border-em-status-warning/25',
    error:
      'bg-em-status-error/10 text-em-status-error border border-em-status-error/25',
  };

  const sizes = {
    sm: 'text-[11px] px-1.5 py-0.5 font-medium leading-none',
    md: 'text-xs px-2 py-1 font-medium leading-tight',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 font-mono uppercase tracking-wide select-none',
        variants[variant],
        sizes[size],
        pill ? 'rounded-full' : 'rounded-sm',
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
