import { HistorySortOption } from './historyHelpers';
import { validateWorkspaceFilename } from './workspaceConfig';

export const EDGEMIND_SETTINGS_STORAGE_KEY = 'edgemind.settings.v1';

export type SidebarDefaultMode = 'auto' | 'expanded' | 'collapsed';
export type EditorWordWrapMode = 'off' | 'on';
export type EditorLineNumbersMode = 'on' | 'off';

export interface AppSettings {
  // General & Interface (applied immediately)
  sidebarDefaultMode: SidebarDefaultMode;
  healthPollingIntervalMs: number;

  // Connection (validated & saved cleanly)
  apiBaseUrl: string;

  // Analysis (applied to analysis requests & defaults)
  defaultFilename: string;
  defaultMaxCandidates: number;
  analysisTimeoutMs: number;

  // AI Diagnosis (applied to bounded SSE requests)
  diagnosisTimeoutMs: number;
  diagnosisContextRadius: number;

  // Workspace & Editor (applied immediately to CodeEditorPanel & Monaco)
  editorFontSize: number;
  editorTabSize: 2 | 4;
  editorMinimap: boolean;
  editorWordWrap: EditorWordWrapMode;
  editorLineNumbers: EditorLineNumbersMode;

  // History & Session Retention
  historyDefaultSort: HistorySortOption;
  historyPageSize: 10 | 20 | 50;
  sessionHistoryLimit: number;
}

export const SETTINGS_LIMITS = {
  healthPollingOptions: [4000, 8000, 15000, 30000] as const,
  minMaxCandidates: 1,
  maxMaxCandidates: 25,
  minAnalysisTimeoutMs: 5000,
  maxAnalysisTimeoutMs: 60000,
  minDiagnosisTimeoutMs: 15000,
  maxDiagnosisTimeoutMs: 120000,
  minContextRadius: 5,
  maxContextRadius: 30,
  editorFontSizes: [12, 13, 14, 15, 16] as const,
  historyPageSizes: [10, 20, 50] as const,
  minSessionHistoryLimit: 5,
  maxSessionHistoryLimit: 50,
} as const;

export const BACKEND_INVARIANTS = {
  staticOnly: true,
  maxSourceCodeBytes: 64 * 1024,
  supportedLanguages: ['python'] as const,
  diagnosisProtocol: 'POST /api/v1/diagnose/stream (SSE)',
  defaultProviderHint: 'Configured server-side via .env (default: Ollama / qwen3:4b)',
} as const;

export function getDefaultApiBaseUrl(): string {
  const rawEnv =
    typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL
      ? String(import.meta.env.VITE_API_BASE_URL).trim()
      : '';
  if (rawEnv) {
    return rawEnv.replace(/\/+$/, '');
  }

  // In deployed production browser builds, default to same-origin so Caddy / reverse proxies
  // work cleanly without hardcoded localhost URLs or extra build-time domain coupling.
  if (
    typeof import.meta !== 'undefined' &&
    import.meta.env?.PROD &&
    typeof window !== 'undefined' &&
    window.location?.origin &&
    /^https?:$/.test(window.location.protocol)
  ) {
    return window.location.origin.replace(/\/+$/, '');
  }

  return 'http://127.0.0.1:8000';
}

export const DEFAULT_APP_SETTINGS: AppSettings = {
  sidebarDefaultMode: 'auto',
  healthPollingIntervalMs: 8000,
  apiBaseUrl: getDefaultApiBaseUrl(),
  defaultFilename: 'snippet.py',
  defaultMaxCandidates: 10,
  analysisTimeoutMs: 15000,
  diagnosisTimeoutMs: 60000,
  diagnosisContextRadius: 15,
  editorFontSize: 13,
  editorTabSize: 4,
  editorMinimap: false,
  editorWordWrap: 'off',
  editorLineNumbers: 'on',
  historyDefaultSort: 'newest',
  historyPageSize: 20,
  sessionHistoryLimit: 25,
};

export interface SettingsValidationErrors {
  apiBaseUrl?: string;
  defaultFilename?: string;
  defaultMaxCandidates?: string;
  analysisTimeoutMs?: string;
  diagnosisTimeoutMs?: string;
  diagnosisContextRadius?: string;
  sessionHistoryLimit?: string;
}

/**
 * Validates that API Base URL uses http/https, has a valid hostname, and embeds no URL credentials.
 */
export function validateApiBaseUrl(rawUrl: string): string | null {
  const trimmed = rawUrl.trim();
  if (!trimmed) {
    return 'API Base URL is required.';
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return 'Enter a valid HTTP or HTTPS URL (e.g., http://127.0.0.1:8000).';
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return 'Only http:// and https:// protocols are permitted.';
  }
  if (!parsed.hostname) {
    return 'API Base URL must include a hostname.';
  }
  if (parsed.username || parsed.password) {
    return 'Credentials must not be embedded in the API Base URL.';
  }
  return null;
}

