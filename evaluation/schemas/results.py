"""
Evaluation Result & Metrics Schemas.

Defines Pydantic models for evaluation outputs, metric scores,
per-example evaluation results, aggregate benchmarks, and final reports.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExampleMetricScores(BaseModel):
    """Detailed metric scores for an individual evaluation example."""
    constraint_extraction_accuracy: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ratio of expected constraints successfully extracted and matched.",
    )
    tool_selection_precision: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Precision of tools invoked: |Selected ∩ Expected| / |Selected|.",
    )
    tool_selection_recall: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Recall of tools invoked: |Selected ∩ Expected| / |Expected|.",
    )
    tool_selection_f1: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Harmonic mean of tool-selection precision and recall.",
    )
    edge_case_coverage_recall: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Proportion of expected edge-case categories identified or targeted.",
    )
    structured_response_validity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="1.0 if response strictly complies with expected structural invariants, 0.0 otherwise.",
    )
    execution_success: bool = Field(
        ...,
        description="Whether the example completed without an unhandled error or crash.",
    )
    provider_error: bool = Field(
        default=False,
        description="Whether a live provider error (401, 429, 500, network) occurred.",
    )


class ExampleEvaluationResult(BaseModel):
    """Execution output and evaluation scores for a single benchmark problem."""
    example_id: str = Field(..., description="Evaluation example unique identifier.")
    name: str = Field(..., description="Problem name.")
    status: str = Field(..., description="Agent completion status (SUCCESS, PROVIDER_UNAVAILABLE, etc.).")
    execution_mode: str = Field(..., description="Execution mode: AI_AGENT, STATIC_ONLY, or DEGRADED_STATIC.")
    duration_ms: float = Field(..., ge=0.0, description="Evaluation run duration in milliseconds.")
    iterations: int = Field(default=0, ge=0, description="Number of agent reasoning iterations.")
    selected_tools: List[str] = Field(default_factory=list, description="Tools actually invoked.")
    extracted_constraints: List[str] = Field(default_factory=list, description="Constraints parsed.")
    covered_edge_case_categories: List[str] = Field(
        default_factory=list,
        description="Edge-case gap categories identified in findings or candidates.",
    )
    generated_candidate_count: int = Field(default=0, ge=0, description="Number of candidate test cases generated.")
    metrics: ExampleMetricScores = Field(..., description="Evaluated metric scores.")
    error_message: Optional[str] = Field(default=None, description="Error detail if run failed.")


class AggregateMetrics(BaseModel):
    """Aggregate benchmark metrics calculated across all evaluated examples."""
    constraint_extraction_accuracy: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Mean constraint extraction accuracy across all examples.",
    )
    tool_selection_precision: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Mean tool-selection precision.",
    )
    tool_selection_recall: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Mean tool-selection recall.",
    )
    tool_selection_f1: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Mean tool-selection F1 score.",
    )
    edge_case_coverage_recall: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Mean edge-case coverage recall.",
    )
    structured_response_validity: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Mean structured response validity rate.",
    )
    evaluation_completion_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ratio of examples that completed without unhandled exceptions.",
    )
    provider_error_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ratio of examples that experienced provider failure.",
    )


class EvaluationReport(BaseModel):
    """Complete evaluation report serializable to latest_evaluation.json."""
    timestamp: str = Field(..., description="ISO 8601 timestamp of evaluation execution.")
    evaluation_mode: str = Field(
        ...,
        description="'deterministic_ci' or 'live_llm'.",
    )
    model: Optional[str] = Field(default=None, description="Target LLM model name, if live.")
    dataset_name: str = Field(..., description="Dataset name.")
    dataset_version: str = Field(..., description="Dataset version.")
    total_examples: int = Field(..., ge=0, description="Total number of examples evaluated.")
    successful_runs: int = Field(..., ge=0, description="Number of runs completing without error.")
    failed_runs: int = Field(..., ge=0, description="Number of runs with unhandled errors.")
    total_duration_ms: float = Field(..., ge=0.0, description="Total evaluation duration in ms.")
    aggregate_metrics: AggregateMetrics = Field(..., description="Dataset-level aggregate metrics.")
    per_example_results: List[ExampleEvaluationResult] = Field(
        default_factory=list,
        description="Itemized results for each evaluation example.",
    )
    summary: str = Field(..., description="Executive narrative summary of the evaluation.")
