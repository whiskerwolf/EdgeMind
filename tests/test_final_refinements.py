"""
EdgeMind Adaptive Test Intelligence - Final Intelligence Refinement Regression Suite.

Verifies the final v1.0.0 refinements across the 4 benchmark problems:
1. Maximum Average Subarray I (#643)
2. Search Insert Position (#35)
3. Valid Parentheses (#20)
4. Maximum Depth of Binary Tree (#104)
"""

import pytest
from core.test_intelligence.constraint_parser import (
    classify_candidate,
    parse_constraint_expressions,
    validate_and_analyze_tree,
)
from core.test_intelligence.extractor import FeatureProfileExtractor
from core.test_intelligence.gap_detector import CoverageGapEvaluator, GapCategory
from core.test_intelligence.models import (
    CandidateClassification,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.synthesizer import TargetedTestSynthesizer


class TestMaximumAverageSubarrayIRefinements:
    """Verifies refinements for Maximum Average Subarray I (#643)."""

    @pytest.fixture
    def setup_problem(self):
        raw = [
            "n == nums.length",
            "1 <= k <= n <= 10^5",
            "-10^4 <= nums[i] <= 10^4",
        ]
        spec, unres = parse_constraint_expressions(raw, known_parameters=["nums", "k"])
        ctx = ProblemContext(
            title="Maximum Average Subarray I",
            constraints=raw,
            constraint_spec=spec,
            parameters=["nums", "k"],
        )
        samples = [
            TestCase(
                id="sample-1",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"nums": [1, 12, -5, -6, 50, 3], "k": 4},
                expected_output=12.75,
            ),
            TestCase(
                id="sample-2",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"nums": [5], "k": 1},
                expected_output=5.0,
            ),
        ]
        return ctx, spec, samples

    def test_k1_coverage_detection_not_reported_as_missing(self, setup_problem):
        """When public samples contain nums=[5], k=1, minimum k=1 is observed and NOT reported as missing."""
        ctx, spec, samples = setup_problem
        extractor = FeatureProfileExtractor(context=ctx)
        profile = extractor.extract(samples, context=ctx)
        evaluator = CoverageGapEvaluator(extractor=extractor)
        gap_res = evaluator.evaluate(samples, context=ctx, profile=profile)

        k_min_gaps = [
            g for g in gap_res.gaps
            if g.param_name == "k" and g.category == GapCategory.LOWER_CONSTRAINT_BOUND
        ]
        assert len(k_min_gaps) == 0, f"k=1 was reported missing despite being present in sample: {k_min_gaps}"

    def test_exact_maximum_boundary_candidate(self, setup_problem):
        """Exact maximum boundary candidate has len(nums) == 100000 and k == 100000, classified as VALID."""
        ctx, spec, samples = setup_problem
        synth = TargetedTestSynthesizer()
        candidates = synth.synthesize(samples, context=ctx, max_candidates=100)

        max_cands = [
            c for c in candidates
            if len(c.input_data.get("nums", [])) == 100000 and c.input_data.get("k") == 100000
        ]
        assert len(max_cands) >= 1, "Failed to synthesize candidate with len(nums) == 100000 and k == 100000"
        for mc in max_cands:
            assert mc.classification == CandidateClassification.VALID.value

    def test_negative_values_preserved_and_valid(self, setup_problem):
        """Negative values within [-10000, 10000] are valid elements."""
        ctx, spec, samples = setup_problem
        tc_neg = TestCase(
            id="test-neg",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"nums": [-10000, -500, 0, 10000], "k": 3},
        )
        cls, reason = classify_candidate(tc_neg, spec, context=ctx)
        assert cls == CandidateClassification.VALID.value

    def test_k_greater_than_len_nums_strictly_robustness_probe(self, setup_problem):
        """Never classify as VALID when k > len(nums); must be ROBUSTNESS_PROBE."""
        ctx, spec, samples = setup_problem
        tc_invalid_k = TestCase(
            id="test-k-gt-len",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"nums": [1, 2, 3], "k": 5},
        )
        cls, reason = classify_candidate(tc_invalid_k, spec, context=ctx)
        assert cls == CandidateClassification.ROBUSTNESS_PROBE.value
        assert "exceeds" in reason.lower() or "cross-parameter" in reason.lower()


