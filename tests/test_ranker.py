"""
Unit and Adversarial Tests for EdgeMind Candidate Ranking and Semantic Deduplication (Phase 5).
"""

import copy
import pytest
from typing import Any, Dict, List

from core.test_intelligence.gap_detector import (
    ConstraintValidity,
    CoverageGap,
    GapSeverity,
)
from core.test_intelligence.models import (
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.ranker import (
    CandidateRanker,
    CandidateRankingResult,
    RankedCandidate,
    RankingScore,
    RankingWeights,
)
from core.test_intelligence.synthesizer import TargetedTestSynthesizer


# =============================================================================
# Helper Fixtures & Builders
# =============================================================================


def make_candidate(
    cand_id: str,
    target_gap: GapCategory,
    input_data: Dict[str, Any],
    param_name: str = "nums",
    relevance_score: float = 0.5,
    is_boundary: bool = False,
    is_performance: bool = False,
) -> TestCase:
    """Helper to construct synthetic candidate test cases with consistent metadata."""
    return TestCase(
        id=cand_id,
        source=TestCaseSource.GENERATED_TEST,
        input_data=input_data,
        expected_output=None,
        is_expected_output_verified=False,
        label=f"Candidate {cand_id}",
        rationale=f"Synthesized for parameter '{param_name}' to cover {target_gap.value}",
        target_gap=target_gap,
        relevance_score=relevance_score,
        is_boundary=is_boundary,
        is_performance=is_performance,
    )


# =============================================================================
# 1. Deterministic Ranking
# =============================================================================


def test_deterministic_ranking_repeated_runs():
    """Ranker produces byte-for-byte identical order, scores, and explanations across runs."""
    c1 = make_candidate("gen-empty-nums", GapCategory.EMPTY_COLLECTION, {"nums": []}, relevance_score=0.9, is_boundary=True)
    c2 = make_candidate("gen-zero-val", GapCategory.ZERO_VALUE, {"val": 0}, param_name="val", relevance_score=0.7)
    c3 = make_candidate("gen-dup-nums", GapCategory.DUPLICATE_ELEMENTS, {"nums": [1, 1, 2]}, relevance_score=0.6)

    ranker = CandidateRanker()
    res1 = ranker.rank_and_select([c1, c2, c3])
    res2 = ranker.rank_and_select([c1, c2, c3])

    assert [c.id for c in res1.selected_candidates] == [c.id for c in res2.selected_candidates]
    assert [r.score for r in res1.ranked_candidates] == [r.score for r in res2.ranked_candidates]
    assert res1.explanations == res2.explanations


def test_no_randomness_in_tie_breaking():
    """Ties are broken strictly by deterministic criteria (gap category, ID, canonical signature)."""
    # Two candidates with identical severity, relevance, boundary flags, and gap
    c_a = make_candidate("gen-zero-a", GapCategory.ZERO_VALUE, {"a": 0}, param_name="a", relevance_score=0.5)
    c_b = make_candidate("gen-zero-b", GapCategory.ZERO_VALUE, {"b": 0}, param_name="b", relevance_score=0.5)

    ranker = CandidateRanker()
    # Regardless of input list order, deterministic tie-breaking produces consistent rank
    res_ab = ranker.rank_and_select([c_a, c_b])
    res_ba = ranker.rank_and_select([c_b, c_a])

    assert [c.id for c in res_ab.selected_candidates] == [c.id for c in res_ba.selected_candidates]


# =============================================================================
# 2. Severity and Relevance Ordering
# =============================================================================


def test_gap_severity_prioritization():
    """HIGH severity gaps rank above MEDIUM, and MEDIUM rank above LOW when relevance is equal."""
    c_high = make_candidate("gen-high", GapCategory.EMPTY_COLLECTION, {"nums": []}, relevance_score=0.5)
    c_med = make_candidate("gen-med", GapCategory.ZERO_VALUE, {"val": 0}, param_name="val", relevance_score=0.5)
    c_low = make_candidate("gen-low", GapCategory.MATRIX_DIMENSIONS, {"grid": [[1, 2]]}, param_name="grid", relevance_score=0.5)

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c_low, c_med, c_high])

    selected_ids = [c.id for c in result.selected_candidates]
    assert selected_ids == ["gen-high", "gen-med", "gen-low"]
    assert result.ranked_candidates[0].score > result.ranked_candidates[1].score
    assert result.ranked_candidates[1].score > result.ranked_candidates[2].score


