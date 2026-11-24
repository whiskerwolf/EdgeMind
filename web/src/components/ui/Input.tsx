import React from 'react';
import { cn } from '../../utils/cn';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, leftIcon, rightIcon, error, disabled, ...props }, ref) => {
    return (
      <div className="w-full">
        <div
          className={cn(
            'relative flex items-center w-full bg-em-surface-card border rounded-md transition-colors duration-150',
            error
              ? 'border-em-status-error focus-within:ring-1 focus-within:ring-em-status-error'
              : 'border-em-border-default hover:border-em-border-strong focus-within:border-em-accent-primary focus-within:ring-1 focus-within:ring-em-accent-primary',
            disabled && 'opacity-40 pointer-events-none'
          )}
        >
          {leftIcon && <span className="pl-3 text-em-text-dim flex items-center">{leftIcon}</span>}
          <input
            ref={ref}
            disabled={disabled}
            className={cn(
              'w-full h-9 bg-transparent px-3 text-xs text-em-text-primary placeholder:text-em-text-dim focus:outline-none disabled:cursor-not-allowed font-mono',
              leftIcon && 'pl-2',
              rightIcon && 'pr-2',
              className
            )}
            {...props}
          />
          {rightIcon && <span className="pr-3 text-em-text-dim flex items-center">{rightIcon}</span>}
        </div>
        {error && <p className="mt-1 text-[11px] text-em-status-error">{error}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';