class TestSearchInsertPositionRefinements:
    """Verifies refinements for Search Insert Position (#35)."""

    @pytest.fixture
    def setup_problem(self):
        raw = [
            "1 <= nums.length <= 10^4",
            "-10^4 <= nums[i] <= 10^4",
            "nums contains distinct values sorted in ascending order.",
            "-10^4 <= target <= 10^4",
        ]
        spec, unres = parse_constraint_expressions(raw, known_parameters=["nums", "target"])
        ctx = ProblemContext(
            title="Search Insert Position",
            constraints=raw,
            constraint_spec=spec,
            parameters=["nums", "target"],
        )
        samples = [
            TestCase(
                id="sample-1",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"nums": [1, 3, 5, 6], "target": 5},
                expected_output=2,
            )
        ]
        return ctx, spec, samples

    def test_maximum_length_candidate_synthesis_exact_array_properties(self, setup_problem):
        """Maximum-length candidate has exactly 10,000 array elements, strictly ascending, unique, and bounded."""
        ctx, spec, samples = setup_problem
        synth = TargetedTestSynthesizer()
        candidates = synth.synthesize(samples, context=ctx, max_candidates=50)

        max_len_cands = [
            c for c in candidates
            if "nums" in c.input_data and isinstance(c.input_data["nums"], (list, tuple)) and len(c.input_data["nums"]) == 10000
        ]
        assert len(max_len_cands) >= 1, "Missing maximum length 10,000 candidate for nums"
        cand = max_len_cands[0]
        arr = cand.input_data["nums"]
        target = cand.input_data["target"]

        # 1. Exact length 10,000
        assert len(arr) == 10000

        # 2. Strictly ascending order (arr[i] < arr[i+1])
        assert all(arr[i] < arr[i+1] for i in range(len(arr) - 1)), "Array is not strictly ascending"

        # 3. All unique elements
        assert len(set(arr)) == 10000, "Array elements are not unique (contains repeated elements)"

        # 4. Elements within bounds [-10000, 10000]
        assert all(-10000 <= x <= 10000 for x in arr), "Array elements exceed [-10000, 10000] bounds"

        # 5. Target within bounds [-10000, 10000]
        assert -10000 <= target <= 10000, f"Target {target} exceeds [-10000, 10000] bounds"

        # 6. Classified as VALID
        assert cand.classification == CandidateClassification.VALID.value

    def test_deliberate_duplicates_and_unsorted_are_robustness_probes(self, setup_problem):
        """Deliberately duplicated or unsorted candidates remain ROBUSTNESS_PROBE."""
        ctx, spec, samples = setup_problem

        # Duplicated array
        tc_dup = TestCase(
            id="test-dup",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"nums": [1, 2, 2, 5], "target": 2},
        )
        cls_dup, r_dup = classify_candidate(tc_dup, spec, context=ctx)
        assert cls_dup == CandidateClassification.ROBUSTNESS_PROBE.value

        # Unsorted array
        tc_unsort = TestCase(
            id="test-unsort",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"nums": [5, 1, 3], "target": 3},
        )
        cls_unsort, r_unsort = classify_candidate(tc_unsort, spec, context=ctx)
        assert cls_unsort == CandidateClassification.ROBUSTNESS_PROBE.value


