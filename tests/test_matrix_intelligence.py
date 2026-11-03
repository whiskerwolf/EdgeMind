"""
Test Suite for Matrix Domain Intelligence & LeetCode 3665 (Twisted Mirror Path Count) Fixes.

Verifies:
1. Parameter inference fallback from baseline samples when AST extraction is unavailable.
2. InferredParameter source tracking (AST_SIGNATURE, EXPLICIT_METADATA, BASELINE_SAMPLE).
3. Matrix dimension constraints parsing (m == grid.length, n == grid[i].length, 2 <= m, n <= 500).
4. Allowed cell-value domain parsing (grid[i][j] is either 0 or 1 -> [0, 1]).
5. Matrix endpoint logical invariants (grid[0][0] == grid[m-1][n-1] == 0).
6. Three-tier candidate classification (VALID, ROBUSTNESS PROBE, CONSTRAINT VALIDITY UNKNOWN).
7. Suppression of constraint-prohibited empty/singleton matrix gaps in baseline mode.
8. Context-based Mode B matrix candidate generation without public samples.
9. End-to-end integration test simulating LeetCode 3665 analysis.
"""

import pytest
from fastapi.testclient import TestClient

from core.api import app
from core.service import analyze_edgemind
from core.test_intelligence.constraint_parser import (
    classify_candidate,
    normalize_latex,
    parse_constraint_expressions,
    parse_number_expression,
)
from core.test_intelligence.context_intelligence import (
    InferredParameter,
    classify_context_candidate,
    infer_parameter_context,
    synthesize_context_candidates,
)
from core.test_intelligence.gap_detector import CoverageGapEvaluator
from core.test_intelligence.synthesizer import TargetedTestSynthesizer
from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)


@pytest.fixture
def client():
    return TestClient(app)


TWISTED_MIRROR_CONSTRAINTS = [
    "m == grid.length",
    "n == grid[i].length",
    "2 <= m, n <= 500",
    "grid[i][j] is either 0 or 1",
    "grid[0][0] == grid[m - 1][n - 1] == 0",
]

TWISTED_MIRROR_SAMPLES = [
    {"grid": [[0, 1, 0], [0, 0, 1], [1, 0, 0]]},
    {"grid": [[0, 0], [0, 0]]},
    {"grid": [[0, 1, 1], [1, 0, 0], [0, 0, 0]]},
]


def test_parameter_inference_fallback_from_baseline_samples():
    """Verify parameters and matrix structure are inferred from baseline samples when AST is unavailable."""
    code = "# Incomplete or non-Python code snippet without function definition"
    ctx = ProblemContext(
        platform="leetcode",
        problem_id="3665",
        title="Twisted Mirror Path Count",
        parameters=[],  # Explicit parameters empty
        constraints=TWISTED_MIRROR_CONSTRAINTS,
    )
    spec, _ = parse_constraint_expressions(ctx.constraints)

    params, limitations, completeness = infer_parameter_context(
        code=code,
        problem_context=ctx,
        spec=spec,
        test_cases=TWISTED_MIRROR_SAMPLES,
    )

    assert len(params) == 1
    p = params[0]
    assert p.name == "grid"
    assert p.structure == "matrix_2d"
    assert p.element_type == "int"
    assert p.source == "BASELINE_SAMPLE"
    # When inferred from baseline samples, report PARTIAL completeness
    assert completeness == "PARTIAL"


def test_matrix_dimension_constraints_parsing():
    """Verify matrix dimensions, cell domain, and endpoint invariants are parsed from LeetCode 3665 constraints."""
    spec, unresolved = parse_constraint_expressions(
        TWISTED_MIRROR_CONSTRAINTS, known_parameters=["grid"]
    )

    assert len(unresolved) == 0
    assert spec.min_rows == 2
    assert spec.max_rows == 500
    assert spec.min_cols == 2
    assert spec.max_cols == 500
    assert spec.min_length == 2
    assert spec.max_length == 500
    assert spec.min_value == 0
    assert spec.max_value == 1
    assert spec.allowed_values == [0, 1]
    assert spec.endpoints_zero is True


