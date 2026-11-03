"""
Tests for EdgeMind Targeted Adaptive Test Generator (Phase 4).
"""

import copy
import pytest
from typing import Any, Dict

from core.test_intelligence.gap_detector import (
    ConstraintValidity,
    CoverageGap,
    CoverageGapEvaluator,
    CoverageGapResult,
    GapSeverity,
)
from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.synthesizer import (
    TargetedTestSynthesizer,
    canonical_input_signature,
)
from core.test_intelligence.constraint_parser import parse_constraint_expressions



# =============================================================================
# 1. Canonical Serialization and Deduplication
# =============================================================================


def test_canonical_input_signature_normalization():
    """Verify dictionary keys, float representations, and nested structures serialize identically."""
    d1 = {"b": 2, "a": [1, 2.0]}
    d2 = {"a": [1, 2], "b": 2.0}
    sig1 = canonical_input_signature(d1)
    sig2 = canonical_input_signature(d2)
    assert sig1 == sig2
    assert sig1 == '{"a": [1, 2], "b": 2}'


def test_deduplication_against_existing_tests():
    """Synthesizer must not generate a candidate if an identical input already exists."""
    tc1 = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": []},
    )
    synth = TargetedTestSynthesizer()
    gap = CoverageGap(
        category=GapCategory.EMPTY_COLLECTION,
        param_name="nums",
        severity=GapSeverity.HIGH,
        constraint_validity=ConstraintValidity.VALID,
        rationale="Empty collection untested",
    )
    candidates = synth.synthesize([tc1], gaps=[gap])
    # Empty nums was already present in tc1, so candidate should be deduplicated out
    assert len(candidates) == 0


def test_deduplication_across_candidates():
    """Synthesizer must deduplicate identical candidates produced across rules."""
    tc1 = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    synth = TargetedTestSynthesizer()
    gap1 = CoverageGap(
        category=GapCategory.EMPTY_COLLECTION,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Empty collection gap 1",
    )
    gap2 = CoverageGap(
        category=GapCategory.EMPTY_COLLECTION,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Empty collection gap 2",
    )
    candidates = synth.synthesize([tc1], gaps=[gap1, gap2])
    assert len(candidates) == 1
    assert candidates[0].input_data == {"nums": []}


# =============================================================================
# 2. Empty and Singleton Collection Generators
# =============================================================================


def test_empty_collection_permitted():
    """When min_length == 0, empty collection is generated with VALID validity."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    spec = ConstraintSpec(min_length=0, max_length=100)
    ctx = ProblemContext(title="test", parameters=["nums"], constraint_spec=spec)
    synth = TargetedTestSynthesizer()

    candidates = synth.synthesize([tc], context=ctx)
    empty_cases = [c for c in candidates if c.target_gap == GapCategory.EMPTY_COLLECTION]
    assert len(empty_cases) == 1
    assert empty_cases[0].input_data["nums"] == []
    assert empty_cases[0].source == TestCaseSource.GENERATED_TEST
    assert empty_cases[0].is_boundary is True
    assert empty_cases[0].id == "gen-empty-nums"


def test_empty_collection_prohibited():
    """When min_length > 0, empty collection must NEVER be generated."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    spec = ConstraintSpec(min_length=1, max_length=100)
    ctx = ProblemContext(title="test", parameters=["nums"], constraint_spec=spec)
    synth = TargetedTestSynthesizer()

    candidates = synth.synthesize([tc], context=ctx)
    empty_cases = [c for c in candidates if c.target_gap == GapCategory.EMPTY_COLLECTION]
    assert len(empty_cases) == 0


def test_empty_collection_unknown_constraints():
    """When constraint spec is absent, empty collection validity is synthesized as candidate."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    synth = TargetedTestSynthesizer()

    candidates = synth.synthesize([tc])
    empty_cases = [c for c in candidates if c.target_gap == GapCategory.EMPTY_COLLECTION]
    assert len(empty_cases) == 1
    assert empty_cases[0].id == "gen-empty-nums"


def test_singleton_collection_generation():
    """Singleton generator creates length-1 collection and string."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [10, 20, 30], "word": "hello"},
    )
    gap_list = CoverageGap(
        category=GapCategory.SINGLETON,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Singleton nums",
    )
    gap_str = CoverageGap(
        category=GapCategory.SINGLETON,
        param_name="word",
        severity=GapSeverity.HIGH,
        rationale="Singleton word",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[gap_list, gap_str])

    c_list = [c for c in candidates if c.id == "gen-singleton-nums"][0]
    assert c_list.input_data["nums"] == [10]

    c_str = [c for c in candidates if c.id == "gen-singleton-word"][0]
    assert c_str.input_data["word"] == "h"


def test_singleton_collection_prohibited():
    """Singleton generation is rejected if min_length > 1."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    spec = ConstraintSpec(min_length=2, max_length=10)
    gap = CoverageGap(
        category=GapCategory.SINGLETON,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Singleton nums",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], context=ProblemContext(title="t", constraint_spec=spec), gaps=[gap])
    assert len(candidates) == 0


# =============================================================================
# 3. Zero and Negative Value Generators
# =============================================================================


def test_zero_value_generation():
    """Zero value generator sets scalar to 0 or inserts 0 into numeric sequence."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"k": 5, "arr": [10, 20]},
    )
    gap_scalar = CoverageGap(
        category=GapCategory.ZERO_VALUE,
        param_name="k",
        severity=GapSeverity.HIGH,
        rationale="Zero k",
    )
    gap_seq = CoverageGap(
        category=GapCategory.ZERO_VALUE,
        param_name="arr",
        severity=GapSeverity.HIGH,
        rationale="Zero arr",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[gap_scalar, gap_seq])

    c_k = [c for c in candidates if c.id == "gen-zero-k"][0]
    assert c_k.input_data["k"] == 0

    c_arr = [c for c in candidates if c.id == "gen-zero-arr"][0]
    assert c_arr.input_data["arr"] == [0, 20]


