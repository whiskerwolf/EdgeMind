import React from 'react';
import { cn } from '../../utils/cn';

export interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  'aria-label': string;
}

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      className,
      variant = 'ghost',
      size = 'md',
      isLoading = false,
      disabled,
      children,
      'aria-label': ariaLabel,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus focus-visible:ring-offset-1 focus-visible:ring-offset-em-canvas disabled:pointer-events-none disabled:opacity-40 select-none';

    const variants = {
      primary:
        'bg-em-accent-primary text-em-canvas hover:bg-em-accent-hover shadow-sm',
      secondary:
        'bg-em-surface-card text-em-text-primary border border-em-border-default hover:bg-em-surface-elevated hover:border-em-border-strong',
      ghost:
        'text-em-text-secondary hover:text-em-text-primary hover:bg-white/[0.06] active:bg-white/[0.09]',
      danger:
        'bg-em-status-error/10 text-em-status-error border border-em-status-error/25 hover:bg-em-status-error/20',
      outline:
        'bg-transparent text-em-text-secondary border border-em-border-default hover:text-em-text-primary hover:border-em-border-strong hover:bg-white/[0.04]',
    };

    const sizes = {
      sm: 'w-7 h-7 rounded-sm text-xs',
      md: 'w-9 h-9 rounded-md text-sm',
      lg: 'w-10 h-10 rounded-md text-base',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        aria-label={ariaLabel}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        {...props}
      >
        {isLoading ? (
          <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          children
        )}
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';
