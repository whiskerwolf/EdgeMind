"""
Automated Test Suite for EdgeMind LLM Evaluation Benchmark.

Validates:
1. Dataset Integrity & Schema Validation (Pydantic validation, duplicate ID rejection, invalid tools).
2. Metric Calculations:
   - Constraint extraction accuracy
   - Tool-selection precision, recall, and F1
   - Edge-case coverage recall (with synonym mapping)
   - Structured response validity
   - Aggregate metrics computation
3. Evaluation Runner in Deterministic CI mode (single and full batch).
4. Error Handling & Provider Failure Resilience.
5. Live Mode Credential Guard (never claim live evaluation without credentials).
6. Deterministic Reproducibility (identical results across consecutive runs).
7. Report Generation & Serialization (JSON schema round-trip).
"""

import json
from pathlib import Path
import pytest

from core.agents.schemas import AgentStepResult
from core.agents.provider import MockAgentProvider
from evaluation.datasets.loader import (
    load_default_dataset,
    load_dataset_from_file,
    validate_dataset_dict,
)
from evaluation.metrics.calculator import (
    calculate_constraint_accuracy,
    calculate_edge_case_recall,
    calculate_structured_response_validity,
    calculate_tool_precision_recall_f1,
    compute_aggregate_metrics,
)
from evaluation.runner import EvaluationRunner, DeterministicEvaluationProvider
from evaluation.schemas.dataset import (
    EvaluationDataset,
    EvaluationExample,
    ExpectedResponseStructure,
)
from evaluation.schemas.results import (
    EvaluationReport,
    ExampleEvaluationResult,
    ExampleMetricScores,
)


@pytest.fixture
def default_dataset():
    """Load default 22-problem evaluation benchmark."""
    return load_default_dataset()


# =============================================================================
# 1. Dataset Integrity & Validation Tests
# =============================================================================

def test_default_dataset_validity(default_dataset):
    """Verify default dataset loads cleanly and satisfies all benchmark invariants."""
    assert default_dataset is not None
    assert len(default_dataset.examples) >= 20
    assert len(default_dataset.examples) == 22

    ids = [ex.id for ex in default_dataset.examples]
    assert len(ids) == len(set(ids)), "All example IDs must be globally unique"

    for ex in default_dataset.examples:
        assert ex.id.startswith("eval-")
        assert len(ex.name) > 0
        assert len(ex.problem_statement) > 0
        assert len(ex.code_snippet) > 0
        assert len(ex.expected_constraints) >= 1
        assert len(ex.expected_edge_case_categories) >= 1
        assert len(ex.expected_relevant_tools) >= 1
        assert len(ex.tags) >= 1
        assert ex.difficulty in ("easy", "medium", "hard")


def test_dataset_validation_rejects_duplicate_ids():
    """Verify dataset validator rejects duplicate IDs."""
    data = {
        "name": "Duplicate Test",
        "version": "1.0.0",
        "description": "Test",
        "examples": [
            {
                "id": "eval-001-dup",
                "name": "Ex 1",
                "problem_statement": "Problem 1",
                "code_snippet": "def f(): pass",
                "expected_constraints": ["x > 0"],
                "expected_edge_case_categories": ["ZERO_VALUE"],
                "expected_relevant_tools": ["analyze_problem_structure"],
                "tags": ["test"],
            },
            {
                "id": "eval-001-dup",  # Duplicate ID
                "name": "Ex 2",
                "problem_statement": "Problem 2",
                "code_snippet": "def g(): pass",
                "expected_constraints": ["y > 0"],
                "expected_edge_case_categories": ["ZERO_VALUE"],
                "expected_relevant_tools": ["analyze_problem_structure"],
                "tags": ["test"],
            },
        ],
    }
    with pytest.raises(ValueError, match="Duplicate evaluation example IDs"):
        validate_dataset_dict(data)


def test_dataset_validation_rejects_unregistered_tools():
    """Verify dataset validator rejects unknown or unregistered tool names."""
    data = {
        "name": "Bad Tool Test",
        "version": "1.0.0",
        "description": "Test",
        "examples": [
            {
                "id": "eval-099-bad-tool",
                "name": "Bad Tool Example",
                "problem_statement": "Solve x",
                "code_snippet": "def f(): pass",
                "expected_constraints": ["x > 0"],
                "expected_edge_case_categories": ["ZERO_VALUE"],
                "expected_relevant_tools": ["non_existent_magic_tool"],  # Unregistered tool
                "tags": ["test"],
            }
        ],
    }
    with pytest.raises(ValueError, match="is not registered"):
        validate_dataset_dict(data)


