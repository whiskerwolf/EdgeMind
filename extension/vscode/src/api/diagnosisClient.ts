/**
 * EdgeMind Finding AI Diagnosis Streaming Client (Phase 5G.5).
 *
 * Dedicated client for consuming POST /api/v1/diagnose/stream SSE endpoints.
 *
 * Guarantees:
 * - Incremental, non-buffered token streaming
 * - Robust cancellation with AbortController / AbortSignal
 * - Reader lock release and body cancellation on abort/error
 * - Typed discriminated event union (diagnosis_started, response_chunk, completed, error)
 * - Safe JSON parsing with zero exposure of stack traces or credentials
 * - Automatic HTTP error translation (401, 404, 422, 429, 500)
 */

import { Endpoints } from './endpoints';
import { RawSSEEvent, SSEParser } from './sseParser';
import {
  DiagnoseFindingRequest,
  DiagnosisCompletedEvent,
  DiagnosisErrorEvent,
  DiagnosisResponseChunkEvent,
  DiagnosisStartedEvent,
  DiagnosisStreamEvent,
} from '../types/diagnosis';

export interface ClientLogger {
  info(message: string): void;
  warn(message: string): void;
  error(message: string, error?: unknown): void;
}

export interface DiagnosisClientOptions {
  baseUrl?: string;
  defaultTimeoutMs?: number;
  logger?: ClientLogger;
  fetchFn?: typeof fetch;
}

export interface StreamDiagnosisOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  onEvent?: (event: DiagnosisStreamEvent) => void;
}

/**
 * Structured client error for diagnosis streaming operations.
 */
export class DiagnosisClientError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly isRateLimit: boolean = false,
    public readonly isUnauthorized: boolean = false,
    public readonly isNetworkError: boolean = false,
    public readonly errorType?: string
  ) {
    super(DiagnosisClientError.sanitizeMessage(message));
    this.name = 'DiagnosisClientError';
  }

  /**
   * Redact sensitive tokens or credentials from error messages.
   */
  private static sanitizeMessage(raw: string): string {
    if (!raw) {
      return '';
    }
    return raw
      .replace(/Bearer\s+[A-Za-z0-9\-_\.]+/gi, 'Bearer [REDACTED]')
      .replace(/(?:sk-(?:proj-)?[a-zA-Z0-9_\-]{20,}|AIza[0-9A-Za-z\-_]{30,})/g, '[REDACTED]')
      .replace(/(?:password|secret_key|api_key)=([^\s&]+)/gi, '$1=[REDACTED]');
  }
}

/**
 * Dedicated streaming client consuming the EdgeMind diagnosis SSE endpoint.
 */
export class DiagnosisClient {
  private baseUrl: string;
  private defaultTimeoutMs: number;
  private logger?: ClientLogger;
  private fetchFn: typeof fetch;

  constructor(options?: DiagnosisClientOptions) {
    this.baseUrl = (options?.baseUrl || 'http://127.0.0.1:8000').replace(/\/+$/, '');
    this.defaultTimeoutMs = options?.defaultTimeoutMs ?? 60000; // 60s default for LLM stream
    this.logger = options?.logger;
    this.fetchFn = options?.fetchFn ?? globalThis.fetch;
  }

  public setBaseUrl(url: string): void {
    this.baseUrl = url.trim().replace(/\/+$/, '');
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * Stream finding diagnosis as real-time Server-Sent Events.
   * Yields typed DiagnosisStreamEvent instances via an async generator.
   */
  public async *streamDiagnosis(
    request: DiagnoseFindingRequest,
    options?: StreamDiagnosisOptions
  ): AsyncGenerator<DiagnosisStreamEvent, void, unknown> {
    const timeout = options?.timeoutMs ?? this.defaultTimeoutMs;
    const fullUrl = `${this.baseUrl}${Endpoints.DIAGNOSE_STREAM}`;

    this.logger?.info(`[DiagnosisClient] POST ${fullUrl} (timeout: ${timeout}ms)`);

    // Setup cancellation and timeout handling
    const abortController = new AbortController();
    const externalSignal = options?.signal;

    if (externalSignal?.aborted) {
      return;
    }

    const abortHandler = () => abortController.abort();
    if (externalSignal) {
      externalSignal.addEventListener('abort', abortHandler, { once: true });
    }

    const timeoutId = setTimeout(() => {
      abortController.abort();
    }, timeout);

    let response: Response;
    try {
      response = await this.fetchFn(fullUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify(request),
        signal: abortController.signal,
      });
    } catch (err: unknown) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', abortHandler);
      }

