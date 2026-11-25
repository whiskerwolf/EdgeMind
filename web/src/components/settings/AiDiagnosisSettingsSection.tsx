import React from 'react';
import { Lock, Sparkles } from 'lucide-react';
import {
  AppSettings,
  BACKEND_INVARIANTS,
  SETTINGS_LIMITS,
  SettingsValidationErrors,
} from '../../utils/settingsConfig';
import { Badge } from '../ui/Badge';
import { Input } from '../ui/Input';

export interface AiDiagnosisSettingsSectionProps {
  draft: AppSettings;
  errors: SettingsValidationErrors;
  onChangeDraft: (partial: Partial<AppSettings>) => void;
}

export const AiDiagnosisSettingsSection: React.FC<AiDiagnosisSettingsSectionProps> = ({
  draft,
  errors,
  onChangeDraft,
}) => {
  return (
    <section
      aria-labelledby="settings-ai-heading"
      className="rounded-lg border border-em-border-default bg-em-card p-4 space-y-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 border-b border-em-border-hairline">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-em-accent-primary" />
          <h3
            id="settings-ai-heading"
            className="text-xs font-semibold uppercase tracking-wider text-em-text-secondary"
          >
            AI Diagnosis Streaming
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="info" size="sm">
            Advisory Only
          </Badge>
          <Badge variant="neutral" size="sm">
            Requires Save
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label
            htmlFor="settings-diagnosis-timeout"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            SSE Stream Timeout (ms)
          </label>
          <Input
            id="settings-diagnosis-timeout"
            type="number"
            step={5000}
            min={SETTINGS_LIMITS.minDiagnosisTimeoutMs}
            max={SETTINGS_LIMITS.maxDiagnosisTimeoutMs}
            value={draft.diagnosisTimeoutMs}
            onChange={(e) => onChangeDraft({ diagnosisTimeoutMs: Number(e.target.value) })}
            error={errors.diagnosisTimeoutMs}
          />
          <p className="text-[11px] text-em-text-muted">
            Client-side timeout for <span className="font-mono">/api/v1/diagnose/stream</span>{' '}
            (15s-120s).
          </p>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="settings-diagnosis-radius"
            className="block text-[11px] font-mono uppercase tracking-wider text-em-text-dim"
          >
            Source Context Line Radius (+/- lines)
          </label>
          <Input
            id="settings-diagnosis-radius"
            type="number"
            min={SETTINGS_LIMITS.minContextRadius}
            max={SETTINGS_LIMITS.maxContextRadius}
            value={draft.diagnosisContextRadius}
            onChange={(e) => onChangeDraft({ diagnosisContextRadius: Number(e.target.value) })}
            error={errors.diagnosisContextRadius}
          />
          <p className="text-[11px] text-em-text-muted">
            Lines extracted around the selected finding ({SETTINGS_LIMITS.minContextRadius}-
            {SETTINGS_LIMITS.maxContextRadius}, strictly capped at 16 KiB).
          </p>
        </div>
      </div>

      {/* Honest Server-Governed Model/Provider Limitations */}
      <div className="rounded-md border border-em-border-default bg-em-workspace p-3 space-y-2 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 font-semibold text-em-text-secondary">
            <Lock className="w-3.5 h-3.5 text-em-text-dim" />
            Server-Controlled Provider Configuration (Unavailable to Edit in Browser)
          </span>
          <Badge variant="neutral" size="sm">
            Server .env Only
          </Badge>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] font-mono">
          <div className="rounded border border-em-border-hairline bg-em-card px-2.5 py-2">
            <span className="text-em-text-dim block">REASONING PROVIDER</span>
            <span className="text-em-text-primary">{BACKEND_INVARIANTS.defaultProviderHint}</span>
          </div>
          <div className="rounded border border-em-border-hairline bg-em-card px-2.5 py-2">
            <span className="text-em-text-dim block">STREAM ENDPOINT &amp; SCOPE</span>
            <span className="text-em-text-primary">
              {BACKEND_INVARIANTS.diagnosisProtocol} · Python Only
            </span>
          </div>
        </div>
        <p className="text-[11px] text-em-text-muted leading-relaxed">
          Switching AI providers (<span className="font-mono">ollama</span> vs.{' '}
          <span className="font-mono">openai</span>), model IDs, sampling temperature (0.1), and
          API keys is restricted to backend environment variables for security; the API exposes no
          runtime provider mutation or live telemetry inspection endpoint.
        </p>
      </div>
    </section>
  );
};
