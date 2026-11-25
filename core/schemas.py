"""
EdgeMind Pydantic Request & Response Schemas.

Defines typed schemas for FastAPI endpoints:
- /health
- /api/v1/analyze
- /api/v1/edgemind/analyze
- /api/v1/projects
- /api/v1/problems
- /api/v1/analyses
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from core.sanitization import (
    MAX_CONSTRAINTS_COUNT,
    MAX_CONSTRAINT_ITEM_CHARS,
    MAX_PROBLEM_DESCRIPTION_CHARS,
    MAX_TITLE_CHARS,
    normalize_unicode,
    sanitize_problem_context_dict,
    sanitize_recursive_value,
    sanitize_text,
    strip_null_bytes,
    validate_filename_label,
    validate_slug,
    validate_source_code,
)


# -----------------------------------------------------------------------------
# Common / System Schemas
# -----------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Schema for /health response."""
    model_config = ConfigDict(extra="ignore")

    status: str = Field(default="healthy", description="Service health state")
    service: str = Field(default="EdgeMind", description="Service identity")
    database: Optional[str] = Field(default=None, description="Database connection state")


class ErrorResponse(BaseModel):
    """Consistent application error response envelope."""
    model_config = ConfigDict(extra="ignore")

    error: str = Field(..., description="High-level error classification (e.g. Bad Request, Not Found)")
    detail: str = Field(..., description="Human-readable description of the error")
    request_id: Optional[str] = Field(default=None, description="Request correlation identifier")


# -----------------------------------------------------------------------------
# Code Analysis & Intelligence Schemas
# -----------------------------------------------------------------------------

class AnalyzeCodeRequest(BaseModel):
    """Schema for POST /api/v1/analyze request body."""
    model_config = ConfigDict(extra="ignore")

    code: str = Field(..., description="Python or JavaScript source code to analyze statically")
    filename: Optional[str] = Field(default="snippet.py", description="Display filename label")
    language: Optional[str] = Field(
        default=None,
        description="Optional source language ('python' or 'javascript'; inferred from filename when omitted)",
    )
    static_only: Optional[bool] = Field(default=True, description="Enforce static-only analysis")

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

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not str(v).strip():
            return None
        cleaned = str(v).strip().lower()
        if cleaned == "js":
            cleaned = "javascript"
        elif cleaned == "py":
            cleaned = "python"
        if cleaned not in ("python", "javascript"):
            raise ValueError(f"Unsupported language '{v}': expected 'python' or 'javascript'.")
        return cleaned