def test_zero_value_prohibited():
    """Zero value is rejected when min_value > 0."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"k": 5},
    )
    spec = ConstraintSpec(min_value=1, max_value=100)
    gap = CoverageGap(
        category=GapCategory.ZERO_VALUE,
        param_name="k",
        severity=GapSeverity.HIGH,
        rationale="Zero k",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], context=ProblemContext(title="t", constraint_spec=spec), gaps=[gap])
    assert len(candidates) == 0


def test_negative_values_permitted():
    """Negative generator produces safe negative value when min_value < 0."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"k": 10},
    )
    spec = ConstraintSpec(min_value=-100, max_value=100)
    gap = CoverageGap(
        category=GapCategory.NEGATIVE_VALUES,
        param_name="k",
        severity=GapSeverity.HIGH,
        rationale="Negative k",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], context=ProblemContext(title="t", constraint_spec=spec), gaps=[gap])

    assert len(candidates) == 1
    assert candidates[0].input_data["k"] < 0
    assert candidates[0].input_data["k"] >= -100
    assert candidates[0].id == "gen-negative-k"


def test_negative_values_prohibited():
    """Negative values are strictly prohibited when min_value >= 0."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"k": 10},
    )
    spec = ConstraintSpec(min_value=0, max_value=100)
    gap = CoverageGap(
        category=GapCategory.NEGATIVE_VALUES,
        param_name="k",
        severity=GapSeverity.HIGH,
        rationale="Negative k",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], context=ProblemContext(title="t", constraint_spec=spec), gaps=[gap])
    assert len(candidates) == 0


# =============================================================================
# 4. Duplicate and All-Identical Generators
# =============================================================================


def test_duplicate_and_identical_generation():
    """Duplicate and all-identical generators construct duplicate elements."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    gap_dup = CoverageGap(
        category=GapCategory.DUPLICATE_ELEMENTS,
        param_name="nums",
        severity=GapSeverity.MEDIUM,
        rationale="Duplicates in nums",
    )
    gap_all = CoverageGap(
        category=GapCategory.IDENTICAL_ALL,
        param_name="nums",
        severity=GapSeverity.MEDIUM,
        rationale="All identical nums",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[gap_dup, gap_all])

    c_dup = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS][0]
    assert c_dup.input_data["nums"] == [1, 1, 3]

    c_all = [c for c in candidates if c.target_gap == GapCategory.IDENTICAL_ALL][0]
    assert len(set(c_all.input_data["nums"])) == 1


# =============================================================================
# 5. Order Variants (Sorted, Reverse, Unsorted)
# =============================================================================


def test_order_variant_generation():
    """Generates already-sorted, reverse-sorted, and unsorted sequence candidates."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [3, 1, 4, 2]},
    )
    gap_sorted = CoverageGap(
        category=GapCategory.ALREADY_SORTED,
        param_name="nums",
        severity=GapSeverity.MEDIUM,
        rationale="Sorted nums",
    )
    gap_rev = CoverageGap(
        category=GapCategory.REVERSE_SORTED,
        param_name="nums",
        severity=GapSeverity.MEDIUM,
        rationale="Reverse sorted nums",
    )
    gap_unsorted = CoverageGap(
        category=GapCategory.UNSORTED_SEQUENCE,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Unsorted nums",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[gap_sorted, gap_rev, gap_unsorted])

    c_s = [c for c in candidates if c.target_gap == GapCategory.ALREADY_SORTED][0]
    assert c_s.input_data["nums"] == [1, 2, 3, 4]

    c_r = [c for c in candidates if c.target_gap == GapCategory.REVERSE_SORTED][0]
    assert c_r.input_data["nums"] == [4, 3, 2, 1]

    c_u = [c for c in candidates if c.target_gap == GapCategory.UNSORTED_SEQUENCE][0]
    assert c_u.input_data["nums"] != [1, 2, 3, 4]
    assert c_u.input_data["nums"] != [4, 3, 2, 1]


# =============================================================================
# 6. Constraint Boundaries (Lower, Upper, String Boundaries)
# =============================================================================


def test_lower_and_upper_constraint_boundaries():
    """Generates exact min/max value and length bounds, with upper length capped at scale."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"val": 50, "arr": [1, 2], "text": "abc"},
    )
    spec = ConstraintSpec(
        min_value=-500,
        max_value=500,
        min_length=1,
        max_length=200000,
    )
    ctx = ProblemContext(title="bounds", parameters=["val", "arr", "text"], constraint_spec=spec)
    synth = TargetedTestSynthesizer()

    candidates = synth.synthesize([tc], context=ctx)

    # Check numeric min/max
    min_val_c = [c for c in candidates if c.id == "gen-bound-min-val-val"][0]
    assert min_val_c.input_data["val"] == -500

    max_val_c = [c for c in candidates if c.id == "gen-bound-max-val-val"][0]
    assert max_val_c.input_data["val"] == 500

    # Check list min/max length
    min_len_arr = [c for c in candidates if c.id == "gen-bound-min-len-arr"][0]
    assert len(min_len_arr.input_data["arr"]) == 1

    max_len_arr = [c for c in candidates if c.id == "gen-bound-max-len-arr"][0]
    assert len(max_len_arr.input_data["arr"]) == TargetedTestSynthesizer.MAX_ARRAY_SCALE
    assert max_len_arr.is_performance is True

    # Check string min/max length
    min_len_str = [c for c in candidates if c.id == "gen-bound-min-len-text"][0]
    assert len(min_len_str.input_data["text"]) == 1

    max_len_str = [c for c in candidates if c.id == "gen-bound-max-len-text"][0]
    assert len(max_len_str.input_data["text"]) == TargetedTestSynthesizer.MAX_ARRAY_SCALE


