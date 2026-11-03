"""
EdgeMind Adaptive Test Intelligence - Comprehensive 15-Problem LeetCode Benchmark Suite.

Systematically verifies:
1. Exact parameter recognition & type inference.
2. Complete constraint parsing with ZERO unhandled syntax errors.
3. Parameter bounds isolation (e.g. k bounds do not clobber nums[i] negative bounds).
4. Multi-parameter & cross-parameter relationship enforcement (e.g. k <= len(nums)).
5. Domain-aware gap detection (suppresses string ordering gaps, constraint-prohibited gaps).
6. Problem-specific candidate synthesis (preserves single-pair sum, distinct sortedness,
   parentheses alphabet, anagram pairs, non-empty linked lists, endpoints zero).
7. Three-tier candidate classification (VALID, ROBUSTNESS PROBE, CONSTRAINT VALIDITY UNKNOWN).
8. Strict static-only analysis invariants (zero execution, untrusted expected outputs).
"""

import pytest
from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.constraint_parser import (
    classify_candidate,
    parse_constraint_expressions,
)
from core.test_intelligence.gap_detector import (
    ConstraintValidity,
    CoverageGapEvaluator,
)
from core.test_intelligence.synthesizer import (
    TargetedTestSynthesizer,
)
from core.service import analyze_edgemind


# =============================================================================
# Helper Assertion for Non-Execution & Provenance Integrity
# =============================================================================

def assert_candidate_invariants(candidates):
    """Enforce EdgeMind's strict static-only analysis and provenance invariants."""
    for c in candidates:
        assert c.source == TestCaseSource.GENERATED_TEST
        assert c.expected_output is None, f"Expected output must remain None, found {c.expected_output}"
        assert c.is_expected_output_verified is False
        assert c.classification in (
            CandidateClassification.VALID.value,
            CandidateClassification.ROBUSTNESS_PROBE.value,
            CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
        )


# =============================================================================
# 1. Two Sum (#1)
# =============================================================================

def test_benchmark_01_two_sum():
    """Two Sum: 2 <= nums.length <= 10^4, -10^9 <= nums[i] <= 10^9, -10^9 <= target <= 10^9, Only one valid answer exists."""
    raw = [
        "2 <= nums.length <= 10^4",
        "-10^9 <= nums[i] <= 10^9",
        "-10^9 <= target <= 10^9",
        "Only one valid answer exists.",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target"])
    assert spec.min_length == 2
    assert spec.max_length == 10000
    assert spec.min_value == -1000000000
    assert spec.max_value == 1000000000
    assert "nums" in spec.param_specs
    assert "target" in spec.param_specs

    # Synthesize candidates from public sample
    ctx = ProblemContext(title="Two Sum", parameters=["nums", "target"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [2, 7, 11, 15], "target": 9})
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)

    assert len(candidates) > 0
    assert_candidate_invariants(candidates)

    # Valid candidates must satisfy single-pair sum invariant
    valid_cands = [c for c in candidates if c.classification == CandidateClassification.VALID.value]
    assert len(valid_cands) >= 1
    for vc in valid_cands:
        arr = vc.input_data["nums"]
        t = vc.input_data["target"]
        assert len(arr) >= 2
        # Verify exactly one pair
        pairs = sum(1 for i in range(len(arr)) for j in range(i + 1, len(arr)) if arr[i] + arr[j] == t)
        assert pairs == 1, f"Candidate {vc.id} has {pairs} pairs summing to {t}"


# =============================================================================
# 2. Add Two Numbers (#2)
# =============================================================================

def test_benchmark_02_add_two_numbers():
    """Add Two Numbers: range [1, 100], 0 <= Node.val <= 9, no leading zeros."""
    raw = [
        "The number of nodes in each list is in the range [1, 100].",
        "0 <= Node.val <= 9",
        "It is guaranteed that the list represents a number that does not have leading zeros, except the number 0 itself.",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["l1", "l2"])
    assert len(unresolved) == 0
    assert spec.min_length == 1
    assert spec.max_length == 100
    assert spec.min_value == 0
    assert spec.max_value == 9
    assert spec.no_leading_zero is True
    assert spec.param_specs["l1"].is_non_empty is True
    assert spec.param_specs["l2"].is_non_empty is True

    # Empty collection gap must be suppressed for l1 and l2
    ctx = ProblemContext(title="Add Two Numbers", parameters=["l1", "l2"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"l1": [2, 4, 3], "l2": [5, 6, 4]})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    gaps = gap_result.gaps
    empty_gaps = [g for g in gaps if g.category == GapCategory.EMPTY_COLLECTION]
    assert len(empty_gaps) == 0, "EMPTY_COLLECTION should be suppressed because min_length=1 and is_non_empty=True"

    # Candidates must never have empty lists or out-of-range digits
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    for c in candidates:
        for p in ("l1", "l2"):
            if p in c.input_data and isinstance(c.input_data[p], list):
                if c.classification == CandidateClassification.VALID.value:
                    assert len(c.input_data[p]) >= 1
                    assert all(0 <= d <= 9 for d in c.input_data[p])