def test_relevance_score_ordering():
    """Within the same severity level, higher relevance score outranks lower relevance score."""
    c_low_rel = make_candidate("gen-dup-low", GapCategory.DUPLICATE_ELEMENTS, {"nums": [1, 1]}, relevance_score=0.2)
    c_high_rel = make_candidate("gen-dup-high", GapCategory.DUPLICATE_ELEMENTS, {"nums": [2, 2]}, relevance_score=0.9)

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c_low_rel, c_high_rel])

    assert result.selected_candidates[0].id == "gen-dup-high"
    assert result.selected_candidates[1].id == "gen-dup-low"


# =============================================================================
# 3. Structural Features: Boundary, Failure Family, and Performance
# =============================================================================


def test_boundary_case_prioritization():
    """Candidates marked is_boundary receive boundary bonus and rank higher."""
    c_non_bound = make_candidate("gen-mid-val", GapCategory.ZERO_VALUE, {"val": 5}, relevance_score=0.5, is_boundary=False)
    c_bound = make_candidate("gen-bound-val", GapCategory.ZERO_VALUE, {"val": 0}, relevance_score=0.5, is_boundary=True)

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c_non_bound, c_bound])

    top = result.ranked_candidates[0]
    assert top.candidate.id == "gen-bound-val"
    assert top.score_breakdown.boundary_score == ranker.weights.boundary_bonus


def test_failure_family_prioritization():
    """Failure family extrapolation candidates receive failure family bonus."""
    c_normal = make_candidate("gen-ord", GapCategory.UNSORTED_SEQUENCE, {"nums": [3, 1, 2]}, relevance_score=0.6)
    c_fail = make_candidate("gen-fail-var", GapCategory.FAILURE_FAMILY_EXTRAPOLATION, {"nums": [10, 20]}, relevance_score=0.6)

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c_normal, c_fail])

    assert result.selected_candidates[0].id == "gen-fail-var"
    assert result.ranked_candidates[0].score_breakdown.failure_family_score == ranker.weights.failure_family_bonus


def test_performance_boundary_prioritization():
    """Upper constraint scale performance candidates receive performance bonus."""
    c_standard = make_candidate("gen-med", GapCategory.SINGLETON, {"nums": [1]}, relevance_score=0.5)
    c_perf = make_candidate("gen-perf", GapCategory.UPPER_CONSTRAINT_BOUND, {"nums": [1] * 100}, relevance_score=0.5, is_performance=True)

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c_standard, c_perf])

    assert result.selected_candidates[0].id == "gen-perf"
    assert result.ranked_candidates[0].score_breakdown.performance_score == ranker.weights.performance_bonus


# =============================================================================
# 4. Diversity Across Parameters & Gaps (Marginal Utility)
# =============================================================================


def test_diversity_prioritizes_unrepresented_parameters():
    """Ranker avoids saturating selection with 1 parameter when other parameters have untested gaps."""
    # 3 candidates for 'nums', 1 candidate for 'target'
    c_nums_1 = make_candidate("c-nums-1", GapCategory.DUPLICATE_ELEMENTS, {"nums": [1, 1], "target": 5}, param_name="nums", relevance_score=0.7)
    c_nums_2 = make_candidate("c-nums-2", GapCategory.DUPLICATE_ELEMENTS, {"nums": [2, 2], "target": 5}, param_name="nums", relevance_score=0.65)
    c_target = make_candidate("c-target-1", GapCategory.ZERO_VALUE, {"nums": [1, 2], "target": 0}, param_name="target", relevance_score=0.6)

    ranker = CandidateRanker(default_max_selected=2)
    result = ranker.rank_and_select([c_nums_1, c_nums_2, c_target])

    selected_ids = [c.id for c in result.selected_candidates]
    # c_nums_1 is chosen first, then c_target is chosen because redundant partition penalty on c_nums_2
    assert "c-nums-1" in selected_ids
    assert "c-target-1" in selected_ids
    assert "c-nums-2" not in selected_ids


def test_diversity_penalty_explanation():
    """Redundant candidates targeting the same partition record a diversity penalty in score breakdown."""
    c1 = make_candidate("c1", GapCategory.DUPLICATE_ELEMENTS, {"nums": [1, 1]}, param_name="nums")
    c2 = make_candidate("c2", GapCategory.DUPLICATE_ELEMENTS, {"nums": [2, 2]}, param_name="nums")

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c1, c2])

    assert result.ranked_candidates[0].score_breakdown.diversity_penalty == 0.0
    assert result.ranked_candidates[1].score_breakdown.diversity_penalty > 0.0
    assert "Redundant Partition Penalty" in result.ranked_candidates[1].explanation


