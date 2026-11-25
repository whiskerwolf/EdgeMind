import React, { useEffect, useMemo, useState } from 'react';
import { useAnalysisContext } from '../context/AnalysisContext';
import { useHealthContext } from '../context/HealthContext';
import { ConnectionProbeResult, useSettingsContext } from '../context/SettingsContext';
import { AppSettings, validateAppSettings } from '../utils/settingsConfig';
import { AiDiagnosisSettingsSection } from '../components/settings/AiDiagnosisSettingsSection';
import { AnalysisSettingsSection } from '../components/settings/AnalysisSettingsSection';
import { ConnectionSettingsSection } from '../components/settings/ConnectionSettingsSection';
import { GeneralEditorSection } from '../components/settings/GeneralEditorSection';
import { HistorySecuritySection } from '../components/settings/HistorySecuritySection';
import { SettingsHeader } from '../components/settings/SettingsHeader';

const SAVEABLE_KEYS: Array<keyof AppSettings> = [
  'apiBaseUrl',
  'healthPollingIntervalMs',
  'defaultFilename',
  'defaultMaxCandidates',
  'analysisTimeoutMs',
  'diagnosisTimeoutMs',
  'diagnosisContextRadius',
  'historyDefaultSort',
  'historyPageSize',
  'sessionHistoryLimit',
];

export const SettingsPage: React.FC = () => {
  const {
    settings,
    storageError,
    saveSettings,
    updateSettingsImmediate,
    resetSettings,
    probeConnection,
  } = useSettingsContext();

  const {
    status: healthStatus,
    data: healthData,
    durationMs: healthLatencyMs,
    error: healthError,
    checkHealth,
  } = useHealthContext();

  const { sessionRuns, clearSessionRuns, authSession, logoutBackend } = useAnalysisContext();

  const [draft, setDraft] = useState<AppSettings>(settings);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(
    null
  );
  const [isProbing, setIsProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<ConnectionProbeResult | null>(null);

  // Keep immediate-apply fields synchronized if changed outside draft
  useEffect(() => {
    setDraft((prev) => ({
      ...prev,
      sidebarDefaultMode: settings.sidebarDefaultMode,
      editorFontSize: settings.editorFontSize,
      editorTabSize: settings.editorTabSize,
      editorMinimap: settings.editorMinimap,
      editorWordWrap: settings.editorWordWrap,
      editorLineNumbers: settings.editorLineNumbers,
    }));
  }, [
    settings.sidebarDefaultMode,
    settings.editorFontSize,
    settings.editorTabSize,
    settings.editorMinimap,
    settings.editorWordWrap,
    settings.editorLineNumbers,
  ]);

  const validationErrors = useMemo(() => validateAppSettings(draft), [draft]);
  const hasValidationErrors = Object.keys(validationErrors).length > 0;

  const hasUnsavedChanges = useMemo(
    () => SAVEABLE_KEYS.some((key) => draft[key] !== settings[key]),
    [draft, settings]
  );

  const handleChangeDraft = (partial: Partial<AppSettings>) => {
    setFeedback(null);
    if ('apiBaseUrl' in partial) {
      setProbeResult(null);
    }
    setDraft((prev) => ({ ...prev, ...partial }));
  };

  const handleImmediateUpdate = (partial: Partial<AppSettings>) => {
    const result = updateSettingsImmediate(partial);
    setDraft((prev) => ({ ...prev, ...partial }));
    if (result.ok) {
      setFeedback({
        type: 'success',
        message: 'Immediate preference updated and saved locally.',
      });
    } else {
      setFeedback({
        type: 'error',
        message: result.error || 'Unable to persist immediate preference.',
      });
    }
  };

  const handleSave = () => {
    if (hasValidationErrors) {
      setFeedback({
        type: 'error',
        message: 'Resolve validation errors before saving settings.',
      });
      return;
    }

    const urlChanged = draft.apiBaseUrl.trim().replace(/\/+$/, '') !== settings.apiBaseUrl;
    const result = saveSettings(draft);
    if (!result.ok) {
      setFeedback({
        type: 'error',
        message: result.error || 'Failed to save configuration.',
      });
      return;
    }

    setFeedback({
      type: 'success',
      message: 'Settings saved locally and applied across active EdgeMind modules.',
    });

    if (urlChanged) {
      void checkHealth();
    }
  };

  const handleDiscard = () => {
    setDraft(settings);
    setProbeResult(null);
    setFeedback({
      type: 'success',
      message: 'Discarded unsaved configuration changes.',
    });
  };

  const handleResetDefaults = () => {
    const defaults = resetSettings();
    setDraft(defaults);
    setProbeResult(null);
    setFeedback({
      type: 'success',
      message: 'Restored all local preferences to EdgeMind defaults.',
    });
    void checkHealth();
  };

  const handleTestConnection = async () => {
    setIsProbing(true);
    setProbeResult(null);
    const result = await probeConnection(draft.apiBaseUrl);
    setProbeResult(result);
    setIsProbing(false);
  };

  return (
    <div className="space-y-4">
      <SettingsHeader
        hasUnsavedChanges={hasUnsavedChanges}
        hasValidationErrors={hasValidationErrors}
        feedback={feedback}
        storageError={storageError}
        onSave={handleSave}
        onDiscard={handleDiscard}
        onResetDefaults={handleResetDefaults}
      />

      <ConnectionSettingsSection
        apiBaseUrl={draft.apiBaseUrl}
        apiBaseUrlError={validationErrors.apiBaseUrl}
        healthPollingIntervalMs={draft.healthPollingIntervalMs}
        healthStatus={healthStatus}
        healthData={healthData}
        healthLatencyMs={healthLatencyMs}
        healthError={healthError}
        isProbing={isProbing}
        probeResult={probeResult}
        onChangeUrl={(nextUrl) => handleChangeDraft({ apiBaseUrl: nextUrl })}
        onChangePolling={(ms) => handleChangeDraft({ healthPollingIntervalMs: ms })}
        onTestConnection={() => {
          void handleTestConnection();
        }}
        onRefreshGlobalHealth={() => {
          void checkHealth();
        }}
      />

      <GeneralEditorSection
        settings={{
          ...settings,
          sidebarDefaultMode: draft.sidebarDefaultMode,
          editorFontSize: draft.editorFontSize,
          editorTabSize: draft.editorTabSize,
          editorMinimap: draft.editorMinimap,
          editorWordWrap: draft.editorWordWrap,
          editorLineNumbers: draft.editorLineNumbers,
        }}
        onUpdateImmediate={handleImmediateUpdate}
      />

      <AnalysisSettingsSection
        draft={draft}
        errors={validationErrors}
        onChangeDraft={handleChangeDraft}
      />

      <AiDiagnosisSettingsSection
        draft={draft}
        errors={validationErrors}
        onChangeDraft={handleChangeDraft}
      />

      <HistorySecuritySection
        draft={draft}
        errors={validationErrors}
        sessionRunCount={sessionRuns.length}
        authSessionEmail={authSession?.email ?? null}
        onChangeDraft={handleChangeDraft}
        onClearSessionHistory={() => {
          clearSessionRuns();
          setFeedback({
            type: 'success',
            message: 'Cleared in-memory browser session history.',
          });
        }}
        onLogoutBackend={() => {
          void logoutBackend();
          setFeedback({
            type: 'success',
            message: 'Signed out of in-memory backend session.',
          });
        }}
      />
    </div>
  );
};