      if (externalSignal?.aborted || (err instanceof Error && err.name === 'AbortError')) {
        return;
      }
      throw new DiagnosisClientError(
        `Failed to connect to EdgeMind diagnosis service: ${err instanceof Error ? err.message : String(err)}`,
        undefined,
        false,
        false,
        true
      );
    }

    // HTTP Status Validation
    if (!response.ok) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', abortHandler);
      }

      const status = response.status;
      let errorDetail = `HTTP ${status}`;
      try {
        const errJson = await response.json();
        if (errJson && typeof errJson === 'object') {
          errorDetail = (errJson as { detail?: string; error?: string }).detail
            || (errJson as { detail?: string; error?: string }).error
            || JSON.stringify(errJson);
        }
      } catch {
        try {
          const errText = await response.text();
          if (errText) {
            errorDetail = errText.slice(0, 256);
          }
        } catch {
          // Ignore secondary read errors
        }
      }

      const isRateLimit = status === 429;
      const isUnauthorized = status === 401;
      throw new DiagnosisClientError(
        `Diagnosis request failed (${status}): ${errorDetail}`,
        status,
        isRateLimit,
        isUnauthorized
      );
    }

    // Content-Type validation
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('text/event-stream')) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', abortHandler);
      }
      throw new DiagnosisClientError(
        `Expected 'text/event-stream' Content-Type from diagnosis endpoint, received '${contentType}'`,
        response.status
      );
    }

    if (!response.body) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', abortHandler);
      }
      throw new DiagnosisClientError('Diagnosis response body is empty', response.status);
    }

    const reader = response.body.getReader();
    const parser = new SSEParser();
    let completedOrTerminalError = false;

    try {
      while (true) {
        if (externalSignal?.aborted) {
          break;
        }

        const { done, value } = await reader.read();

        if (done) {
          // Stream EOF: flush remaining buffer
          const trailing = parser.flush();
          if (trailing) {
            const event = this.mapRawEvent(trailing);
            if (event) {
              if (event.event === 'completed' || event.event === 'error') {
                completedOrTerminalError = true;
              }
              options?.onEvent?.(event);
              yield event;
            }
          }
          break;
        }

        if (value) {
          for (const raw of parser.feed(value)) {
            if (externalSignal?.aborted) {
              break;
            }

            const event = this.mapRawEvent(raw);
            if (!event) {
              continue;
            }

            if (event.event === 'completed' || event.event === 'error') {
              completedOrTerminalError = true;
            }

            options?.onEvent?.(event);
            yield event;

            if (completedOrTerminalError) {
              return;
            }
          }
        }
      }
    } catch (err: unknown) {
      if (externalSignal?.aborted || (err instanceof Error && err.name === 'AbortError')) {
        return;
      }
      throw new DiagnosisClientError(
        `Error while reading diagnosis stream: ${err instanceof Error ? err.message : String(err)}`,
        response.status
      );
    } finally {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', abortHandler);
      }
      reader.releaseLock();
      try {
        await response.body.cancel();
      } catch {
        // Ignore body cancellation errors
      }
    }

    // Check premature stream termination
    if (!externalSignal?.aborted && !completedOrTerminalError) {
      throw new DiagnosisClientError(
        'Diagnosis stream terminated prematurely without a completion or error event',
        response.status
      );
    }
  }

  /**
   * Validate and map a raw SSE wire event into a strongly-typed DiagnosisStreamEvent.
   */
  private mapRawEvent(raw: RawSSEEvent): DiagnosisStreamEvent | null {
    if (!raw.event || !raw.data) {
      return null;
    }

    const data = SSEParser.parseJsonData<Record<string, unknown>>(raw.data);
    if (!data || typeof data !== 'object') {
      this.logger?.warn(`[DiagnosisClient] Skipped non-JSON SSE data for event '${raw.event}'`);
      return null;
    }

    const seqId = typeof data.sequence_id === 'number'
      ? data.sequence_id
      : (raw.id ? parseInt(raw.id, 10) : 0);

    const timestamp = typeof data.timestamp === 'string'
      ? data.timestamp
      : new Date().toISOString();

    switch (raw.event) {
      case 'diagnosis_started': {
        const event: DiagnosisStartedEvent = {
          event: 'diagnosis_started',
          session_id: String(data.session_id || ''),
          finding_id: String(data.finding_id || ''),
          finding_type: String(data.finding_type || ''),
          line: typeof data.line === 'number' ? data.line : null,
          sequence_id: seqId,
          timestamp,
        };
        return event;
      }

      case 'response_chunk': {
        const event: DiagnosisResponseChunkEvent = {
          event: 'response_chunk',
          session_id: String(data.session_id || ''),
          finding_id: String(data.finding_id || ''),
          chunk: String(data.chunk || ''),
          sequence_id: seqId,
          timestamp,
        };
        return event;
      }

      case 'completed': {
        const event: DiagnosisCompletedEvent = {
          event: 'completed',
          session_id: String(data.session_id || ''),
          finding_id: String(data.finding_id || ''),
          status: String(data.status || 'completed'),
          duration_ms: typeof data.duration_ms === 'number' ? data.duration_ms : 0,
          token_usage: data.token_usage ?? null,
          finish_reason: String(data.finish_reason || 'stop'),
          sequence_id: seqId,
          timestamp,
        };
        return event;
      }

      case 'error': {
        const event: DiagnosisErrorEvent = {
          event: 'error',
          session_id: data.session_id ? String(data.session_id) : undefined,
          finding_id: data.finding_id ? String(data.finding_id) : undefined,
          error_type: String(data.error_type || 'unknown_error'),
          message: String(data.message || 'An error occurred during diagnosis.'),
          retryable: Boolean(data.retryable),
          sequence_id: seqId,
          timestamp,
        };
        return event;
      }

      default:
        this.logger?.warn(`[DiagnosisClient] Unknown SSE event type '${raw.event}' ignored`);
        return null;
    }
  }
}