# =============================================================================
# 5. Semantic Deduplication
# =============================================================================


def test_exact_canonical_duplicates_eliminated():
    """Candidates with identical canonical inputs are deduplicated to single selection."""
    c1 = make_candidate("cand-1", GapCategory.EMPTY_COLLECTION, {"a": [], "b": 1})
    c2 = make_candidate("cand-2", GapCategory.EMPTY_COLLECTION, {"b": 1.0, "a": []})  # Equivalent canonical representation

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c1, c2])

    assert len(result.selected_candidates) == 1
    assert result.exact_duplicates_removed == 1


def test_candidates_duplicating_existing_test_cases_discarded():
    """Candidates that produce inputs identical to existing test cases are discarded."""
    existing_tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    cand_dup = make_candidate("gen-dup", GapCategory.ALREADY_SORTED, {"nums": [1, 2, 3]})
    cand_new = make_candidate("gen-new", GapCategory.REVERSE_SORTED, {"nums": [3, 2, 1]})

    ranker = CandidateRanker()
    result = ranker.rank_and_select([cand_dup, cand_new], existing_tests=[existing_tc])

    assert len(result.selected_candidates) == 1
    assert result.selected_candidates[0].id == "gen-new"
    assert result.exact_duplicates_removed == 1


def test_preserve_meaningfully_distinct_cases():
    """Distinct boundary positions (e.g. index 0 vs index -1) are preserved, not collapsed."""
    c_first = make_candidate("gen-first", GapCategory.TARGET_AT_BOUNDARIES, {"nums": [10, 20], "target": 10}, is_boundary=True)
    c_last = make_candidate("gen-last", GapCategory.TARGET_AT_BOUNDARIES, {"nums": [10, 20], "target": 20}, is_boundary=True)

    ranker = CandidateRanker(default_max_selected=5)
    result = ranker.rank_and_select([c_first, c_last])

    assert len(result.selected_candidates) == 2
    selected_targets = [c.input_data["target"] for c in result.selected_candidates]
    assert 10 in selected_targets and 20 in selected_targets


# =============================================================================
# 6. Candidate Limits & Empty Pools
# =============================================================================


def test_max_selected_ceiling_respected():
    """CandidateRanker respects max_selected limit while preserving full ranking in ranked_candidates."""
    cands = [
        make_candidate(f"c-{i}", GapCategory.ZERO_VALUE, {"k": i}, param_name="k", relevance_score=0.1 * i)
        for i in range(10)
    ]
    ranker = CandidateRanker(default_max_selected=3)
    result = ranker.rank_and_select(cands, max_selected=4)

    assert len(result.selected_candidates) == 4
    assert len(result.ranked_candidates) == 10
    assert result.selection_limit == 4


def test_empty_candidate_set_handling():
    """Empty candidate pool returns valid empty result without crashing."""
    ranker = CandidateRanker()
    result = ranker.rank_and_select([])

    assert len(result.selected_candidates) == 0
    assert len(result.ranked_candidates) == 0
    assert result.total_evaluated == 0
    assert "No candidates provided" in result.explanations[0]


def test_all_candidates_duplicate_returns_empty_selection():
    """When all candidates match existing tests, returns empty selection with clear explanation."""
    tc = TestCase(id="sample-1", source=TestCaseSource.PUBLIC_SAMPLE, input_data={"x": 5})
    c1 = make_candidate("c1", GapCategory.ZERO_VALUE, {"x": 5})

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c1], existing_tests=[tc])

    assert len(result.selected_candidates) == 0
    assert result.exact_duplicates_removed == 1
    assert "All candidates were exact duplicates" in result.explanations[0]


# =============================================================================
# 7. Input Immutability & Provenance Integrity
# =============================================================================


def test_input_immutability_under_ranking():
    """Original candidate objects and nested inputs are never mutated during ranking."""
    orig_input = {"nums": [1, 2, 3], "nested": {"k": "v"}}
    c = make_candidate("c1", GapCategory.ZERO_VALUE, copy.deepcopy(orig_input))

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c])

    # Mutate selected candidate input
    result.selected_candidates[0].input_data["nums"].append(999)
    result.selected_candidates[0].input_data["nested"]["k"] = "modified"

    # Original candidate must be pristine
    assert c.input_data["nums"] == [1, 2, 3]
    assert c.input_data["nested"]["k"] == "v"


