"""
Tests for EdgeMind Adaptive Test Intelligence - Phase 2: Feature Profile Extractor.
"""

import copy
import pytest

from core.test_intelligence.extractor import (
    CollectionProfile,
    FeatureProfileExtractor,
    FeatureStatus,
    InputFeatureProfile,
    MultiplicityProfile,
    NumericProfile,
    OrderProfile,
    ParameterProfile,
    RelationalProfile,
)
from core.test_intelligence.models import (
    ConstraintSpec,
    ProblemContext,
    TestCase,
    TestCaseSource,
)


def test_collection_cardinality_extraction():
    """Verify cardinality extraction: observed lengths, empty, and singleton detection."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": []}),
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": [42]}),
        TestCase(id="3", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": [1, 2, 3, 4]}),
    ]

    extractor = FeatureProfileExtractor()
    profile = extractor.extract(cases)

    arr_coll = profile.parameters["arr"].collection
    assert arr_coll.observed_lengths == [0, 1, 4]
    assert arr_coll.has_empty == FeatureStatus.OBSERVED
    assert arr_coll.has_singleton == FeatureStatus.OBSERVED
    assert arr_coll.min_length == 0
    assert arr_coll.max_length == 4

    # Test cases without empty collection
    non_empty_cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": [10]}),
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"arr": [1, 2]}),
    ]
    profile2 = extractor.extract(non_empty_cases)
    arr_coll2 = profile2.parameters["arr"].collection
    assert arr_coll2.has_empty == FeatureStatus.UNOBSERVED
    assert arr_coll2.has_singleton == FeatureStatus.OBSERVED


def test_numeric_sign_and_range_extraction():
    """Verify numeric sign and min/max value extraction from scalars and collections."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [-15, 0], "k": 5}),
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [20], "k": -1}),
    ]

    extractor = FeatureProfileExtractor()
    profile = extractor.extract(cases)

    nums_num = profile.parameters["nums"].numeric
    assert nums_num.has_negative == FeatureStatus.OBSERVED
    assert nums_num.has_zero == FeatureStatus.OBSERVED
    assert nums_num.has_positive == FeatureStatus.OBSERVED
    assert nums_num.min_value == -15
    assert nums_num.max_value == 20

    k_num = profile.parameters["k"].numeric
    assert k_num.has_negative == FeatureStatus.OBSERVED
    assert k_num.has_zero == FeatureStatus.UNOBSERVED
    assert k_num.has_positive == FeatureStatus.OBSERVED
    assert k_num.min_value == -1
    assert k_num.max_value == 5