class TestValidParenthesesRefinements:
    """Verifies refinements for Valid Parentheses (#20)."""

    @pytest.fixture
    def setup_problem(self):
        raw = [
            "1 <= s.length <= 10^4",
            "s consists of parentheses only '()[]{}'.",
        ]
        spec, unres = parse_constraint_expressions(raw, known_parameters=["s"])
        ctx = ProblemContext(
            title="Valid Parentheses",
            constraints=raw,
            constraint_spec=spec,
            parameters=["s"],
        )
        samples = [
            TestCase(
                id="sample-1",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"s": "()"},
                expected_output=True,
            ),
            TestCase(
                id="sample-2",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"s": "()[]{}"},
                expected_output=True,
            ),
            TestCase(
                id="sample-3",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"s": "(]"},
                expected_output=False,
            ),
        ]
        return ctx, spec, samples

    def test_avoid_duplicate_singleton_and_lower_bound_gaps(self, setup_problem):
        """When min_length == 1, duplicate SINGLETON gap is suppressed in favor of LOWER_CONSTRAINT_BOUND."""
        ctx, spec, samples = setup_problem
        extractor = FeatureProfileExtractor(context=ctx)
        profile = extractor.extract(samples, context=ctx)
        evaluator = CoverageGapEvaluator(extractor=extractor)
        gap_res = evaluator.evaluate(samples, context=ctx, profile=profile)

        gap_cats = [g.category for g in gap_res.gaps]
        has_singleton = GapCategory.SINGLETON in gap_cats
        has_lower_bound = GapCategory.LOWER_CONSTRAINT_BOUND in gap_cats

        assert not (has_singleton and has_lower_bound), "Both SINGLETON and LOWER_CONSTRAINT_BOUND were reported"

    def test_exact_maximum_length_string_preserved(self, setup_problem):
        """Preserves exact maximum length (10,000 characters) composed of allowed bracket characters."""
        ctx, spec, samples = setup_problem
        synth = TargetedTestSynthesizer()
        candidates = synth.synthesize(samples, context=ctx, max_candidates=50)

        max_cands = [
            c for c in candidates
            if "s" in c.input_data and isinstance(c.input_data["s"], str) and len(c.input_data["s"]) == 10000
        ]
        assert len(max_cands) >= 1, "Missing exact 10,000 maximum string length candidate"
        for mc in max_cands:
            s_val = mc.input_data["s"]
            assert len(s_val) == 10000
            assert all(ch in "()[]{}" for ch in s_val), "Candidate contains characters outside '()[]{}'"
            assert mc.classification == CandidateClassification.VALID.value

    def test_bracket_specific_patterns_and_input_validity(self, setup_problem):
        """Verifies bracket patterns: balanced nesting, mismatched, incorrect nesting, consecutive pairs, singletons."""
        ctx, spec, samples = setup_problem

        # Interleaved incorrect nesting is valid input syntax (even if algorithm returns False)
        tc_interleaved = TestCase(
            id="test-interleaved",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"s": "([)]"},
        )
        cls, reason = classify_candidate(tc_interleaved, spec, context=ctx)
        assert cls == CandidateClassification.VALID.value

        # Mismatched bracket pair is valid input syntax
        tc_mismatch = TestCase(
            id="test-mismatch",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"s": "(]"},
        )
        cls_m, _ = classify_candidate(tc_mismatch, spec, context=ctx)
        assert cls_m == CandidateClassification.VALID.value

        # Balanced nesting is valid input syntax
        tc_balanced = TestCase(
            id="test-balanced",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"s": "{[()]}"},
        )
        cls_b, _ = classify_candidate(tc_balanced, spec, context=ctx)
        assert cls_b == CandidateClassification.VALID.value

        # Consecutive pairs is valid input syntax
        tc_consec = TestCase(
            id="test-consec",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"s": "()[]{}"},
        )
        cls_c, _ = classify_candidate(tc_consec, spec, context=ctx)
        assert cls_c == CandidateClassification.VALID.value

        # Singleton is valid input syntax
        tc_single = TestCase(
            id="test-singleton",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"s": "("},
        )
        cls_s, _ = classify_candidate(tc_single, spec, context=ctx)
        assert cls_s == CandidateClassification.VALID.value


