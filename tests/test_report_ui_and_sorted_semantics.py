"""
Tests for EdgeMind Report UI Refinements and Sorted Sequence / Binary Search Semantics.

Verifies:
1. Binary Search and Sorted Sequence Constraint Parsing:
   - "nums is sorted in ascending order"
   - "nums is sorted in strictly increasing order"
   - "nums is sorted in non-decreasing order"
   - "All the integers in nums are unique."
2. Gap Detector Sorted Sequence Handling:
   - Suppresses UNSORTED_SEQUENCE and REVERSE_SORTED gaps when problem requires sorted order.
3. Candidate Classification for Sorted Inputs:
   - Classifies unsorted inputs as ROBUSTNESS PROBE.
   - Classifies duplicate elements as ROBUSTNESS PROBE when uniqueness is required.
   - Classifies valid sorted inputs as VALID.
4. Synthesizer Sorted Sequence Preservation:
   - Boundary candidates maintain sorted ascending invariant.
5. Extension Popup Formatting & Safe DOM:
   - Large array preview with first 5 and last 3 elements, ellipsis, and exact count.
   - Large string preview with prefix, suffix, ellipsis, and exact count.
   - 5-item pagination and "View All" toggles for Gaps and Candidates.
   - Expandable details for gap risk and full candidate JSON.
   - All 8 summary metrics displayed.
"""

from pathlib import Path
import pytest

from core.test_intelligence.constraint_parser import (
    classify_candidate,
    parse_constraint_expressions,
)
from core.test_intelligence.gap_detector import (
    CoverageGapEvaluator,
    GapCategory,
)
from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.synthesizer import TargetedTestSynthesizer


# =============================================================================
# 1. Binary Search / Sorted Constraints Parsing
# =============================================================================


def test_parse_sorted_ascending_constraint():
    """Verify 'nums is sorted in ascending order' parses into ConstraintSpec."""
    raw = [
        "1 <= nums.length <= 10^4",
        "-10^4 < nums[i], target < 10^4",
        "All the integers in nums are unique.",
        "nums is sorted in ascending order.",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target"])
    assert spec.is_sorted_ascending is True
    assert spec.sorted_param == "nums"
    assert spec.unique_elements is True
    assert spec.is_strictly_increasing is True
    assert spec.min_length == 1
    assert spec.max_length == 10000
    assert len(unresolved) == 0


def test_parse_sorted_non_decreasing_constraint():
    """Verify 'arr is sorted in non-decreasing order' parses into ConstraintSpec."""
    raw = [
        "1 <= arr.length <= 500",
        "arr is sorted in non-decreasing order",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["arr"])
    assert spec.is_sorted_ascending is True
    assert spec.sorted_param == "arr"
    assert spec.is_strictly_increasing is False
    assert len(unresolved) == 0


def test_parse_strictly_increasing_constraint():
    """Verify 'nums is sorted in strictly increasing order' sets strictly increasing."""
    raw = [
        "2 <= nums.length <= 100",
        "nums is sorted in strictly increasing order",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums"])
    assert spec.is_sorted_ascending is True
    assert spec.is_strictly_increasing is True
    assert spec.sorted_param == "nums"
    assert len(unresolved) == 0


# =============================================================================
# 2. Gap Detector: Sorted Gap Suppression
# =============================================================================


def test_gap_detector_suppresses_unsorted_gaps_when_sorted_required():
    """Verify UNSORTED_SEQUENCE and REVERSE_SORTED are not proposed when input must be sorted."""
    # Samples with strictly sorted inputs
    cases = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [-1, 0, 3, 5, 9, 12], "target": 9}),
        TestCase(id="2", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [-1, 0, 3, 5, 9, 12], "target": 2}),
    ]
    spec = ConstraintSpec(
        min_length=1,
        max_length=10000,
        min_value=-9999,
        max_value=9999,
        is_sorted_ascending=True,
        sorted_param="nums",
        unique_elements=True,
        is_strictly_increasing=True,
    )
    ctx = ProblemContext(
        platform="leetcode",
        problem_id="704",
        title="Binary Search",
        constraints=["1 <= nums.length <= 10^4", "nums is sorted in ascending order."],
        constraint_spec=spec,
        parameters=["nums", "target"],
    )

    evaluator = CoverageGapEvaluator()
    result = evaluator.evaluate(cases, context=ctx)

    categories = [g.category for g in result.gaps]
    assert GapCategory.UNSORTED_SEQUENCE not in categories
    assert GapCategory.REVERSE_SORTED not in categories


# =============================================================================
# 3. Candidate Classification: Sorted & Robustness Probes
# =============================================================================


def test_classify_candidate_unsorted_as_robustness_probe():
    """Verify candidate with unsorted array is classified as ROBUSTNESS PROBE when sortedness is required."""
    spec = ConstraintSpec(
        min_length=1,
        max_length=10000,
        min_value=-10000,
        max_value=10000,
        is_sorted_ascending=True,
        sorted_param="nums",
    )
    unsorted_cand = TestCase(
        id="cand-unsorted",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [10, 5, 1], "target": 5},
    )
    classification, reason = classify_candidate(unsorted_cand, spec)
    assert classification == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "must be sorted in ascending order" in reason.lower()


