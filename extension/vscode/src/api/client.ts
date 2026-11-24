import { Endpoints } from './endpoints';
import {
  ApiResponse,
  HealthResponse,
  ApiError,
  AnalyzeCodeRequest,
  AnalysisReport,
} from '../types/api';

export interface ClientLogger {
  info(message: string): void;
  warn(message: string): void;
  error(message: string, error?: unknown): void;
}

export interface ApiClientOptions {
  baseUrl?: string;
  defaultTimeoutMs?: number;
  logger?: ClientLogger;
}

/**
 * Reusable HTTP client for EdgeMind FastAPI backend.
 * Uses native Node.js fetch with AbortSignal timeout and structured error handling.
 */
export class ApiClient {
  private baseUrl: string;
  private defaultTimeoutMs: number;
  private logger?: ClientLogger;

  constructor(options?: ApiClientOptions) {
    this.baseUrl = (options?.baseUrl || 'http://127.0.0.1:8000').replace(/\/+$/, '');
    this.defaultTimeoutMs = options?.defaultTimeoutMs ?? 10000;
    this.logger = options?.logger;
  }

  public setBaseUrl(url: string): void {
    this.baseUrl = url.trim().replace(/\/+$/, '');
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * Send a GET request to /health to verify backend connectivity.
   */
  public async checkHealth(timeoutMs?: number): Promise<ApiResponse<HealthResponse>> {
    return this.request<HealthResponse>(Endpoints.HEALTH, {
      method: 'GET',
      timeoutMs: timeoutMs ?? this.defaultTimeoutMs,
    });
  }

  /**
   * Send source code to POST /api/v1/analyze for static analysis.
   */
  public async analyzeCode(
    payload: AnalyzeCodeRequest,
    options?: { timeoutMs?: number; signal?: AbortSignal }
  ): Promise<ApiResponse<AnalysisReport>> {
    return this.request<AnalysisReport>(Endpoints.ANALYZE, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        code: payload.code,
        filename: payload.filename || 'snippet.py',
        static_only: true,
      }),
      timeoutMs: options?.timeoutMs ?? this.defaultTimeoutMs,
      signal: options?.signal,
    });
  }

  /**
   * Generic HTTP request dispatcher with timeout, error translation, and timing metrics.
   */
  public async request<T>(
    endpointPath: string,
    options?: RequestInit & { timeoutMs?: number }
  ): Promise<ApiResponse<T>> {
    const timeout = options?.timeoutMs ?? this.defaultTimeoutMs;
    const method = options?.method ?? 'GET';
    const cleanPath = endpointPath.startsWith('/') ? endpointPath : `/${endpointPath}`;
    const fullUrl = `${this.baseUrl}${cleanPath}`;

    this.logger?.info(`[ApiClient] ${method} ${fullUrl} (timeout: ${timeout}ms)`);
    const startTime = performance.now();

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    // Link external cancellation signal if provided
    if (options?.signal) {
      if (options.signal.aborted) {
        controller.abort();
      } else {
        options.signal.addEventListener('abort', () => controller.abort(), { once: true });
      }
    }

    try {
      const response = await fetch(fullUrl, {
        ...options,
        signal: controller.signal,
        headers: {
          'Accept': 'application/json',
          ...(options?.headers || {}),
        },
      });

      clearTimeout(timeoutId);
      const durationMs = Math.round(performance.now() - startTime);

      if (!response.ok) {
        let errorDetail = `HTTP ${response.status} ${response.statusText}`;
        try {
          const errBody = (await response.json()) as ApiError;
          if (errBody && (errBody.detail || errBody.error)) {
            errorDetail = errBody.detail || errBody.error;
          }
        } catch {
          // If body is not JSON, try reading as text
          try {
            const textBody = await response.text();
            if (textBody && textBody.length < 200) {
              errorDetail = `${errorDetail}: ${textBody.trim()}`;
            }
          } catch {
            // Keep status text
          }
        }

        this.logger?.warn(`[ApiClient] Failed: ${method} ${fullUrl} -> ${response.status} (${durationMs}ms): ${errorDetail}`);
        return {
          success: false,
          error: errorDetail,
          statusCode: response.status,
          durationMs,
        };
      }

      let parsedData: T;
      try {
        parsedData = (await response.json()) as T;
      } catch (jsonErr) {
        this.logger?.error(`[ApiClient] Malformed JSON response from ${fullUrl} (${durationMs}ms)`, jsonErr);
        return {
          success: false,
          error: 'Backend returned invalid or malformed JSON.',
          statusCode: response.status,
          durationMs,
        };
      }

      this.logger?.info(`[ApiClient] Success: ${method} ${fullUrl} -> ${response.status} (${durationMs}ms)`);
      return {
        success: true,
        data: parsedData,
        statusCode: response.status,
        durationMs,
      };
    } catch (err: unknown) {
      clearTimeout(timeoutId);
      const durationMs = Math.round(performance.now() - startTime);

      let errorMessage = 'Network error communicating with EdgeMind backend.';
      if (err instanceof Error) {
        if (err.name === 'AbortError') {
          if (options?.signal?.aborted) {
            errorMessage = 'Request was cancelled.';
          } else {
            errorMessage = `Request timed out after ${timeout}ms. Is the EdgeMind backend responding?`;
          }
        } else if (err.message.includes('ECONNREFUSED')) {
          errorMessage = `Connection refused at ${this.baseUrl}. Is the EdgeMind server running?`;
        } else if (err.message.includes('ENOTFOUND')) {
          errorMessage = `Hostname lookup failed for ${this.baseUrl}. Please check your backend URL setting.`;
        } else {
          errorMessage = `Connection failed: ${err.message}`;
        }
      }

      this.logger?.warn(`[ApiClient] Network failure for ${method} ${fullUrl} (${durationMs}ms): ${errorMessage}`);
      return {
        success: false,
        error: errorMessage,
        durationMs,
      };
    }
  }
}
