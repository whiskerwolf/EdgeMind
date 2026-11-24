import React from 'react';
import { Settings } from 'lucide-react';
import { Badge } from '../components/ui/Badge';

export const SettingsPage: React.FC = () => {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between border-b border-em-border-default pb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">Settings</h2>
            <Badge variant="neutral">PHASE 6.4 FOUNDATION</Badge>
          </div>
          <p className="text-xs text-em-text-muted">
            Backend API endpoints, AI reasoning provider status, and editor preferences.
          </p>
        </div>
      </div>

      <div className="p-6 rounded-lg border border-em-border-default bg-em-surface-card">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-md bg-white/[0.04] border border-white/[0.08] text-em-accent-primary">
            <Settings className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-semibold text-em-text-primary">Settings Foundation</h3>
            <p className="text-xs text-em-text-secondary leading-relaxed max-w-xl">
              API connectivity configuration, local Ollama provider inspection, and workspace preferences will be configured in a later phase.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
