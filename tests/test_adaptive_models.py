"""
Tests for EdgeMind Adaptive Test Intelligence - Phase 1: Models & Provenance.
"""

import pytest
from core.models import (
    AdaptiveTestReport as CoreAdaptiveTestReport,
    ConstraintSpec as CoreConstraintSpec,
    GapCategory as CoreGapCategory,
    ProblemContext as CoreProblemContext,
    TestCase as CoreTestCase,
    TestCaseSource as CoreTestCaseSource,
)
from core.test_intelligence.models import (
    AdaptiveTestReport,
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)


def test_testcase_source_enum_members():
    """Verify all 5 required test case sources are defined with exact names."""
    expected_members = {
        "PUBLIC_SAMPLE",
        "AUTHORIZED_PLATFORM_TEST",
        "GENERATED_TEST",
        "PLATFORM_REVEALED_FAILURE",
        "USER_PROVIDED_TEST",
    }
    actual_members = {s.value for s in TestCaseSource}
    assert actual_members == expected_members


def test_testcase_source_helpers():
    """Verify helper methods distinguish generated vs platform-native tests."""
    assert TestCaseSource.GENERATED_TEST.is_generated() is True
    assert TestCaseSource.PUBLIC_SAMPLE.is_generated() is False
    assert TestCaseSource.USER_PROVIDED_TEST.is_generated() is False

    assert TestCaseSource.PUBLIC_SAMPLE.is_platform_native() is True
    assert TestCaseSource.AUTHORIZED_PLATFORM_TEST.is_platform_native() is True
    assert TestCaseSource.PLATFORM_REVEALED_FAILURE.is_platform_native() is True
    assert TestCaseSource.GENERATED_TEST.is_platform_native() is False
    assert TestCaseSource.USER_PROVIDED_TEST.is_platform_native() is False


def test_testcase_valid_initialization_and_serialization():
    """Verify valid TestCase creation, to_dict, and from_dict roundtrip."""
    tc = TestCase(
        id="gen-001",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [1, 2, 3], "target": 4},
        expected_output=None,
        is_expected_output_verified=False,
        label="Boundary Test",
        rationale="Tests target inside nums",
        target_gap=GapCategory.TARGET_AT_BOUNDARIES,
        relevance_score=0.85,
        is_boundary=True,
        is_performance=False,
    )
    data = tc.to_dict()
    assert data["id"] == "gen-001"
    assert data["source"] == "GENERATED_TEST"
    assert data["target_gap"] == "TARGET_AT_BOUNDARIES"
    assert data["expected_output"] is None
    assert data["is_expected_output_verified"] is False
    assert data["is_boundary"] is True

    # Roundtrip from_dict
    tc_reconstructed = TestCase.from_dict(data)
    assert tc_reconstructed.id == tc.id
    assert tc_reconstructed.source == TestCaseSource.GENERATED_TEST
    assert tc_reconstructed.target_gap == GapCategory.TARGET_AT_BOUNDARIES
    assert tc_reconstructed.input_data == {"nums": [1, 2, 3], "target": 4}


def test_testcase_string_source_coercion():
    """Verify string source value is automatically coerced to TestCaseSource enum."""
    tc = TestCase(
        id="sample-1",
        source="PUBLIC_SAMPLE",  # passed as string
        input_data={"a": 1},
    )
    assert isinstance(tc.source, TestCaseSource)
    assert tc.source == TestCaseSource.PUBLIC_SAMPLE


def test_testcase_invalid_source_rejected():
    """Verify invalid source strings are strictly rejected."""
    with pytest.raises(ValueError, match="Invalid test case source 'SECRET_HIDDEN_TEST'"):
        TestCase(
            id="bad-1",
            source="SECRET_HIDDEN_TEST",
            input_data={"a": 1},
        )


def test_testcase_invalid_target_gap_rejected():
    """Verify invalid gap category strings are strictly rejected."""
    with pytest.raises(ValueError, match="Invalid target_gap 'MAGIC_GAP'"):
        TestCase(
            id="bad-gap",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"a": 1},
            target_gap="MAGIC_GAP",
        )


def test_testcase_invalid_input_data_rejected():
    """Verify non-dict input_data is rejected."""
    with pytest.raises(TypeError, match="input_data must be a dict"):
        TestCase(
            id="bad-input",
            source=TestCaseSource.PUBLIC_SAMPLE,
            input_data=[1, 2, 3],  # not a dict
        )


