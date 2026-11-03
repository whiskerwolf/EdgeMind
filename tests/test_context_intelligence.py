"""
Regression and Feature Test Suite for EdgeMind Context-Based Adaptive Test Intelligence (Mode B).

Verifies the 16 core regression requirements:
1. Baseline-driven mode remains unchanged.
2. Context-based mode activates when zero samples are available.
3. Integer parameters are identified correctly.
4. Array parameters are inferred from reliable signatures and context.
5. Matrix parameters are supported when determinable.
6. Numerical constraints are respected.
7. Exponential constraints remain correctly parsed.
8. Unsupported or ambiguous structures do not produce fabricated inputs.
9. Candidate validity classification.
10. Robustness probe classification.
11. Unknown logical semantics classification.
12. No baseline coverage claims in context-based mode.
13. API response identifies the analysis mode.
14. Static Code Hygiene remains available without samples.
15. Expected outputs remain unverified.
16. Original baseline-driven Two Sum workflow remains intact.
"""

import pytest
from fastapi.testclient import TestClient

from core.api import app
from core.service import analyze_edgemind
from core.test_intelligence.context_intelligence import (
    InferredParameter,
    classify_context_candidate,
    infer_parameter_context,
    synthesize_context_candidates,
)
from core.test_intelligence.constraint_parser import (
    parse_constraint_expressions,
    parse_number_expression,
)
from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    ProblemContext,
    TestCase,
    TestCaseSource,
)


@pytest.fixture
def client():
    return TestClient(app)


TWO_SUM_CODE_ANNOTATED = (
    "class Solution:\n"
    "    def twoSum(self, nums: list[int], target: int) -> list[int]:\n"
    "        seen = {}\n"
    "        for i, n in enumerate(nums):\n"
    "            comp = target - n\n"
    "            if comp in seen:\n"
    "                return [seen[comp], i]\n"
    "            seen[n] = i\n"
    "        return []\n"
)

TWO_SUM_CONTEXT = {
    "platform": "leetcode",
    "problem_id": "1",
    "title": "Two Sum",
    "function_name": "twoSum",
    "parameters": ["nums", "target"],
    "description": "Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
    "constraints": [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
        "Only one valid answer exists.",
    ],
}