def test_matrix_candidate_classification_three_tier():
    """Verify correct three-tier classification of matrix candidates."""
    spec, _ = parse_constraint_expressions(TWISTED_MIRROR_CONSTRAINTS, known_parameters=["grid"])

    # 1. Empty matrix violates min_rows (0 < 2) -> ROBUSTNESS PROBE
    c_empty = TestCase(
        id="c-empty",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": []},
    )
    cls_empty, reason_empty = classify_candidate(c_empty, spec)
    assert cls_empty == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "minimum" in reason_empty.lower()

    # 2. Single row matrix violates min_rows (1 < 2) -> ROBUSTNESS PROBE
    c_single_row = TestCase(
        id="c-row",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 1, 0]]},
    )
    cls_row, reason_row = classify_candidate(c_single_row, spec)
    assert cls_row == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "minimum rows" in reason_row.lower()

    # 3. Single column matrix violates min_cols (1 < 2) -> ROBUSTNESS PROBE
    c_single_col = TestCase(
        id="c-col",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0], [0]]},
    )
    cls_col, reason_col = classify_candidate(c_single_col, spec)
    assert cls_col == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "minimum columns" in reason_col.lower()

    # 4. Out-of-domain cell value (e.g. 2 outside {0, 1}) -> ROBUSTNESS PROBE
    c_bad_cell = TestCase(
        id="c-cell",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 2], [1, 0]]},
    )
    cls_cell, reason_cell = classify_candidate(c_bad_cell, spec)
    assert cls_cell == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "outside allowed" in reason_cell.lower()

    # 5. Non-zero start endpoint violates grid[0][0] == 0 -> ROBUSTNESS PROBE
    c_bad_start = TestCase(
        id="c-start",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[1, 0], [0, 0]]},
    )
    cls_start, reason_start = classify_candidate(c_bad_start, spec)
    assert cls_start == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "endpoint invariant" in reason_start.lower()

    # 6. Non-zero end endpoint violates grid[m-1][n-1] == 0 -> ROBUSTNESS PROBE
    c_bad_end = TestCase(
        id="c-end",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 0], [0, 1]]},
    )
    cls_end, reason_end = classify_candidate(c_bad_end, spec)
    assert cls_end == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "endpoint invariant" in reason_end.lower()

    # 7. Valid 2x2 matrix satisfying dimensions, cell domain, and endpoints -> VALID
    c_valid = TestCase(
        id="c-valid",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 1], [1, 0]]},
    )
    cls_valid, _ = classify_candidate(c_valid, spec)
    assert cls_valid == CandidateClassification.VALID.value

    # 8. Valid 2x3 rectangular matrix -> VALID
    c_valid_rect = TestCase(
        id="c-valid-rect",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 1, 0], [0, 0, 0]]},
    )
    cls_valid_rect, _ = classify_candidate(c_valid_rect, spec)
    assert cls_valid_rect == CandidateClassification.VALID.value


def test_baseline_mode_matrix_coverage_gap_suppression():
    """Verify that empty and singleton collection gaps are suppressed when min_rows >= 2."""
    spec, _ = parse_constraint_expressions(TWISTED_MIRROR_CONSTRAINTS, known_parameters=["grid"])
    ctx = ProblemContext(
        platform="leetcode",
        problem_id="3665",
        title="Twisted Mirror Path Count",
        parameters=["grid"],
        constraints=TWISTED_MIRROR_CONSTRAINTS,
        constraint_spec=spec,
    )

    result = analyze_edgemind(
        code="class Solution:\n    def countPaths(self, grid: list[list[int]]) -> int:\n        return 0\n",
        filename="solution.py",
        problem_context=ctx.to_dict(),
        test_cases=TWISTED_MIRROR_SAMPLES,
    )

    assert result["status"] == "SUCCESS"
    assert result["analysis_mode"] == "BASELINE_DRIVEN"
    intel = result["test_intelligence"]
    gaps = [g["category"] for g in intel["coverage_gaps"]]

    # Empty and singleton collections MUST NOT be flagged as valid gaps when min_rows >= 2
    assert GapCategory.EMPTY_COLLECTION.value not in gaps
    assert GapCategory.SINGLETON.value not in gaps


