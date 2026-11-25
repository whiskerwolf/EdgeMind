import React from 'react';
import { Cpu, Lock, ShieldCheck } from 'lucide-react';
import { AppSettings, BACKEND_INVARIANTS, SETTINGS_LIMITS, SettingsValidationErrors } from '../../utils/settingsConfig';
import { WORKSPACE_LANGUAGES } from '../../utils/workspaceConfig';
import { Badge } from '../ui/Badge';
import { Input } from '../ui/Input';

export interface AnalysisSettingsSectionProps {
  draft: AppSettings;
  errors: SettingsValidationErrors;
  onChangeDraft: (partial: Partial<AppSettings>) => void;
}

export const AnalysisSettingsSection: React.FC<AnalysisSettingsSectionProps> = ({
  draft,
  errors,
  onChangeDraft,
}) => {
  return (
    <section
      aria-labelledby="settings-analysis-heading"
      className="rounded-lg border border-em-border-default bg-em-card p-4 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-em-border-hairline">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-em-accent-primary" />
          <h3
            id="settings-analysis-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            Static Analysis &amp; Test Intelligence
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="success" size="sm">
            <ShieldCheck className="w-3 h-3" />
            Static-Only Enforced
          </Badge>
          <Badge variant="neutral" size="sm">
            Requires Save
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="space-y-1.5">
          <label
            htmlFor="settings-default-filename"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            Default Workspace Filename
          </label>
          <Input
            id="settings-default-filename"
            type="text"
            value={draft.defaultFilename}
            onChange={(e) => onChangeDraft({ defaultFilename: e.target.value })}
            placeholder="snippet.py"
            error={errors.defaultFilename}
          />
          <p className="text-[11px] text-em-text-muted">
            Applied when initializing or clearing Workspace drafts.
          </p>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="settings-max-candidates"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            Max Test Candidates ({SETTINGS_LIMITS.minMaxCandidates}-{SETTINGS_LIMITS.maxMaxCandidates})
          </label>
          <Input
            id="settings-max-candidates"
            type="number"
            min={SETTINGS_LIMITS.minMaxCandidates}
            max={SETTINGS_LIMITS.maxMaxCandidates}
            value={draft.defaultMaxCandidates}
            onChange={(e) => onChangeDraft({ defaultMaxCandidates: Number(e.target.value) })}
            error={errors.defaultMaxCandidates}
          />
          <p className="text-[11px] text-em-text-muted">
            Sent as <span className="font-mono">max_candidates</span> to{' '}
            <span className="font-mono">/api/v1/edgemind/analyze</span>.
          </p>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="settings-analysis-timeout"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            Analysis Request Timeout (ms)
          </label>
          <Input
            id="settings-analysis-timeout"
            type="number"
            step={1000}
            min={SETTINGS_LIMITS.minAnalysisTimeoutMs}
            max={SETTINGS_LIMITS.maxAnalysisTimeoutMs}
            value={draft.analysisTimeoutMs}
            onChange={(e) => onChangeDraft({ analysisTimeoutMs: Number(e.target.value) })}
            error={errors.analysisTimeoutMs}
          />
          <p className="text-[11px] text-em-text-muted">
            Client abort timeout ({SETTINGS_LIMITS.minAnalysisTimeoutMs / 1000}s-
            {SETTINGS_LIMITS.maxAnalysisTimeoutMs / 1000}s).
          </p>
        </div>
      </div>

      {/* Backend-Enforced Read-Only Invariants & Supported Languages */}
      <div className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-2.5 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 font-semibold text-em-text-secondary">
            <Lock className="w-3.5 h-3.5 text-em-text-dim" />
            Backend-Enforced Analysis Constraints (Read-Only)
          </span>
          <span className="text-[11px] font-mono text-em-text-dim">core/config.py</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-[11px] font-mono">
          <div className="rounded border border-em-border-hairline bg-em-card px-2.5 py-2">
            <span className="text-em-text-dim block">EXECUTION POLICY</span>
            <span className="text-em-status-success font-semibold">static_only = true</span>
          </div>
          <div className="rounded border border-em-border-hairline bg-em-card px-2.5 py-2">
            <span className="text-em-text-dim block">MAX PAYLOAD SIZE</span>
            <span className="text-em-text-primary font-semibold">
              64 KiB ({BACKEND_INVARIANTS.maxSourceCodeBytes.toLocaleString()} B)
            </span>
          </div>
          <div className="rounded border border-em-border-hairline bg-em-card px-2.5 py-2">
            <span className="text-em-text-dim block">LANGUAGE ENGINES</span>
            <div className="flex flex-wrap gap-1 mt-0.5">
              {WORKSPACE_LANGUAGES.map((lang) => (
                <Badge
                  key={lang.id}
                  variant={lang.supported ? 'success' : 'neutral'}
                  size="sm"
                >
                  {lang.id}
                </Badge>
              ))}
            </div>
          </div>
        </div>
        <p className="text-[11px] text-em-text-muted">
          Arbitrary code execution is permanently disabled on the API. JavaScript and TypeScript
          remain disabled in the static analyzer and cannot be enabled via client settings.
        </p>
      </div>
    </section>
  );
};
