"""
Tests for EdgeMind Constraint Parser, Relational Duplicate Generation, and Candidate Classification.

Regression tests covering:
3. Constraints with positive and negative bounds.
4. Exponent notation such as 10^4 and 10^9.
5. Minimum array length of two: empty and singleton inputs are not classified as valid.
6. Duplicate candidate generation for supported relational contexts.
7. Candidate classification when constraints are missing or incomplete.
"""

import pytest

from core.test_intelligence.constraint_parser import (
    classify_candidate,
    count_valid_pairs,
    is_two_sum_context,
    parse_constraint_expressions,
    parse_number_expression,
)
from core.test_intelligence.gap_detector import CoverageGap, GapCategory, GapSeverity
from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.synthesizer import TargetedTestSynthesizer


# =============================================================================
# 1. Exponent and Numeric Notation Parsing (Regression Test 4)
# =============================================================================


def test_parse_number_expression_exponents_and_negatives():
    """Verify exponent notation, signs, offsets, and multiplication."""
    # Standard integers & floats
    assert parse_number_expression("0") == 0.0
    assert parse_number_expression("2") == 2.0
    assert parse_number_expression("-5") == -5.0
    assert parse_number_expression("3.14") == 3.14

    # Exponents: 10^4 and 10^9
    assert parse_number_expression("10^4") == 10000.0
    assert parse_number_expression("10^9") == 1000000000.0
    assert parse_number_expression("-10^9") == -1000000000.0
    assert parse_number_expression("+10^5") == 100000.0

    # 32-bit signed limits: 2^31 - 1 and -2^31
    assert parse_number_expression("2^31 - 1") == 2147483647.0
    assert parse_number_expression("-2^31") == -2147483648.0
    assert parse_number_expression("2^31") == 2147483648.0

    # Multiplicative exponent: 2 * 10^4
    assert parse_number_expression("2 * 10^4") == 20000.0
    assert parse_number_expression("5 * 10^4") == 50000.0

    # Unicode minus: −10^9
    assert parse_number_expression("−10^9") == -1000000000.0

    # Malformed strings safely return None
    assert parse_number_expression("not_a_number") is None
    assert parse_number_expression("") is None


def test_parse_number_expression_collapsed_exponents():
    """Verify collapsed exponents from scrapers or flattened DOM parse correctly."""
    assert parse_number_expression("109") == 1000000000
    assert parse_number_expression("-109") == -1000000000
    assert parse_number_expression("104") == 10000
    assert parse_number_expression("105") == 100000
    assert parse_number_expression("231") == 2147483648


def test_parse_collapsed_constraint_expressions_two_sum():
    """Verify raw strings with collapsed exponents (104, -109, 109) resolve to 10000, -1000000000, 1000000000."""
    raw = [
        "2 <= nums.length <= 104",
        "-109 <= nums[i] <= 109",
        "-109 <= target <= 109",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target"])
    assert spec.min_length == 2
    assert spec.max_length == 10000
    assert spec.min_value == -1000000000
    assert spec.max_value == 1000000000
    assert len(unresolved) == 0



# =============================================================================
# 2. Positive and Negative Bounds Parsing (Regression Test 3)
# =============================================================================


def test_parse_constraint_expressions_leetcode_two_sum():
    """Verify parsing of standard LeetCode Two Sum constraints."""
    raw = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
        "Only one valid answer exists.",
    ]

    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target"])

    # Bounds properly mapped
    assert spec.min_length == 2
    assert spec.max_length == 10000
    assert spec.min_value == -1000000000.0
    assert spec.max_value == 1000000000.0

    # Unmapped constraint preserved as unresolved without fabricating
    assert unresolved == ["Only one valid answer exists."]
    assert spec.raw_constraints == raw


def test_parse_constraint_expressions_single_inequalities_and_strings():
    """Verify single inequalities and character sets."""
    raw = [
        "nums.length >= 2",
        "nums.length <= 5000",
        "target >= -1000",
        "target <= 1000",
        "s consists of only lowercase English letters.",
        "Array is 0-indexed.",
    ]

    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target", "s"])

    assert spec.min_length == 2
    assert spec.max_length == 5000
    assert spec.min_value == -1000.0
    assert spec.max_value == 1000.0
    assert spec.allowed_characters == "a-z"
    assert unresolved == ["Array is 0-indexed."]


# =============================================================================
# 3. Minimum Array Length of Two (Regression Test 5)
# =============================================================================