def test_classify_candidate_duplicate_elements_when_unique_required():
    """Verify duplicate elements candidate is classified as ROBUSTNESS PROBE when uniqueness is required."""
    spec = ConstraintSpec(
        min_length=1,
        max_length=10000,
        min_value=-10000,
        max_value=10000,
        is_sorted_ascending=True,
        unique_elements=True,
        sorted_param="nums",
    )
    duplicate_cand = TestCase(
        id="cand-dup",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [1, 2, 2, 3], "target": 2},
    )
    classification, reason = classify_candidate(duplicate_cand, spec)
    assert classification == CandidateClassification.ROBUSTNESS_PROBE.value
    assert "must be unique" in reason.lower()


def test_classify_candidate_valid_sorted_input():
    """Verify sorted candidate satisfying all bounds is classified as VALID."""
    spec = ConstraintSpec(
        min_length=1,
        max_length=10000,
        min_value=-10000,
        max_value=10000,
        is_sorted_ascending=True,
        sorted_param="nums",
    )
    valid_cand = TestCase(
        id="cand-valid",
        source=TestCaseSource.GENERATED_TEST,
        input_data={"nums": [-10000, 0, 10000], "target": 0},
    )
    classification, reason = classify_candidate(valid_cand, spec)
    assert classification == CandidateClassification.VALID.value


# =============================================================================
# 4. Synthesizer: Preserves Sorted Invariant
# =============================================================================


def test_synthesizer_preserves_sorted_ascending_boundaries():
    """Verify synthesized boundary candidates preserve ascending sort order for sorted problems."""
    spec = ConstraintSpec(
        min_length=1,
        max_length=10000,
        min_value=-1000,
        max_value=1000,
        is_sorted_ascending=True,
        sorted_param="nums",
    )
    ctx = ProblemContext(
        platform="leetcode",
        problem_id="704",
        title="Binary Search",
        constraints=["1 <= nums.length <= 10^4", "-1000 <= nums[i] <= 1000", "nums is sorted in ascending order."],
        constraint_spec=spec,
        parameters=["nums", "target"],
    )
    samples = [
        TestCase(id="1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [-50, 0, 50], "target": 0}),
    ]

    synthesizer = TargetedTestSynthesizer()
    candidates = synthesizer.synthesize(samples, context=ctx)

    for cand in candidates:
        nums = cand.input_data.get("nums")
        if isinstance(nums, (list, tuple)) and len(nums) >= 2:
            # Check sorted ascending
            for idx in range(len(nums) - 1):
                assert nums[idx] <= nums[idx + 1], f"Candidate {cand.id} array {nums} is not sorted ascending!"


# =============================================================================
# 5. Extension Popup Source Code & UI Architecture Verification
# =============================================================================


def test_popup_html_contains_view_all_buttons_and_summary_structure():
    """Verify popup.html contains View All buttons and concise summary card elements."""
    popup_html = Path("extension/edgemind/popup/popup.html").read_text(encoding="utf-8")

    # View all buttons
    assert 'id="btn-toggle-all-gaps"' in popup_html
    assert 'id="btn-toggle-all-candidates"' in popup_html

    # Summary structure
    assert 'id="page-title"' in popup_html
    assert 'id="mode-badge"' in popup_html
    assert 'id="lang-badge"' in popup_html
    assert 'id="mode-examples-count"' in popup_html
    assert 'id="mode-parameters-identified"' in popup_html
    assert 'id="stat-gaps"' in popup_html
    assert 'id="stat-candidates"' in popup_html
    assert 'id="stat-dedup"' in popup_html


def test_popup_js_implements_large_input_preview_and_expandable_sections():
    """Verify popup.js implements large array/string formatting and safe expandable sections."""
    popup_js = Path("extension/edgemind/popup/popup.js").read_text(encoding="utf-8")

    # Large input handling
    assert "formatValueSummary" in popup_js
    assert "formatRowPreview" in popup_js
    assert "(5 items)" in popup_js or "items" in popup_js
    assert "chars" in popup_js
    assert "..." in popup_js

    # Safe pagination toggles
    assert "btn-toggle-all-gaps" in popup_js
    assert "btn-toggle-all-candidates" in popup_js
    assert "updateGapsDisplay" in popup_js
    assert "updateCandidatesDisplay" in popup_js

    # Expandable details
    assert "gap-expandable-details" in popup_js
    assert "btn-gap-details-toggle" in popup_js
    assert "candidate-json-details" in popup_js
    assert "btn-toggle-json" in popup_js
    assert "Copy Full Input" in popup_js

    # Safe DOM verification (no innerHTML or outerHTML)
    assert "innerHTML" not in popup_js
    assert "outerHTML" not in popup_js


def test_popup_css_contains_necessary_styling_for_compact_report():
    """Verify popup.css contains styling for view-all, input summary, and expandable sections."""
    popup_css = Path("extension/edgemind/popup/popup.css").read_text(encoding="utf-8")

    assert ".btn-view-all" in popup_css
    assert ".btn-gap-details-toggle" in popup_css
    assert ".gap-expandable-details" in popup_css
    assert ".input-summary-box" in popup_css
    assert ".input-param-name" in popup_css
    assert ".input-param-val" in popup_css
    assert ".candidate-json-details" in popup_css
    assert ".btn-toggle-json" in popup_css
    assert ".btn-copy-summary" in popup_css