# =============================================================================
# 7. Relational Search Targets and Boundaries
# =============================================================================


def test_relational_target_not_found_and_boundaries():
    """Generates target-absent, target-at-first-index, and target-at-last-index with metadata."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [10, 20, 30, 40], "target": 20},
    )
    rel_meta = {"collection_param": "nums", "target_param": "target"}
    synth = TargetedTestSynthesizer()

    candidates = synth.synthesize([tc], relational_metadata=rel_meta)

    c_absent = [c for c in candidates if c.id == "gen-rel-absent-target"][0]
    assert c_absent.input_data["target"] not in c_absent.input_data["nums"]

    c_first = [c for c in candidates if c.id == "gen-rel-first-idx-target"][0]
    assert c_first.input_data["target"] == 10
    assert c_first.is_boundary is True

    c_last = [c for c in candidates if c.id == "gen-rel-last-idx-target"][0]
    assert c_last.input_data["target"] == 40
    assert c_last.is_boundary is True


def test_missing_relational_metadata_produces_no_relational_cases():
    """When relational metadata is absent, relational cases are not generated."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [10, 20, 30, 40], "target": 20},
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], relational_metadata=None)

    rel_cases = [
        c for c in candidates
        if c.target_gap in (GapCategory.TARGET_NOT_FOUND, GapCategory.TARGET_AT_BOUNDARIES)
    ]
    assert len(rel_cases) == 0


# =============================================================================
# 8. Matrix Dimensions Generator
# =============================================================================


def test_matrix_dimensions_generation():
    """When square matrix was tested, rectangular matrix is synthesized."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"grid": [[1, 2], [3, 4]]},
    )
    gap = CoverageGap(
        category=GapCategory.MATRIX_DIMENSIONS,
        param_name="grid",
        severity=GapSeverity.MEDIUM,
        rationale="Rectangular matrix gap",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[gap])

    assert len(candidates) == 1
    matrix = candidates[0].input_data["grid"]
    rows = len(matrix)
    cols = len(matrix[0])
    assert rows != cols  # Non-square rectangular
    assert rows == 2 and cols == 3


# =============================================================================
# 9. Failure Family Extrapolation
# =============================================================================


def test_failure_family_extrapolation():
    """Derives variations from PLATFORM_REVEALED_FAILURE test cases."""
    tc_sample = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    tc_fail = TestCase(
        id="fail-1",
        source=TestCaseSource.PLATFORM_REVEALED_FAILURE,
        input_data={"nums": [10, 20, 30, 40, 50]},
    )
    gap = CoverageGap(
        category=GapCategory.FAILURE_FAMILY_EXTRAPOLATION,
        severity=GapSeverity.HIGH,
        rationale="Failure family gap",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc_sample, tc_fail], gaps=[gap])

    assert len(candidates) >= 1
    c_fail = candidates[0]
    assert c_fail.source == TestCaseSource.GENERATED_TEST
    assert c_fail.target_gap == GapCategory.FAILURE_FAMILY_EXTRAPOLATION
    assert len(c_fail.input_data["nums"]) == 4  # Truncated variation of failed 5-element sequence


# =============================================================================
# 10. Test Case Integrity and Safety Invariants
# =============================================================================


def test_test_case_integrity_invariants():
    """All synthesized cases must have GENERATED_TEST source, expected_output=None, verified=False, no execution."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc])

    assert len(candidates) > 0
    for c in candidates:
        assert c.source == TestCaseSource.GENERATED_TEST
        assert c.expected_output is None
        assert c.is_expected_output_verified is False
        assert c.id.startswith("gen-")
        assert c.label is not None and len(c.label) > 0
        assert c.rationale is not None and len(c.rationale) > 0
        assert c.target_gap is not None


def test_prohibited_gap_safety():
    """Synthesizer rejects gaps with PROHIBITED constraint validity."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    prohibited_gap = CoverageGap(
        category=GapCategory.EMPTY_COLLECTION,
        param_name="nums",
        severity=GapSeverity.HIGH,
        constraint_validity=ConstraintValidity.PROHIBITED,
        rationale="Prohibited empty gap",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[prohibited_gap])
    assert len(candidates) == 0


def test_input_immutability():
    """Synthesizer must not mutate existing TestCase input_data or input structures."""
    original_input = {"nums": [1, 2, 3], "val": 10}
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data=copy.deepcopy(original_input),
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc])

    # Assert source test case was untouched
    assert tc.input_data == original_input

    # Assert mutating candidate does not affect source test case
    candidates[0].input_data["nums"].append(999)
    assert tc.input_data["nums"] == [1, 2, 3]


def test_max_candidates_ceiling_and_deterministic_order():
    """Synthesizer respects max_candidates limit and produces identical output on repeated runs."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3], "val": 10},
    )
    synth = TargetedTestSynthesizer(default_max_candidates=3)

    cands_run1 = synth.synthesize([tc], max_candidates=4)
    assert len(cands_run1) == 4

    cands_run2 = synth.synthesize([tc], max_candidates=4)
    assert [c.id for c in cands_run1] == [c.id for c in cands_run2]
    assert [c.input_data for c in cands_run1] == [c.input_data for c in cands_run2]


