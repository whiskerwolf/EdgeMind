import { apiClient } from './client';
import {
  DiagnoseFindingRequest,
  DiagnosisCompletedEvent,
  DiagnosisErrorEvent,
  DiagnosisResponseChunkEvent,
  DiagnosisStartedEvent,
  DiagnosisStreamEvent,
} from '../types/api';
import { RawSSEEvent, SSEParser } from '../utils/sseParser';

export interface StreamDiagnosisOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
  onEvent?: (event: DiagnosisStreamEvent) => void;
}

export class DiagnosisStreamError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
    public readonly retryable: boolean = true,
    public readonly errorType: string = 'diagnosis_error'
  ) {
    super(DiagnosisStreamError.sanitizeMessage(message));
    this.name = 'DiagnosisStreamError';
  }

  private static sanitizeMessage(raw: string): string {
    if (!raw) return '';
    return raw
      .replace(/Bearer\s+[A-Za-z0-9\-_.]+/gi, 'Bearer [REDACTED]')
      .replace(/(?:sk-(?:proj-)?[a-zA-Z0-9_-]{20,}|AIza[0-9A-Za-z\-_]{30,})/g, '[REDACTED]')
      .replace(/(password|secret_key|api_key)=([^\s&]+)/gi, '$1=[REDACTED]');
  }
}

export class WebDiagnosisClient {
  private defaultTimeoutMs: number;

  constructor(defaultTimeoutMs: number = 60000) {
    this.defaultTimeoutMs = defaultTimeoutMs;
  }

