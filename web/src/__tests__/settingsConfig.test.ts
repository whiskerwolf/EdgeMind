import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  clearStoredSettings,
  DEFAULT_APP_SETTINGS,
  EDGEMIND_SETTINGS_STORAGE_KEY,
  getDefaultApiBaseUrl,
  loadStoredSettings,
  saveStoredSettings,
  validateApiBaseUrl,
  validateAppSettings,
} from '../utils/settingsConfig';

describe('settingsConfig', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('resolves non-empty default API base URL safely', () => {
    const resolved = getDefaultApiBaseUrl();
    expect(validateApiBaseUrl(resolved)).toBeNull();
    expect(resolved.endsWith('/')).toBe(false);
  });

  it('validates API base URLs strictly against unsafe protocols and embedded credentials', () => {
    expect(validateApiBaseUrl('http://127.0.0.1:8000')).toBeNull();
    expect(validateApiBaseUrl('https://edgemind.internal:8443/api')).toBeNull();
    expect(validateApiBaseUrl('')).toMatch(/required/i);
    expect(validateApiBaseUrl('not-a-url')).toMatch(/valid HTTP/i);
    expect(validateApiBaseUrl('javascript:alert(1)')).toMatch(/http:\/\/ and https:\/\//i);
    expect(validateApiBaseUrl('http://user:pass@127.0.0.1:8000')).toMatch(/credentials/i);
  });

  it('validates numeric bounds and filename rules across AppSettings', () => {
    const invalid = {
      ...DEFAULT_APP_SETTINGS,
      defaultFilename: '   ',
      defaultMaxCandidates: 99,
      analysisTimeoutMs: 500,
      diagnosisTimeoutMs: 2000,
      diagnosisContextRadius: 1,
      sessionHistoryLimit: 200,
    };
    const errors = validateAppSettings(invalid);
    expect(errors.defaultFilename).toBeDefined();
    expect(errors.defaultMaxCandidates).toBeDefined();
    expect(errors.analysisTimeoutMs).toBeDefined();
    expect(errors.diagnosisTimeoutMs).toBeDefined();
    expect(errors.diagnosisContextRadius).toBeDefined();
    expect(errors.sessionHistoryLimit).toBeDefined();
  });

  it('persists valid settings cleanly and recovers safely from corrupted localStorage', () => {
    const custom = {
      ...DEFAULT_APP_SETTINGS,
      apiBaseUrl: 'http://localhost:9000',
      editorFontSize: 15,
      editorTabSize: 2 as const,
      editorMinimap: true,
      historyPageSize: 50 as const,
    };

    expect(saveStoredSettings(custom)).toEqual({ ok: true });
    expect(loadStoredSettings()).toEqual(custom);

    // Corrupted JSON or invalid bounds in storage fall back cleanly
    localStorage.setItem(EDGEMIND_SETTINGS_STORAGE_KEY, '{invalid json');
    expect(loadStoredSettings()).toEqual(DEFAULT_APP_SETTINGS);

    localStorage.setItem(
      EDGEMIND_SETTINGS_STORAGE_KEY,
      JSON.stringify({
        apiBaseUrl: 'javascript:evil()',
        defaultMaxCandidates: 999,
        editorFontSize: 99,
      })
    );
    const sanitized = loadStoredSettings();
    expect(sanitized.apiBaseUrl).toBe(DEFAULT_APP_SETTINGS.apiBaseUrl);
    expect(sanitized.defaultMaxCandidates).toBe(25);
    expect(sanitized.editorFontSize).toBe(DEFAULT_APP_SETTINGS.editorFontSize);

    clearStoredSettings();
    expect(localStorage.getItem(EDGEMIND_SETTINGS_STORAGE_KEY)).toBeNull();
  });

  it('handles storage write errors without throwing', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });

    const result = saveStoredSettings(DEFAULT_APP_SETTINGS);
    expect(result).toEqual({ ok: false, error: 'QuotaExceededError' });
  });
});
