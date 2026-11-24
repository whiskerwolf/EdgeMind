import React from 'react';
import { cn } from '../../utils/cn';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from './Button';

export interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  title = 'Failed to Load Data',
  message,
  onRetry,
  className,
}) => {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-6 text-center rounded-lg border border-em-status-error/30 bg-em-status-error/5 my-4',
        className
      )}
      role="alert"
    >
      <div className="w-9 h-9 rounded-full bg-em-status-error/15 border border-em-status-error/30 flex items-center justify-center text-em-status-error mb-2.5">
        <AlertCircle className="w-4 h-4" />
      </div>
      <h3 className="text-sm font-semibold text-em-text-primary mb-1">{title}</h3>
      <p className="text-xs text-em-status-error/90 max-w-md mb-4 leading-relaxed font-mono">{message}</p>
      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
          onClick={onRetry}
        >
          Try Again
        </Button>
      )}
    </div>
  );
};