def test_context_based_mode_matrix_synthesis_without_samples():
    """Verify context-based Mode B synthesizes compliant matrix candidates and robustness probes without public samples."""
    code = (
        "class Solution:\n"
        "    def countPaths(self, grid: list[list[int]]) -> int:\n"
        "        return 0\n"
    )
    ctx = ProblemContext(
        platform="leetcode",
        problem_id="3665",
        title="Twisted Mirror Path Count",
        constraints=TWISTED_MIRROR_CONSTRAINTS,
    )

    result = analyze_edgemind(
        code=code,
        filename="solution.py",
        problem_context=ctx.to_dict(),
        test_cases=[],  # Zero public examples -> Mode B
    )

    assert result["status"] == "SUCCESS"
    assert result["analysis_mode"] == "CONTEXT_BASED"
    assert result["baseline_available"] is False
    assert len(result["identified_parameters"]) == 1
    assert result["identified_parameters"][0]["structure"] == "matrix_2d"

    candidates = result["test_intelligence"]["generated_candidates"]
    assert len(candidates) > 0

    valid_cands = [c for c in candidates if c.get("classification") == CandidateClassification.VALID.value]
    probe_cands = [c for c in candidates if c.get("classification") == CandidateClassification.ROBUSTNESS_PROBE.value]

    # Compliant valid candidates (2x2 and rectangular) must exist
    assert len(valid_cands) >= 1
    for vc in valid_cands:
        mat = vc["input_data"]["grid"]
        assert len(mat) >= 2
        assert len(mat[0]) >= 2
        assert mat[0][0] == 0
        assert mat[-1][-1] == 0
        assert all(cell in (0, 1) for row in mat for cell in row)

    # Deliberate robustness probes must be distinctly labeled
    assert len(probe_cands) >= 1


