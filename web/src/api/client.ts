import { ApiError, HealthResponse } from '../types/api';

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

export class ApiClient {
  private baseUrl: string;
  private defaultTimeoutMs: number;

  constructor(
    baseUrl: string = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
    defaultTimeoutMs: number = 8000
  ) {
    // Strip trailing slash if present
    this.baseUrl = baseUrl.replace(/\/+$/, '');
    this.defaultTimeoutMs = defaultTimeoutMs;
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  public setBaseUrl(url: string): void {
    this.baseUrl = url.replace(/\/+$/, '');
  }

  public async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { timeoutMs = this.defaultTimeoutMs, signal, headers, ...restOptions } = options;

    const controller = new AbortController();
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    // Combine caller signal with timeout
    if (signal) {
      signal.addEventListener('abort', () => controller.abort());
    }

    if (timeoutMs > 0) {
      timeoutId = setTimeout(() => {
        controller.abort();
      }, timeoutMs);
    }

    const cleanPath = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${this.baseUrl}${cleanPath}`;

    try {
      const response = await fetch(url, {
        ...restOptions,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          ...headers,
        },
      });

      if (timeoutId) clearTimeout(timeoutId);

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
          detail: errorData.detail || response.statusText || 'Request failed',
          status_code: response.status,
          request_id: response.headers.get('X-Request-ID') || errorData.request_id || null,
        };

        throw normalizedError;
      }

      if (isJson) {
        return (await response.json()) as T;
      }
      return (await response.text()) as unknown as T;
    } catch (err: unknown) {
      if (timeoutId) clearTimeout(timeoutId);

      if ((err as Error)?.name === 'AbortError') {
        throw {
          error: 'TimeoutError',
          detail: `Request timed out after ${timeoutMs}ms`,
          status_code: 408,
          request_id: null,
        } as ApiError;
      }

      // If already normalized ApiError, rethrow
      if (typeof err === 'object' && err !== null && 'error' in err && 'detail' in err) {
        throw err as ApiError;
      }

      // Network or other runtime failure
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
}

export const apiClient = new ApiClient();