# =============================================================================
# 3. Longest Substring Without Repeating Characters (#3)
# =============================================================================

def test_benchmark_03_longest_substring():
    """Longest Substring: 0 <= s.length <= 5 * 10^4, English letters, digits, symbols and spaces."""
    raw = [
        "0 <= s.length <= 5 * 10^4",
        "s consists of English letters, digits, symbols and spaces.",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["s"])
    assert len(unresolved) == 0
    assert spec.min_length == 0
    assert spec.max_length == 50000

    ctx = ProblemContext(title="Longest Substring Without Repeating Characters", parameters=["s"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": "abcabcbb"})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    gaps = gap_result.gaps

    # Domain-aware rule: Suppress numeric sequence ordering gaps for strings!
    order_gaps = [g for g in gaps if g.category in (GapCategory.ALREADY_SORTED, GapCategory.REVERSE_SORTED, GapCategory.UNSORTED_SEQUENCE)]
    assert len(order_gaps) == 0, "Sequence ordering gaps must be suppressed for string parameters"

    # Empty string is valid (min_length=0)
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    empty_cands = [c for c in candidates if c.input_data.get("s") == ""]
    if empty_cands:
        assert empty_cands[0].classification == CandidateClassification.VALID.value


# =============================================================================
# 4. Palindrome Number (#9)
# =============================================================================

def test_benchmark_04_palindrome_number():
    """Palindrome Number: -2^31 <= x <= 2^31 - 1."""
    raw = [
        "-2^31 <= x <= 2^31 - 1",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["x"])
    assert len(unresolved) == 0
    assert spec.min_value == -2147483648
    assert spec.max_value == 2147483647
    assert spec.param_specs["x"].min_value == -2147483648
    assert spec.param_specs["x"].max_value == 2147483647

    ctx = ProblemContext(title="Palindrome Number", parameters=["x"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"x": 121})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    gaps = gap_result.gaps

    # Negative numbers and zero are valid equivalence partitions
    neg_gaps = [g for g in gaps if g.category == GapCategory.NEGATIVE_VALUES]
    assert len(neg_gaps) == 1
    assert neg_gaps[0].constraint_validity == ConstraintValidity.VALID

    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)


# =============================================================================
# 5. Valid Parentheses (#20)
# =============================================================================

def test_benchmark_05_valid_parentheses():
    """Valid Parentheses: 1 <= s.length <= 10^4, s consists of parentheses only '()[]{}'."""
    raw = [
        "1 <= s.length <= 10^4",
        "s consists of parentheses only '()[]{}'.",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["s"])
    assert len(unresolved) == 0
    assert spec.min_length == 1
    assert spec.max_length == 10000
    assert spec.allowed_characters == "()[]{}"

    ctx = ProblemContext(title="Valid Parentheses", parameters=["s"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": "()[]{}"})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)

    # Empty string must be suppressed (1 <= s.length)
    empty_gaps = [g for g in gap_result.gaps if g.category == GapCategory.EMPTY_COLLECTION]
    assert len(empty_gaps) == 0

    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    for c in candidates:
        val = c.input_data.get("s", "")
        # All valid candidates must only contain allowed parentheses
        if c.classification == CandidateClassification.VALID.value:
            assert all(ch in "()[]{}" for ch in val)
            assert len(val) >= 1


# =============================================================================
# 6. Search Insert Position (#35)
# =============================================================================

def test_benchmark_06_search_insert_position():
    """Search Insert Position: 1 <= nums.length <= 10^4, distinct values sorted ascending."""
    raw = [
        "1 <= nums.length <= 10^4",
        "-10^4 <= nums[i] <= 10^4",
        "nums contains distinct values sorted in ascending order.",
        "-10^4 <= target <= 10^4",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target"])
    assert len(unresolved) == 0
    assert spec.min_length == 1
    assert spec.max_length == 10000
    assert spec.is_sorted_ascending is True
    assert spec.unique_elements is True
    assert spec.is_strictly_increasing is True

    # Duplicates must be suppressed because distinctness is guaranteed
    ctx = ProblemContext(title="Search Insert Position", parameters=["nums", "target"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 3, 5, 6], "target": 5})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    dup_gaps = [g for g in gap_result.gaps if g.category in (GapCategory.DUPLICATE_ELEMENTS, GapCategory.IDENTICAL_ALL)]
    assert len(dup_gaps) == 0, "Duplicate gaps must be suppressed when unique_elements=True"

    # Candidates must preserve strictly ascending sortedness for valid candidates
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    valid_cands = [c for c in candidates if c.classification == CandidateClassification.VALID.value]
    for vc in valid_cands:
        arr = vc.input_data["nums"]
        for i in range(len(arr) - 1):
            assert arr[i] < arr[i + 1], f"nums must be strictly increasing, got {arr}"


# =============================================================================
# 7. Climbing Stairs (#70)
# =============================================================================

def test_benchmark_07_climbing_stairs():
    """Climbing Stairs: 1 <= n <= 45."""
    raw = [
        "1 <= n <= 45",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["n"])
    assert len(unresolved) == 0
    # Must be recognized as scalar bounds, NOT matrix columns!
    assert spec.min_value == 1
    assert spec.max_value == 45
    assert spec.min_cols is None
    assert spec.max_cols is None
    assert spec.param_specs["n"].min_value == 1
    assert spec.param_specs["n"].max_value == 45

    # Zero value and negative value gaps must be suppressed (n >= 1)
    ctx = ProblemContext(title="Climbing Stairs", parameters=["n"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"n": 2})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    gaps = gap_result.gaps
    zero_neg_gaps = [g for g in gaps if g.category in (GapCategory.ZERO_VALUE, GapCategory.NEGATIVE_VALUES)]
    assert len(zero_neg_gaps) == 0, "Zero and negative value gaps must be suppressed for n >= 1"

    # Boundary synthesis: n=1 and n=45
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    n_values = [c.input_data["n"] for c in candidates if "n" in c.input_data]
    assert 1 in n_values, f"Exact lower bound n=1 must be generated, got {n_values}"
    assert 45 in n_values, f"Exact upper bound n=45 must be generated, got {n_values}"


# =============================================================================
# 8. Set Matrix Zeroes (#73)
# =============================================================================

def test_benchmark_08_set_matrix_zeroes():
    """Set Matrix Zeroes: m == matrix.length, n == matrix[0].length, 1 <= m, n <= 200, -2^31 <= matrix[i][j] <= 2^31 - 1."""
    raw = [
        "m == matrix.length",
        "n == matrix[0].length",
        "1 <= m, n <= 200",
        "-2^31 <= matrix[i][j] <= 2^31 - 1",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["matrix"])
    assert len(unresolved) == 0
    assert spec.min_rows == 1
    assert spec.max_rows == 200
    assert spec.min_cols == 1
    assert spec.max_cols == 200
    assert spec.min_value == -2147483648
    assert spec.max_value == 2147483647

    ctx = ProblemContext(title="Set Matrix Zeroes", parameters=["matrix"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"matrix": [[1, 1, 1], [1, 0, 1], [1, 1, 1]]})
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)

    # Rectangular matrix candidate generated
    rect_cands = [c for c in candidates if len(c.input_data["matrix"]) != len(c.input_data["matrix"][0])]
    assert len(rect_cands) >= 1
    assert rect_cands[0].classification == CandidateClassification.VALID.value


# =============================================================================
# 9. Maximum Depth of Binary Tree (#104)
# =============================================================================

def test_benchmark_09_maximum_depth_binary_tree():
    """Maximum Depth of Binary Tree: range [0, 10^4], -100 <= Node.val <= 100."""
    raw = [
        "The number of nodes in the tree is in the range [0, 10^4].",
        "-100 <= Node.val <= 100",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["root"])
    assert len(unresolved) == 0
    assert spec.min_length == 0
    assert spec.max_length == 10000
    assert spec.min_value == -100
    assert spec.max_value == 100

    ctx = ProblemContext(title="Maximum Depth of Binary Tree", parameters=["root"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"root": [3, 9, 20, None, None, 15, 7]})
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)


# =============================================================================
# 10. House Robber (#198)
# =============================================================================

def test_benchmark_10_house_robber():
    """House Robber: 1 <= nums.length <= 100, 0 <= nums[i] <= 400."""
    raw = [
        "1 <= nums.length <= 100",
        "0 <= nums[i] <= 400",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums"])
    assert len(unresolved) == 0
    assert spec.min_length == 1
    assert spec.max_length == 100
    assert spec.min_value == 0
    assert spec.max_value == 400

    # Negative values and empty collection must be suppressed
    ctx = ProblemContext(title="House Robber", parameters=["nums"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 2, 3, 1]})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    gaps = gap_result.gaps
    assert not any(g.category == GapCategory.EMPTY_COLLECTION for g in gaps)
    assert not any(g.category == GapCategory.NEGATIVE_VALUES for g in gaps)

    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    for c in candidates:
        if c.classification == CandidateClassification.VALID.value:
            arr = c.input_data["nums"]
            assert len(arr) >= 1
            assert all(0 <= x <= 400 for x in arr)


# =============================================================================
# 11. Contains Duplicate (#217)
# =============================================================================

def test_benchmark_11_contains_duplicate():
    """Contains Duplicate: 1 <= nums.length <= 10^5, -10^9 <= nums[i] <= 10^9."""
    raw = [
        "1 <= nums.length <= 10^5",
        "-10^9 <= nums[i] <= 10^9",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums"])
    assert len(unresolved) == 0
    assert spec.min_length == 1
    assert spec.max_length == 100000
    assert spec.min_value == -1000000000
    assert spec.max_value == 1000000000

    ctx = ProblemContext(title="Contains Duplicate", parameters=["nums"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 2, 3, 1]})
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)


