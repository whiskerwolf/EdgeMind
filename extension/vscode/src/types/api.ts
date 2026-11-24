/**
 * EdgeMind API Types & Interfaces.
 * Mirrors existing FastAPI schemas from core/schemas.py.
 */

export interface HealthResponse {
  status: string;
  service: string;
  database?: string | null;
}

export interface ApiError {
  error: string;
  detail: string;
  request_id?: string | null;
}

export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  statusCode?: number;
  durationMs: number;
}

export type BackendStatus = 'online' | 'offline' | 'checking';

/**
 * Request payload for POST /api/v1/analyze
 */
export interface AnalyzeCodeRequest {
  code: string;
  filename?: string;
  static_only?: boolean;
}

/**
 * Diagnostic finding in code analysis report
 */
export interface ReportFinding {
  type: string;
  line: number;
  line_number: number;
  message: string;
  why: string;
  explanation: string;
  fix: string;
  suggested_fix: string;
  concept: string;
  severity?: string;
}

/**
 * Category breakdown in code analysis report
 */
export interface AnalysisSummary {
  syntax: string;
  runtime: string;
  logic: string;
  quality: string;
  complexity: string;
}

/**
 * Full response report from POST /api/v1/analyze
 */
export interface AnalysisReport {
  file_path: string;
  file: string;
  overall_status: string;
  status: string;
  score: number;
  total_errors: number;
  total_warnings: number;
  syntax_status: string;
  runtime_status: string;
  logic_status: string;
  quality_status: string;
  complexity_status: string;
  detailed_errors?: ReportFinding[];
  errors: ReportFinding[];
  detailed_warnings?: ReportFinding[];
  warnings: ReportFinding[];
  summary: AnalysisSummary;
  ai_reasoning?: unknown;
}