# =============================================================================
# 11. Adversarial Robustness & Safety Verification
# =============================================================================


def test_adversarial_boolean_elements_not_corrupted_into_ints():
    """Booleans (subclass of int in Python) must never be corrupted into 0 or -1."""
    tc = TestCase(
        id="sample-bool",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"flags": [True, False], "active": True},
    )
    gap_zero = CoverageGap(
        category=GapCategory.ZERO_VALUE,
        param_name="flags",
        severity=GapSeverity.HIGH,
        rationale="Zero gap",
    )
    gap_neg = CoverageGap(
        category=GapCategory.NEGATIVE_VALUES,
        param_name="flags",
        severity=GapSeverity.HIGH,
        rationale="Negative gap",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[gap_zero, gap_neg])

    # No zero or negative numeric cases should have been synthesized for boolean data
    for c in candidates:
        for val in c.input_data.get("flags", []):
            assert isinstance(val, bool)
            assert not isinstance(val, int) or isinstance(val, bool)


def test_adversarial_string_relational_target_type_safe():
    """String relational searches must use string absent targets, never int sentinel."""
    tc = TestCase(
        id="sample-str-rel",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"words": ["apple", "banana"], "target": "apple"},
    )
    rel_meta = {"collection_param": "words", "target_param": "target"}
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], relational_metadata=rel_meta)

    c_absent = [c for c in candidates if c.id == "gen-rel-absent-target"][0]
    target_val = c_absent.input_data["target"]
    assert isinstance(target_val, str)
    assert target_val not in c_absent.input_data["words"]
    assert target_val != -999999


def test_adversarial_matrix_dimension_preserves_cell_type():
    """String and boolean matrices must preserve their element types in rectangular synthesis."""
    # 1. String matrix
    tc_str = TestCase(
        id="sample-str-mat",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"grid": [["a", "b"], ["c", "d"]]},
    )
    gap_mat = CoverageGap(
        category=GapCategory.MATRIX_DIMENSIONS,
        param_name="grid",
        severity=GapSeverity.MEDIUM,
        rationale="Matrix dimensions gap",
    )
    synth = TargetedTestSynthesizer()
    cands_str = synth.synthesize([tc_str], gaps=[gap_mat])
    assert len(cands_str) == 1
    grid_str = cands_str[0].input_data["grid"]
    assert len(grid_str) == 2 and len(grid_str[0]) == 3
    for row in grid_str:
        for cell in row:
            assert isinstance(cell, str)

    # 2. Boolean matrix
    tc_bool = TestCase(
        id="sample-bool-mat",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"grid": [[True, False], [False, True]]},
    )
    cands_bool = synth.synthesize([tc_bool], gaps=[gap_mat])
    assert len(cands_bool) == 1
    grid_bool = cands_bool[0].input_data["grid"]
    assert len(grid_bool) == 2 and len(grid_bool[0]) == 3
    for row in grid_bool:
        for cell in row:
            assert isinstance(cell, bool)


def test_adversarial_array_scale_respects_high_min_length():
    """When min_length > MAX_ARRAY_SCALE, generated length must be >= min_length."""
    tc = TestCase(
        id="sample-scale",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    spec = ConstraintSpec(min_length=200, max_length=500)
    ctx = ProblemContext(title="high_min_len", parameters=["nums"], constraint_spec=spec)
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], context=ctx)

    max_len_c = [c for c in candidates if c.id == "gen-bound-max-len-nums"][0]
    gen_len = len(max_len_c.input_data["nums"])
    assert gen_len >= 200
    assert gen_len <= 500


def test_adversarial_fallback_context_text_constraints():
    """Generators parse raw text constraints from ProblemContext when ConstraintSpec is missing."""
    tc = TestCase(
        id="sample-text-ctx",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    # Context constraints state length >= 1 and values >= 0
    ctx = ProblemContext(
        title="raw_constraints",
        parameters=["nums"],
        constraints=["1 <= nums.length <= 100", "0 <= nums[i] <= 1000"],
    )
    gap_empty = CoverageGap(
        category=GapCategory.EMPTY_COLLECTION,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Empty nums",
    )
    gap_neg = CoverageGap(
        category=GapCategory.NEGATIVE_VALUES,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Negative nums",
    )
    synth = TargetedTestSynthesizer()
    # Both empty and negative should be rejected due to parsed fallback constraints
    candidates = synth.synthesize([tc], context=ctx, gaps=[gap_empty, gap_neg])
    assert len(candidates) == 0


def test_adversarial_contradictory_constraints_produce_no_candidates():
    """Contradictory constraints (e.g. min > max) safely generate zero candidates without crashing."""
    tc = TestCase(
        id="sample-contra",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3], "val": 10},
    )
    spec_val = ConstraintSpec(min_value=100, max_value=10)
    spec_len = ConstraintSpec(min_length=50, max_length=5)

    synth = TargetedTestSynthesizer()
    cands_val = synth.synthesize([tc], context=ProblemContext(title="c1", constraint_spec=spec_val))
    assert not any(c.id.startswith("gen-bound-min-val") for c in cands_val)

    cands_len = synth.synthesize([tc], context=ProblemContext(title="c2", constraint_spec=spec_len))
    assert not any(c.id.startswith("gen-bound-min-len") for c in cands_len)