# =============================================================================
# 12. Valid Anagram (#242)
# =============================================================================

def test_benchmark_12_valid_anagram():
    """Valid Anagram: 1 <= s.length, t.length <= 5 * 10^4, lowercase English letters."""
    raw = [
        "1 <= s.length, t.length <= 5 * 10^4",
        "s and t consist of lowercase English letters.",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["s", "t"])
    assert len(unresolved) == 0
    assert spec.min_length == 1
    assert spec.max_length == 50000
    assert spec.allowed_characters == "a-z"
    assert spec.param_specs["s"].min_length == 1
    assert spec.param_specs["t"].min_length == 1
    assert spec.param_specs["s"].allowed_characters == "a-z"
    assert spec.param_specs["t"].allowed_characters == "a-z"

    ctx = ProblemContext(title="Valid Anagram", parameters=["s", "t"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"s": "anagram", "t": "nagaram"})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)

    # Empty string suppressed
    empty_gaps = [g for g in gap_result.gaps if g.category == GapCategory.EMPTY_COLLECTION]
    assert len(empty_gaps) == 0

    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)


# =============================================================================
# 13. Maximum Average Subarray I (#643)
# =============================================================================

def test_benchmark_13_maximum_average_subarray():
    """Maximum Average Subarray I: 1 <= k <= n <= 10^5, -10^4 <= nums[i] <= 10^4."""
    raw = [
        "n == nums.length",
        "1 <= k <= n <= 10^5",
        "-10^4 <= nums[i] <= 10^4",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "k"])
    assert len(unresolved) == 0
    # Parameter bounds isolation: k's lower bound (1) must NOT clobber nums[i] min_value (-10000)!
    assert spec.param_specs["k"].min_value == 1
    assert spec.param_specs["nums"].min_value == -10000
    assert spec.param_specs["nums"].max_value == 10000

    # Cross-parameter constraint recognized
    assert len(spec.cross_constraints) >= 1
    cross_c = spec.cross_constraints[0]
    assert cross_c.relation_type in ("WINDOW_LEQ_ARRAY_LENGTH", "LEQ_LENGTH")

    # Gap detection: zero value for k is suppressed (k >= 1), but negative values for nums are permitted
    ctx = ProblemContext(title="Maximum Average Subarray I", parameters=["nums", "k"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [1, 12, -5, -6, 50, 3], "k": 4})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    k_zero_gaps = [g for g in gap_result.gaps if g.category == GapCategory.ZERO_VALUE and g.param_name == "k"]
    assert len(k_zero_gaps) == 0

    # Relationship preservation: never generate k > len(nums) for VALID candidates
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    valid_cands = [c for c in candidates if c.classification == CandidateClassification.VALID.value]
    for vc in valid_cands:
        assert vc.input_data["k"] <= len(vc.input_data["nums"]), (
            f"Candidate {vc.id} violated k <= len(nums): k={vc.input_data['k']}, len={len(vc.input_data['nums'])}"
        )