def test_end_to_end_twisted_mirror_simulation(client):
    """End-to-end API simulation matching the exact observed prompt conditions for LeetCode 3665."""
    payload = {
        "code": "class Solution:\n    def countPaths(self, grid: list[list[int]]) -> int:\n        return 0\n",
        "filename": "solution.py",
        "problem_context": {
            "platform": "leetcode",
            "problem_id": "3665",
            "title": "Twisted Mirror Path Count",
            "constraints": TWISTED_MIRROR_CONSTRAINTS,
        },
        "test_cases": TWISTED_MIRROR_SAMPLES,
        "max_candidates": 10,
    }

    response = client.post("/api/v1/edgemind/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "SUCCESS"
    assert data["analysis_mode"] == "BASELINE_DRIVEN"
    assert data["baseline_available"] is True
    # Parameters Identified is at least 1 (grid)
    assert len(data["identified_parameters"]) == 1
    assert data["identified_parameters"][0]["name"] == "grid"
    # Constraints status is PARSED and unresolved is empty
    assert data["parsed_constraints"]["status"] == "PARSED"
    assert len(data["parsed_constraints"]["unresolved"]) == 0

    # Ensure no candidate is falsely labeled CONSTRAINT VALIDITY UNKNOWN
    for cand in data["test_intelligence"]["generated_candidates"]:
        assert cand["classification"] in (
            CandidateClassification.VALID.value,
            CandidateClassification.ROBUSTNESS_PROBE.value,
        )


# =============================================================================
# LEETCODE 3665 RAW KATEX CONSTRAINT REGRESSION SUITE (15 TESTS)
# =============================================================================

RAW_LC_3665_KATEX_CONSTRAINTS = [
    r"m == \text{grid.length}",
    r"n == \text{grid}[i].\text{length}",
    r"2 <= m,\ n <= 500",
    r"\text{grid}[i][j] is either 0 or 1",
    r"\text{grid}[0][0] == \text{grid}[m - 1][n - 1] == 0",
]


def test_regression_01_raw_katex_constraint_normalization():
    """Verify raw KaTeX expressions are deterministically normalized."""
    assert normalize_latex(r"\text{grid.length}") == "grid.length"
    assert normalize_latex(r"\text{grid}[i].\text{length}") == "grid[i].length"
    assert normalize_latex(r"\text{grid}[i][j]") == "grid[i][j]"
    assert normalize_latex(r"\text{grid}[0][0]") == "grid[0][0]"
    assert normalize_latex(r"2 <= m,\ n <= 500") == "2 <= m, n <= 500"
    assert normalize_latex(r"2 \le m,\, n \le 500") == "2 <= m, n <= 500"
    assert normalize_latex(r"2 \le m \quad n \le 500") == "2 <= m n <= 500"
    assert normalize_latex(r"\mathbf{nums.length}") == "nums.length"
    assert normalize_latex(r"10^{9}") == "10^9"


def test_regression_02_nested_text_wrappers():
    """Verify nested \text{} and formatting wrappers are safely and completely unwrapped."""
    assert normalize_latex(r"\text{text{grid}}[i].\text{length}") == "grid[i].length"
    assert normalize_latex(r"\text{\text{grid}}[i].\text{length}") == "grid[i].length"
    assert normalize_latex(r"\text{\textbf{grid}}") == "grid"
    assert normalize_latex(r"\text{\text{\mathrm{grid}}}[0][0]") == "grid[0][0]"


def test_regression_03_latex_thin_and_escaped_spaces():
    """Verify LaTeX thin spaces, escaped spaces, and tildes are normalized to standard whitespace."""
    s1 = normalize_latex(r"2 \le m,\, n \le 500")
    assert s1 == "2 <= m, n <= 500"
    s2 = normalize_latex(r"2 <= m,\ n <= 500")
    assert s2 == "2 <= m, n <= 500"
    s3 = normalize_latex(r"2 <= m~n <= 500")
    assert s3 == "2 <= m n <= 500"


def test_regression_04_matrix_row_and_column_parsing_from_raw_katex():
    """Verify min/max rows and columns are correctly parsed from raw KaTeX LeetCode 3665 constraints."""
    spec, unresolved = parse_constraint_expressions(
        RAW_LC_3665_KATEX_CONSTRAINTS, known_parameters=["grid"]
    )
    assert len(unresolved) == 0
    assert spec.min_rows == 2
    assert spec.max_rows == 500
    assert spec.min_cols == 2
    assert spec.max_cols == 500
    assert spec.min_length == 2
    assert spec.max_length == 500


def test_regression_05_allowed_matrix_cell_values_from_raw_katex():
    """Verify discrete cell domain is parsed from raw KaTeX constraint."""
    spec, _ = parse_constraint_expressions(
        RAW_LC_3665_KATEX_CONSTRAINTS, known_parameters=["grid"]
    )
    assert spec.allowed_values == [0, 1]
    assert spec.min_value == 0
    assert spec.max_value == 1


def test_regression_06_endpoint_zero_invariant_from_raw_katex():
    """Verify grid[0][0] == grid[m-1][n-1] == 0 is recognized only when complete relationship is established."""
    spec, _ = parse_constraint_expressions(
        RAW_LC_3665_KATEX_CONSTRAINTS, known_parameters=["grid"]
    )
    assert spec.endpoints_zero is True

    # Incomplete relationship must NOT be recognized
    spec_incomplete, _ = parse_constraint_expressions(
        [r"\text{grid}[0][0] == 0"], known_parameters=["grid"]
    )
    assert spec_incomplete.endpoints_zero is False


def test_regression_07_effective_specification_merging():
    """Verify all matrix-specific constraint fields survive _get_effective_spec merging."""
    ctx = ProblemContext(
        title="3665. Twisted Mirror Path Count",
        parameters=["grid"],
        constraints=RAW_LC_3665_KATEX_CONSTRAINTS,
    )
    evaluator = CoverageGapEvaluator()
    synthesizer = TargetedTestSynthesizer(evaluator=evaluator)
    eff_spec = synthesizer._get_effective_spec(ctx)

    assert eff_spec is not None
    assert eff_spec.min_rows == 2
    assert eff_spec.max_rows == 500
    assert eff_spec.min_cols == 2
    assert eff_spec.max_cols == 500
    assert eff_spec.allowed_values == [0, 1]
    assert eff_spec.endpoints_zero is True


def test_regression_08_empty_matrix_classification_probe():
    """Verify empty matrix candidate is classified as ROBUSTNESS PROBE when min_rows >= 2."""
    spec, _ = parse_constraint_expressions(
        RAW_LC_3665_KATEX_CONSTRAINTS, known_parameters=["grid"]
    )
    tc = TestCase(
        id="c-empty",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": []},
    )
    classification, reason = classify_candidate(tc, spec)
    assert classification == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "0 < 2" in reason or "minimum" in reason.lower()


def test_regression_09_single_row_matrix_classification_probe():
    """Verify single-row matrix candidate is classified as ROBUSTNESS PROBE when min_rows >= 2."""
    spec, _ = parse_constraint_expressions(
        RAW_LC_3665_KATEX_CONSTRAINTS, known_parameters=["grid"]
    )
    tc = TestCase(
        id="c-row",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 1, 0]]},
    )
    classification, reason = classify_candidate(tc, spec)
    assert classification == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "1 < 2" in reason or "minimum rows" in reason.lower()