def test_testcase_unverified_expected_output_handling():
    """
    Ensure that when expected_output is None (untrusted / unknown oracle),
    is_expected_output_verified is never True.
    """
    tc = TestCase(
        id="gen-empty",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": []},
        expected_output=None,
        is_expected_output_verified=True,  # Attempting to mark None as verified
    )
    # Post-init invariant forces False
    assert tc.is_expected_output_verified is False


def test_constraint_spec_serialization():
    """Verify ConstraintSpec data handling and roundtrip."""
    spec = ConstraintSpec(
        min_value=-1000.0,
        max_value=1000.0,
        min_length=0,
        max_length=100000,
        allowed_characters="a-z",
        raw_constraints=["1 <= nums.length <= 10^5", "-1000 <= nums[i] <= 1000"],
    )
    data = spec.to_dict()
    assert data["min_length"] == 0
    assert data["max_length"] == 100000
    assert len(data["raw_constraints"]) == 2

    reconstructed = ConstraintSpec.from_dict(data)
    assert reconstructed.min_value == -1000.0
    assert reconstructed.max_length == 100000
    assert reconstructed.allowed_characters == "a-z"


def test_problem_context_serialization():
    """Verify ProblemContext serialization including nested ConstraintSpec."""
    spec = ConstraintSpec(min_length=1, max_length=1000)
    ctx = ProblemContext(
        platform="leetcode",
        problem_id="1",
        title="Two Sum",
        constraints=["1 <= nums.length <= 1000"],
        constraint_spec=spec,
        time_limit_seconds=1.5,
        memory_limit_mb=512,
        function_name="twoSum",
        parameters=["nums", "target"],
    )
    data = ctx.to_dict()
    assert data["platform"] == "leetcode"
    assert data["title"] == "Two Sum"
    assert data["time_limit_seconds"] == 1.5
    assert data["constraint_spec"]["max_length"] == 1000

    reconstructed = ProblemContext.from_dict(data)
    assert reconstructed.platform == "leetcode"
    assert reconstructed.constraint_spec is not None
    assert reconstructed.constraint_spec.max_length == 1000
    assert reconstructed.parameters == ["nums", "target"]


def test_adaptive_test_report_defaults_and_disclaimer():
    """
    Verify AdaptiveTestReport defaults to execution_available=False
    and includes explicit disclaimer regarding input-pattern vs code coverage.
    """
    report = AdaptiveTestReport()
    assert report.execution_available is False
    assert "Input-pattern domain coverage only" in report.coverage_disclaimer
    assert "does not prove program code statement or branch coverage" in report.coverage_disclaimer

    data = report.to_dict()
    assert data["execution_available"] is False
    assert data["suggested_tests"] == []


def test_adaptive_test_report_with_cases_roundtrip():
    """Verify AdaptiveTestReport serialization with test cases."""
    tc1 = TestCase(
        id="s-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [2, 7, 11, 15], "target": 9},
        expected_output=[0, 1],
        is_expected_output_verified=True,
    )
    tc2 = TestCase(
        id="g-1",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [], "target": 0},
        expected_output=None,
        is_expected_output_verified=False,
        target_gap=GapCategory.EMPTY_COLLECTION,
    )
    report = AdaptiveTestReport(
        existing_tests_analyzed=1,
        observed_features={"has_empty": False, "has_duplicates": False},
        identified_gaps=["EMPTY_COLLECTION", "DUPLICATE_ELEMENTS"],
        suggested_tests=[tc1, tc2],
        execution_available=False,
    )
    data = report.to_dict()
    assert len(data["suggested_tests"]) == 2
    assert data["suggested_tests"][0]["source"] == "PUBLIC_SAMPLE"
    assert data["suggested_tests"][1]["source"] == "GENERATED_TEST"

    reconstructed = AdaptiveTestReport.from_dict(data)
    assert reconstructed.existing_tests_analyzed == 1
    assert len(reconstructed.suggested_tests) == 2
    assert reconstructed.suggested_tests[1].target_gap == GapCategory.EMPTY_COLLECTION
    assert reconstructed.suggested_tests[1].expected_output is None


def test_core_models_reexport_parity():
    """Ensure models re-exported from core.models are identical to core.test_intelligence.models."""
    assert CoreTestCase is TestCase
    assert CoreTestCaseSource is TestCaseSource
    assert CoreGapCategory is GapCategory
    assert CoreConstraintSpec is ConstraintSpec
    assert CoreProblemContext is ProblemContext
    assert CoreAdaptiveTestReport is AdaptiveTestReport
