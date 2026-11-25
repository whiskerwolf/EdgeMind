/**
 * EdgeMind Finding AI Diagnosis Streaming Types & Interfaces (Phase 5G.5).
 * Mirrors backend contracts from core/schemas.py and core/routes/diagnose.py.
 */

/**
 * Finding payload sent in diagnosis request.
 */
export interface FindingPayload {
  finding_id: string;
  type: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  line?: number | null;
  static_why?: string | null;
  static_fix?: string | null;
}

/**
 * Request body for POST /api/v1/diagnose/stream.
 */
export interface DiagnoseFindingRequest {
  finding: FindingPayload;
  code_context: string;
  context_start_line: number;
  context_end_line: number;
  filename?: string;
  language?: string;
}

/**
 * Event 1: diagnosis_started
 * Emitted when SSE connection is established and diagnosis starts.
 */
export interface DiagnosisStartedEvent {
  event: 'diagnosis_started';
  session_id: string;
  finding_id: string;
  finding_type: string;
  line: number | null;
  sequence_id: number;
  timestamp: string;
}

/**
 * Event 2: response_chunk
 * Incremental Markdown diagnosis token chunks.
 */
export interface DiagnosisResponseChunkEvent {
  event: 'response_chunk';
  session_id: string;
  finding_id: string;
  chunk: string;
  sequence_id: number;
  timestamp: string;
}

/**
 * Event 3: completed
 * Emitted on successful stream termination.
 */
export interface DiagnosisCompletedEvent {
  event: 'completed';
  session_id: string;
  finding_id: string;
  status: string;
  duration_ms: number;
  token_usage?: unknown | null;
  finish_reason: string;
  sequence_id: number;
  timestamp: string;
}

/**
 * Event 4: error
 * Emitted when provider is unavailable, times out, or upstream fails.
 */
export interface DiagnosisErrorEvent {
  event: 'error';
  session_id?: string;
  finding_id?: string;
  error_type: string;
  message: string;
  retryable: boolean;
  sequence_id?: number;
  timestamp: string;
}

/**
 * Discriminated union of all SSE diagnosis events emitted by EdgeMind backend.
 */
export type DiagnosisStreamEvent =
  | DiagnosisStartedEvent
  | DiagnosisResponseChunkEvent
  | DiagnosisCompletedEvent
  | DiagnosisErrorEvent;