def test_dataset_validation_rejects_empty_constraints():
    """Verify dataset validator rejects examples without constraints."""
    data = {
        "name": "Empty Constraints Test",
        "version": "1.0.0",
        "description": "Test",
        "examples": [
            {
                "id": "eval-099-empty-constraints",
                "name": "Empty Constraints",
                "problem_statement": "Solve x",
                "code_snippet": "def f(): pass",
                "expected_constraints": [],  # Empty
                "expected_edge_case_categories": ["ZERO_VALUE"],
                "expected_relevant_tools": ["analyze_problem_structure"],
                "tags": ["test"],
            }
        ],
    }
    with pytest.raises(ValueError, match="at least 1 expected constraint"):
        validate_dataset_dict(data)


def test_dataset_filtering(default_dataset):
    """Verify filtering examples by tags and difficulty levels."""
    smoke_examples = default_dataset.filter_by_tag("ci-smoke")
    assert len(smoke_examples) >= 2
    for ex in smoke_examples:
        assert "ci-smoke" in ex.tags

    easy_examples = default_dataset.filter_by_difficulty("easy")
    assert len(easy_examples) >= 3
    for ex in easy_examples:
        assert ex.difficulty == "easy"

    example_001 = default_dataset.get_example_by_id("eval-001-two-sum")
    assert example_001 is not None
    assert example_001.name == "Two Sum"


# =============================================================================
# 2. Metric Calculation Tests
# =============================================================================

def test_metric_constraint_accuracy():
    """Verify constraint extraction accuracy metric."""
    expected = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
    ]

    # Perfect match
    extracted_full = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
    ]
    assert calculate_constraint_accuracy(expected, extracted_full) == 1.0

    # Partial match (2 out of 3)
    extracted_partial = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
    ]
    assert calculate_constraint_accuracy(expected, extracted_partial) == pytest.approx(2 / 3, 0.01)

    # Token overlap match (re-formatted inequality)
    extracted_token = [
        "nums.length between 2 and 10^4",
        "nums[i] within -10^9 to 10^9",
        "target bounded by 10^9",
    ]
    assert calculate_constraint_accuracy(expected, extracted_token) == 1.0

    # Zero match
    assert calculate_constraint_accuracy(expected, ["completely unrelated string"]) == 0.0

    # Empty cases
    assert calculate_constraint_accuracy([], ["any"]) == 1.0
    assert calculate_constraint_accuracy(expected, []) == 0.0


def test_metric_tool_precision_recall_f1():
    """Verify tool selection precision, recall, and F1 calculations."""
    expected = ["analyze_problem_structure", "parse_problem_constraints", "detect_coverage_gaps"]

    # 1. Perfect match
    p, r, f1 = calculate_tool_precision_recall_f1(expected, expected)
    assert (p, r, f1) == (1.0, 1.0, 1.0)

    # 2. Under-selection (selected 2 out of 3 expected): Precision = 1.0, Recall = 2/3, F1 = 0.8
    selected_under = ["analyze_problem_structure", "parse_problem_constraints"]
    p, r, f1 = calculate_tool_precision_recall_f1(expected, selected_under)
    assert p == 1.0
    assert r == pytest.approx(2 / 3, 0.001)
    assert f1 == pytest.approx(0.8, 0.001)

    # 3. Over-selection (selected 3 expected + 1 unexpected): Precision = 3/4 = 0.75, Recall = 1.0
    selected_over = expected + ["generate_candidate_inputs"]
    p, r, f1 = calculate_tool_precision_recall_f1(expected, selected_over)
    assert p == 0.75
    assert r == 1.0
    assert f1 == pytest.approx(2 * 0.75 * 1.0 / 1.75, 0.001)

    # 4. Disjoint sets
    p, r, f1 = calculate_tool_precision_recall_f1(expected, ["rank_candidate_inputs"])
    assert (p, r, f1) == (0.0, 0.0, 0.0)

    # 5. Empty cases
    assert calculate_tool_precision_recall_f1([], []) == (1.0, 1.0, 1.0)
    assert calculate_tool_precision_recall_f1(expected, []) == (0.0, 0.0, 0.0)