def test_adversarial_canonical_signature_distinguishes_types():
    """Canonical signatures must distinguish lists, tuples, and sets without collisions."""
    sig_list = canonical_input_signature({"a": [1, 2]})
    sig_tuple = canonical_input_signature({"a": (1, 2)})
    sig_set = canonical_input_signature({"a": {1, 2}})

    assert sig_list != sig_tuple
    assert sig_list != sig_set
    assert sig_tuple != sig_set


def test_adversarial_tuple_sequence_preservation():
    """Tuples in inputs are preserved as tuples across candidate generators."""
    tc = TestCase(
        id="sample-tup",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"coords": (30, 10, 20)},
    )
    gap_singleton = CoverageGap(
        category=GapCategory.SINGLETON,
        param_name="coords",
        severity=GapSeverity.HIGH,
        rationale="Singleton coords",
    )
    gap_sorted = CoverageGap(
        category=GapCategory.ALREADY_SORTED,
        param_name="coords",
        severity=GapSeverity.MEDIUM,
        rationale="Sorted coords",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc], gaps=[gap_singleton, gap_sorted])

    c_sing = [c for c in candidates if c.target_gap == GapCategory.SINGLETON][0]
    assert isinstance(c_sing.input_data["coords"], tuple)
    assert len(c_sing.input_data["coords"]) == 1

    c_sort = [c for c in candidates if c.target_gap == GapCategory.ALREADY_SORTED][0]
    assert isinstance(c_sort.input_data["coords"], tuple)
    assert c_sort.input_data["coords"] == (10, 20, 30)


def test_adversarial_malformed_relational_metadata_handled_gracefully():
    """Non-dict or invalid relational metadata must safely skip relational generation without throwing."""
    tc = TestCase(
        id="sample-rel-bad",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3], "target": 2},
    )
    synth = TargetedTestSynthesizer()

    # Pass non-dict
    c1 = synth.synthesize([tc], relational_metadata="invalid_str")  # type: ignore
    assert not any(c.target_gap in (GapCategory.TARGET_NOT_FOUND, GapCategory.TARGET_AT_BOUNDARIES) for c in c1)

    # Pass dict with invalid types or missing keys
    c2 = synth.synthesize([tc], relational_metadata={"collection_param": 123, "target_param": None})
    assert not any(c.target_gap in (GapCategory.TARGET_NOT_FOUND, GapCategory.TARGET_AT_BOUNDARIES) for c in c2)


def test_adversarial_no_inference_from_param_names_alone():
    """Never infer relational targets from parameter names like 'target' without explicit metadata."""
    tc = TestCase(
        id="sample-no-infer",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"target": 5, "nums": [1, 2, 3]},
    )
    synth = TargetedTestSynthesizer()
    # relational_metadata is None
    candidates = synth.synthesize([tc], relational_metadata=None)
    assert not any(c.target_gap in (GapCategory.TARGET_NOT_FOUND, GapCategory.TARGET_AT_BOUNDARIES) for c in candidates)


def test_adversarial_unsupported_types_handled_safely():
    """Unsupported custom object types in input_data are safely skipped or preserved without crashing."""
    class CustomArbitraryType:
        def __init__(self, val):
            self.val = val

    tc = TestCase(
        id="sample-custom",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"obj": CustomArbitraryType(42), "nums": [1, 2, 3]},
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc])
    # Should not crash, and should synthesize normal cases for nums while preserving obj
    assert len(candidates) > 0
    for c in candidates:
        assert "obj" in c.input_data
        assert isinstance(c.input_data["obj"], CustomArbitraryType)


