import {
  AnalysisReport,
  AnalysisSessionItem,
  AnalyzeCodeRequest,
  ApiError,
  AuthTokenResponse,
  EdgeMindAnalyzeRequest,
  EdgeMindAnalyzeResponse,
  HealthResponse,
  PaginatedReportsResponse,
  PersistedReportDocument,
  UserLoginPayload,
} from '../types/api';

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export function sanitizeApiErrorDetail(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/Bearer\s+[A-Za-z0-9\-_.]+/gi, 'Bearer [REDACTED]')
    .replace(/(?:sk-(?:proj-)?[a-zA-Z0-9_-]{20,}|AIza[0-9A-Za-z\-_]{30,})/g, '[REDACTED]')
    .replace(/(password|secret_key|api_key)=([^\s&]+)/gi, '$1=[REDACTED]');
}

function resolveInitialBaseUrl(): string {
  const envUrl =
    typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE_URL
      ? String(import.meta.env.VITE_API_BASE_URL).trim()
      : '';
  if (envUrl) return envUrl.replace(/\/+$/, '');

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

export class ApiClient {
  private baseUrl: string;
  private defaultTimeoutMs: number;
  private authToken: string | null = null;

  constructor(
    baseUrl: string = resolveInitialBaseUrl(),
    defaultTimeoutMs: number = 8000
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.defaultTimeoutMs = defaultTimeoutMs;
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  public setBaseUrl(url: string): void {
    this.baseUrl = url.replace(/\/+$/, '');
  }

  public setAuthToken(token: string | null): void {
    this.authToken = token && token.trim() ? token.trim() : null;
  }

  public hasAuthToken(): boolean {
    return this.authToken !== null;
  }

  public async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { timeoutMs = this.defaultTimeoutMs, signal, headers, ...restOptions } = options;

    const controller = new AbortController();
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let onCallerAbort: (() => void) | undefined;

    if (signal) {
      if (signal.aborted) {
        controller.abort();
      } else {
        onCallerAbort = () => controller.abort();
        signal.addEventListener('abort', onCallerAbort, { once: true });
      }
    }

    if (timeoutMs > 0) {
      timeoutId = setTimeout(() => {
        controller.abort();
      }, timeoutMs);
    }

    const cleanPath = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${this.baseUrl}${cleanPath}`;

    try {
      const requestHeaders: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      };
      if (this.authToken) {
        requestHeaders.Authorization = `Bearer ${this.authToken}`;
      }

      const response = await fetch(url, {
        ...restOptions,
        signal: controller.signal,
        headers: {
          ...requestHeaders,
          ...headers,
        },
      });

      if (timeoutId) clearTimeout(timeoutId);
      if (signal && onCallerAbort) {
        signal.removeEventListener('abort', onCallerAbort);
      }

      const contentType = response.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');

      if (!response.ok) {
        let errorData: Partial<ApiError> = {};
        if (isJson) {
          try {
            errorData = await response.json();
          } catch {
            // Ignore parse failure on error body
          }
        } else {
          const text = await response.text();
          errorData = { detail: text };
        }

        const normalizedError: ApiError = {
          error: errorData.error || `HTTP ${response.status}`,
          detail: sanitizeApiErrorDetail(errorData.detail || response.statusText || 'Request failed'),
          status_code: response.status,
          request_id: response.headers.get('X-Request-ID') || errorData.request_id || null,
        };

        throw normalizedError;
      }

      if (response.status === 204) {
        return undefined as unknown as T;
      }

      if (isJson) {
        return (await response.json()) as T;
      }
      return (await response.text()) as unknown as T;
    } catch (err: unknown) {
      if (timeoutId) clearTimeout(timeoutId);
      if (signal && onCallerAbort) {
        signal.removeEventListener('abort', onCallerAbort);
      }

      if ((err as Error)?.name === 'AbortError') {
        if (signal?.aborted) {
          const abortError = new Error('Aborted');
          abortError.name = 'AbortError';
          throw abortError;
        }
        throw {
          error: 'TimeoutError',
          detail: `Request timed out after ${timeoutMs}ms`,
          status_code: 408,
          request_id: null,
        } as ApiError;
      }

      if (typeof err === 'object' && err !== null && 'error' in err && 'detail' in err) {
        throw err as ApiError;
      }

      const networkError: ApiError = {
        error: 'NetworkError',
        detail: (err as Error)?.message || 'Failed to connect to EdgeMind backend',
        status_code: 0,
        request_id: null,
      };
      throw networkError;
    }
  }

  public async getHealth(signal?: AbortSignal, timeoutMs: number = 5000): Promise<HealthResponse> {
    return this.request<HealthResponse>('/health', {
      method: 'GET',
      signal,
      timeoutMs,
    });
  }

  public async analyzeCode(
    payload: AnalyzeCodeRequest,
    signal?: AbortSignal,
    timeoutMs: number = 15000
  ): Promise<AnalysisReport> {
    return this.request<AnalysisReport>('/api/v1/analyze', {
      method: 'POST',
      body: JSON.stringify({
        code: payload.code,
        filename: payload.filename || 'snippet.py',
        static_only: true,
      }),
      signal,
      timeoutMs,
    });
  }

  public async analyzeEdgeMind(
    payload: EdgeMindAnalyzeRequest,
    signal?: AbortSignal,
    timeoutMs: number = 15000
  ): Promise<EdgeMindAnalyzeResponse> {
    return this.request<EdgeMindAnalyzeResponse>('/api/v1/edgemind/analyze', {
      method: 'POST',
      body: JSON.stringify({
        code: payload.code,
        filename: payload.filename || 'snippet.py',
        problem_context: payload.problem_context,
        test_cases: payload.test_cases,
        max_candidates: payload.max_candidates ?? 10,
        static_only: true,
      }),
      signal,
      timeoutMs,
    });
  }

  public async getRecentAnalyses(
    limit: number = 5,
    signal?: AbortSignal,
    timeoutMs: number = 6000
  ): Promise<AnalysisSessionItem[]> {
    const boundedLimit = Math.max(1, Math.min(50, Math.floor(limit)));
    return this.request<AnalysisSessionItem[]>(
      `/api/v1/analyses/report?skip=0&limit=${boundedLimit}`,
      {
        method: 'GET',
        signal,
        timeoutMs,
      }
    );
  }

  public async getPersistedReports(
    params: { skip?: number; limit?: number; projectId?: string; problemSlug?: string } = {},
    signal?: AbortSignal,
    timeoutMs: number = 8000
  ): Promise<PaginatedReportsResponse> {
    const skip = Math.max(0, Math.floor(params.skip ?? 0));
    const limit = Math.max(1, Math.min(100, Math.floor(params.limit ?? 20)));
    const search = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (params.projectId) search.set('project_id', params.projectId);
    if (params.problemSlug) search.set('problem_slug', params.problemSlug);

    return this.request<PaginatedReportsResponse>(`/api/v1/reports?${search.toString()}`, {
      method: 'GET',
      signal,
      timeoutMs,
    });
  }

  public async getReportBySessionId(
    analysisId: string,
    signal?: AbortSignal,
    timeoutMs: number = 8000
  ): Promise<PersistedReportDocument> {
    return this.request<PersistedReportDocument>(`/api/v1/analyses/${encodeURIComponent(analysisId)}/report`, {
      method: 'GET',
      signal,
      timeoutMs,
    });
  }

  public async deleteAnalysisReport(
    analysisId: string,
    signal?: AbortSignal,
    timeoutMs: number = 8000
  ): Promise<void> {
    await this.request<void>(`/api/v1/analyses/${encodeURIComponent(analysisId)}/report`, {
      method: 'DELETE',
      signal,
      timeoutMs,
    });
  }

  public async login(
    payload: UserLoginPayload,
    signal?: AbortSignal,
    timeoutMs: number = 8000
  ): Promise<AuthTokenResponse> {
    return this.request<AuthTokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
      signal,
      timeoutMs,
    });
  }

  public async logout(
    refreshToken: string,
    signal?: AbortSignal,
    timeoutMs: number = 5000
  ): Promise<void> {
    await this.request<void>('/api/v1/auth/logout', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken }),
      signal,
      timeoutMs,
    });
  }

  public async getGoogleOAuthAuthorizationUrl(
    frontendOrigin?: string,
    signal?: AbortSignal,
    timeoutMs: number = 8000
  ): Promise<{ provider: string; authorization_url: string; expires_in: number }> {
    const query = frontendOrigin
      ? `?frontend_origin=${encodeURIComponent(frontendOrigin)}`
      : '';
    return this.request<{ provider: string; authorization_url: string; expires_in: number }>(
      `/api/v1/auth/oauth/google${query}`,
      {
        method: 'GET',
        signal,
        timeoutMs,
      }
    );
  }
}

export const apiClient = new ApiClient();