# =============================================================================
# 14. Binary Search (#704)
# =============================================================================

def test_benchmark_14_binary_search():
    """Binary Search: 1 <= nums.length <= 10^4, -10^4 < nums[i], target < 10^4, unique, sorted ascending."""
    raw = [
        "1 <= nums.length <= 10^4",
        "-10^4 < nums[i], target < 10^4",
        "All the integers in nums are unique.",
        "nums is sorted in ascending order.",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["nums", "target"])
    assert len(unresolved) == 0
    assert spec.min_length == 1
    assert spec.max_length == 10000
    assert spec.is_sorted_ascending is True
    assert spec.unique_elements is True
    assert spec.is_strictly_increasing is True

    # Duplicates suppressed
    ctx = ProblemContext(title="Binary Search", parameters=["nums", "target"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"nums": [-1, 0, 3, 5, 9, 12], "target": 9})
    evaluator = CoverageGapEvaluator()
    gap_result = evaluator.evaluate([sample], context=ctx)
    dup_gaps = [g for g in gap_result.gaps if g.category in (GapCategory.DUPLICATE_ELEMENTS, GapCategory.IDENTICAL_ALL)]
    assert len(dup_gaps) == 0

    # Candidates must preserve strictly ascending sortedness for valid candidates
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)
    valid_cands = [c for c in candidates if c.classification == CandidateClassification.VALID.value]
    for vc in valid_cands:
        arr = vc.input_data["nums"]
        for i in range(len(arr) - 1):
            assert arr[i] < arr[i + 1], f"nums must be strictly increasing, got {arr}"