class TestMaximumDepthOfBinaryTreeRefinements:
    """Verifies refinements for Maximum Depth of Binary Tree (#104)."""

    @pytest.fixture
    def setup_problem(self):
        raw = [
            "The number of nodes in the tree is in the range [0, 10^4].",
            "-100 <= Node.val <= 100",
        ]
        spec, unres = parse_constraint_expressions(raw, known_parameters=["root"])
        ctx = ProblemContext(
            title="Maximum Depth of Binary Tree",
            constraints=raw,
            constraint_spec=spec,
            parameters=["root"],
        )
        samples = [
            TestCase(
                id="sample-1",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"root": [3, 9, 20, None, None, 15, 7]},
                expected_output=3,
            ),
            TestCase(
                id="sample-2",
                source=TestCaseSource.PUBLIC_SAMPLE,
                input_data={"root": [1, None, 2]},
                expected_output=2,
            ),
        ]
        return ctx, spec, samples

    def test_empty_tree_root_is_classified_valid(self, setup_problem):
        """Empty tree root = [] or root = None is valid and classified as VALID."""
        ctx, spec, samples = setup_problem
        tc_empty_list = TestCase(
            id="test-empty-list",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"root": []},
        )
        cls_list, _ = classify_candidate(tc_empty_list, spec, context=ctx)
        assert cls_list == CandidateClassification.VALID.value

        tc_empty_none = TestCase(
            id="test-empty-none",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"root": None},
        )
        cls_none, _ = classify_candidate(tc_empty_none, spec, context=ctx)
        assert cls_none == CandidateClassification.VALID.value

    def test_tree_metrics_distinguish_nodes_length_and_depth(self):
        """Distinguishes actual non-null nodes (N), serialized length (L), and maximum tree depth (D)."""
        # Empty tree: N=0, L=0, D=0
        is_v, n, l, d, err = validate_and_analyze_tree([])
        assert (is_v, n, l, d) == (True, 0, 0, 0)

        # Single-node tree: N=1, L=1, D=1
        is_v, n, l, d, err = validate_and_analyze_tree([1])
        assert (is_v, n, l, d) == (True, 1, 1, 1)

        # Left-skewed: N=3, L=4, D=3
        is_v, n, l, d, err = validate_and_analyze_tree([1, 2, None, 3])
        assert (is_v, n, l, d) == (True, 3, 4, 3)

        # Right-skewed: N=3, L=5, D=3
        is_v, n, l, d, err = validate_and_analyze_tree([1, None, 2, None, 3])
        assert (is_v, n, l, d) == (True, 3, 5, 3)

        # Balanced complete tree: N=7, L=7, D=3
        is_v, n, l, d, err = validate_and_analyze_tree([1, 2, 3, 4, 5, 6, 7])
        assert (is_v, n, l, d) == (True, 7, 7, 3)

        # Sparse tree: N=5, L=7, D=3
        is_v, n, l, d, err = validate_and_analyze_tree([1, 2, 3, None, 4, None, 5])
        assert (is_v, n, l, d) == (True, 5, 7, 3)

        # Max 10,000-node tree: N=10000, L=10000, D=14
        is_v, n, l, d, err = validate_and_analyze_tree([1] * 10000)
        assert (is_v, n, l, d) == (True, 10000, 10000, 14)

    def test_malformed_tree_serialization_detected(self, setup_problem):
        """Malformed tree serialization (orphan nodes under null) is rejected as ROBUSTNESS_PROBE."""
        ctx, spec, samples = setup_problem
        # [1, None, None, 2]: children cannot appear under exhausted/null parents
        tc_malformed = TestCase(
            id="test-malformed-tree",
            source=TestCaseSource.GENERATED_TEST,
            input_data={"root": [1, None, None, 2]},
        )
        cls, reason = classify_candidate(tc_malformed, spec, context=ctx)
        assert cls == CandidateClassification.ROBUSTNESS_PROBE.value
        assert "orphan" in reason.lower() or "structural" in reason.lower()

    def test_synthesis_generates_all_required_tree_variants(self, setup_problem):
        """Synthesizer generates empty, single-node, left-skewed, right-skewed, balanced, sparse, and max tree."""
        ctx, spec, samples = setup_problem
        synth = TargetedTestSynthesizer()
        candidates = synth.synthesize(samples, context=ctx, max_candidates=50)

        cand_ids = [c.id for c in candidates]
        assert any("empty" in cid for cid in cand_ids), "Missing empty tree candidate"
        assert any("single" in cid for cid in cand_ids), "Missing single-node tree candidate"
        assert any("left-skewed" in cid for cid in cand_ids), "Missing left-skewed tree candidate"
        assert any("right-skewed" in cid for cid in cand_ids), "Missing right-skewed tree candidate"
        assert any("balanced" in cid for cid in cand_ids), "Missing balanced tree candidate"
        assert any("sparse" in cid for cid in cand_ids), "Missing sparse tree candidate"
        assert any("max" in cid for cid in cand_ids), "Missing maximum size tree candidate"

        # All generated tree candidates must be classified as VALID
        for cand in candidates:
            if "tree" in cand.id or "root" in cand.id:
                assert cand.classification == CandidateClassification.VALID.value

