"""
Dataset Schemas for LLM Evaluation Sets.

Defines Pydantic models for evaluation examples, ground truth definitions,
expected constraints, edge-case categories, tools, and evaluation datasets.
"""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from core.agents.tools import default_tool_registry

# Recognized tool names from default registry
KNOWN_TOOL_NAMES = set(default_tool_registry._tools.keys())


class ExpectedResponseStructure(BaseModel):
    """Specifies the structural invariants expected from the agent response."""
    required_fields: List[str] = Field(
        default_factory=lambda: [
            "status",
            "session_id",
            "execution_mode",
            "code_analysis",
            "test_intelligence",
        ],
        description="Fields that must exist and be non-null in the response.",
    )
    allowed_statuses: List[str] = Field(
        default_factory=lambda: [
            "SUCCESS",
            "STATIC_ONLY",
            "PROVIDER_UNAVAILABLE",
            "PARTIAL",
        ],
        description="Acceptable completion statuses.",
    )
    min_candidates: int = Field(
        default=1,
        ge=0,
        description="Minimum number of synthesized candidate test cases expected.",
    )
    require_code_analysis: bool = Field(
        default=True,
        description="Whether code_analysis must contain metrics and findings.",
    )
    require_test_intelligence: bool = Field(
        default=True,
        description="Whether test_intelligence must contain coverage gaps and candidates.",
    )


class EvaluationExample(BaseModel):
    """A single representative coding-problem evaluation example."""
    id: str = Field(
        ...,
        description="Globally unique identifier (e.g. eval-001-two-sum).",
    )
    name: str = Field(
        ...,
        description="Human-readable problem name.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Short description of the evaluation focus or scenario.",
    )
    problem_statement: str = Field(
        ...,
        description="Full coding problem description, signature, and constraints.",
    )
    code_snippet: str = Field(
        ...,
        description="Python implementation code subjected to agent analysis.",
    )
    filename: str = Field(
        default="solution.py",
        description="Filename label for the code snippet.",
    )
    test_cases: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Baseline test cases provided in the evaluation scenario.",
    )
    problem_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional problem metadata (title, constraints, parameters).",
    )
    expected_constraints: List[str] = Field(
        ...,
        description="Ground-truth mathematical and domain constraint inequalities.",
    )
    expected_edge_case_categories: List[str] = Field(
        ...,
        description="Ground-truth input domain gap categories (e.g. EMPTY_COLLECTION, ZERO_VALUE).",
    )
    expected_relevant_tools: List[str] = Field(
        ...,
        description="Names of tools that an autonomous agent should invoke for this problem.",
    )
    expected_response_structure: ExpectedResponseStructure = Field(
        default_factory=ExpectedResponseStructure,
        description="Expected structure and content invariants of the analysis response.",
    )
    tags: List[str] = Field(
        ...,
        description="Evaluation tags (e.g. ['arrays', 'hash-table', 'boundary', 'ci-smoke']).",
    )
    difficulty: str = Field(
        default="medium",
        description="Difficulty tier: easy, medium, or hard.",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary additional metadata (source, leetcode_id, author, etc.).",
    )

    @field_validator("id")
    @classmethod
    def validate_id_format(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Evaluation example 'id' must not be empty.")
        if not re.match(r"^eval-[0-9]{3}(-[a-z0-9\-]+)?$", v):
            raise ValueError(
                f"Evaluation example 'id' '{v}' must follow pattern 'eval-XXX' or 'eval-XXX-name'."
            )
        return v

    @field_validator("name", "problem_statement", "code_snippet")
    @classmethod
    def validate_non_empty_strings(cls, v: str, info) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"Field '{info.field_name}' must be a non-empty string.")
        return v.strip()

    @field_validator("expected_constraints")
    @classmethod
    def validate_constraints(cls, v: List[str]) -> List[str]:
        if not v or len(v) == 0:
            raise ValueError("Evaluation example must specify at least 1 expected constraint.")
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Expected constraints must contain non-empty strings.")
        return v

    @field_validator("expected_edge_case_categories")
    @classmethod
    def validate_categories(cls, v: List[str]) -> List[str]:
        if not v or len(v) == 0:
            raise ValueError("Evaluation example must specify at least 1 expected edge-case category.")
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Expected edge-case categories must be non-empty strings.")
        return v

    @field_validator("expected_relevant_tools")
    @classmethod
    def validate_tools(cls, v: List[str]) -> List[str]:
        if not v or len(v) == 0:
            raise ValueError("Evaluation example must specify at least 1 expected relevant tool.")
        for tool in v:
            if tool not in KNOWN_TOOL_NAMES:
                raise ValueError(
                    f"Tool '{tool}' in expected_relevant_tools is not registered. "
                    f"Available tools: {sorted(list(KNOWN_TOOL_NAMES))}"
                )
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        if not v or len(v) == 0:
            raise ValueError("Evaluation example must have at least 1 tag.")
        return [t.strip().lower() for t in v if t.strip()]


class EvaluationDataset(BaseModel):
    """Collection of evaluation examples comprising a test benchmark."""
    name: str = Field(
        default="EdgeMind LLM Benchmark",
        description="Dataset name.",
    )
    version: str = Field(
        default="1.0.0",
        description="Dataset semantic version.",
    )
    description: str = Field(
        default="Representative coding problems for evaluating multi-step AI reasoning and tool use.",
        description="Dataset overview.",
    )
    examples: List[EvaluationExample] = Field(
        default_factory=list,
        description="List of evaluation examples.",
    )

    @model_validator(mode="after")
    def validate_unique_ids_and_count(self) -> "EvaluationDataset":
        seen_ids = set()
        duplicates = []
        for example in self.examples:
            if example.id in seen_ids:
                duplicates.append(example.id)
            seen_ids.add(example.id)

        if duplicates:
            raise ValueError(f"Duplicate evaluation example IDs detected: {duplicates}")

        return self

    def get_example_by_id(self, example_id: str) -> Optional[EvaluationExample]:
        """Lookup an example by ID."""
        for ex in self.examples:
            if ex.id == example_id:
                return ex
        return None

    def filter_by_tag(self, tag: str) -> List[EvaluationExample]:
        """Return all examples matching a tag."""
        target = tag.strip().lower()
        return [ex for ex in self.examples if target in ex.tags]

    def filter_by_difficulty(self, difficulty: str) -> List[EvaluationExample]:
        """Return all examples matching a difficulty tier."""
        target = difficulty.strip().lower()
        return [ex for ex in self.examples if ex.difficulty.lower() == target]