# =============================================================================
# 15. Twisted Mirror Path Count (#3665)
# =============================================================================

def test_benchmark_15_twisted_mirror_path_count():
    """Twisted Mirror Path Count: 2 <= m, n <= 500, grid[r][c] either 0 or 1, grid[0][0] == grid[m-1][n-1] == 0."""
    raw = [
        r"m == \text{grid.length}",
        r"n == \text{grid}[i].\text{length}",
        r"2 <= m,\ n <= 500",
        r"\text{grid}[r][c] \text{ is either } 0 \text{ or } 1.",
        r"\text{grid}[0][0] == \text{grid}[m - 1][n - 1] == 0",
    ]
    spec, unresolved = parse_constraint_expressions(raw, known_parameters=["grid"])
    assert len(unresolved) == 0
    assert spec.min_rows == 2
    assert spec.max_rows == 500
    assert spec.min_cols == 2
    assert spec.max_cols == 500
    assert spec.allowed_values == [0, 1]
    assert spec.endpoints_zero is True

    ctx = ProblemContext(title="Twisted Mirror Path Count", parameters=["grid"], constraints=raw, constraint_spec=spec)
    sample = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"grid": [[0, 1, 0], [1, 0, 1], [0, 1, 0]]})
    synth = TargetedTestSynthesizer()
    candidates = synth.synthesize([sample], context=ctx)
    assert len(candidates) > 0
    assert_candidate_invariants(candidates)

    valid_cands = [c for c in candidates if c.classification == CandidateClassification.VALID.value]
    for vc in valid_cands:
        mat = vc.input_data["grid"]
        assert len(mat) >= 2
        assert len(mat[0]) >= 2
        assert mat[0][0] == 0, f"grid[0][0] must be 0, got {mat[0][0]}"
        assert mat[-1][-1] == 0, f"grid[m-1][n-1] must be 0, got {mat[-1][-1]}"
        for r in mat:
            for cell in r:
                assert cell in (0, 1)


# =============================================================================
# End-to-End EdgeMind Service Benchmark Simulation
# =============================================================================

def test_benchmark_end_to_end_service_execution():
    """Verify analyze_edgemind runs end-to-end on benchmark problems with zero exceptions."""
    res_twosum = analyze_edgemind(
        code="def twoSum(nums, target): return [0, 1]",
        test_cases=[{"id": "s1", "input_data": {"nums": [2, 7, 11, 15], "target": 9}}],
        problem_context={
            "title": "Two Sum",
            "parameters": ["nums", "target"],
            "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9", "-10^9 <= target <= 10^9", "Only one valid answer exists."],
        },
    )
    assert res_twosum["baseline_available"] is True
    candidates_twosum = res_twosum["test_intelligence"]["generated_candidates"]
    assert len(candidates_twosum) > 0

    res_subarray = analyze_edgemind(
        code="def findMaxAverage(nums, k): return 12.75",
        test_cases=[{"id": "s1", "input_data": {"nums": [1, 12, -5, -6, 50, 3], "k": 4}}],
        problem_context={
            "title": "Maximum Average Subarray I",
            "parameters": ["nums", "k"],
            "constraints": ["n == nums.length", "1 <= k <= n <= 10^5", "-10^4 <= nums[i] <= 10^4"],
        },
    )
    assert res_subarray["baseline_available"] is True
    candidates_subarray = res_subarray["test_intelligence"]["generated_candidates"]
    assert len(candidates_subarray) > 0
    for cand in candidates_subarray:
        assert cand.get("expected_output") is None
        assert cand.get("is_expected_output_verified") is False