class ProblemContextSchema(BaseModel):
    """Schema for programming problem context (LeetCode/custom)."""
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = Field(default=None, description="Problem title")
    slug: Optional[str] = Field(default=None, description="Problem URL slug")
    description: Optional[str] = Field(default=None, description="Problem description text")
    constraints: Optional[List[str]] = Field(default_factory=list, description="List of natural language constraint strings")
    parameters: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Identified problem parameters")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return sanitize_text(v, max_length=MAX_TITLE_CHARS, allow_newlines=False)
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug_val(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.strip():
            try:
                return validate_slug(v)
            except ValueError:
                return sanitize_text(v, max_length=MAX_TITLE_CHARS, allow_newlines=False)
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return sanitize_text(v, max_length=MAX_PROBLEM_DESCRIPTION_CHARS, allow_newlines=True)
        return v

    @field_validator("constraints")
    @classmethod
    def validate_constraints(cls, v: Optional[List[str]]) -> List[str]:
        if not v:
            return []
        cleaned: List[str] = []
        for item in v[:MAX_CONSTRAINTS_COUNT]:
            if item is not None:
                c = sanitize_text(str(item), max_length=MAX_CONSTRAINT_ITEM_CHARS, allow_newlines=False)
                if c:
                    cleaned.append(c)
        return cleaned


class EdgeMindAnalyzeRequest(BaseModel):
    """Schema for POST /api/v1/edgemind/analyze request body."""
    model_config = ConfigDict(extra="ignore")

    code: str = Field(..., description="Python solution source code to analyze")
    filename: Optional[str] = Field(default="solution.py", description="Display filename label")
    problem_context: Optional[Dict[str, Any]] = Field(default=None, description="Optional problem context dictionary")
    test_cases: Optional[List[Any]] = Field(default=None, description="Optional baseline test cases")
    max_candidates: Optional[int] = Field(default=10, description="Maximum candidate test inputs to generate")
    static_only: Optional[bool] = Field(default=True, description="Enforce static-only analysis")
    project_id: Optional[str] = Field(default=None, description="Optional associated Project UUID")

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


# -----------------------------------------------------------------------------
# Project Schemas
# -----------------------------------------------------------------------------

ALLOWED_PROJECT_STATUSES = {"active", "in_progress", "completed", "archived"}


class ProjectCreate(BaseModel):
    """Schema for creating a new Project."""
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    description: Optional[str] = Field(default=None, description="Detailed project description")
    language: Optional[str] = Field(default="python", max_length=64, description="Primary programming language")
    technology_stack: Optional[Dict[str, Any]] = Field(default_factory=dict, description="JSON metadata of tech stack")
    status: Optional[str] = Field(default="active", description="Project status")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> str:
        if v is None:
            return "active"
        cleaned = v.strip().lower()
        if cleaned not in ALLOWED_PROJECT_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Allowed: {sorted(ALLOWED_PROJECT_STATUSES)}")
        return cleaned

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Project name must not be empty or whitespace-only.")
        return cleaned


class ProjectUpdate(BaseModel):
    """Schema for updating an existing Project."""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    language: Optional[str] = Field(default=None, max_length=64)
    technology_stack: Optional[Dict[str, Any]] = Field(default=None)
    status: Optional[str] = Field(default=None)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().lower()
        if cleaned not in ALLOWED_PROJECT_STATUSES:
            raise ValueError(f"Invalid status '{v}'. Allowed: {sorted(ALLOWED_PROJECT_STATUSES)}")
        return cleaned

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Project name must not be empty or whitespace-only.")
        return cleaned


class ProjectResponse(BaseModel):
    """Schema for Project representation in API responses."""
    model_config = ConfigDict(extra="ignore")

    id: str
    owner_user_id: Optional[str] = None
    name: str
    description: Optional[str] = None
    language: Optional[str] = "python"
    technology_stack: Dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProjectWithStatsResponse(ProjectResponse):
    """Project representation including aggregated SQL JOIN session counts."""
    session_count: int = Field(default=0, description="Total analysis sessions associated with this project")


# -----------------------------------------------------------------------------
# Problem Schemas
# -----------------------------------------------------------------------------

class ProblemCreate(BaseModel):
    """Schema for creating a new Problem record."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255, description="Problem title")
    problem_slug: str = Field(..., min_length=1, max_length=255, description="Unique problem slug on platform")
    platform: Optional[str] = Field(default="leetcode", max_length=64, description="Challenge platform name")
    difficulty: Optional[str] = Field(default=None, max_length=32, description="Difficulty (Easy, Medium, Hard)")

    @field_validator("title", "problem_slug")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field must not be empty or whitespace-only.")
        return cleaned


class ProblemResponse(BaseModel):
    """Schema for Problem representation in API responses."""
    model_config = ConfigDict(extra="ignore")

    id: str
    platform: str
    problem_slug: str
    title: str
    difficulty: Optional[str] = None
    created_at: Optional[str] = None


# -----------------------------------------------------------------------------
# Analysis Session Schemas
# -----------------------------------------------------------------------------

class AnalysisSessionCreate(BaseModel):
    """Schema for manual or programmatic AnalysisSession creation."""
    model_config = ConfigDict(extra="forbid")

    analysis_mode: str = Field(default="BASELINE_DRIVEN", description="BASELINE_DRIVEN or CONTEXT_BASED")
    language: Optional[str] = Field(default="python", description="Programming language analyzed")
    analysis_status: Optional[str] = Field(default="SUCCESS", description="Execution status")
    gaps_detected: Optional[int] = Field(default=0, ge=0)
    candidates_generated: Optional[int] = Field(default=0, ge=0)
    duration_ms: Optional[float] = Field(default=0.0, ge=0.0)
    project_id: Optional[str] = Field(default=None, description="Optional Project UUID")
    problem_id: Optional[str] = Field(default=None, description="Optional Problem UUID")
    report_storage_status: Optional[str] = Field(
        default="NOT_CONFIGURED",
        description="Report storage status: PENDING, STORED, FAILED, DELETED, NOT_CONFIGURED",
    )


class AnalysisSessionResponse(BaseModel):
    """Schema for AnalysisSession output."""
    model_config = ConfigDict(extra="ignore")

    id: str
    user_id: Optional[str] = None
    project_id: Optional[str] = None
    problem_id: Optional[str] = None
    analysis_mode: str
    language: str
    analysis_status: str
    gaps_detected: int
    candidates_generated: int
    duration_ms: float
    report_storage_status: Optional[str] = Field(
        default="NOT_CONFIGURED",
        description="Report storage status: PENDING, STORED, FAILED, DELETED, NOT_CONFIGURED",
    )
    created_at: Optional[str] = None


class AnalysisReportItemResponse(AnalysisSessionResponse):
    """SQL JOIN report representation linking session with Project and Problem metadata."""
    project_name: Optional[str] = Field(default=None, description="Joined project name")
    problem_title: Optional[str] = Field(default=None, description="Joined problem title")
    problem_slug: Optional[str] = Field(default=None, description="Joined problem slug")
    platform: Optional[str] = Field(default=None, description="Joined problem platform")


# -----------------------------------------------------------------------------
# Finding AI Diagnosis Schemas (Phase 5G)
# -----------------------------------------------------------------------------

MAX_DIAGNOSIS_CODE_CONTEXT_BYTES: int = 16 * 1024  # 16 KiB (~400 lines)
StructuredSeverity = Literal["error", "warning", "info"]


def _normalize_finding_severity(v: Any) -> str:
    """Validate and normalize finding severity labels across request and output schemas."""
    if not isinstance(v, str):
        raise ValueError("Severity must be a string.")
    cleaned = v.strip().lower()
    if cleaned not in ("error", "warning", "info"):
        raise ValueError(f"Invalid severity '{v}': must be one of 'error', 'warning', 'info'.")
    return cleaned


def _clean_non_empty_text(v: Any, field_label: str = "Field") -> str:
    """Reject non-strings, null bytes, and empty/whitespace-only text."""
    if not isinstance(v, str):
        raise ValueError(f"{field_label} must be a string.")
    safe = normalize_unicode(strip_null_bytes(v)).strip()
    if not safe:
        raise ValueError(f"{field_label} must not be empty or whitespace-only.")
    return safe


def _clean_optional_text(v: Any) -> Optional[str]:
    """Normalize optional string fields, returning None when blank."""
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError("Optional text field must be a string.")
    safe = normalize_unicode(strip_null_bytes(v)).strip()
    return safe if safe else None


class FindingPayload(BaseModel):
    """Schema for individual static analysis finding sent for AI diagnosis."""
    model_config = ConfigDict(extra="ignore")

    finding_id: str = Field(..., min_length=1, max_length=64, description="Unique identifier of the finding")
    type: str = Field(..., min_length=1, max_length=128, description="Finding category or detector rule")
    severity: str = Field(..., description="Severity level: error, warning, info")
    message: str = Field(..., min_length=1, max_length=1000, description="Short descriptive finding message")
    line: Optional[int] = Field(default=None, ge=1, description="1-based source line number (None for module-level)")
    static_why: Optional[str] = Field(default=None, max_length=1000, description="Pre-computed static explanation")
    static_fix: Optional[str] = Field(default=None, max_length=1000, description="Pre-computed static fix recommendation")

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        return _normalize_finding_severity(v)

    @field_validator("finding_id", "type", "message")
    @classmethod
    def validate_required_string_fields(cls, v: str) -> str:
        return _clean_non_empty_text(v)

    @field_validator("static_why", "static_fix")
    @classmethod
    def validate_optional_string_fields(cls, v: Optional[str]) -> Optional[str]:
        return _clean_optional_text(v)


class DiagnoseFindingRequest(BaseModel):
    """Schema for POST /api/v1/diagnose/stream request body."""
    model_config = ConfigDict(extra="ignore")

    finding: FindingPayload = Field(..., description="Static analysis finding to diagnose")
    code_context: str = Field(..., description="Bounded Python code snippet around the finding")
    context_start_line: int = Field(default=1, ge=1, description="1-based starting line of context snippet")
    context_end_line: int = Field(default=1, ge=1, description="1-based ending line of context snippet")
    filename: Optional[str] = Field(default="snippet.py", description="Display filename label")
    language: Optional[str] = Field(default="python", description="Language of snippet (must be python)")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return "snippet.py"
        return validate_filename_label(v)

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> str:
        if v is None or not str(v).strip():
            return "python"
        cleaned = str(v).strip().lower()
        if cleaned != "python":
            raise ValueError(f"Unsupported language '{v}'. Only 'python' is currently supported.")
        return cleaned

    @field_validator("code_context")
    @classmethod
    def validate_code_context(cls, v: str) -> str:
        return validate_source_code(v, max_bytes=MAX_DIAGNOSIS_CODE_CONTEXT_BYTES)

    @model_validator(mode="after")
    def validate_context_and_lines(self) -> "DiagnoseFindingRequest":
        if self.context_end_line < self.context_start_line:
            raise ValueError(
                f"context_end_line ({self.context_end_line}) cannot be less than "
                f"context_start_line ({self.context_start_line})."
            )
        if self.finding.line is not None:
            if not (self.context_start_line <= self.finding.line <= self.context_end_line):
                raise ValueError(
                    f"Finding line {self.finding.line} must be within the provided "
                    f"context range [{self.context_start_line}, {self.context_end_line}]."
                )
        return self


class CodeLocation(BaseModel):
    """Relevant source code location referenced by a structured diagnosis."""
    model_config = ConfigDict(extra="forbid")

    file: Optional[str] = Field(default=None, max_length=255, description="Filename label")
    start_line: int = Field(..., ge=1, description="1-based starting line number")
    end_line: Optional[int] = Field(default=None, ge=1, description="Optional 1-based ending line number")
    symbol: Optional[str] = Field(default=None, max_length=128, description="Optional enclosing function or class name")

    @field_validator("file")
    @classmethod
    def validate_location_file(cls, v: Optional[str]) -> Optional[str]:
        cleaned = _clean_optional_text(v)
        return validate_filename_label(cleaned) if cleaned else None

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: Optional[str]) -> Optional[str]:
        return _clean_optional_text(v)

    @model_validator(mode="after")
    def validate_line_bounds(self) -> "CodeLocation":
        if self.end_line is not None and self.end_line < self.start_line:
            raise ValueError(f"end_line ({self.end_line}) cannot be less than start_line ({self.start_line}).")
        return self


class DiagnosisFindingItem(BaseModel):
    """Individual validated finding detail within a structured AI diagnosis."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=300, description="Concise title of the identified issue")
    severity: StructuredSeverity = Field(..., description="Severity level: error, warning, or info")
    explanation: str = Field(..., min_length=1, max_length=4000, description="Detailed diagnosis explanation")
    recommendation: str = Field(..., min_length=1, max_length=4000, description="Actionable remediation guidance")
    locations: List[CodeLocation] = Field(default_factory=list, description="Relevant code locations")
    related_finding_id: Optional[str] = Field(default=None, max_length=64, description="Matching static finding ID")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_item_severity(cls, v: Any) -> str:
        return _normalize_finding_severity(v)

    @field_validator("title", "explanation", "recommendation")
    @classmethod
    def clean_required_fields(cls, v: str) -> str:
        return _clean_non_empty_text(v)

    @field_validator("related_finding_id")
    @classmethod
    def clean_related_id(cls, v: Optional[str]) -> Optional[str]:
        return _clean_optional_text(v)


class StructuredDiagnosisOutput(BaseModel):
    """
    Strictly validated Pydantic schema for structured AI finding diagnosis outputs.

    Note: `confidence` is optional and defaults to `None`; confidence scores are never
    fabricated when not genuinely supplied by the reasoning output.
    """
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=1, max_length=2000, description="Concise summary of the diagnosis")
    root_cause: str = Field(..., min_length=1, max_length=4000, description="Primary root cause statement")
    explanation: str = Field(..., min_length=1, max_length=6000, description="Technical explanation of why this occurs")
    severity: StructuredSeverity = Field(..., description="Assessed severity: error, warning, or info")
    findings: List[DiagnosisFindingItem] = Field(..., min_length=1, description="Validated finding breakdown entries")
    recommendations: List[str] = Field(..., min_length=1, description="Ordered actionable remediation steps")
    code_locations: List[CodeLocation] = Field(default_factory=list, description="Relevant code spans")
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional self-reported model confidence [0.0, 1.0]; None when omitted",
    )
    example_fix: Optional[str] = Field(default=None, max_length=8000, description="Corrected Python code example")

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_root_severity(cls, v: Any) -> str:
        return _normalize_finding_severity(v)

    @field_validator("summary", "root_cause", "explanation")
    @classmethod
    def clean_root_text(cls, v: str) -> str:
        return _clean_non_empty_text(v)

    @field_validator("recommendations")
    @classmethod
    def clean_recommendations(cls, v: List[str]) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("recommendations must be a list of non-empty strings.")
        cleaned = [_clean_non_empty_text(item, "Recommendation") for item in v]
        if not cleaned:
            raise ValueError("recommendations must include at least one non-empty item.")
        return cleaned

    @field_validator("example_fix")
    @classmethod
    def clean_example_fix(cls, v: Optional[str]) -> Optional[str]:
        return _clean_optional_text(v)


class DiagnosisExecutionResult(BaseModel):
    """
    Diagnosis pipeline outcome uniting validated structured output, fallback status,
    rendered user-facing Markdown, and usage metadata without breaking existing UIs.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    finding_id: str
    status: Literal["structured", "fallback_markdown", "fallback_static", "unavailable", "error"]
    structured: Optional[StructuredDiagnosisOutput] = None
    markdown: str = ""
    used_fallback: bool = False
    validation_error: Optional[str] = None
    provider: str = "unknown"
    model: Optional[str] = None
    usage: Optional[Any] = None

    def to_report_payload(self) -> Dict[str, Any]:
        """Convert outcome into report-compatible metadata for downstream persistence."""
        payload: Dict[str, Any] = {
            "finding_id": self.finding_id,
            "status": self.status,
            "used_fallback": self.used_fallback,
            "markdown": self.markdown,
            "provider": self.provider,
            "model": self.model,
        }
        if self.validation_error:
            payload["validation_error"] = self.validation_error
        if self.structured is not None:
            payload["structured"] = self.structured.model_dump(mode="json")
        return payload