def test_min_length_two_empty_and_singleton_classified_as_robustness_probe():
    """Empty and singleton inputs violate min_length=2 and are classified as ROBUSTNESS PROBE, not VALID."""
    spec = ConstraintSpec(
        min_length=2,
        max_length=10000,
        min_value=-1000000000,
        max_value=1000000000,
    )

    tc_empty = TestCase(
        id="probe-empty",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [], "target": 9},
        target_gap=GapCategory.EMPTY_COLLECTION,
    )
    class_empty, reason_empty = classify_candidate(tc_empty, spec)
    assert class_empty == CandidateClassification.ROBUSTNESS_PROBE.value
    assert class_empty != CandidateClassification.VALID.value
    assert "minimum length" in reason_empty.lower()

    tc_singleton = TestCase(
        id="probe-singleton",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [5], "target": 9},
        target_gap=GapCategory.SINGLETON,
    )
    class_single, reason_single = classify_candidate(tc_singleton, spec)
    assert class_single == CandidateClassification.ROBUSTNESS_PROBE.value
    assert class_single != CandidateClassification.VALID.value
    assert "minimum length" in reason_single.lower()

    # In contrast, an input satisfying min_length=2 is classified VALID
    tc_valid = TestCase(
        id="cand-valid",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [2, 7], "target": 9},
    )
    class_valid, _ = classify_candidate(tc_valid, spec)
    assert class_valid == CandidateClassification.VALID.value


# =============================================================================
# 4. Relational Duplicate Generation (Regression Test 6)
# =============================================================================


def test_duplicate_candidate_generation_relational_two_sum():
    """Duplicate candidate generation preserves target relationship for Two Sum producing [3, 3] and target 6."""
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=[
            "2 <= nums.length <= 10^4",
            "-10^9 <= nums[i] <= 10^9",
            "-10^9 <= target <= 10^9",
        ],
    )
    gap = CoverageGap(
        category=GapCategory.DUPLICATE_ELEMENTS,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Untested duplicates in nums",
    )

    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap])

    # Find the generated duplicate candidate
    dup_cands = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS]
    assert len(dup_cands) >= 1
    target_cand = dup_cands[0]

    # Verify relational consistency: nums=[3, 3] and target=6
    assert target_cand.input_data["nums"] == [3, 3]
    assert target_cand.input_data["target"] == 6
    assert target_cand.input_data["nums"][0] + target_cand.input_data["nums"][1] == target_cand.input_data["target"]

    # Verify classification is VALID (satisfies length and bounds)
    spec, _ = parse_constraint_expressions(ctx.constraints, known_parameters=ctx.parameters)
    classification, _ = classify_candidate(target_cand, spec)
    assert classification == CandidateClassification.VALID.value


# =============================================================================
# 5. Missing or Incomplete Constraints Classification (Regression Test 7)
# =============================================================================


def test_candidate_classification_missing_or_incomplete_constraints():
    """When constraints are missing or incomplete, candidates are classified as CONSTRAINT VALIDITY UNKNOWN."""
    tc = TestCase(
        id="cand-1",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [1, 2, 3]},
    )

    # 1. spec is None
    class_none, reason_none = classify_candidate(tc, None, has_supplied_constraints=False)
    assert class_none == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value
    assert "no verified constraint" in reason_none.lower()

    # 2. spec has no bounds defined
    empty_spec = ConstraintSpec()
    class_empty, reason_empty = classify_candidate(tc, empty_spec, has_supplied_constraints=False)
    assert class_empty == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value

    # 3. spec has only allowed_characters (irrelevant to integer array)
    char_spec = ConstraintSpec(allowed_characters="a-z")
    class_unrelated, _ = classify_candidate(tc, char_spec, has_supplied_constraints=True)
    assert class_unrelated == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value


def test_candidate_value_out_of_bounds_classified_as_robustness_probe():
    """Numeric values exceeding bounds are classified as ROBUSTNESS PROBE."""
    spec = ConstraintSpec(min_value=0, max_value=100)

    # Negative value violates min_value=0
    tc_neg = TestCase(
        id="cand-neg",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"val": -5},
    )
    class_neg, reason_neg = classify_candidate(tc_neg, spec)
    assert class_neg == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "-5 < 0" in reason_neg

    # Large value violates max_value=100
    tc_large = TestCase(
        id="cand-large",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [5, 105]},
    )
    class_large, reason_large = classify_candidate(tc_large, spec)
    assert class_large == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "above maximum value constraint" in reason_large


# =============================================================================
# 6. Issue 1 & Issue 2 Regression Tests: Exponents, Distinct Indices & Two Sum Invariants
# =============================================================================


