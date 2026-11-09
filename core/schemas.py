"""
EdgeMind Pydantic Request & Response Schemas.

Defines typed schemas for FastAPI endpoints:
- /health
- /api/v1/analyze
- /api/v1/edgemind/analyze
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class HealthResponse(BaseModel):
    """Schema for /health response."""
    model_config = ConfigDict(extra="ignore")

    status: str = Field(default="healthy", description="Service health state")
    service: str = Field(default="EdgeMind", description="Service identity")


class ErrorResponse(BaseModel):
    """Consistent application error response envelope."""
    model_config = ConfigDict(extra="ignore")

    error: str = Field(..., description="High-level error classification (e.g. Bad Request, Internal Server Error)")
    detail: str = Field(..., description="Human-readable description of the error")
    request_id: Optional[str] = Field(default=None, description="Request correlation identifier")


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

