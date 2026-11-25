import React from 'react';
import { CheckCircle2, RotateCcw, Save, Settings, Undo2, AlertCircle } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';

export interface SettingsHeaderProps {
  hasUnsavedChanges: boolean;
  hasValidationErrors: boolean;
  feedback: { type: 'success' | 'error'; message: string } | null;
  storageError: string | null;
  onSave: () => void;
  onDiscard: () => void;
  onResetDefaults: () => void;
}

export const SettingsHeader: React.FC<SettingsHeaderProps> = ({
  hasUnsavedChanges,
  hasValidationErrors,
  feedback,
  storageError,
  onSave,
  onDiscard,
  onResetDefaults,
}) => {
  return (
    <div className="space-y-3">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between pb-4 border-b border-em-border-hairline">
        <div className="space-y-1.5 min-w-0">
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-em-card border border-em-border-default flex items-center justify-center text-em-accent-primary shrink-0">
              <Settings className="w-4 h-4" />
            </div>
            <h2 className="text-lg font-semibold text-em-text-primary tracking-tight">
              Settings &amp; Configuration
            </h2>
            {hasUnsavedChanges ? (
              <Badge variant="warning" size="sm">
                Unsaved Changes
              </Badge>
            ) : (
              <Badge variant="neutral" size="sm">
                Local Preferences Synced
              </Badge>
            )}
          </div>
          <p className="text-xs text-em-text-muted max-w-3xl leading-relaxed">
            Configure API endpoint connectivity, editor preferences, bounded static analysis
            defaults, and session retention. Backend environment secrets and runtime invariants
            remain read-only.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {hasUnsavedChanges && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leftIcon={<Undo2 className="w-3.5 h-3.5" />}
              onClick={onDiscard}
            >
              Discard
            </Button>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
            onClick={onResetDefaults}
          >
            Reset Defaults
          </Button>

          <Button
            type="button"
            variant="primary"
            size="sm"
            leftIcon={<Save className="w-3.5 h-3.5" />}
            disabled={!hasUnsavedChanges || hasValidationErrors}
            onClick={onSave}
          >
            Save Settings
          </Button>
        </div>
      </header>

      {storageError && (
        <div
          role="alert"
          className="rounded-md border border-em-status-error/30 bg-em-status-error/10 p-3 text-xs text-em-status-error flex items-center gap-2"
        >
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Browser storage error: {storageError}</span>
        </div>
      )}

      {feedback && (feedback.type === 'success' || !storageError) && (
        <div
          role={feedback.type === 'error' ? 'alert' : 'status'}
          className={
            feedback.type === 'error'
              ? 'rounded-md border border-em-status-error/30 bg-em-status-error/10 p-3 text-xs text-em-status-error flex items-center gap-2'
              : 'rounded-md border border-em-status-success/30 bg-em-status-success/10 p-3 text-xs text-em-status-success flex items-center gap-2'
          }
        >
          {feedback.type === 'error' ? (
            <AlertCircle className="w-4 h-4 shrink-0" />
          ) : (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}
    </div>
  );
};