def test_regression_10_single_column_matrix_classification_probe():
    """Verify single-column matrix candidate is classified as ROBUSTNESS PROBE when min_cols >= 2."""
    spec, _ = parse_constraint_expressions(
        RAW_LC_3665_KATEX_CONSTRAINTS, known_parameters=["grid"]
    )
    tc = TestCase(
        id="c-col",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0], [0]]},
    )
    classification, reason = classify_candidate(tc, spec)
    assert classification == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "minimum columns" in reason.lower()


def test_regression_11_valid_matrix_classification():
    """Verify compliant 2x2 and rectangular matrices are classified as VALID, while violators are PROBEs."""
    spec, unresolved = parse_constraint_expressions(
        RAW_LC_3665_KATEX_CONSTRAINTS, known_parameters=["grid"]
    )
    assert len(unresolved) == 0

    # Valid 2x2 binary matrix with zero endpoints
    tc_valid_2x2 = TestCase(
        id="c-valid-2x2",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 1], [1, 0]]},
    )
    cls_2x2, _ = classify_candidate(tc_valid_2x2, spec, unresolved_constraints=unresolved)
    assert cls_2x2 == CandidateClassification.VALID.value

    # Valid 2x3 rectangular binary matrix with zero endpoints
    tc_valid_2x3 = TestCase(
        id="c-valid-2x3",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 1, 0], [1, 0, 0]]},
    )
    cls_2x3, _ = classify_candidate(tc_valid_2x3, spec, unresolved_constraints=unresolved)
    assert cls_2x3 == CandidateClassification.VALID.value

    # Invalid cell value (2) -> ROBUSTNESS PROBE
    tc_invalid_cell = TestCase(
        id="c-bad-cell",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[0, 2], [1, 0]]},
    )
    cls_cell, _ = classify_candidate(tc_invalid_cell, spec, unresolved_constraints=unresolved)
    assert cls_cell == CandidateClassification.ROBUSTNESS_PROBE.value

    # Invalid non-zero endpoint -> ROBUSTNESS PROBE
    tc_bad_endpoint = TestCase(
        id="c-bad-end",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"grid": [[1, 0], [0, 0]]},
    )
    cls_end, _ = classify_candidate(tc_bad_endpoint, spec, unresolved_constraints=unresolved)
    assert cls_end == CandidateClassification.ROBUSTNESS_PROBE.value


def test_regression_12_mode_a_gap_suppression_with_raw_katex():
    """Verify that in Mode A with raw KaTeX constraints, EMPTY_COLLECTION and SINGLETON gaps are suppressed."""
    result = analyze_edgemind(
        code="class Solution:\n    def countPaths(self, grid: list[list[int]]) -> int:\n        return 0\n",
        filename="solution.py",
        problem_context={
            "platform": "leetcode",
            "problem_id": "3665",
            "title": "Twisted Mirror Path Count",
            "parameters": ["grid"],
            "constraints": RAW_LC_3665_KATEX_CONSTRAINTS,
        },
        test_cases=TWISTED_MIRROR_SAMPLES,
    )

    assert result["status"] == "SUCCESS"
    assert result["analysis_mode"] == "BASELINE_DRIVEN"
    assert result["parsed_constraints"]["status"] == "PARSED"
    assert len(result["parsed_constraints"]["unresolved"]) == 0

    gaps = [g["category"] for g in result["test_intelligence"]["coverage_gaps"]]
    assert GapCategory.EMPTY_COLLECTION.value not in gaps
    assert GapCategory.SINGLETON.value not in gaps


