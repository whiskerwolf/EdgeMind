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

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


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

    code: str = Field(..., description="Python source code to analyze statically")
    filename: Optional[str] = Field(default="snippet.py", description="Display filename label")
    static_only: Optional[bool] = Field(default=True, description="Enforce static-only analysis")


class ProblemContextSchema(BaseModel):
    """Schema for programming problem context (LeetCode/custom)."""
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = Field(default=None, description="Problem title")
    slug: Optional[str] = Field(default=None, description="Problem URL slug")
    description: Optional[str] = Field(default=None, description="Problem description text")
    constraints: Optional[List[str]] = Field(default_factory=list, description="List of natural language constraint strings")
    parameters: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Identified problem parameters")


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
    report_storage_status: Optional[str] = Field(default="NOT_CONFIGURED")


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
    report_storage_status: Optional[str] = "NOT_CONFIGURED"
    created_at: Optional[str] = None


class AnalysisReportItemResponse(AnalysisSessionResponse):
    """SQL JOIN report representation linking session with Project and Problem metadata."""
    project_name: Optional[str] = Field(default=None, description="Joined project name")
    problem_title: Optional[str] = Field(default=None, description="Joined problem title")
    problem_slug: Optional[str] = Field(default=None, description="Joined problem slug")
    platform: Optional[str] = Field(default=None, description="Joined problem platform")
