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


class AgentStatus(str, Enum):
    """Execution status for the multi-step agent session."""
    SUCCESS = "SUCCESS"
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

    @field_validator("arguments", mode="before")
    @classmethod
    def parse_arguments_json(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return v
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
    finish_reason: str = Field(default="stop", description="'tool_calls', 'stop', 'length', or 'error'")


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
    static_only: bool = Field(
        default=True,
        description="Safety invariant: static analysis only with zero code execution",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not isinstance(v, str):
            raise TypeError("Source code must be a string.")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Source code must not be empty or whitespace-only.")
        if len(v.encode("utf-8")) > 65536:
            raise ValueError("Source code exceeds maximum allowed size of 64 KiB (65,536 bytes).")
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
    test_intelligence: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Synthesized test intelligence findings and ranked edge-case candidates",
    )
    code_analysis: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Static code analysis findings and metrics",
    )
    total_duration_ms: float = Field(default=0.0, description="Total execution duration in milliseconds")
    persisted_report_id: Optional[str] = Field(
        default=None,
        description="UUID of the persisted PostgreSQL JSONB report document (if saved)",
    )
    warnings: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