export function normalizeApiBaseUrl(rawUrl: string): string {
  return rawUrl.trim().replace(/\/+$/, '');
}

export function validateAppSettings(candidate: AppSettings): SettingsValidationErrors {
  const errors: SettingsValidationErrors = {};

  const urlErr = validateApiBaseUrl(candidate.apiBaseUrl);
  if (urlErr) errors.apiBaseUrl = urlErr;

  const fileErr = validateWorkspaceFilename(candidate.defaultFilename);
  if (fileErr) errors.defaultFilename = fileErr;

  if (
    !Number.isFinite(candidate.defaultMaxCandidates) ||
    candidate.defaultMaxCandidates < SETTINGS_LIMITS.minMaxCandidates ||
    candidate.defaultMaxCandidates > SETTINGS_LIMITS.maxMaxCandidates
  ) {
    errors.defaultMaxCandidates = `Must be between ${SETTINGS_LIMITS.minMaxCandidates} and ${SETTINGS_LIMITS.maxMaxCandidates}.`;
  }

  if (
    !Number.isFinite(candidate.analysisTimeoutMs) ||
    candidate.analysisTimeoutMs < SETTINGS_LIMITS.minAnalysisTimeoutMs ||
    candidate.analysisTimeoutMs > SETTINGS_LIMITS.maxAnalysisTimeoutMs
  ) {
    errors.analysisTimeoutMs = `Must be between ${SETTINGS_LIMITS.minAnalysisTimeoutMs} and ${SETTINGS_LIMITS.maxAnalysisTimeoutMs} ms.`;
  }

  if (
    !Number.isFinite(candidate.diagnosisTimeoutMs) ||
    candidate.diagnosisTimeoutMs < SETTINGS_LIMITS.minDiagnosisTimeoutMs ||
    candidate.diagnosisTimeoutMs > SETTINGS_LIMITS.maxDiagnosisTimeoutMs
  ) {
    errors.diagnosisTimeoutMs = `Must be between ${SETTINGS_LIMITS.minDiagnosisTimeoutMs} and ${SETTINGS_LIMITS.maxDiagnosisTimeoutMs} ms.`;
  }

  if (
    !Number.isFinite(candidate.diagnosisContextRadius) ||
    candidate.diagnosisContextRadius < SETTINGS_LIMITS.minContextRadius ||
    candidate.diagnosisContextRadius > SETTINGS_LIMITS.maxContextRadius
  ) {
    errors.diagnosisContextRadius = `Must be between ${SETTINGS_LIMITS.minContextRadius} and ${SETTINGS_LIMITS.maxContextRadius} lines.`;
  }

  if (
    !Number.isFinite(candidate.sessionHistoryLimit) ||
    candidate.sessionHistoryLimit < SETTINGS_LIMITS.minSessionHistoryLimit ||
    candidate.sessionHistoryLimit > SETTINGS_LIMITS.maxSessionHistoryLimit
  ) {
    errors.sessionHistoryLimit = `Must be between ${SETTINGS_LIMITS.minSessionHistoryLimit} and ${SETTINGS_LIMITS.maxSessionHistoryLimit} runs.`;
  }

  return errors;
}

function clampInt(val: unknown, min: number, max: number, fallback: number): number {
  if (typeof val !== 'number' || !Number.isFinite(val)) return fallback;
  return Math.max(min, Math.min(max, Math.round(val)));
}

/**
 * Loads non-secret frontend settings safely from localStorage, falling back cleanly on corruption or blocked storage.
 */