# =============================================================================
# Requirement 1: Baseline-driven mode remains unchanged
# =============================================================================
def test_regression_01_baseline_driven_mode_remains_unchanged(client):
    """Verify that when public baseline examples are provided, Mode A executes with existing gap detection."""
    payload = {
        "code": TWO_SUM_CODE_ANNOTATED,
        "filename": "two_sum.py",
        "problem_context": TWO_SUM_CONTEXT,
        "test_cases": [
            {"nums": [2, 7, 11, 15], "target": 9},
            {"nums": [3, 2, 4], "target": 6},
        ],
        "max_candidates": 8,
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    assert data["analysis_mode"] == "BASELINE_DRIVEN"
    assert data["baseline_available"] is True
    assert data["context_completeness"] in ("DETECTED", "PARTIAL")

    intel = data["test_intelligence"]
    assert intel["existing_tests_analyzed"] == 2
    assert len(intel["coverage_gaps"]) > 0
    assert intel["total_gaps"] > 0
    assert len(intel["generated_candidates"]) > 0


# =============================================================================
# Requirement 2: Context-based mode activates when zero samples are available
# =============================================================================
def test_regression_02_context_based_mode_activates_when_zero_samples(client):
    """Verify that when test_cases is empty, Mode B automatically activates and generates candidates."""
    payload = {
        "code": TWO_SUM_CODE_ANNOTATED,
        "filename": "two_sum.py",
        "problem_context": TWO_SUM_CONTEXT,
        "test_cases": [],  # Zero baseline samples
        "max_candidates": 10,
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    assert data["analysis_mode"] == "CONTEXT_BASED"
    assert data["baseline_available"] is False
    assert data["generation_status"] == "SUCCESS"

    intel = data["test_intelligence"]
    assert intel["existing_tests_analyzed"] == 0
    assert len(intel["generated_candidates"]) > 0
    assert intel["coverage_gaps"] == []
    assert intel["total_gaps"] == 0


# =============================================================================
# Requirement 3: Integer parameters are identified correctly
# =============================================================================
def test_regression_03_integer_parameters_identified_correctly():
    """Verify scalar integer parameters are inferred from type annotations and numerical constraints."""
    code = (
        "class Solution:\n"
        "    def mySqrt(self, x: int) -> int:\n"
        "        return int(x ** 0.5)\n"
    )
    ctx = ProblemContext(
        title="Sqrt(x)",
        description="Given a non-negative integer x, return the square root of x rounded down to the nearest integer.",
        constraints=["0 <= x <= 2^31 - 1"],
    )
    spec, _ = parse_constraint_expressions(ctx.constraints, known_parameters=["x"])
    params, limitations, completeness = infer_parameter_context(code, ctx, spec)

    assert len(params) == 1
    p = params[0]
    assert p.name == "x"
    assert p.param_type == "int"
    assert p.structure == "scalar"
    assert p.min_value == 0
    assert p.max_value == 2147483647
    assert p.is_ambiguous is False
    assert completeness == "DETECTED"

    # Synthesize candidates for scalar integer
    selected, _, _ = synthesize_context_candidates(params, ctx, spec, max_candidates=5)
    values = [c.input_data["x"] for c in selected]
    assert 0 in values  # Min permitted value / zero
    assert 2147483647 in values  # Max permitted value


# =============================================================================
# Requirement 4: Array parameters are inferred from reliable signatures and context
# =============================================================================
def test_regression_04_array_parameters_inferred_from_signatures_and_context():
    """Verify 1D array parameters are inferred from List[int], list[int], and length constraints."""
    code = (
        "class Solution:\n"
        "    def findMedianSortedArrays(self, nums1: list[int], nums2: list[int]) -> float:\n"
        "        return 0.0\n"
    )
    ctx = ProblemContext(
        title="Median of Two Sorted Arrays",
        description="Given two sorted arrays nums1 and nums2 of size m and n respectively, return the median.",
        constraints=["0 <= nums1.length <= 1000", "0 <= nums2.length <= 1000", "-10^6 <= nums1[i], nums2[i] <= 10^6"],
    )
    spec, _ = parse_constraint_expressions(ctx.constraints, known_parameters=["nums1", "nums2"])
    params, _, completeness = infer_parameter_context(code, ctx, spec)

    assert len(params) == 2
    p1, p2 = params[0], params[1]
    assert p1.name == "nums1" and p1.structure == "array_1d" and p1.element_type == "int"
    assert p2.name == "nums2" and p2.structure == "array_1d" and p2.element_type == "int"
    assert p1.min_length == 0 and p1.max_length == 1000
    assert p2.min_length == 0 and p2.max_length == 1000


# =============================================================================
# Requirement 5: Matrix parameters are supported when determinable
# =============================================================================
def test_regression_05_matrix_parameters_supported_when_determinable():
    """Verify 2D matrix parameters are inferred from List[List[int]] and matrix dimensions."""
    code = (
        "class Solution:\n"
        "    def rotate(self, matrix: list[list[int]]) -> None:\n"
        "        pass\n"
    )
    ctx = ProblemContext(
        title="Rotate Image",
        description="You are given an n x n 2D matrix representing an image, rotate the image by 90 degrees.",
        constraints=["n == matrix.length == matrix[i].length", "1 <= n <= 20", "-1000 <= matrix[i][j] <= 1000"],
    )
    spec, _ = parse_constraint_expressions(ctx.constraints, known_parameters=["matrix"])
    params, _, completeness = infer_parameter_context(code, ctx, spec)

    assert len(params) == 1
    p = params[0]
    assert p.name == "matrix"
    assert p.structure == "matrix_2d"
    assert p.element_type == "int"

    selected, _, _ = synthesize_context_candidates(params, ctx, spec, max_candidates=5)
    matrices = [c.input_data["matrix"] for c in selected]
    # Check that 2D structures are generated (list of lists)
    assert any(isinstance(m, list) and len(m) > 0 and isinstance(m[0], list) for m in matrices)
    # 1x1 matrix should be present
    assert any(m == [[1]] for m in matrices)


# =============================================================================
# Requirement 6: Numerical constraints are respected
# =============================================================================
def test_regression_06_numerical_constraints_are_respected():
    """Verify synthesized candidates respect min_value and max_value bounds."""
    code = "def check(nums: list[int]) -> bool:\n    return True\n"
    ctx = ProblemContext(
        title="Check Numbers",
        constraints=["1 <= nums.length <= 100", "-50 <= nums[i] <= 50"],
    )
    spec, _ = parse_constraint_expressions(ctx.constraints, known_parameters=["nums"])
    params, _, _ = infer_parameter_context(code, ctx, spec)
    selected, _, _ = synthesize_context_candidates(params, ctx, spec, max_candidates=10)

    for cand in selected:
        arr = cand.input_data.get("nums", [])
        if cand.classification == CandidateClassification.VALID.value:
            for elem in arr:
                assert -50 <= elem <= 50


# =============================================================================
# Requirement 7: Exponential constraints remain correctly parsed
# =============================================================================
def test_regression_07_exponential_constraints_remain_correctly_parsed():
    """Verify exponential expressions like 10^4, -10^9, 2^31 - 1, 2*10^4, 10⁹ parse correctly."""
    assert parse_number_expression("10^4") == 10000
    assert parse_number_expression("-10^9") == -1000000000
    assert parse_number_expression("10^9") == 1000000000
    assert parse_number_expression("2^31 - 1") == 2147483647
    assert parse_number_expression("-2^31") == -2147483648
    assert parse_number_expression("2 * 10^4") == 20000
    assert parse_number_expression("10⁹") == 1000000000


# =============================================================================
# Requirement 8: Unsupported or ambiguous structures do not produce fabricated inputs
# =============================================================================
def test_regression_08_unsupported_or_ambiguous_structures_no_fabricated_inputs(client):
    """Verify that ambiguous parameters without context or type annotations return INSUFFICIENT_CONTEXT."""
    untyped_code = "def solve(x):\n    return x\n"
    payload = {
        "code": untyped_code,
        "filename": "solve.py",
        "test_cases": [],
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "INSUFFICIENT_CONTEXT"
    assert data["analysis_mode"] == "CONTEXT_BASED"
    assert data["test_intelligence"]["generated_candidates"] == []
    assert len(data["warnings"]) > 0
    assert any("ambiguous" in w.lower() or "parameter" in w.lower() for w in data["warnings"] + data["limitations"])


# =============================================================================
# Requirement 9: Candidate validity classification
# =============================================================================
def test_regression_09_candidate_validity_classification():
    """Verify candidates satisfying all constraints and semantic invariants are classified as VALID."""
    cand = TestCase(
        id="c1",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    spec = ConstraintSpec(min_length=2, max_length=10000, min_value=-1000000000, max_value=1000000000)
    ctx = ProblemContext(title="Two Sum", problem_id="1")
    params = [
        InferredParameter(name="nums", structure="array_1d", element_type="int", min_length=2, max_length=10000),
        InferredParameter(name="target", structure="scalar", param_type="int", min_value=-1000000000, max_value=1000000000),
    ]

    classification, reason = classify_context_candidate(cand, spec, ctx, params)
    assert classification == CandidateClassification.VALID.value
    assert "exactly one valid pair" in reason.lower()


# =============================================================================
# Requirement 10: Robustness probe classification
# =============================================================================
def test_regression_10_robustness_probe_classification():
    """Verify intentional constraint violations (e.g. empty collection when min_length >= 1) are ROBUSTNESS PROBE."""
    cand_empty = TestCase(
        id="c-empty",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [], "target": 0},
    )
    spec = ConstraintSpec(min_length=2, max_length=10000)
    ctx = ProblemContext(title="Two Sum")
    params = [
        InferredParameter(name="nums", structure="array_1d", element_type="int", min_length=2),
        InferredParameter(name="target", structure="scalar", param_type="int"),
    ]

    classification, reason = classify_context_candidate(cand_empty, spec, ctx, params)
    assert classification == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "Deliberate robustness probe" in reason


# =============================================================================
# Requirement 11: Unknown logical semantics classification
# =============================================================================
def test_regression_11_unknown_logical_semantics_classification():
    """Verify that when logical relationships are unknown or violated, candidate is classified as CONSTRAINT VALIDITY UNKNOWN."""
    # Two Sum violation: no valid pair
    cand_no_pair = TestCase(
        id="c-no-pair",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [1, 1, 1], "target": 5},
    )
    spec = ConstraintSpec(min_length=2, max_length=10000, min_value=-1000, max_value=1000)
    ctx_twosum = ProblemContext(title="Two Sum")
    params_twosum = [
        InferredParameter(name="nums", structure="array_1d", element_type="int"),
        InferredParameter(name="target", structure="scalar", param_type="int"),
    ]
    cls_twosum, reason_twosum = classify_context_candidate(cand_no_pair, spec, ctx_twosum, params_twosum)
    assert cls_twosum == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value
    assert "no pair in collection sums to target" in reason_twosum.lower()

    # Multi-parameter non-Two-Sum problem: unknown relationship
    cand_search = TestCase(
        id="c-search",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [1, 3, 5], "target": 4},
    )
    ctx_search = ProblemContext(title="Binary Search")
    params_search = [
        InferredParameter(name="nums", structure="array_1d", element_type="int"),
        InferredParameter(name="target", structure="scalar", param_type="int"),
    ]
    cls_search, reason_search = classify_context_candidate(cand_search, spec, ctx_search, params_search)
    assert cls_search == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value
    assert "inter-parameter logical semantics are unverified" in reason_search.lower()


# =============================================================================
# Requirement 12: No baseline coverage claims in context-based mode
# =============================================================================
def test_regression_12_no_baseline_coverage_claims_in_context_based_mode(client):
    """Verify that Mode B reports zero gaps, empty coverage_gaps, and empty detected_patterns."""
    payload = {
        "code": TWO_SUM_CODE_ANNOTATED,
        "filename": "two_sum.py",
        "problem_context": TWO_SUM_CONTEXT,
        "test_cases": [],
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    intel = data["test_intelligence"]
    assert intel["coverage_gaps"] == []
    assert intel["total_gaps"] == 0
    assert intel["detected_patterns"] == {}
    assert any("no public baseline examples were available" in w.lower() for w in data["warnings"])


# =============================================================================
# Requirement 13: API response identifies the analysis mode
# =============================================================================
def test_regression_13_api_response_identifies_the_analysis_mode(client):
    """Verify explicit analysis_mode and baseline_available metadata in response."""
    # 1. Baseline driven
    res_a = client.post(
        "/api/v1/edgemind/analyze",
        json={"code": TWO_SUM_CODE_ANNOTATED, "problem_context": TWO_SUM_CONTEXT, "test_cases": [{"nums": [1, 2], "target": 3}]},
    ).json()
    assert res_a["analysis_mode"] == "BASELINE_DRIVEN"
    assert res_a["baseline_available"] is True

    # 2. Context based
    res_b = client.post(
        "/api/v1/edgemind/analyze",
        json={"code": TWO_SUM_CODE_ANNOTATED, "problem_context": TWO_SUM_CONTEXT, "test_cases": []},
    ).json()
    assert res_b["analysis_mode"] == "CONTEXT_BASED"
    assert res_b["baseline_available"] is False


# =============================================================================
# Requirement 14: Static Code Hygiene remains available without samples
# =============================================================================
def test_regression_14_static_code_hygiene_remains_available_without_samples(client):
    """Verify EdgeMind static analysis runs and reports smells even when test cases are absent."""
    code_with_smell = (
        "class Solution:\n"
        "    def twoSum(self, nums: list[int], target: int) -> list[int]:\n"
        "        unused_variable = 42\n"  # Unused variable smell
        "        return []\n"
    )
    payload = {
        "code": code_with_smell,
        "filename": "two_sum.py",
        "problem_context": TWO_SUM_CONTEXT,
        "test_cases": [],
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "code_analysis" in data
    code_report = data["code_analysis"]
    assert "score" in code_report
    assert len(code_report["detailed_warnings"]) > 0
    assert any("unused_variable" in str(w) for w in code_report["detailed_warnings"])


# =============================================================================
# Requirement 15: Expected outputs remain unverified
# =============================================================================
def test_regression_15_expected_outputs_remain_unverified(client):
    """Verify all generated candidates have expected_output=None and is_expected_output_verified=False."""
    payload = {
        "code": TWO_SUM_CODE_ANNOTATED,
        "filename": "two_sum.py",
        "problem_context": TWO_SUM_CONTEXT,
        "test_cases": [],
        "max_candidates": 10,
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    candidates = data["test_intelligence"]["generated_candidates"]
    assert len(candidates) > 0
    for cand in candidates:
        assert cand["expected_output"] is None
        assert cand["is_expected_output_verified"] is False
        assert cand["source"] == TestCaseSource.GENERATED_TEST.value


# =============================================================================
# Requirement 16: Original baseline-driven Two Sum workflow remains intact
# =============================================================================
def test_regression_16_original_baseline_driven_two_sum_workflow_intact(client):
    """Verify complete end-to-end Two Sum workflow with public samples matches existing test specifications."""
    payload = {
        "code": TWO_SUM_CODE_ANNOTATED,
        "filename": "two_sum.py",
        "problem_context": TWO_SUM_CONTEXT,
        "test_cases": [
            {"nums": [2, 7, 11, 15], "target": 9},
            {"nums": [3, 2, 4], "target": 6},
            {"nums": [3, 3], "target": 6},
        ],
        "max_candidates": 10,
    }
    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    assert data["analysis_mode"] == "BASELINE_DRIVEN"
    assert data["baseline_available"] is True
    assert data["test_intelligence"]["existing_tests_analyzed"] == 3
    assert data["code_analysis"]["overall_status"] == "PASS"

    candidates = data["test_intelligence"]["generated_candidates"]
    assert len(candidates) > 0
    assert len(candidates) <= 10

    # Ensure valid Two Sum candidates exist
    valid_cands = [c for c in candidates if c.get("classification") == CandidateClassification.VALID.value]
    assert len(valid_cands) > 0

