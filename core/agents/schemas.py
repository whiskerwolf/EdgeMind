"""
Pydantic Schemas for EdgeMind Multi-Step AI Agent & Tool Calling Architecture.

Defines schemas for:
- Agent lifecycle states and messages
- Tool definitions and execution records
- Tool argument payloads with strict validation
- Agent API request and response models
"""

from enum import Enum
import json
from typing import Any, Dict, List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.cost.models import AgentUsageSummary, TokenUsage, UsageSource

from core.sanitization import (
    normalize_unicode,
    sanitize_problem_context_dict,
    sanitize_recursive_value,
    sanitize_tool_arguments_dict,
    strip_null_bytes,
    validate_filename_label,
    validate_source_code,
    validate_tool_name,
)


class AgentStatus(str, Enum):
    """Execution status for the multi-step agent session."""
    SUCCESS = "SUCCESS"
    STATIC_ONLY = "STATIC_ONLY"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    PARTIAL = "PARTIAL"
    MAX_ITERATIONS_REACHED = "MAX_ITERATIONS_REACHED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class ToolExecutionStatus(str, Enum):
    """Execution status of an individual tool call."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ToolCall(BaseModel):
    """Represents a tool call requested by the reasoning model."""
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    name: str = Field(..., description="Name of the registered tool to execute")
    arguments: Union[Dict[str, Any], str] = Field(
        default_factory=dict,
        description="Parsed argument dictionary or JSON argument string",
    )

    @field_validator("name")
    @classmethod
    def validate_tool_identifier(cls, v: str) -> str:
        return validate_tool_name(v)

    @field_validator("arguments", mode="before")
    @classmethod
    def parse_arguments_json(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return sanitize_tool_arguments_dict(parsed)
                return parsed
            except Exception:
                return v
        if isinstance(v, dict):
            return sanitize_tool_arguments_dict(v)
        return v

    def get_arguments_dict(self) -> Dict[str, Any]:
        """Ensure arguments are returned as a dictionary."""
        if isinstance(self.arguments, dict):
            return self.arguments
        if isinstance(self.arguments, str):
            try:
                parsed = json.loads(self.arguments)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {}


class ToolExecutionRecord(BaseModel):
    """Audit log record for an executed tool call."""
    tool_call_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    status: ToolExecutionStatus = ToolExecutionStatus.SUCCESS
    duration_ms: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AgentMessage(BaseModel):
    """Chat message in the agent conversational reasoning context."""
    role: str = Field(..., description="Role: system, user, assistant, or tool")
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


class AgentStepResult(BaseModel):
    """The result of a single reasoning step from an agent provider."""
    model_config = ConfigDict(extra="ignore")

    thought: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    content: Optional[str] = None
    finish_reason: str = Field(default="stop", description="'tool_calls', 'stop', 'length', 'unavailable', or 'error'")
    error: Optional[str] = None
    error_type: Optional[str] = None
    status_code: Optional[int] = None
    chunks: Optional[List[str]] = Field(default=None, description="Optional streamable token chunks")
    usage: Optional[TokenUsage] = Field(default=None, description="Captured token usage for this step")
    request_id: Optional[str] = Field(default=None, description="Provider request ID")
    model: Optional[str] = Field(default=None, description="Model used for this step")


class AgentState(BaseModel):
    """Execution state tracking throughout the multi-step agent reasoning loop."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    iteration: int = 0
    max_iterations: int = 5
    tool_call_count: int = 0
    max_tool_calls: int = 15
    messages: List[AgentMessage] = Field(default_factory=list)
    tool_executions: List[ToolExecutionRecord] = Field(default_factory=list)
    usage_records: List[TokenUsage] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.SUCCESS
    final_summary: Optional[str] = None
    accumulated_context: Dict[str, Any] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Tool Arguments Schemas (Strict Pydantic Validation)
# -----------------------------------------------------------------------------