def test_adversarial_deep_immutability_and_oracle_integrity():
    """Verify deep immutability, GENERATED_TEST provenance, and unverified expected_output."""
    original_input = {
        "nested": {"arr": [1, 2, 3], "meta": {"k": "v"}},
        "val": 10,
    }
    tc = TestCase(
        id="sample-deep",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data=copy.deepcopy(original_input),
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([tc])

    for c in candidates:
        assert c.source == TestCaseSource.GENERATED_TEST
        assert c.expected_output is None
        assert c.is_expected_output_verified is False
        assert "pass" not in c.label.lower()
        assert "fail" not in c.label.lower()

    # Mutate candidate nested input that preserved nested structure
    c_nested = [c for c in candidates if "arr" in c.input_data.get("nested", {})][0]
    c_nested.input_data["nested"]["arr"].append(999)
    c_nested.input_data["nested"]["meta"]["k"] = "modified"

    # Original input must remain pristine
    assert tc.input_data["nested"]["arr"] == [1, 2, 3]
    assert tc.input_data["nested"]["meta"]["k"] == "v"


# =============================================================================
# 12. Regression Tests: Relational Duplicate Generation and Semantic Invariants
# =============================================================================


def test_duplicate_candidate_generation_two_sum_relational():
    """Two Sum duplicate pair generation: when additive semantics are supported by problem context,
    synthesizes duplicate pair [3, 3] and target 6 maintaining additive invariant."""
    base_tc = TestCase(
        id="sample-two-sum",
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

    dup_cands = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS]
    assert len(dup_cands) >= 1
    cand = dup_cands[0]
    assert cand.source == TestCaseSource.GENERATED_TEST
    assert cand.expected_output is None
    assert cand.is_expected_output_verified is False
    assert cand.input_data["nums"] == [3, 3]
    assert cand.input_data["target"] == 6
    assert cand.input_data["nums"][0] + cand.input_data["nums"][1] == cand.input_data["target"]


def test_duplicate_candidate_generation_two_sum_relational_metadata():
    """When relational_metadata explicitly specifies type='PAIR_SUM', additive semantics are used."""
    base_tc = TestCase(
        id="sample-two-sum-meta",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    rel_meta = {
        "type": "PAIR_SUM",
        "collection_param": "nums",
        "target_param": "target",
    }
    gap = CoverageGap(
        category=GapCategory.DUPLICATE_ELEMENTS,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Untested duplicates in nums",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], gaps=[gap], relational_metadata=rel_meta)

    dup_cands = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS]
    assert len(dup_cands) >= 1
    cand = dup_cands[0]
    assert cand.source == TestCaseSource.GENERATED_TEST
    assert cand.input_data["nums"] == [3, 3]
    assert cand.input_data["target"] == 6


def test_duplicate_candidate_generation_binary_search_preserves_target():
    """Binary Search duplicate generation: does not assume additive relationship or modify target."""
    base_tc = TestCase(
        id="sample-bs",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [-1, 0, 3, 5, 9, 12], "target": 9},
    )
    ctx = ProblemContext(
        title="Binary Search",
        function_name="search",
        parameters=["nums", "target"],
        constraints=[
            "1 <= nums.length <= 10^4",
            "-10^4 < nums[i], target < 10^4",
            "All the integers in nums are unique.",
            "nums is sorted in ascending order.",
        ],
    )
    gap = CoverageGap(
        category=GapCategory.DUPLICATE_ELEMENTS,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Untested duplicate elements in nums",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap])

    dup_cands = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS]
    assert len(dup_cands) >= 1
    cand = dup_cands[0]

    # Target must NOT be modified using an assumed sum relationship (must not be 6, 18, etc.)
    assert cand.input_data["target"] == 9
    # Duplicate elements are generated in nums without altering target
    assert cand.input_data["nums"] == [-1, -1, 3, 5, 9, 12]
    assert cand.source == TestCaseSource.GENERATED_TEST
    assert cand.expected_output is None
    assert cand.is_expected_output_verified is False


def test_duplicate_candidate_generation_binary_search_with_containment_metadata():
    """Binary Search with explicit relational_metadata type='CONTAINMENT' does not modify target."""
    base_tc = TestCase(
        id="sample-bs-meta",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [-1, 0, 3, 5, 9, 12], "target": 9},
    )
    rel_meta = {
        "type": "CONTAINMENT",
        "collection_param": "nums",
        "target_param": "target",
    }
    gap = CoverageGap(
        category=GapCategory.DUPLICATE_ELEMENTS,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Untested duplicate elements in nums",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], gaps=[gap], relational_metadata=rel_meta)

    dup_cands = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS]
    assert len(dup_cands) >= 1
    cand = dup_cands[0]
    # Target must NOT be modified
    assert cand.input_data["target"] == 9
    assert cand.input_data["nums"] == [-1, -1, 3, 5, 9, 12]


def test_duplicate_candidate_generation_unknown_relationship():
    """Unknown target relationship: does not infer mathematical relationships solely from parameter name 'target'."""
    base_tc = TestCase(
        id="sample-unknown",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 4], "target": 5},
    )
    ctx = ProblemContext(
        title="Custom Problem",
        parameters=["nums", "target"],
    )
    gap = CoverageGap(
        category=GapCategory.DUPLICATE_ELEMENTS,
        param_name="nums",
        severity=GapSeverity.MEDIUM,
        rationale="Untested duplicates in nums",
    )
    synth = TargetedTestSynthesizer()
    # No additive metadata and non-additive title
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap], relational_metadata=None)

    dup_cands = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS]
    assert len(dup_cands) >= 1
    cand = dup_cands[0]

    # Target must remain unchanged (5, not 6 or 2*v)
    assert cand.input_data["target"] == 5
    assert cand.input_data["nums"] == [1, 1, 4]
    assert cand.source == TestCaseSource.GENERATED_TEST
    assert cand.expected_output is None
    assert cand.is_expected_output_verified is False


def test_duplicate_candidate_existing_constraint_classification():
    """Constraint classification on duplicate candidates: valid bounds -> VALID; out-of-bounds -> ROBUSTNESS PROBE."""
    from core.test_intelligence.constraint_parser import classify_candidate

    spec_valid = ConstraintSpec(
        min_length=2,
        max_length=1000,
        min_value=-100,
        max_value=100,
    )

    # Valid candidate within bounds
    cand_valid = TestCase(
        id="gen-dup-valid",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [5, 5, 10], "target": 10},
        target_gap=GapCategory.DUPLICATE_ELEMENTS,
    )
    c_status, c_reason = classify_candidate(cand_valid, spec_valid)
    assert c_status == CandidateClassification.VALID.value
    assert "satisfies all" in c_reason.lower()

    # Candidate violating min_length (robustness probe)
    cand_short = TestCase(
        id="gen-dup-short",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [5], "target": 10},
        target_gap=GapCategory.DUPLICATE_ELEMENTS,
    )
    c_status_short, c_reason_short = classify_candidate(cand_short, spec_valid)
    assert c_status_short == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "minimum length" in c_reason_short.lower()

    # Candidate violating max_value (robustness probe)
    cand_high = TestCase(
        id="gen-dup-high",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [5, 5], "target": 500},
        target_gap=GapCategory.DUPLICATE_ELEMENTS,
    )
    c_status_high, c_reason_high = classify_candidate(cand_high, spec_valid)
    assert c_status_high == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "maximum value" in c_reason_high.lower()

    # Candidate with missing/unknown constraints
    cand_unknown = TestCase(
        id="gen-dup-unk",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [5, 5], "target": 10},
        target_gap=GapCategory.DUPLICATE_ELEMENTS,
    )
    c_status_unk, _ = classify_candidate(cand_unknown, None, has_supplied_constraints=False)
    assert c_status_unk == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value