def test_issue1_exponential_expressions_and_inequalities():
    """Verify parsing of 10^9, -10^9, 10^4, 2^31 - 1, -2^31, 2 * 10^4, and unicode superscripts."""
    assert parse_number_expression("10^9") == 1000000000
    assert parse_number_expression("-10^9") == -1000000000
    assert parse_number_expression("10^4") == 10000
    assert parse_number_expression("2^31 - 1") == 2147483647
    assert parse_number_expression("-2^31") == -2147483648
    assert parse_number_expression("2 * 10^4") == 20000
    assert parse_number_expression("5 * 10^4") == 50000
    assert parse_number_expression("10⁹") == 1000000000
    assert parse_number_expression("-10⁹") == -1000000000
    assert parse_number_expression("2³¹ - 1") == 2147483647
    assert parse_number_expression("-2³¹") == -2147483648

    # Test full constraints parsing with spaces and exponential bounds
    raw = [
        "2 <= nums.length <= 2 * 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-2^31 <= target <= 2^31 - 1",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target"])
    assert spec.min_length == 2
    assert spec.max_length == 20000
    assert spec.min_value == -1000000000
    assert spec.max_value == 1000000000
    assert unresolved == []


def test_issue2_count_valid_pairs_distinct_indices_semantics():
    """Verify distinct-index semantics: nums[i] + nums[j] == target with i < j."""
    # Distinct pair
    assert count_valid_pairs([2, 7, 11, 15], 9) == 1
    # Multiple distinct pairs: 1+3=4 (indices 0,2 and 0,3)
    assert count_valid_pairs([1, 2, 3, 3], 4) == 2
    # All identical: [1, 1, 1] target 2 has 3 pairs: (0,1), (0,2), (1,2)
    assert count_valid_pairs([1, 1, 1], 2) == 3
    # Same element cannot be used twice: [3] target 6 has 0 pairs
    assert count_valid_pairs([3], 6) == 0
    # [3, 4, 5] target 6 has 0 pairs because 3+3 requires using index 0 twice
    assert count_valid_pairs([3, 4, 5], 6) == 0
    # Duplicate element [3, 3] target 6 has 1 pair: (0, 1)
    assert count_valid_pairs([3, 3], 6) == 1
    # Negative and zero target pairs
    assert count_valid_pairs([-5, 5], 0) == 1
    assert count_valid_pairs([-7, 2, 10], -5) == 1
    assert count_valid_pairs([-10, -5], -15) == 1


def test_issue2_two_sum_semantic_classification_unique_pair():
    """Verify that candidate inputs in Two Sum context require exactly one pair to be VALID."""
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=[
            "2 <= nums.length <= 10^4",
            "-10^9 <= nums[i] <= 10^9",
            "-10^9 <= target <= 10^9",
        ],
    )
    spec, _ = parse_constraint_expressions(ctx.constraints, known_parameters=ctx.parameters)

    # 1. Valid candidate with exactly one pair
    tc_valid = TestCase(
        id="cand-valid",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    cls_valid, reason_valid = classify_candidate(tc_valid, spec, context=ctx)
    assert cls_valid == CandidateClassification.VALID.value
    assert "one valid pair" in reason_valid.lower()

    # 2. Defect 1 from live run: {"nums": [2, 2], "target": 9} -> 0 pairs -> UNKNOWN
    tc_no_pair1 = TestCase(
        id="cand-no-pair1",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [2, 2], "target": 9},
    )
    cls_no1, reason_no1 = classify_candidate(tc_no_pair1, spec, context=ctx)
    assert cls_no1 == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value
    assert "no pair" in reason_no1.lower() or "0 pairs" in reason_no1.lower()

    # 3. Defect 2 from live run: {"nums": [2, 7, 11, 15], "target": 0} -> 0 pairs -> UNKNOWN
    tc_no_pair2 = TestCase(
        id="cand-no-pair2",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [2, 7, 11, 15], "target": 0},
    )
    cls_no2, reason_no2 = classify_candidate(tc_no_pair2, spec, context=ctx)
    assert cls_no2 == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value
    assert "no pair" in reason_no2.lower() or "0 pairs" in reason_no2.lower()

    # 4. Violates unique-pair condition: multiple pairs (e.g. 3 pairs) -> UNKNOWN
    tc_multi = TestCase(
        id="cand-multi",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [1, 1, 1], "target": 2},
    )
    cls_multi, reason_multi = classify_candidate(tc_multi, spec, context=ctx)
    assert cls_multi == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value
    assert "3 valid pairs" in reason_multi or "instead of exactly one" in reason_multi


def test_issue2_unknown_semantics_not_inferred_solely_from_parameter_names():
    """Verify that Two Sum semantics are NOT inferred solely from parameter names like nums and target."""
    # Binary Search also has parameters nums and target, but does NOT require pairs summing to target!
    ctx_search = ProblemContext(
        title="Binary Search",
        parameters=["nums", "target"],
        constraints=[
            "1 <= nums.length <= 10^4",
            "-10^4 < nums[i], target < 10^4",
        ],
    )
    spec_search, _ = parse_constraint_expressions(
        ["1 <= nums.length <= 10^4", "-10000 <= nums[i] <= 10000"],
        known_parameters=["nums", "target"]
    )

    tc_search = TestCase(
        id="cand-search",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [1, 3, 5, 7], "target": 4},  # target 4 is not in nums and no pairs sum to 4
    )
    # Does not enforce pair sum condition because context is not Two Sum
    cls_search, _ = classify_candidate(tc_search, spec_search, context=ctx_search)
    assert cls_search == CandidateClassification.VALID.value