def test_regression_13_mode_b_matrix_generation_with_raw_katex():
    """Verify that in Mode B with raw KaTeX constraints, valid matrices and probes are synthesized."""
    result = analyze_edgemind(
        code="class Solution:\n    def countPaths(self, grid: list[list[int]]) -> int:\n        return 0\n",
        filename="solution.py",
        problem_context={
            "platform": "leetcode",
            "problem_id": "3665",
            "title": "Twisted Mirror Path Count",
            "constraints": RAW_LC_3665_KATEX_CONSTRAINTS,
        },
        test_cases=[],  # Zero public samples -> Mode B
    )

    assert result["status"] == "SUCCESS"
    assert result["analysis_mode"] == "CONTEXT_BASED"
    assert result["parsed_constraints"]["status"] == "PARSED"
    assert len(result["parsed_constraints"]["unresolved"]) == 0

    candidates = result["test_intelligence"]["generated_candidates"]
    assert len(candidates) > 0

    valid_cands = [c for c in candidates if c.get("classification") == CandidateClassification.VALID.value]
    probe_cands = [c for c in candidates if c.get("classification") == CandidateClassification.ROBUSTNESS_PROBE.value]

    assert len(valid_cands) >= 1
    assert len(probe_cands) >= 1

    # Verify that valid candidates satisfy 2x2 minimum and zero endpoints
    for vc in valid_cands:
        mat = vc["input_data"]["grid"]
        assert len(mat) >= 2
        assert len(mat[0]) >= 2
        assert mat[0][0] == 0
        assert mat[-1][-1] == 0
        assert all(cell in (0, 1) for row in mat for cell in row)


def test_regression_14_existing_two_sum_regression():
    """Verify Two Sum semantic validation is fully preserved when parsing constraints with LaTeX normalization."""
    raw_two_sum_constraints = [
        r"2 \le \text{nums.length} \le 10^4",
        r"-10^9 \le \text{nums}[i] \le 10^9",
        r"-10^9 \le \text{target} \le 10^9",
        r"Only one valid answer exists.",
    ]
    spec, unres = parse_constraint_expressions(raw_two_sum_constraints, known_parameters=["nums", "target"])
    assert spec.min_length == 2
    assert spec.max_length == 10000
    assert spec.min_value == -1000000000
    assert spec.max_value == 1000000000

    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=raw_two_sum_constraints,
        constraint_spec=spec,
    )

    # Valid candidate with exactly one pair summing to target
    tc_valid = TestCase(
        id="c-two-sum-valid",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    cls_val, reason_val = classify_candidate(
        tc_valid, spec, has_supplied_constraints=True, context=ctx, unresolved_constraints=unres
    )
    assert cls_val == CandidateClassification.VALID.value
    assert "exactly one valid pair" in reason_val


def test_regression_15_legitimate_literal_numbers_unchanged():
    """Verify that legitimate literal numbers, powers, offsets, and signs are parsed accurately without distortion."""
    assert parse_number_expression("500") == 500
    assert parse_number_expression("0") == 0
    assert parse_number_expression("1") == 1
    assert parse_number_expression("10^9") == 1000000000
    assert parse_number_expression("10^{9}") == 1000000000
    assert parse_number_expression("10^4") == 10000
    assert parse_number_expression("10^{4}") == 10000
    assert parse_number_expression("2^31 - 1") == 2147483647
    assert parse_number_expression("2^{31} - 1") == 2147483647
    assert parse_number_expression("2^31-1") == 2147483647
    assert parse_number_expression("-10^9") == -1000000000
    assert parse_number_expression("-10^{9}") == -1000000000
    assert parse_number_expression("-2^31") == -2147483648
    assert parse_number_expression("-2^{31}") == -2147483648
    assert parse_number_expression("2 * 10^4") == 20000
    assert parse_number_expression(r"2 \times 10^{4}") == 20000