  public async *streamDiagnosis(
    request: DiagnoseFindingRequest,
    options?: StreamDiagnosisOptions
  ): AsyncGenerator<DiagnosisStreamEvent, void, unknown> {
    const baseUrl = apiClient.getBaseUrl().replace(/\/+$/, '');
    const fullUrl = `${baseUrl}/api/v1/diagnose/stream`;
    const timeoutMs = options?.timeoutMs ?? this.defaultTimeoutMs;
    const externalSignal = options?.signal;

    if (externalSignal?.aborted) {
      return;
    }

    const abortController = new AbortController();
    const onExternalAbort = () => abortController.abort();
    if (externalSignal) {
      externalSignal.addEventListener('abort', onExternalAbort, { once: true });
    }

    let didTimeout = false;
    const timeoutId = setTimeout(() => {
      didTimeout = true;
      abortController.abort();
    }, timeoutMs);

    let response: Response;
    try {
      response = await fetch(fullUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(request),
        signal: abortController.signal,
      });
    } catch (err: unknown) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', onExternalAbort);
      }

      if (externalSignal?.aborted) {
        return;
      }
      if (didTimeout) {
        throw new DiagnosisStreamError(
          `Diagnosis stream timed out after ${Math.round(timeoutMs / 1000)}s.`,
          408,
          true,
          'stream_timeout'
        );
      }
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      throw new DiagnosisStreamError(
        `Failed to connect to AI diagnosis endpoint: ${err instanceof Error ? err.message : String(err)}`,
        0,
        true,
        'network_error'
      );
    }

    if (!response.ok) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', onExternalAbort);
      }

      const status = response.status;
      let detail = `HTTP ${status}`;
      try {
        const errJson = (await response.json()) as { detail?: unknown; error?: unknown };
        if (typeof errJson.detail === 'string' && errJson.detail) {
          detail = errJson.detail;
        } else if (typeof errJson.error === 'string' && errJson.error) {
          detail = errJson.error;
        }
      } catch {
        try {
          const text = await response.text();
          if (text) detail = text.slice(0, 256);
        } catch {
          // Ignore secondary text read error
        }
      }

      const retryable = status >= 500 || status === 429 || status === 408;
      throw new DiagnosisStreamError(
        `Diagnosis request failed (${status}): ${detail}`,
        status,
        retryable,
        status === 429 ? 'rate_limit' : 'http_error'
      );
    }

    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('text/event-stream')) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', onExternalAbort);
      }
      throw new DiagnosisStreamError(
        `Expected text/event-stream from diagnosis endpoint, received '${contentType || 'unknown'}'`,
        response.status,
        false,
        'invalid_content_type'
      );
    }

    if (!response.body) {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', onExternalAbort);
      }
      throw new DiagnosisStreamError(
        'Diagnosis response body stream is unavailable.',
        response.status,
        true,
        'empty_body'
      );
    }

    const reader = response.body.getReader();
    const parser = new SSEParser();
    let completedOrError = false;

    try {
      while (true) {
        if (externalSignal?.aborted) {
          break;
        }

        const { done, value } = await reader.read();

        if (done) {
          const trailing = parser.flush();
          if (trailing) {
            const event = this.mapRawEvent(trailing);
            if (event) {
              if (event.event === 'completed' || event.event === 'error') {
                completedOrError = true;
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
            if (!event) continue;

            if (event.event === 'completed' || event.event === 'error') {
              completedOrError = true;
            }
            options?.onEvent?.(event);
            yield event;

            if (completedOrError) {
              return;
            }
          }
        }
      }
    } catch (err: unknown) {
      if (externalSignal?.aborted) {
        return;
      }
      if (didTimeout) {
        throw new DiagnosisStreamError(
          `Diagnosis stream timed out after ${Math.round(timeoutMs / 1000)}s.`,
          408,
          true,
          'stream_timeout'
        );
      }
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      throw new DiagnosisStreamError(
        `Error reading diagnosis stream: ${err instanceof Error ? err.message : String(err)}`,
        response.status,
        true,
        'stream_read_error'
      );
    } finally {
      clearTimeout(timeoutId);
      if (externalSignal) {
        externalSignal.removeEventListener('abort', onExternalAbort);
      }
      reader.releaseLock();
      try {
        await response.body.cancel();
      } catch {
        // Ignore cancellation cleanup errors
      }
    }

    if (!externalSignal?.aborted && !completedOrError) {
      throw new DiagnosisStreamError(
        'Diagnosis stream ended unexpectedly without completion or error event.',
        response.status,
        true,
        'premature_eof'
      );
    }
  }

  private mapRawEvent(raw: RawSSEEvent): DiagnosisStreamEvent | null {
    if (!raw.event || !raw.data) return null;
    const data = SSEParser.parseJsonData<Record<string, unknown>>(raw.data);
    if (!data || typeof data !== 'object') return null;

    const seqId =
      typeof data.sequence_id === 'number'
        ? data.sequence_id
        : raw.id
          ? parseInt(raw.id, 10) || 0
          : 0;
    const timestamp =
      typeof data.timestamp === 'string' ? data.timestamp : new Date().toISOString();

    switch (raw.event) {
      case 'diagnosis_started': {
        const evt: DiagnosisStartedEvent = {
          event: 'diagnosis_started',
          session_id: String(data.session_id || ''),
          finding_id: String(data.finding_id || ''),
          finding_type: String(data.finding_type || ''),
          line: typeof data.line === 'number' ? data.line : null,
          sequence_id: seqId,
          timestamp,
        };
        return evt;
      }
      case 'response_chunk': {
        const evt: DiagnosisResponseChunkEvent = {
          event: 'response_chunk',
          session_id: String(data.session_id || ''),
          finding_id: String(data.finding_id || ''),
          chunk: String(data.chunk || ''),
          sequence_id: seqId,
          timestamp,
        };
        return evt;
      }
      case 'completed': {
        const evt: DiagnosisCompletedEvent = {
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
        return evt;
      }
      case 'error': {
        const evt: DiagnosisErrorEvent = {
          event: 'error',
          session_id: data.session_id ? String(data.session_id) : undefined,
          finding_id: data.finding_id ? String(data.finding_id) : undefined,
          error_type: String(data.error_type || 'unknown_error'),
          message: String(data.message || 'An error occurred during diagnosis.'),
          retryable: Boolean(data.retryable),
          sequence_id: seqId,
          timestamp,
        };
        return evt;
      }
      default:
        return null;
    }
  }
}

export const diagnosisClient = new WebDiagnosisClient();
