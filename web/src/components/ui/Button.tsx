import React from 'react';
import { cn } from '../../utils/cn';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'secondary',
      size = 'md',
      isLoading = false,
      disabled,
      children,
      leftIcon,
      rightIcon,
      ...props
    },
    ref
  ) => {
    const baseStyles =
      'inline-flex items-center justify-center font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-em-border-focus focus-visible:ring-offset-1 focus-visible:ring-offset-em-canvas disabled:pointer-events-none disabled:opacity-40 select-none';

    const variants = {
      primary:
        'bg-em-accent-primary text-em-canvas font-semibold hover:bg-em-accent-hover shadow-sm active:translate-y-[0.5px]',
      secondary:
        'bg-em-surface-card text-em-text-primary border border-em-border-default hover:bg-em-surface-elevated hover:border-em-border-strong active:bg-em-surface-overlay',
      ghost:
        'text-em-text-secondary hover:text-em-text-primary hover:bg-white/[0.06] active:bg-white/[0.09]',
      danger:
        'bg-em-status-error/10 text-em-status-error border border-em-status-error/25 hover:bg-em-status-error/20 active:bg-em-status-error/30',
      outline:
        'bg-transparent text-em-text-secondary border border-em-border-default hover:text-em-text-primary hover:border-em-border-strong hover:bg-white/[0.04]',
    };

    const sizes = {
      sm: 'h-7 px-2.5 text-xs rounded-sm gap-1.5',
      md: 'h-9 px-3.5 text-xs rounded-md gap-2',
      lg: 'h-10 px-4 text-sm rounded-md gap-2.5',
    };

    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(baseStyles, variants[variant], sizes[size], className)}
        {...props}
      >
        {isLoading ? (
          <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
        ) : (
          leftIcon
        )}
        {children}
        {!isLoading && rightIcon}
      </button>
    );
  }
);

Button.displayName = 'Button';
