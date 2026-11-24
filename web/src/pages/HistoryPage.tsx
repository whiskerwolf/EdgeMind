import React from 'react';
import { Clock } from 'lucide-react';
import { Badge } from '../components/ui/Badge';

export const HistoryPage: React.FC = () => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between border-b border-em-border-default pb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">Analysis History</h2>
            <Badge variant="neutral">PHASE 6.4 FOUNDATION</Badge>
          </div>
          <p className="text-xs text-em-text-muted">
            Audit history of past code analyses and stored JSONB reports.
          </p>
        </div>
      </div>

      <div className="p-6 rounded-lg border border-em-border-default bg-em-surface-card">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-md bg-white/[0.04] border border-white/[0.08] text-em-accent-primary">
            <Clock className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-em-text-primary">Analysis History Foundation</h3>
            <p className="text-xs text-em-text-secondary leading-relaxed max-w-xl">
              Database-backed historical sessions and report documents will be presented in a later phase.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