export function loadStoredSettings(): AppSettings {
  const defaults = { ...DEFAULT_APP_SETTINGS, apiBaseUrl: getDefaultApiBaseUrl() };
  if (typeof window === 'undefined') return defaults;

  try {
    const raw = window.localStorage.getItem(EDGEMIND_SETTINGS_STORAGE_KEY);
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<AppSettings> | null;
    if (!parsed || typeof parsed !== 'object') return defaults;

    const validUrl =
      typeof parsed.apiBaseUrl === 'string' && !validateApiBaseUrl(parsed.apiBaseUrl)
        ? normalizeApiBaseUrl(parsed.apiBaseUrl)
        : defaults.apiBaseUrl;

    const validFilename =
      typeof parsed.defaultFilename === 'string' &&
      !validateWorkspaceFilename(parsed.defaultFilename)
        ? parsed.defaultFilename.trim()
        : defaults.defaultFilename;

    const sidebarDefaultMode: SidebarDefaultMode =
      parsed.sidebarDefaultMode === 'expanded' ||
      parsed.sidebarDefaultMode === 'collapsed' ||
      parsed.sidebarDefaultMode === 'auto'
        ? parsed.sidebarDefaultMode
        : defaults.sidebarDefaultMode;

    const healthPollingIntervalMs = SETTINGS_LIMITS.healthPollingOptions.includes(
      parsed.healthPollingIntervalMs as (typeof SETTINGS_LIMITS.healthPollingOptions)[number]
    )
      ? (parsed.healthPollingIntervalMs as number)
      : defaults.healthPollingIntervalMs;

    const editorFontSize = SETTINGS_LIMITS.editorFontSizes.includes(
      parsed.editorFontSize as (typeof SETTINGS_LIMITS.editorFontSizes)[number]
    )
      ? (parsed.editorFontSize as number)
      : defaults.editorFontSize;

    const editorTabSize: 2 | 4 = parsed.editorTabSize === 2 || parsed.editorTabSize === 4
      ? parsed.editorTabSize
      : defaults.editorTabSize;

    const historyPageSize: 10 | 20 | 50 = SETTINGS_LIMITS.historyPageSizes.includes(
      parsed.historyPageSize as (typeof SETTINGS_LIMITS.historyPageSizes)[number]
    )
      ? (parsed.historyPageSize as 10 | 20 | 50)
      : defaults.historyPageSize;

    const validSorts: HistorySortOption[] = ['newest', 'oldest', 'score-desc', 'score-asc'];
    const historyDefaultSort: HistorySortOption = validSorts.includes(
      parsed.historyDefaultSort as HistorySortOption
    )
      ? (parsed.historyDefaultSort as HistorySortOption)
      : defaults.historyDefaultSort;

    return {
      sidebarDefaultMode,
      healthPollingIntervalMs,
      apiBaseUrl: validUrl,
      defaultFilename: validFilename,
      defaultMaxCandidates: clampInt(
        parsed.defaultMaxCandidates,
        SETTINGS_LIMITS.minMaxCandidates,
        SETTINGS_LIMITS.maxMaxCandidates,
        defaults.defaultMaxCandidates
      ),
      analysisTimeoutMs: clampInt(
        parsed.analysisTimeoutMs,
        SETTINGS_LIMITS.minAnalysisTimeoutMs,
        SETTINGS_LIMITS.maxAnalysisTimeoutMs,
        defaults.analysisTimeoutMs
      ),
      diagnosisTimeoutMs: clampInt(
        parsed.diagnosisTimeoutMs,
        SETTINGS_LIMITS.minDiagnosisTimeoutMs,
        SETTINGS_LIMITS.maxDiagnosisTimeoutMs,
        defaults.diagnosisTimeoutMs
      ),
      diagnosisContextRadius: clampInt(
        parsed.diagnosisContextRadius,
        SETTINGS_LIMITS.minContextRadius,
        SETTINGS_LIMITS.maxContextRadius,
        defaults.diagnosisContextRadius
      ),
      editorFontSize,
      editorTabSize,
      editorMinimap:
        typeof parsed.editorMinimap === 'boolean' ? parsed.editorMinimap : defaults.editorMinimap,
      editorWordWrap:
        parsed.editorWordWrap === 'on' || parsed.editorWordWrap === 'off'
          ? parsed.editorWordWrap
          : defaults.editorWordWrap,
      editorLineNumbers:
        parsed.editorLineNumbers === 'on' || parsed.editorLineNumbers === 'off'
          ? parsed.editorLineNumbers
          : defaults.editorLineNumbers,
      historyDefaultSort,
      historyPageSize,
      sessionHistoryLimit: clampInt(
        parsed.sessionHistoryLimit,
        SETTINGS_LIMITS.minSessionHistoryLimit,
        SETTINGS_LIMITS.maxSessionHistoryLimit,
        defaults.sessionHistoryLimit
      ),
    };
  } catch {
    return defaults;
  }
}

export function saveStoredSettings(
  settings: AppSettings
): { ok: true } | { ok: false; error: string } {
  const errors = validateAppSettings(settings);
  if (Object.keys(errors).length > 0) {
    return { ok: false, error: 'Settings failed validation before saving.' };
  }

  if (typeof window === 'undefined') {
    return { ok: true };
  }

  try {
    window.localStorage.setItem(EDGEMIND_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      error:
        err instanceof Error
          ? err.message
          : 'Browser localStorage denied write permission.',
    };
  }
}

export function clearStoredSettings(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(EDGEMIND_SETTINGS_STORAGE_KEY);
  } catch {
    // Ignore restricted storage cleanup errors
  }
}
