/**
 * EdgeMind Web API Types & Interfaces
 * Mirrored directly from core/schemas.py and core/models.py.
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

export interface AnalyzeCodeRequest {
  code: string;
  filename?: string;
  static_only?: boolean;
}

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
}

export interface AnalysisCategorySummary {
  syntax: string;
  runtime: string;
  logic: string;
  quality: string;
  complexity: string;
}

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
  summary: AnalysisCategorySummary;
}

/**
 * Mirrors AnalysisReportItemResponse / AnalysisSessionResponse from core/schemas.py.
 */
export interface AnalysisSessionItem {
  id: string;
  user_id?: string | null;
  project_id?: string | null;
  problem_id?: string | null;
  analysis_mode: string;
  language: string;
  analysis_status: string;
  gaps_detected: number;
  candidates_generated: number;
  duration_ms: number;
  report_storage_status?: string;
  created_at?: string | null;
  project_name?: string | null;
  problem_title?: string | null;
  problem_slug?: string | null;
  platform?: string | null;
}

export interface SessionAnalysisRecord {
  id: string;
  filename: string;
  score: number;
  overall_status: string;
  total_errors: number;
  total_warnings: number;
  durationMs: number;
  executedAt: string;
  report: AnalysisReport;
}

export type FindingSeverity = 'error' | 'warning';

export interface DiagnosisFindingPayload {
  finding_id: string;
  type: string;
  severity: 'error' | 'warning' | 'info';
  message: string;
  line: number | null;
  static_why?: string | null;
  static_fix?: string | null;
}

export interface DiagnoseFindingRequest {
  finding: DiagnosisFindingPayload;
  code_context: string;
  context_start_line: number;
  context_end_line: number;
  filename?: string;
  language?: string;
}

export interface DiagnosisStartedEvent {
  event: 'diagnosis_started';
  session_id: string;
  finding_id: string;
  finding_type: string;
  line: number | null;
  sequence_id: number;
  timestamp: string;
}

export interface DiagnosisResponseChunkEvent {
  event: 'response_chunk';
  session_id: string;
  finding_id: string;
  chunk: string;
  sequence_id: number;
  timestamp: string;
}

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

export type DiagnosisStreamEvent =
  | DiagnosisStartedEvent
  | DiagnosisResponseChunkEvent
  | DiagnosisCompletedEvent
  | DiagnosisErrorEvent;

export interface EdgeMindProblemContextPayload {
  title?: string;
  constraints?: string[];
  parameters?: Array<string | { name: string }>;
  function_name?: string;
  platform?: string;
}

export interface EdgeMindAnalyzeRequest {
  code: string;
  filename?: string;
  problem_context?: EdgeMindProblemContextPayload;
  test_cases?: Array<Record<string, unknown>>;
  max_candidates?: number;
  static_only?: boolean;
}

export interface IdentifiedParameter {
  name: string;
  param_type: string;
  structure: string;
  element_type?: string | null;
  min_length?: number | null;
  max_length?: number | null;
  min_value?: number | null;
  max_value?: number | null;
  source?: string;
  is_ambiguous?: boolean;
  ambiguity_reason?: string | null;
}

export interface ParsedConstraintsMeta {
  status: 'PARSED' | 'PARTIALLY_PARSED' | 'UNAVAILABLE' | string;
  total_raw: number;
  unresolved: string[];
  unresolved_explanations?: Record<string, string>;
}

export interface CoverageGapItem {
  category: string;
  param_name?: string | null;
  severity: 'HIGH' | 'MEDIUM' | 'LOW' | string;
  constraint_validity: 'VALID' | 'PROHIBITED' | 'UNKNOWN' | string;
  relevance_score: number;
  rationale: string;
  risk_explained: string;
  suggested_action: string;
  metadata?: Record<string, unknown>;
}

export interface CandidateScoreBreakdown {
  severity_score: number;
  relevance_score: number;
  boundary_score: number;
  failure_family_score: number;
  performance_score: number;
  novelty_score: number;
  diversity_penalty: number;
  total_score: number;
  explanation: string;
}

export interface EdgeMindCandidate {
  id: string;
  source: string;
  input_data: Record<string, unknown>;
  expected_output: null | unknown;
  is_expected_output_verified: boolean;
  label: string;
  rationale: string;
  target_gap?: string | null;
  relevance_score: number;
  is_boundary: boolean;
  is_performance: boolean;
  classification: string;
  classification_reason?: string | null;
  raw_stdin?: string | null;
}

export interface RankedCandidateItem {
  candidate: EdgeMindCandidate;
  rank: number;
  score: number;
  score_breakdown: CandidateScoreBreakdown;
  explanation: string;
  canonical_signature?: string;
}

export interface EdgeMindTestIntelligenceSection {
  existing_tests_analyzed: number;
  detected_patterns: Record<string, unknown>;
  coverage_gaps: CoverageGapItem[];
  total_gaps: number;
  unresolved_constraints: string[];
  ranking_summary: {
    total_evaluated: number;
    exact_duplicates_removed: number;
    redundant_candidates_penalized: number;
    selection_limit?: number | null;
  };
  generated_candidates: EdgeMindCandidate[];
  ranked_candidates: RankedCandidateItem[];
}

export interface EdgeMindAnalyzeResponse {
  status: string;
  product: string;
  version: string;
  analysis_mode: 'BASELINE_DRIVEN' | 'CONTEXT_BASED' | string;
  baseline_available: boolean;
  context_completeness: string;
  identified_parameters: IdentifiedParameter[];
  parsed_constraints: ParsedConstraintsMeta;
  generation_status: string;
  code_analysis: AnalysisReport;
  test_intelligence: EdgeMindTestIntelligenceSection;
  provenance: {
    source: string;
    execution_performed: boolean;
    expected_outputs_known: boolean;
    guarantees: string[];
  };
  limitations: string[];
  warnings: string[];
  analysis_session_id?: string | null;
  report_storage_status?: string;
}

export interface PersistedReportDocument {
  id?: string;
  analysis_session_id: string;
  user_id?: string | null;
  project_id?: string | null;
  problem_id?: string | null;
  problem?: {
    title?: string;
    slug?: string;
    platform?: string;
    difficulty?: string | null;
  } | null;
  problem_slug?: string | null;
  platform?: string | null;
  language?: string;
  analysis_mode?: string;
  analysis_status?: string;
  generated_candidates?: EdgeMindCandidate[];
  candidate_classifications?: Record<string, number>;
  constraints?: Record<string, unknown>;
  coverage_gaps?: CoverageGapItem[];
  explanations?: {
    limitations?: string[];
    warnings?: string[];
    unresolved_constraints?: string[];
  };
  analysis_metadata?: {
    duration_ms?: number;
    gaps_detected?: number;
    candidates_generated?: number;
    existing_tests_analyzed?: number;
    ranking_summary?: Record<string, unknown>;
    provenance?: Record<string, unknown>;
    code_metrics?: Record<string, unknown>;
    code_summary?: Record<string, unknown>;
    [key: string]: unknown;
  };
  created_at?: string | null;
  updated_at?: string | null;
  schema_version?: string;
}

export interface PaginatedReportsResponse {
  items: PersistedReportDocument[];
  total: number;
  skip: number;
  limit: number;
}

export interface UserLoginPayload {
  email: string;
  password: string;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}