def test_metric_edge_case_recall():
    """Verify edge-case coverage recall including synonym normalization."""
    expected = ["EMPTY_COLLECTION", "ZERO_VALUE", "NEGATIVE_VALUES", "DUPLICATE_ELEMENTS"]

    # Exact match
    covered_exact = ["EMPTY_COLLECTION", "ZERO_VALUE", "NEGATIVE_VALUES", "DUPLICATE_ELEMENTS"]
    assert calculate_edge_case_recall(expected, covered_exact) == 1.0

    # Synonym mapping: "EMPTY_ARRAY" -> "EMPTY_COLLECTION", "ZEROS" -> "ZERO_VALUE"
    covered_synonyms = ["EMPTY_ARRAY", "ZEROS", "EXTRA_CATEGORY"]
    # Matches 2 out of 4 expected
    assert calculate_edge_case_recall(expected, covered_synonyms) == 0.5

    # Empty cases
    assert calculate_edge_case_recall([], ["any"]) == 1.0
    assert calculate_edge_case_recall(expected, []) == 0.0


def test_metric_structured_response_validity():
    """Verify structured response validity against schema invariants."""
    exp_struct = ExpectedResponseStructure(
        required_fields=["status", "session_id", "execution_mode", "code_analysis", "test_intelligence"],
        allowed_statuses=["SUCCESS", "STATIC_ONLY"],
        min_candidates=1,
    )

    valid_response = {
        "status": "SUCCESS",
        "session_id": "test-session-uuid",
        "execution_mode": "AI_AGENT",
        "code_analysis": {"metrics": {}, "findings_count": 0},
        "test_intelligence": {
            "coverage_gaps": [],
            "generated_candidates": [{"input_data": {"x": 1}}],
        },
    }
    assert calculate_structured_response_validity(valid_response, exp_struct) == 1.0

    # Invalid: missing required field 'test_intelligence'
    invalid_missing = dict(valid_response)
    del invalid_missing["test_intelligence"]
    assert calculate_structured_response_validity(invalid_missing, exp_struct) == 0.0

    # Invalid: status not in allowed statuses
    invalid_status = dict(valid_response)
    invalid_status["status"] = "UNKNOWN_STATUS"
    assert calculate_structured_response_validity(invalid_status, exp_struct) == 0.0

    # Invalid: 0 candidates when min_candidates=1
    invalid_cand = dict(valid_response)
    invalid_cand["test_intelligence"] = {"coverage_gaps": [], "generated_candidates": []}
    assert calculate_structured_response_validity(invalid_cand, exp_struct) == 0.0


def test_compute_aggregate_metrics():
    """Verify computation of aggregate benchmark metrics across multiple results."""
    m1 = ExampleMetricScores(
        constraint_extraction_accuracy=1.0,
        tool_selection_precision=1.0,
        tool_selection_recall=1.0,
        tool_selection_f1=1.0,
        edge_case_coverage_recall=0.8,
        structured_response_validity=1.0,
        execution_success=True,
        provider_error=False,
    )
    m2 = ExampleMetricScores(
        constraint_extraction_accuracy=0.6,
        tool_selection_precision=0.8,
        tool_selection_recall=0.6,
        tool_selection_f1=0.6857,
        edge_case_coverage_recall=0.4,
        structured_response_validity=1.0,
        execution_success=True,
        provider_error=False,
    )
    r1 = ExampleEvaluationResult(
        example_id="eval-001",
        name="Ex 1",
        status="SUCCESS",
        execution_mode="AI_AGENT",
        duration_ms=50.0,
        metrics=m1,
    )
    r2 = ExampleEvaluationResult(
        example_id="eval-002",
        name="Ex 2",
        status="SUCCESS",
        execution_mode="AI_AGENT",
        duration_ms=60.0,
        metrics=m2,
    )

    agg = compute_aggregate_metrics([r1, r2])
    assert agg.constraint_extraction_accuracy == pytest.approx(0.8, 0.001)
    assert agg.tool_selection_precision == pytest.approx(0.9, 0.001)
    assert agg.tool_selection_recall == pytest.approx(0.8, 0.001)
    assert agg.tool_selection_f1 == pytest.approx((1.0 + 0.6857) / 2, 0.001)
    assert agg.edge_case_coverage_recall == pytest.approx(0.6, 0.001)
    assert agg.structured_response_validity == 1.0
    assert agg.evaluation_completion_rate == 1.0
    assert agg.provider_error_rate == 0.0


# =============================================================================
# 3. Evaluation Runner Tests (Deterministic CI Mode)
# =============================================================================

