import React from 'react';
import { AlertCircle, AlertTriangle } from 'lucide-react';
import { FindingSeverity } from '../../types/api';
import { Badge } from '../ui/Badge';

export interface SeverityBadgeProps {
  severity: FindingSeverity;
  showIcon?: boolean;
}

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({
  severity,
  showIcon = true,
}) => {
  const isError = severity === 'error';

  return (
    <Badge variant={isError ? 'error' : 'warning'}>
      {showIcon &&
        (isError ? (
          <AlertCircle className="w-3 h-3 shrink-0" aria-hidden="true" />
        ) : (
          <AlertTriangle className="w-3 h-3 shrink-0" aria-hidden="true" />
        ))}
      <span>{isError ? 'ERROR' : 'WARNING'}</span>
    </Badge>
  );
};