def test_duplicate_and_all_identical_detection():
    """Verify multiplicity extraction: duplicates, all-identical, and all-unique sequences."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"seq": [1, 2, 2, 3]}),
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"seq": [7, 7, 7]}),
        TestCase(id="3", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"seq": [4, 5, 6]}),
    ]

    extractor = FeatureProfileExtractor()
    profile = extractor.extract(cases)

    mult = profile.parameters["seq"].multiplicity
    assert mult.has_duplicates == FeatureStatus.OBSERVED
    assert mult.has_all_identical == FeatureStatus.OBSERVED
    assert mult.has_all_unique == FeatureStatus.OBSERVED

    # Case with strictly unique elements
    unique_cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"seq": [1, 2, 3]}),
    ]
    p_uniq = extractor.extract(unique_cases).parameters["seq"].multiplicity
    assert p_uniq.has_duplicates == FeatureStatus.UNOBSERVED
    assert p_uniq.has_all_identical == FeatureStatus.UNOBSERVED
    assert p_uniq.has_all_unique == FeatureStatus.OBSERVED


def test_sequence_ordering_extraction():
    """Verify sequence ordering: strictly increasing, decreasing, non-decreasing, constant, unsorted."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": [1, 2, 3]}),     # strictly inc
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": [3, 2, 1]}),     # strictly dec
        TestCase(id="3", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": [1, 2, 2, 3]}),  # non-decreasing
        TestCase(id="4", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": [5, 5, 5]}),     # constant
        TestCase(id="5", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": [4, 1, 2]}),     # unsorted
    ]

    extractor = FeatureProfileExtractor()
    profile = extractor.extract(cases)

    order = profile.parameters["s"].order
    assert order.has_strictly_increasing == FeatureStatus.OBSERVED
    assert order.has_strictly_decreasing == FeatureStatus.OBSERVED
    assert order.has_non_decreasing == FeatureStatus.OBSERVED
    assert order.has_constant == FeatureStatus.OBSERVED
    assert order.has_unsorted == FeatureStatus.OBSERVED


def test_nested_lists_and_matrices():
    """Verify matrix dimensions, square/rectangular status, and empty subcollections."""
    cases = [
        TestCase(
            id="1",
            source=TestCaseSource.PUBLIC_SAMPLE,
            input_data={"grid": [[1, 2], [3, 4]]},  # 2x2 square
        ),
        TestCase(
            id="2",
            source=TestCaseSource.PUBLIC_SAMPLE,
            input_data={"grid": [[1, 2, 3], [4, 5, 6]]},  # 2x3 rectangular
        ),
        TestCase(
            id="3",
            source=TestCaseSource.PUBLIC_SAMPLE,
            input_data={"grid": [[], [1]]},  # empty subcollection
        ),
    ]

    extractor = FeatureProfileExtractor()
    profile = extractor.extract(cases)

    grid_coll = profile.parameters["grid"].collection
    assert grid_coll.is_nested is True
    assert grid_coll.is_matrix == FeatureStatus.OBSERVED
    assert grid_coll.is_square_matrix == FeatureStatus.OBSERVED
    assert grid_coll.is_rectangular_matrix == FeatureStatus.OBSERVED
    assert grid_coll.has_empty_subcollections == FeatureStatus.OBSERVED
    assert [2, 2] in grid_coll.matrix_dimensions
    assert [2, 3] in grid_coll.matrix_dimensions

    # Elements inside matrix contribute to numeric features
    grid_num = profile.parameters["grid"].numeric
    assert grid_num.min_value == 1
    assert grid_num.max_value == 6


def test_empty_inputs_handling():
    """Verify extractor handles empty test suite without crashing."""
    extractor = FeatureProfileExtractor()
    profile = extractor.extract([])

    assert profile.test_cases_analyzed == 0
    assert profile.parameters == {}
    assert profile.relational == []
    data = profile.to_dict()
    assert data["test_cases_analyzed"] == 0


def test_mixed_types_and_unsupported_structures():
    """Verify mixed types, unorderable elements, and dicts are handled gracefully."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"data": [1, "two", 3]}),
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"mapping": {"a": 10, "b": -5}}),
    ]

    extractor = FeatureProfileExtractor()
    profile = extractor.extract(cases)

    data_param = profile.parameters["data"]
    assert "list" in data_param.types_observed
    # Incomparable elements fallback safely for order
    assert data_param.order.has_strictly_increasing == FeatureStatus.NOT_APPLICABLE

    map_param = profile.parameters["mapping"]
    assert "dict" in map_param.types_observed
    assert map_param.numeric.has_positive == FeatureStatus.OBSERVED
    assert map_param.numeric.has_negative == FeatureStatus.OBSERVED
    assert map_param.numeric.min_value == -5
    assert map_param.numeric.max_value == 10


def test_explicit_relational_metadata():
    """Verify relational features when explicit parameter relationship metadata is provided."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"haystack": "hello", "needle": "h"}),  # first index
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"haystack": "hello", "needle": "o"}),  # last index
        TestCase(id="3", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"haystack": "hello", "needle": "z"}),  # absent
    ]

    rel_spec = {
        "type": "CONTAINMENT",
        "collection_param": "haystack",
        "target_param": "needle",
    }

    extractor = FeatureProfileExtractor()
    profile = extractor.extract(cases, relational_metadata=rel_spec)

    assert len(profile.relational) == 1
    rel = profile.relational[0]
    assert rel.relationship_type == "CONTAINMENT"
    assert rel.target_present == FeatureStatus.OBSERVED
    assert rel.target_absent == FeatureStatus.OBSERVED
    assert rel.target_at_first_index == FeatureStatus.OBSERVED
    assert rel.target_at_last_index == FeatureStatus.OBSERVED


def test_missing_relational_metadata_never_assumes():
    """Verify extractor never infers or guesses parameter relationships without explicit metadata."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 2, 3], "target": 2}),
    ]

    extractor = FeatureProfileExtractor()
    # No relational metadata passed
    profile = extractor.extract(cases)

    assert len(profile.relational) == 1
    rel = profile.relational[0]
    assert rel.relationship_type == "UNKNOWN"
    assert rel.target_present == FeatureStatus.NOT_APPLICABLE
    assert rel.target_absent == FeatureStatus.NOT_APPLICABLE


def test_constraint_boundary_observations():
    """Verify whether observed values and lengths hit specified constraint boundaries."""
    spec = ConstraintSpec(
        min_value=-10.0,
        max_value=100.0,
        min_length=1,
        max_length=5,
    )
    context = ProblemContext(platform="leetcode", constraint_spec=spec)

    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"val": 100}),  # hits max_value (100)
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"val": -5}),   # does not hit min_value (-10)
    ]

    extractor = FeatureProfileExtractor(context=context)
    profile = extractor.extract(cases)

    num = profile.parameters["val"].numeric
    assert num.includes_constraint_max == FeatureStatus.OBSERVED
    assert num.includes_constraint_min == FeatureStatus.UNOBSERVED


def test_deterministic_repeated_results():
    """Verify that multiple extractions on the same test cases produce identical results."""
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"z": [3, 2, 1], "a": 10}),
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"z": [], "a": -5}),
    ]

    extractor = FeatureProfileExtractor()
    res1 = extractor.extract(cases).to_dict()
    res2 = extractor.extract(cases).to_dict()

    assert res1 == res2
    # Ensure parameter keys are sorted deterministically
    assert list(res1["parameters"].keys()) == ["a", "z"]


def test_input_objects_are_not_mutated():
    """Verify that feature extraction is strictly side-effect free and never mutates inputs."""
    original_data = {"nums": [3, 1, 2], "meta": {"nested": [10, 20]}}
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data=original_data),
    ]

    cases_copy = copy.deepcopy(cases)

    extractor = FeatureProfileExtractor()
    _ = extractor.extract(cases)

    # Assert exact equality with pristine deep copy
    assert cases == cases_copy
    assert cases[0].input_data == original_data
    assert cases[0].input_data["nums"] == [3, 1, 2]  # not sorted in place