# =============================================================================
# 17. Regression Tests for Two Sum Semantics, Target Boundaries & Label Accuracy
# =============================================================================


def test_two_sum_synthesis_min_max_target_boundaries():
    """Verify Two Sum minimum and maximum target boundaries maintain exactly one valid pair and valid bounds."""
    from core.test_intelligence.constraint_parser import (
        classify_candidate,
        count_valid_pairs,
        parse_constraint_expressions,
    )

    raw_constraints = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
        "Only one valid answer exists.",
    ]
    spec, _ = parse_constraint_expressions(raw_constraints, known_parameters=["nums", "target"])
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=raw_constraints,
        constraint_spec=spec,
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )

    gap_min_target = CoverageGap(
        category=GapCategory.LOWER_CONSTRAINT_BOUND,
        param_name="target",
        severity=GapSeverity.HIGH,
        rationale="Target minimum boundary",
    )
    gap_max_target = CoverageGap(
        category=GapCategory.UPPER_CONSTRAINT_BOUND,
        param_name="target",
        severity=GapSeverity.HIGH,
        rationale="Target maximum boundary",
    )

    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_min_target, gap_max_target])

    min_cands = [c for c in candidates if c.target_gap == GapCategory.LOWER_CONSTRAINT_BOUND and "target" in c.id]
    max_cands = [c for c in candidates if c.target_gap == GapCategory.UPPER_CONSTRAINT_BOUND and "target" in c.id]

    assert len(min_cands) >= 1
    assert len(max_cands) >= 1

    # Min target candidate: target is -10^9, exactly 1 pair, elements within bounds
    min_tc = min_cands[0]
    assert min_tc.input_data["target"] == -1000000000
    assert count_valid_pairs(min_tc.input_data["nums"], min_tc.input_data["target"]) == 1
    for x in min_tc.input_data["nums"]:
        assert -1000000000 <= x <= 1000000000
    cls_min, _ = classify_candidate(min_tc, spec, context=ctx)
    assert cls_min == CandidateClassification.VALID.value

    # Max target candidate: target is 10^9, exactly 1 pair, elements within bounds
    max_tc = max_cands[0]
    assert max_tc.input_data["target"] == 1000000000
    assert count_valid_pairs(max_tc.input_data["nums"], max_tc.input_data["target"]) == 1
    for x in max_tc.input_data["nums"]:
        assert -1000000000 <= x <= 1000000000
    cls_max, _ = classify_candidate(max_tc, spec, context=ctx)
    assert cls_max == CandidateClassification.VALID.value


def test_two_sum_synthesis_negative_target_with_single_valid_pair():
    """Verify negative target candidate maintains exactly one valid pair."""
    from core.test_intelligence.constraint_parser import (
        classify_candidate,
        count_valid_pairs,
        parse_constraint_expressions,
    )

    raw_constraints = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
    ]
    spec, _ = parse_constraint_expressions(raw_constraints, known_parameters=["nums", "target"])
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=raw_constraints,
        constraint_spec=spec,
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )

    gap_neg_target = CoverageGap(
        category=GapCategory.NEGATIVE_VALUES,
        param_name="target",
        severity=GapSeverity.HIGH,
        rationale="Negative target",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_neg_target])

    neg_cands = [c for c in candidates if c.target_gap == GapCategory.NEGATIVE_VALUES and "target" in c.id]
    assert len(neg_cands) >= 1
    tc = neg_cands[0]
    assert tc.input_data["target"] < 0
    assert count_valid_pairs(tc.input_data["nums"], tc.input_data["target"]) == 1
    cls, _ = classify_candidate(tc, spec, context=ctx)
    assert cls == CandidateClassification.VALID.value


def test_two_sum_synthesis_zero_target_with_single_valid_pair():
    """Verify zero target candidate maintains exactly one valid pair (e.g. [-5, 5])."""
    from core.test_intelligence.constraint_parser import (
        classify_candidate,
        count_valid_pairs,
        parse_constraint_expressions,
    )

    raw_constraints = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
    ]
    spec, _ = parse_constraint_expressions(raw_constraints, known_parameters=["nums", "target"])
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=raw_constraints,
        constraint_spec=spec,
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )

    gap_zero_target = CoverageGap(
        category=GapCategory.ZERO_VALUE,
        param_name="target",
        severity=GapSeverity.HIGH,
        rationale="Zero target",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_zero_target])

    zero_cands = [c for c in candidates if c.target_gap == GapCategory.ZERO_VALUE and "target" in c.id]
    assert len(zero_cands) >= 1
    tc = zero_cands[0]
    assert tc.input_data["target"] == 0
    assert count_valid_pairs(tc.input_data["nums"], 0) == 1
    cls, _ = classify_candidate(tc, spec, context=ctx)
    assert cls == CandidateClassification.VALID.value


