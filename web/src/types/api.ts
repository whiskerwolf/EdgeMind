/**
 * EdgeMind Web API Types & Interfaces
 */

export interface HealthResponse {
  status: string;
  service: string;
  database?: string | null;
}

export interface ApiError {
  error: string;
  detail: string;
  status_code?: number;
  request_id?: string | null;
}

export type HealthStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export interface HealthState {
  status: HealthStatus;
  data: HealthResponse | null;
  error: string | null;
  durationMs: number | null;
  lastChecked: Date | null;
}
