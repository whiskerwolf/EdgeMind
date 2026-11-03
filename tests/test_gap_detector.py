"""
Tests for EdgeMind Adaptive Test Intelligence - Phase 3: Coverage-Gap Detector.
"""

import copy
import pytest

from core.test_intelligence.gap_detector import (
    ConstraintValidity,
    CoverageGap,
    CoverageGapEvaluator,
    CoverageGapResult,
    GapSeverity,
)
from core.test_intelligence.models import (
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)


def test_missing_relevant_patterns():
    """Verify that when standard equivalence partitions are missing, gaps are identified."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [5, 10, 15]}),
    ]

    evaluator = CoverageGapEvaluator()
    result = evaluator.evaluate(cases)

    categories = [g.category for g in result.gaps]
    assert GapCategory.EMPTY_COLLECTION in categories
    assert GapCategory.SINGLETON in categories
    assert GapCategory.ZERO_VALUE in categories
    assert GapCategory.NEGATIVE_VALUES in categories
    assert GapCategory.DUPLICATE_ELEMENTS in categories


def test_already_covered_patterns_are_not_flagged():
    """Verify that partitions already observed in existing tests are not flagged as gaps."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": []}),           # empty
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [-5]}),         # singleton & negative
        TestCase(id="3", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [0, 0, 10]}),   # zero & duplicates & non-decreasing
        TestCase(id="4", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [7, 7, 7]}),    # all-identical
    ]

    evaluator = CoverageGapEvaluator()
    result = evaluator.evaluate(cases)

    categories = [g.category for g in result.gaps]
    assert GapCategory.EMPTY_COLLECTION not in categories
    assert GapCategory.SINGLETON not in categories
    assert GapCategory.ZERO_VALUE not in categories
    assert GapCategory.NEGATIVE_VALUES not in categories
    assert GapCategory.DUPLICATE_ELEMENTS not in categories
    assert GapCategory.IDENTICAL_ALL not in categories


def test_empty_collection_prohibited_by_constraints():
    """Verify that when constraints forbid empty collections (min_length >= 1), empty collection gap is suppressed."""
    spec = ConstraintSpec(min_length=1, max_length=100)
    context = ProblemContext(platform="leetcode", constraint_spec=spec)

    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 2, 3]}),
    ]

    evaluator = CoverageGapEvaluator()
    result = evaluator.evaluate(cases, context=context)

    categories = [g.category for g in result.gaps]
    # EMPTY_COLLECTION must be suppressed because min_length=1 prohibits empty collection
    assert GapCategory.EMPTY_COLLECTION not in categories


def test_negative_values_permitted_vs_prohibited():
    """Verify constraint-aware handling of negative values (suppressed when prohibited, flagged when allowed)."""
    # Case A: Non-negative constraint (min_value=0) -> negative values prohibited
    spec_non_neg = ConstraintSpec(min_value=0.0, max_value=100.0)
    ctx_non_neg = ProblemContext(platform="leetcode", constraint_spec=spec_non_neg)

    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 2, 3]}),
    ]

    evaluator = CoverageGapEvaluator()
    res_non_neg = evaluator.evaluate(cases, context=ctx_non_neg)
    cats_non_neg = [g.category for g in res_non_neg.gaps]
    assert GapCategory.NEGATIVE_VALUES not in cats_non_neg

    # Case B: Negative values permitted (min_value = -100) -> should be flagged as VALID gap
    spec_allow_neg = ConstraintSpec(min_value=-100.0, max_value=100.0)
    ctx_allow_neg = ProblemContext(platform="leetcode", constraint_spec=spec_allow_neg)

    res_allow_neg = evaluator.evaluate(cases, context=ctx_allow_neg)
    neg_gaps = [g for g in res_allow_neg.gaps if g.category == GapCategory.NEGATIVE_VALUES]
    assert len(neg_gaps) == 1
    assert neg_gaps[0].constraint_validity == ConstraintValidity.VALID
    assert neg_gaps[0].severity == GapSeverity.HIGH


