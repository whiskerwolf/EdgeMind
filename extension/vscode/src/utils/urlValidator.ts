export const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';

export interface UrlValidationResult {
  valid: boolean;
  normalized?: string;
  error?: string;
}

/**
 * Validate and normalize a candidate backend URL.
 * Accepts only http:// and https:// URLs with valid hostnames.
 */
export function validateBackendUrl(rawUrl: string): UrlValidationResult {
  if (!rawUrl || typeof rawUrl !== 'string' || !rawUrl.trim()) {
    return { valid: false, error: 'Backend URL must not be empty.' };
  }

  const trimmed = rawUrl.trim();
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return {
        valid: false,
        error: `Unsupported protocol '${parsed.protocol}'. Only http:// and https:// are permitted.`,
      };
    }
    if (!parsed.hostname) {
      return { valid: false, error: 'URL must contain a valid hostname or IP address.' };
    }
    // Return normalized URL without trailing slash
    const normalized = `${parsed.protocol}//${parsed.host}${parsed.pathname.replace(/\/+$/, '')}`;
    return { valid: true, normalized };
  } catch {
    return { valid: false, error: `Invalid URL format: '${trimmed}'` };
  }
}
