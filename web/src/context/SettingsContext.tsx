import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { ApiClient, apiClient } from '../api/client';
import { ApiError, HealthResponse } from '../types/api';
import {
  AppSettings,
  clearStoredSettings,
  DEFAULT_APP_SETTINGS,
  getDefaultApiBaseUrl,
  loadStoredSettings,
  normalizeApiBaseUrl,
  saveStoredSettings,
  validateApiBaseUrl,
} from '../utils/settingsConfig';

export interface ConnectionProbeResult {
  ok: boolean;
  url: string;
  latencyMs: number;
  service?: string;
  statusText?: string;
  errorDetail?: string;
}

export interface SettingsContextValue {
  settings: AppSettings;
  storageError: string | null;
  saveSettings: (next: AppSettings) => { ok: boolean; error?: string };
  updateSettingsImmediate: (partial: Partial<AppSettings>) => { ok: boolean; error?: string };
  resetSettings: () => AppSettings;
  probeConnection: (targetUrl: string, signal?: AbortSignal) => Promise<ConnectionProbeResult>;
}

const SettingsContext = createContext<SettingsContextValue | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<AppSettings>(() => {
    const initial = loadStoredSettings();
    apiClient.setBaseUrl?.(initial.apiBaseUrl);
    return initial;
  });
  const [storageError, setStorageError] = useState<string | null>(null);

  // Keep singleton apiClient synchronized with validated persisted Base URL
  useEffect(() => {
    apiClient.setBaseUrl?.(settings.apiBaseUrl);
  }, [settings.apiBaseUrl]);

  const applyAndPersist = useCallback((candidate: AppSettings): { ok: boolean; error?: string } => {
    const normalized: AppSettings = {
      ...candidate,
      apiBaseUrl: normalizeApiBaseUrl(candidate.apiBaseUrl),
      defaultFilename: candidate.defaultFilename.trim() || DEFAULT_APP_SETTINGS.defaultFilename,
    };

    const result = saveStoredSettings(normalized);
    if (!result.ok) {
      setStorageError(result.error);
      return { ok: false, error: result.error };
    }

    setStorageError(null);
    setSettings(normalized);
    apiClient.setBaseUrl?.(normalized.apiBaseUrl);
    return { ok: true };
  }, []);

  const saveSettings = useCallback(
    (next: AppSettings) => applyAndPersist(next),
    [applyAndPersist]
  );

  const updateSettingsImmediate = useCallback(
    (partial: Partial<AppSettings>) => applyAndPersist({ ...settings, ...partial }),
    [settings, applyAndPersist]
  );

  const resetSettings = useCallback((): AppSettings => {
    clearStoredSettings();
    const defaults: AppSettings = {
      ...DEFAULT_APP_SETTINGS,
      apiBaseUrl: getDefaultApiBaseUrl(),
    };
    setStorageError(null);
    setSettings(defaults);
    apiClient.setBaseUrl?.(defaults.apiBaseUrl);
    return defaults;
  }, []);

  const probeConnection = useCallback(
    async (targetUrl: string, signal?: AbortSignal): Promise<ConnectionProbeResult> => {
      const urlErr = validateApiBaseUrl(targetUrl);
      if (urlErr) {
        return {
          ok: false,
          url: targetUrl,
          latencyMs: 0,
          errorDetail: urlErr,
        };
      }

      const normalizedUrl = normalizeApiBaseUrl(targetUrl);
      const tempClient = new ApiClient(normalizedUrl, 4000);
      const start = performance.now();
      try {
        const res: HealthResponse = await tempClient.getHealth(signal, 4000);
        const latencyMs = Math.max(1, Math.round(performance.now() - start));
        if (res?.status === 'healthy') {
          return {
            ok: true,
            url: normalizedUrl,
            latencyMs,
            service: res.service,
            statusText: res.status,
          };
        }
        return {
          ok: false,
          url: normalizedUrl,
          latencyMs,
          errorDetail: 'Endpoint responded but did not return healthy EdgeMind health payload.',
        };
      } catch (err: unknown) {
        const latencyMs = Math.max(1, Math.round(performance.now() - start));
        const apiErr = err as ApiError;
        return {
          ok: false,
          url: normalizedUrl,
          latencyMs,
          errorDetail:
            apiErr?.detail || (err instanceof Error ? err.message : 'Unable to connect to endpoint.'),
        };
      }
    },
    []
  );

  return (
    <SettingsContext.Provider
      value={{
        settings,
        storageError,
        saveSettings,
        updateSettingsImmediate,
        resetSettings,
        probeConnection,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
};

export function useSettingsContext(): SettingsContextValue {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettingsContext must be used within a SettingsProvider');
  }
  return context;
}

export function useOptionalSettings(): AppSettings {
  const context = useContext(SettingsContext);
  return context ? context.settings : DEFAULT_APP_SETTINGS;
}