def test_two_sum_synthesis_negative_array_values_with_single_valid_pair():
    """Verify negative array values candidate maintains exactly one valid pair."""
    from core.test_intelligence.constraint_parser import (
        classify_candidate,
        count_valid_pairs,
        parse_constraint_expressions,
    )

    raw_constraints = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
    ]
    spec, _ = parse_constraint_expressions(raw_constraints, known_parameters=["nums", "target"])
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=raw_constraints,
        constraint_spec=spec,
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )

    gap_neg_nums = CoverageGap(
        category=GapCategory.NEGATIVE_VALUES,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Negative array elements",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_neg_nums])

    neg_cands = [c for c in candidates if c.target_gap == GapCategory.NEGATIVE_VALUES and "nums" in c.id]
    assert len(neg_cands) >= 1
    tc = neg_cands[0]
    assert any(x < 0 for x in tc.input_data["nums"])
    assert count_valid_pairs(tc.input_data["nums"], tc.input_data["target"]) == 1
    cls, _ = classify_candidate(tc, spec, context=ctx)
    assert cls == CandidateClassification.VALID.value


def test_two_sum_duplicate_elements_single_valid_pair():
    """Duplicate candidate [3, 3] target 6 has exactly one valid pair."""
    from core.test_intelligence.constraint_parser import (
        classify_candidate,
        count_valid_pairs,
        parse_constraint_expressions,
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
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    gap_dup = CoverageGap(
        category=GapCategory.DUPLICATE_ELEMENTS,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Duplicate elements",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_dup])

    dup_cands = [c for c in candidates if c.target_gap == GapCategory.DUPLICATE_ELEMENTS]
    assert len(dup_cands) >= 1
    tc = dup_cands[0]
    assert tc.input_data["nums"] == [3, 3]
    assert tc.input_data["target"] == 6
    assert count_valid_pairs(tc.input_data["nums"], tc.input_data["target"]) == 1

    spec, _ = parse_constraint_expressions(ctx.constraints, known_parameters=ctx.parameters)
    cls, _ = classify_candidate(tc, spec, context=ctx)
    assert cls == CandidateClassification.VALID.value


def test_all_identical_two_sum_classified_as_constraint_validity_unknown():
    """All-identical candidates for Two Sum (e.g. [2, 2, 2, 2] target 4) violate uniqueness and are UNKNOWN."""
    from core.test_intelligence.constraint_parser import classify_candidate

    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"],
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    gap_identical = CoverageGap(
        category=GapCategory.IDENTICAL_ALL,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="All identical elements",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_identical])

    assert len(candidates) >= 1
    cand = candidates[0]
    spec = ConstraintSpec(min_length=2, max_length=10000, min_value=-1000000000, max_value=1000000000)
    cls, reason = classify_candidate(cand, spec, context=ctx)
    # Must NOT be labeled VALID because multiple or 0 pairs exist
    assert cls == CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value


def test_candidate_array_size_labels_matching_actual_lengths():
    """Candidate labels must never claim maximum-boundary coverage if length is less than max."""
    from core.test_intelligence.constraint_parser import parse_constraint_expressions

    raw_constraints = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
    ]
    spec, _ = parse_constraint_expressions(raw_constraints, known_parameters=["nums", "target"])
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=raw_constraints,
        constraint_spec=spec,
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    gap_scale = CoverageGap(
        category=GapCategory.UPPER_CONSTRAINT_BOUND,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Upper length bound",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_scale])

    scale_cands = [c for c in candidates if c.target_gap == GapCategory.UPPER_CONSTRAINT_BOUND and "scale" in c.id]
    assert len(scale_cands) >= 1
    tc = scale_cands[0]
    actual_len = len(tc.input_data["nums"])
    assert actual_len == 10000
    assert "10000 elements" in tc.label
    assert "Maximum constraint length (10000 elements)" in tc.label


def test_candidate_provenance_and_unverified_expected_output_invariants():
    """All synthesized candidates preserve GENERATED_TEST provenance and unverified expected output."""
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9", "-10^9 <= target <= 10^9"],
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx)

    assert len(candidates) > 0
    for cand in candidates:
        assert cand.source == TestCaseSource.GENERATED_TEST
        assert cand.expected_output is None
        assert cand.is_expected_output_verified is False


def test_maximum_constraint_length_10000_explicit_assertion():
    """
    Explicit test asserting len(candidate.input_data['nums']) == 10000
    for a candidate genuinely labelled as the maximum constraint length.
    """
    raw_constraints = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
    ]
    spec, _ = parse_constraint_expressions(raw_constraints, known_parameters=["nums", "target"])
    ctx = ProblemContext(
        title="Two Sum",
        parameters=["nums", "target"],
        constraints=raw_constraints,
        constraint_spec=spec,
    )
    base_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
    )
    gap_scale = CoverageGap(
        category=GapCategory.UPPER_CONSTRAINT_BOUND,
        param_name="nums",
        severity=GapSeverity.HIGH,
        rationale="Maximum constraint length boundary",
    )
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([base_tc], context=ctx, gaps=[gap_scale])

    # Find candidates labelled as the maximum constraint length
    max_len_candidates = [
        c for c in candidates
        if "maximum constraint length" in (c.label or "").lower()
    ]
    assert len(max_len_candidates) >= 1, "Expected at least one candidate labelled as maximum constraint length"

    for candidate in max_len_candidates:
        assert len(candidate.input_data["nums"]) == 10000, (
            f"Candidate labelled as maximum constraint length must have exactly 10000 elements, "
            f"got {len(candidate.input_data['nums'])}"
        )




