import React from 'react';
import { cn } from '../../utils/cn';
import { LucideIcon } from 'lucide-react';

export interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon: Icon,
  title,
  description,
  action,
  className,
}) => {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center p-8 text-center rounded-lg border border-em-border-default bg-em-surface-card/40 my-4',
        className
      )}
    >
      {Icon && (
        <div className="w-10 h-10 rounded-full bg-white/[0.04] border border-white/[0.08] flex items-center justify-center text-em-text-dim mb-3">
          <Icon className="w-5 h-5 text-em-text-muted" />
        </div>
      )}
      <h3 className="text-sm font-semibold text-em-text-primary mb-1">{title}</h3>
      <p className="text-xs text-em-text-muted max-w-sm mb-4 leading-relaxed">{description}</p>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
};