@pytest.mark.anyio
async def test_runner_deterministic_single_example(default_dataset):
    """Test evaluation runner on single example eval-001-two-sum."""
    example = default_dataset.get_example_by_id("eval-001-two-sum")
    runner = EvaluationRunner(dataset=default_dataset)

    result = await runner.evaluate_example(example)

    assert result.example_id == "eval-001-two-sum"
    assert result.status == "SUCCESS"
    assert result.execution_mode == "AI_AGENT"
    assert result.iterations == 4
    assert len(result.selected_tools) == 6
    assert result.metrics.execution_success is True
    assert result.metrics.constraint_extraction_accuracy == 1.0
    assert result.metrics.tool_selection_f1 == 1.0
    assert result.metrics.structured_response_validity == 1.0


@pytest.mark.anyio
async def test_runner_deterministic_subset_by_tag(default_dataset):
    """Test evaluation runner on smoke subset."""
    runner = EvaluationRunner(dataset=default_dataset)
    report = await runner.run_deterministic(tags=["ci-smoke"], save_report=False)

    assert report.total_examples >= 2
    assert report.successful_runs == report.total_examples
    assert report.failed_runs == 0
    assert report.aggregate_metrics.evaluation_completion_rate == 1.0
    assert report.aggregate_metrics.tool_selection_f1 == 1.0
    assert report.aggregate_metrics.structured_response_validity == 1.0


@pytest.mark.anyio
async def test_runner_deterministic_reproducibility(default_dataset):
    """Running deterministic evaluation twice yields identical metric scores."""
    runner = EvaluationRunner(dataset=default_dataset)

    report1 = await runner.run_deterministic(example_ids=["eval-001-two-sum", "eval-002-valid-parentheses"], save_report=False)
    report2 = await runner.run_deterministic(example_ids=["eval-001-two-sum", "eval-002-valid-parentheses"], save_report=False)

    assert report1.total_examples == report2.total_examples
    assert report1.aggregate_metrics.constraint_extraction_accuracy == report2.aggregate_metrics.constraint_extraction_accuracy
    assert report1.aggregate_metrics.tool_selection_f1 == report2.aggregate_metrics.tool_selection_f1
    assert report1.aggregate_metrics.edge_case_coverage_recall == report2.aggregate_metrics.edge_case_coverage_recall
    assert report1.aggregate_metrics.structured_response_validity == report2.aggregate_metrics.structured_response_validity


# =============================================================================
# 4. Error Handling, Provider Failures & Live Mode Guards
# =============================================================================

@pytest.mark.anyio
async def test_runner_handles_provider_exception_gracefully(default_dataset):
    """Evaluation runner traps provider exceptions without crashing."""
    class FailingProvider(MockAgentProvider):
        @property
        def name(self):
            return "failing_mock"

        async def chat_completion(self, messages, tools, temperature=0.0):
            raise ConnectionResetError("Simulated remote provider connection reset")

    example = default_dataset.get_example_by_id("eval-001-two-sum")
    runner = EvaluationRunner(dataset=default_dataset)

    # AgentOrchestrator traps provider errors and falls back to DEGRADED_STATIC
    result = await runner.evaluate_example(example, provider=FailingProvider(), is_live=False)

    assert result.status == "PROVIDER_ERROR"
    assert result.execution_mode == "DEGRADED_STATIC"
    assert result.metrics.execution_success is True


@pytest.mark.anyio
async def test_runner_live_mode_without_credentials_raises_error(default_dataset, monkeypatch):
    """Live LLM evaluation must never claim live evaluation when credentials are missing."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("EDGEMIND_AI_PROVIDER_KEY", raising=False)

    runner = EvaluationRunner(dataset=default_dataset)

    with pytest.raises(RuntimeError, match="AI provider API key is not configured"):
        await runner.run_live(save_report=False)


# =============================================================================
# 5. Report Generation & JSON Serialization Tests
# =============================================================================

@pytest.mark.anyio
async def test_evaluation_report_file_generation(default_dataset, tmp_path):
    """Verify evaluation report is generated, saved, and deserializable."""
    runner = EvaluationRunner(dataset=default_dataset, reports_dir=tmp_path)
    report = await runner.run_deterministic(
        example_ids=["eval-001-two-sum"],
        save_report=True,
    )

    report_path = tmp_path / "latest_evaluation.json"
    assert report_path.exists()
    assert report_path.stat().st_size > 0

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate against EvaluationReport Pydantic schema
    loaded_report = EvaluationReport(**data)
    assert loaded_report.total_examples == 1
    assert loaded_report.evaluation_mode == "deterministic_ci"
    assert loaded_report.per_example_results[0].example_id == "eval-001-two-sum"