class ParseConstraintsArgs(BaseModel):
    """Arguments for the parse_problem_constraints tool."""
    raw_constraints: List[str] = Field(
        ...,
        description="List of raw constraint strings (e.g. '1 <= nums.length <= 10^5')",
    )
    known_parameters: Optional[List[str]] = Field(
        default=None,
        description="Optional list of parameter names known from function signature",
    )

    @field_validator("raw_constraints")
    @classmethod
    def sanitize_constraints_list(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise TypeError("raw_constraints must be a list of strings.")
        cleaned: List[str] = []
        for item in v[:50]:
            if isinstance(item, str):
                s = strip_null_bytes(normalize_unicode(item)).strip()
                if s:
                    cleaned.append(s[:500])
        return cleaned


class AnalyzeProblemStructureArgs(BaseModel):
    """Arguments for the analyze_problem_structure tool."""
    code: str = Field(
        ...,
        max_length=65536,
        description="Python source code snippet to statically analyze (max 64 KiB)",
    )
    test_cases: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional list of baseline test cases to infer parameter types from",
    )

    @field_validator("code")
    @classmethod
    def validate_code_security(cls, v: str) -> str:
        return validate_source_code(v)


class DetectCoverageGapsArgs(BaseModel):
    """Arguments for the detect_coverage_gaps tool."""
    test_cases: List[Dict[str, Any]] = Field(
        ...,
        description="List of existing test cases to evaluate against input partitions",
    )
    parameters: Optional[List[str]] = Field(
        default=None,
        description="Optional parameter names to evaluate",
    )
    constraints: Optional[List[str]] = Field(
        default=None,
        description="Optional problem constraint strings",
    )


class RetrieveExistingAnalysisArgs(BaseModel):
    """Arguments for the retrieve_existing_analysis tool."""
    project_id: Optional[str] = Field(
        default=None,
        description="Optional UUID of the project to retrieve historical reports for",
    )
    problem_id: Optional[str] = Field(
        default=None,
        description="Optional UUID or slug of the problem",
    )
    limit: Optional[int] = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of historical analysis records to retrieve",
    )


class RetrieveKnowledgeContextArgs(BaseModel):
    """Arguments for the retrieve_knowledge_context vector RAG tool."""
    query: str = Field(
        ...,
        min_length=2,
        max_length=2000,
        description="Semantic search query describing the algorithmic concept, pattern, or edge-case context to retrieve",
    )
    top_k: Optional[int] = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of relevant knowledge chunks to retrieve",
    )
    similarity_threshold: Optional[float] = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score threshold for relevance",
    )

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        cleaned = strip_null_bytes(normalize_unicode(v)).strip()
        if len(cleaned) < 2:
            raise ValueError("Query must be at least 2 characters.")
        if len(cleaned) > 2000:
            cleaned = cleaned[:2000]
        return cleaned


class GenerateCandidateInputsArgs(BaseModel):
    """Arguments for the generate_candidate_inputs tool."""
    test_cases: List[Dict[str, Any]] = Field(
        ...,
        description="Existing test cases providing baseline structure",
    )
    gaps: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Detected coverage gaps to target",
    )
    constraints: Optional[List[str]] = Field(
        default=None,
        description="Problem constraint strings to respect",
    )
    max_candidates: Optional[int] = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of candidate test cases to generate",
    )


class ValidateCandidateInputsArgs(BaseModel):
    """Arguments for the validate_candidate_inputs tool."""
    candidates: List[Dict[str, Any]] = Field(
        ...,
        description="List of candidate test cases to validate against constraints",
    )
    constraints: Optional[List[str]] = Field(
        default=None,
        description="Problem constraints to validate against",
    )
    parameters: Optional[List[str]] = Field(
        default=None,
        description="Parameter names in the problem",
    )


class RankCandidateInputsArgs(BaseModel):
    """Arguments for the rank_candidate_inputs tool."""
    candidates: List[Dict[str, Any]] = Field(
        ...,
        description="Generated candidate test cases to rank and select",
    )
    existing_tests: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Existing baseline test cases for redundancy checking",
    )
    gaps: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Detected gaps used for coverage scoring",
    )
    max_selected: Optional[int] = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of candidates to select",
    )


# -----------------------------------------------------------------------------
# Agent Request & Response Schemas
# -----------------------------------------------------------------------------