def test_provenance_and_oracle_invariants():
    """All selected candidates maintain GENERATED_TEST provenance and unverified expected_output."""
    c = make_candidate("c1", GapCategory.EMPTY_COLLECTION, {"nums": []})
    # Even if someone accidentally set expected_output verified without an oracle
    c.expected_output = None
    c.is_expected_output_verified = True

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c])

    selected = result.selected_candidates[0]
    assert selected.source == TestCaseSource.GENERATED_TEST
    assert selected.expected_output is None
    assert selected.is_expected_output_verified is False


# =============================================================================
# 8. Synthesizer Integration (synthesize_and_rank)
# =============================================================================


def test_synthesizer_integration_with_ranker():
    """TargetedTestSynthesizer integrates with CandidateRanker via synthesize_and_rank."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3], "val": 10},
    )
    spec = ConstraintSpec(min_value=-100, max_value=100, min_length=0, max_length=100)
    ctx = ProblemContext(title="test", constraint_spec=spec)

    synth = TargetedTestSynthesizer()
    rank_result = synth.synthesize_and_rank([tc], context=ctx, max_candidates=5)

    assert isinstance(rank_result, CandidateRankingResult)
    assert len(rank_result.selected_candidates) <= 5
    assert len(rank_result.ranked_candidates) >= len(rank_result.selected_candidates)
    assert len(rank_result.explanations) > 0

    # Ensure every selected candidate has GENERATED_TEST source
    for c in rank_result.selected_candidates:
        assert c.source == TestCaseSource.GENERATED_TEST
        assert c.expected_output is None
        assert c.is_expected_output_verified is False


def test_synthesizer_constructor_ranker_injection():
    """Injecting ranker into TargetedTestSynthesizer constructor activates ranking in synthesize()."""
    tc = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"nums": [1, 2, 3]},
    )
    ranker = CandidateRanker(default_max_selected=3)
    synth = TargetedTestSynthesizer(ranker=ranker)

    candidates = synth.synthesize([tc])
    assert len(candidates) <= 3
    for c in candidates:
        assert c.source == TestCaseSource.GENERATED_TEST


# =============================================================================
# 9. Focused Adversarial & Ranking Regression Tests
# =============================================================================


def test_configurable_weights_respected():
    """Custom RankingWeights are strictly honored across all score computations."""
    custom_weights = RankingWeights(
        severity_high=80.0,
        relevance_multiplier=40.0,
        boundary_bonus=25.0,
        novel_param_bonus=30.0,
    )
    c = make_candidate(
        "gen-custom",
        GapCategory.EMPTY_COLLECTION,
        {"nums": []},
        param_name="nums",
        relevance_score=0.5,
        is_boundary=True,
    )
    ranker = CandidateRanker(weights=custom_weights)
    result = ranker.rank_and_select([c])

    score = result.ranked_candidates[0].score_breakdown
    assert score.severity_score == 80.0
    assert score.relevance_score == 20.0  # 0.5 * 40.0
    assert score.boundary_score == 25.0
    assert score.novelty_score >= 30.0


def test_relevance_score_extreme_and_out_of_range_handling():
    """Ranker handles negative, extreme, None, and NaN relevance scores safely."""
    import math

    c_neg = make_candidate("c-neg", GapCategory.ZERO_VALUE, {"k": 0}, relevance_score=-5.0)
    c_huge = make_candidate("c-huge", GapCategory.ZERO_VALUE, {"k": 1}, relevance_score=999.0)
    c_zero = make_candidate("c-zero", GapCategory.ZERO_VALUE, {"k": 2}, relevance_score=0.0)
    c_nan = make_candidate("c-nan", GapCategory.ZERO_VALUE, {"k": 3}, relevance_score=float("nan"))

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c_neg, c_huge, c_zero, c_nan])

    assert len(result.selected_candidates) == 4
    scores_by_id = {r.candidate.id: r.score_breakdown for r in result.ranked_candidates}

    # Negative clamped to 0.0 -> relevance_score component is 0.0
    assert scores_by_id["c-neg"].relevance_score == 0.0

    # 999.0 clamped to 1.0 -> relevance_score component is 25.0
    assert scores_by_id["c-huge"].relevance_score == 25.0

    # 0.0 clamped to 0.0 -> relevance_score component is 0.0
    assert scores_by_id["c-zero"].relevance_score == 0.0

    # NaN safely defaulted to 0.5 -> relevance_score component is 12.5
    assert scores_by_id["c-nan"].relevance_score == 12.5


def test_exact_input_deduplication_ignores_different_ids_and_labels():
    """Candidate IDs, labels, and rationales must not prevent exact-input deduplication."""
    c1 = TestCase(
        id="alpha-1",
        source=TestCaseSource.GENERATED_TEST,
        label="First Label",
        rationale="First rationale",
        target_gap=GapCategory.EMPTY_COLLECTION,
        input_data={"matrix": []},
    )
    c2 = TestCase(
        id="beta-99",
        source=TestCaseSource.GENERATED_TEST,
        label="Completely Different Label",
        rationale="Completely different rationale",
        target_gap=GapCategory.EMPTY_COLLECTION,
        input_data={"matrix": []},
    )

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c1, c2])

    assert len(result.selected_candidates) == 1
    assert result.exact_duplicates_removed == 1


def test_candidates_sharing_inputs_differing_gaps_prefers_higher_priority():
    """When candidates share inputs but target different gaps, the higher-priority candidate is retained."""
    # c_zero targets ZERO_VALUE (MEDIUM severity, no boundary flag)
    c_zero = make_candidate("c-zero", GapCategory.ZERO_VALUE, {"x": 0}, relevance_score=0.5, is_boundary=False)
    # c_bound targets LOWER_CONSTRAINT_BOUND (HIGH severity, boundary flag)
    c_bound = make_candidate("c-bound", GapCategory.LOWER_CONSTRAINT_BOUND, {"x": 0}, relevance_score=0.5, is_boundary=True)

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c_zero, c_bound])

    # Exactly one retained, and the higher-priority boundary case wins
    assert len(result.selected_candidates) == 1
    assert result.selected_candidates[0].id == "c-bound"
    assert result.exact_duplicates_removed == 1


def test_provenance_preservation_for_non_generated_tests():
    """Non-generated test provenance (USER_PROVIDED_TEST, PUBLIC_SAMPLE) is never silently rewritten."""
    tc_user = TestCase(
        id="user-1",
        source=TestCaseSource.USER_PROVIDED_TEST,
        input_data={"k": 50},
        target_gap=GapCategory.ZERO_VALUE,
    )
    tc_pub = TestCase(
        id="sample-1",
        source=TestCaseSource.PUBLIC_SAMPLE,
        input_data={"k": 100},
        target_gap=GapCategory.ZERO_VALUE,
    )

    ranker = CandidateRanker()
    result = ranker.rank_and_select([tc_user, tc_pub])

    selected_sources = {c.id: c.source for c in result.selected_candidates}
    assert selected_sources["user-1"] == TestCaseSource.USER_PROVIDED_TEST
    assert selected_sources["sample-1"] == TestCaseSource.PUBLIC_SAMPLE


def test_diversity_penalty_bounding_and_auditability():
    """Diversity penalty decreases score for identical partitions without unintentionally hiding explanations."""
    c1 = make_candidate("c1", GapCategory.DUPLICATE_ELEMENTS, {"nums": [1, 1]}, param_name="nums", relevance_score=0.5)
    c2 = make_candidate("c2", GapCategory.DUPLICATE_ELEMENTS, {"nums": [2, 2]}, param_name="nums", relevance_score=0.5)
    c3 = make_candidate("c3", GapCategory.DUPLICATE_ELEMENTS, {"nums": [3, 3]}, param_name="nums", relevance_score=0.5)

    ranker = CandidateRanker()
    result = ranker.rank_and_select([c1, c2, c3])

    ranked = result.ranked_candidates
    assert ranked[0].score_breakdown.diversity_penalty == 0.0
    assert ranked[1].score_breakdown.diversity_penalty == 15.0
    assert ranked[2].score_breakdown.diversity_penalty == 30.0

    # Ensure total_score cannot be negative
    assert all(r.score >= 0.0 for r in ranked)
    assert "Redundant Partition Penalty (-15.0)" in ranked[1].explanation
    assert "Redundant Partition Penalty (-30.0)" in ranked[2].explanation