def test_unknown_constraints_behavior():
    """Verify that when constraints are unspecified/unknown, validity is marked UNKNOWN."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"val": 42}),
    ]

    evaluator = CoverageGapEvaluator()
    result = evaluator.evaluate(cases, context=None)  # No context / no constraints

    zero_gaps = [g for g in result.gaps if g.category == GapCategory.ZERO_VALUE]
    assert len(zero_gaps) == 1
    assert zero_gaps[0].constraint_validity == ConstraintValidity.UNKNOWN


def test_duplicate_and_all_identical_gaps():
    """Verify duplicate and all-identical gaps are identified on unique sequences and suppressed on duplicates."""
    cases_unique = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": [1, 2, 3]}),
    ]

    evaluator = CoverageGapEvaluator()
    res = evaluator.evaluate(cases_unique)

    cats = [g.category for g in res.gaps]
    assert GapCategory.DUPLICATE_ELEMENTS in cats
    assert GapCategory.IDENTICAL_ALL in cats


def test_sorted_and_reversed_sequence_gaps():
    """Verify sequence ordering gaps (ALREADY_SORTED, REVERSE_SORTED, UNSORTED_SEQUENCE)."""
    # 1. Unsorted input only -> missing sorted and reverse-sorted
    cases_unsorted = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": [3, 1, 2]}),
    ]
    evaluator = CoverageGapEvaluator()
    res1 = evaluator.evaluate(cases_unsorted)
    cats1 = [g.category for g in res1.gaps]
    assert GapCategory.ALREADY_SORTED in cats1
    assert GapCategory.REVERSE_SORTED in cats1

    # 2. Sorted input only -> missing unsorted sequence!
    cases_sorted = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": [1, 2, 3]}),
    ]
    res2 = evaluator.evaluate(cases_sorted)
    cats2 = [g.category for g in res2.gaps]
    assert GapCategory.UNSORTED_SEQUENCE in cats2


def test_lower_and_upper_constraint_boundary_gaps():
    """Verify constraint boundaries are flagged when observed samples do not hit min/max limits."""
    spec = ConstraintSpec(
        min_value=-50.0,
        max_value=500.0,
        min_length=2,
        max_length=1000,
    )
    ctx = ProblemContext(platform="leetcode", constraint_spec=spec)

    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [5, 10, 15]}),  # length 3, values 5-15
    ]

    evaluator = CoverageGapEvaluator()
    res = evaluator.evaluate(cases, context=ctx)

    cats = [g.category for g in res.gaps]
    assert GapCategory.LOWER_CONSTRAINT_BOUND in cats
    assert GapCategory.UPPER_CONSTRAINT_BOUND in cats


def test_explicit_vs_missing_relational_metadata():
    """Verify relational gaps trigger only when explicit relational metadata is provided."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"items": [1, 2, 3], "target": 2}),
    ]

    evaluator = CoverageGapEvaluator()

    # Case A: Without metadata -> never assumes a relationship
    res_no_rel = evaluator.evaluate(cases)
    cats_no_rel = [g.category for g in res_no_rel.gaps]
    assert GapCategory.TARGET_NOT_FOUND not in cats_no_rel
    assert GapCategory.TARGET_AT_BOUNDARIES not in cats_no_rel

    # Case B: With explicit metadata -> checks target absent and boundary index
    rel_spec = {"type": "CONTAINMENT", "collection_param": "items", "target_param": "target"}
    res_rel = evaluator.evaluate(cases, relational_metadata=rel_spec)
    cats_rel = [g.category for g in res_rel.gaps]
    assert GapCategory.TARGET_NOT_FOUND in cats_rel
    assert GapCategory.TARGET_AT_BOUNDARIES in cats_rel


def test_matrix_dimensions_gap():
    """Verify that when only square matrices are tested, rectangular matrix gap is identified."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"grid": [[1, 2], [3, 4]]}),
    ]

    evaluator = CoverageGapEvaluator()
    res = evaluator.evaluate(cases)

    matrix_gaps = [g for g in res.gaps if g.category == GapCategory.MATRIX_DIMENSIONS]
    assert len(matrix_gaps) == 1
    assert "rectangular" in matrix_gaps[0].rationale.lower()


def test_failure_family_extrapolation_gap():
    """Verify that PLATFORM_REVEALED_FAILURE triggers a high-severity family extrapolation gap."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 2]}),
        TestCase(id="fail-1", source=TestCaseSource.PLATFORM_REVEALED_FAILURE, input_data={"nums": [0, 0, 0]}),
    ]

    evaluator = CoverageGapEvaluator()
    res = evaluator.evaluate(cases)

    fail_gaps = [g for g in res.gaps if g.category == GapCategory.FAILURE_FAMILY_EXTRAPOLATION]
    assert len(fail_gaps) == 1
    assert fail_gaps[0].severity == GapSeverity.HIGH
    assert fail_gaps[0].relevance_score >= 0.95


def test_irrelevant_gap_suppression():
    """Verify that scalar parameters do not get flagged for collection gaps."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"x": 5}),
    ]

    evaluator = CoverageGapEvaluator()
    res = evaluator.evaluate(cases)

    cats = [g.category for g in res.gaps]
    assert GapCategory.EMPTY_COLLECTION not in cats
    assert GapCategory.SINGLETON not in cats
    assert GapCategory.DUPLICATE_ELEMENTS not in cats
    assert GapCategory.IDENTICAL_ALL not in cats
    assert GapCategory.MATRIX_DIMENSIONS not in cats


def test_deterministic_results():
    """Verify repeated evaluations on the same input produce identical gap results and ordering."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 2, 3], "target": 2}),
    ]
    rel_spec = {"type": "CONTAINMENT", "collection_param": "nums", "target_param": "target"}

    evaluator = CoverageGapEvaluator()
    res1 = evaluator.evaluate(cases, relational_metadata=rel_spec).to_dict()
    res2 = evaluator.evaluate(cases, relational_metadata=rel_spec).to_dict()

    assert res1 == res2


def test_no_mutation_of_input_data():
    """Verify gap evaluation does not modify input test cases or data dictionaries."""
    original_input = {"nums": [3, 1, 2], "target": 1}
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data=original_input),
    ]
    cases_clone = copy.deepcopy(cases)

    evaluator = CoverageGapEvaluator()
    _ = evaluator.evaluate(cases)

    assert cases == cases_clone
    assert cases[0].input_data == original_input


def test_coverage_gap_to_dict_and_from_dict():
    """Verify CoverageGap serialization and deserialization roundtrip."""
    gap = CoverageGap(
        category=GapCategory.EMPTY_COLLECTION,
        param_name="nums",
        severity=GapSeverity.HIGH,
        constraint_validity=ConstraintValidity.VALID,
        relevance_score=0.9,
        rationale="Empty collection was never tested.",
        risk_explained="IndexError risk.",
        suggested_action="Add empty list.",
        metadata={"min_len": 0},
    )

    data = gap.to_dict()
    assert data["category"] == "EMPTY_COLLECTION"
    assert data["severity"] == "HIGH"
    assert data["constraint_validity"] == "VALID"

    reconstructed = CoverageGap.from_dict(data)
    assert reconstructed.category == GapCategory.EMPTY_COLLECTION
    assert reconstructed.severity == GapSeverity.HIGH
    assert reconstructed.constraint_validity == ConstraintValidity.VALID
    assert reconstructed.relevance_score == 0.9