class AgentAnalyzeRequest(BaseModel):
    """Incoming request payload for multi-step agent analysis."""
    code: str = Field(..., description="Python source code to analyze (max 64 KiB)")
    filename: Optional[str] = Field(default="solution.py", description="Display label for the code file")
    problem_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional problem metadata (title, constraints, parameters)",
    )
    test_cases: Optional[List[Any]] = Field(
        default=None,
        description="Optional list of baseline test cases",
    )
    project_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional associated project UUID",
    )
    problem_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional associated problem UUID",
    )
    max_iterations: Optional[int] = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum multi-step reasoning cycles (1-10)",
    )
    max_candidates: Optional[int] = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum candidate edge-cases to include in final output",
    )
    model: Optional[str] = Field(
        default=None,
        description="Target reasoning model identifier",
    )
    mode: Optional[str] = Field(
        default="agent",
        description="Analysis execution mode: 'agent' (AI multi-step agent) or 'static_only' (deterministic static analysis)",
    )
    static_only: bool = Field(
        default=True,
        description="Safety invariant: static analysis only with zero code execution",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return validate_source_code(v)

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return validate_filename_label(v)
        return v

    @field_validator("problem_context")
    @classmethod
    def validate_problem_context(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if v is not None:
            return sanitize_problem_context_dict(v)
        return v

    @field_validator("test_cases")
    @classmethod
    def validate_test_cases(cls, v: Optional[List[Any]]) -> Optional[List[Any]]:
        if v is not None:
            return sanitize_recursive_value(v)
        return v

    @field_validator("static_only")
    @classmethod
    def validate_static_only(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Runtime code execution is disabled; static_only must be True.")
        return v


class AgentAnalyzeResponse(BaseModel):
    """Complete structured response from the EdgeMind Multi-Step Agent."""
    status: str = Field(..., description="Agent execution status (SUCCESS, PARTIAL, etc.)")
    product: str = Field(default="EdgeMind")
    version: str = Field(default="1.0.0")
    session_id: str = Field(..., description="Unique UUID for this agent session")
    iterations: int = Field(..., description="Number of iterative reasoning steps taken")
    tool_executions: List[ToolExecutionRecord] = Field(
        default_factory=list,
        description="Chronological log of all tool executions and outcomes",
    )
    final_summary: str = Field(..., description="Agent's synthesized final reasoning and summary")
    execution_mode: str = Field(
        default="AI_AGENT",
        description="Execution mode: AI_AGENT, STATIC_ONLY, or DEGRADED_STATIC",
    )
    ai_reasoning_performed: bool = Field(
        default=False,
        description="Whether actual AI LLM reasoning was performed during this session",
    )
    test_intelligence: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Synthesized test intelligence findings and ranked edge-case candidates",
    )
    code_analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Static code analysis findings and metrics",
    )
    analysis_mode: Optional[str] = Field(
        default="BASELINE_DRIVEN",
        description="Operating mode: BASELINE_DRIVEN or CONTEXT_BASED",
    )
    baseline_available: Optional[bool] = Field(
        default=True,
        description="Whether baseline public examples were available",
    )
    context_completeness: Optional[str] = Field(
        default="DETECTED",
        description="Completeness of extracted problem context",
    )
    identified_parameters: List[str] = Field(
        default_factory=list,
        description="Parameter names identified from solution or context",
    )
    parsed_constraints: Dict[str, Any] = Field(
        default_factory=dict,
        description="Constraints parsed from problem description",
    )
    total_duration_ms: float = Field(default=0.0, description="Total execution duration in milliseconds")
    persisted_report_id: Optional[str] = Field(
        default=None,
        description="UUID of the persisted PostgreSQL JSONB report document (if saved)",
    )
    usage: Optional[AgentUsageSummary] = Field(
        default=None,
        description="Aggregated token usage and estimated cost accounting",
    )
    warnings: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Server-Sent Events (SSE) Streaming Schemas
# -----------------------------------------------------------------------------

class SSEEventType(str, Enum):
    """Defined event types for the EdgeMind SSE streaming response."""
    STATUS = "status"
    ANALYSIS_STARTED = "analysis_started"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    PROGRESS = "progress"
    RESPONSE_CHUNK = "response_chunk"
    COMPLETED = "completed"
    ERROR = "error"
    USAGE = "usage"


def format_sse_event(
    event_type: Union[SSEEventType, str],
    data: Any,
    event_id: Optional[int] = None,
) -> str:
    """
    Format structured payload into RFC 8895 Server-Sent Events wire format.
    Guarantees sequential event IDs, correct event naming, JSON serialization,
    and double newline termination.
    """
    evt_name = event_type.value if isinstance(event_type, SSEEventType) else str(event_type)
    lines: List[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {evt_name}")

    if isinstance(data, BaseModel):
        payload_str = json.dumps(data.model_dump(mode="json"))
    elif isinstance(data, (dict, list)):
        payload_str = json.dumps(data, default=str)
    else:
        payload_str = json.dumps({"message": str(data)}, default=str)

    lines.append(f"data: {payload_str}")
    return "\n".join(lines) + "\n\n"
