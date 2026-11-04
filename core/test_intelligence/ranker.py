"""
EdgeMind Adaptive Test Intelligence - Candidate Ranking & Semantic Deduplication (Phase 5).

Provides deterministic, evidence-based ranking and selection for synthesized test candidates.
Evaluates coverage gap severity, relevance scores, boundary conditions, failure-family
extrapolations, novelty, and diversity across parameters and equivalence partitions.
Enforces semantic deduplication, candidate ceilings, provenance integrity, and input immutability.
"""

import copy
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

from core.test_intelligence.gap_detector import (
    CoverageGap,
    GapSeverity,
)
from core.test_intelligence.models import (
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.synthesizer import canonical_input_signature


@dataclass
class RankingWeights:
    """
    Configurable, documented weights for deterministic candidate scoring.
    All scores are non-negative and derived strictly from available evidence.
    """
    # Gap Severity weights (max 30.0)
    severity_high: float = 30.0
    severity_medium: float = 20.0
    severity_low: float = 10.0
    severity_default: float = 5.0

    # Relevance multiplier (relevance_score in [0.0, 1.0] -> max 25.0)
    relevance_multiplier: float = 25.0

    # Structural feature bonuses
    boundary_bonus: float = 15.0
    failure_family_bonus: float = 20.0
    performance_bonus: float = 10.0

    # Novelty & Diversity bonuses / penalties
    novel_param_bonus: float = 10.0
    novel_gap_bonus: float = 10.0
    redundant_partition_penalty: float = 15.0


@dataclass
class RankingScore:
    """
    Detailed breakdown of a candidate's calculated ranking score.
    Provides transparent auditability for ranking decisions.
    """
    severity_score: float = 0.0
    relevance_score: float = 0.0
    boundary_score: float = 0.0
    failure_family_score: float = 0.0
    performance_score: float = 0.0
    novelty_score: float = 0.0
    diversity_penalty: float = 0.0
    total_score: float = 0.0
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity_score": round(self.severity_score, 2),
            "relevance_score": round(self.relevance_score, 2),
            "boundary_score": round(self.boundary_score, 2),
            "failure_family_score": round(self.failure_family_score, 2),
            "performance_score": round(self.performance_score, 2),
            "novelty_score": round(self.novelty_score, 2),
            "diversity_penalty": round(self.diversity_penalty, 2),
            "total_score": round(self.total_score, 2),
            "explanation": self.explanation,
        }


@dataclass
class RankedCandidate:
    """
    Encapsulates a synthesized TestCase with its deterministic rank,
    evaluated score breakdown, and selection rationale.
    """
    candidate: TestCase
    rank: int
    score: float
    score_breakdown: RankingScore
    explanation: str
    canonical_signature: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate": self.candidate.to_dict(),
            "rank": self.rank,
            "score": round(self.score, 2),
            "score_breakdown": self.score_breakdown.to_dict(),
            "explanation": self.explanation,
            "canonical_signature": self.canonical_signature,
        }


# Inform pytest that domain models are not test suites
RankedCandidate.__test__ = False


@dataclass
class CandidateRankingResult:
    """
    Comprehensive output of the candidate ranking and deduplication engine.
    """
    selected_candidates: List[TestCase] = field(default_factory=list)
    ranked_candidates: List[RankedCandidate] = field(default_factory=list)
    total_evaluated: int = 0
    exact_duplicates_removed: int = 0
    redundant_candidates_penalized: int = 0
    selection_limit: Optional[int] = None
    explanations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_candidates": [c.to_dict() for c in self.selected_candidates],
            "ranked_candidates": [r.to_dict() for r in self.ranked_candidates],
            "total_evaluated": self.total_evaluated,
            "exact_duplicates_removed": self.exact_duplicates_removed,
            "redundant_candidates_penalized": self.redundant_candidates_penalized,
            "selection_limit": self.selection_limit,
            "explanations": list(self.explanations),
        }


CandidateRankingResult.__test__ = False


class CandidateRanker:
    """
    Deterministic ranker and semantic deduplicator for synthesized test candidates.

    Ranking Criteria:
    1. Gap Severity (HIGH > MEDIUM > LOW)
    2. Relevance Score (from CoverageGapEvaluator)
    3. Structural Boundary & Failure Extrapolation Bonuses
    4. Diversity & Novelty (balances parameters and gap partitions)
    5. Redundancy Mitigation (penalizes repeated identical partitions)
    6. Canonical Deduplication (removes equivalent representations)
    """

    def __init__(
        self,
        default_max_selected: Optional[int] = 10,
        weights: Optional[RankingWeights] = None,
    ):
        self.default_max_selected = default_max_selected
        self.weights = weights or RankingWeights()

    def rank_and_select(
        self,
        candidates: List[TestCase],
        existing_tests: Optional[List[TestCase]] = None,
        gaps: Optional[List[CoverageGap]] = None,
        max_selected: Optional[int] = None,
    ) -> CandidateRankingResult:
        """
        Deduplicate, rank, and select synthesized test candidates deterministically.

        Parameters:
            candidates: Synthesized candidates to evaluate.
            existing_tests: Base test cases (samples, failures, user tests) for deduplication.
            gaps: Optional list of identified coverage gaps for severity lookup.
            max_selected: Maximum number of candidates to select.

        Returns:
            CandidateRankingResult containing selected cases, full ranking, and explanations.
        """
        limit = max_selected if max_selected is not None else self.default_max_selected

        if not candidates:
            return CandidateRankingResult(
                selected_candidates=[],
                ranked_candidates=[],
                total_evaluated=0,
                exact_duplicates_removed=0,
                redundant_candidates_penalized=0,
                selection_limit=limit,
                explanations=["No candidates provided for ranking."],
            )

        # 1. Guarantee input immutability: Deepcopy candidates
        working_candidates = [copy.deepcopy(c) for c in candidates]

        # 2. Build canonical signatures for existing test cases to prevent re-testing known inputs
        seen_existing_signatures: Set[str] = set()
        existing_params: Set[str] = set()
        if existing_tests:
            for tc in existing_tests:
                if isinstance(tc.input_data, dict):
                    seen_existing_signatures.add(canonical_input_signature(tc.input_data))
                    existing_params.update(tc.input_data.keys())

        # 3. Canonical Deduplication across candidates
        # Group identical inputs and retain the highest-quality candidate per unique signature
        by_signature: Dict[str, List[TestCase]] = {}
        exact_duplicates_count = 0

        for cand in working_candidates:
            if not isinstance(cand.input_data, dict):
                continue
            sig = canonical_input_signature(cand.input_data)
            # Check against existing test cases
            if sig in seen_existing_signatures:
                exact_duplicates_count += 1
                continue
            by_signature.setdefault(sig, []).append(cand)

        deduped_candidates: List[TestCase] = []
        for sig, cand_list in by_signature.items():
            if len(cand_list) > 1:
                exact_duplicates_count += len(cand_list) - 1
                # Sort to pick candidate with highest priority (boundary, failure family, relevance, ID)
                cand_list.sort(
                    key=lambda c: (
                        1 if c.is_boundary else 0,
                        1 if c.target_gap == GapCategory.FAILURE_FAMILY_EXTRAPOLATION else 0,
                        c.relevance_score,
                        c.id,
                    ),
                    reverse=True,
                )
            deduped_candidates.append(cand_list[0])

        if not deduped_candidates:
            return CandidateRankingResult(
                selected_candidates=[],
                ranked_candidates=[],
                total_evaluated=len(working_candidates),
                exact_duplicates_removed=exact_duplicates_count,
                redundant_candidates_penalized=0,
                selection_limit=limit,
                explanations=["All candidates were exact duplicates of existing tests or prior candidates."],
            )

        # 4. Map gaps for rapid metadata and severity lookup
        gap_map: Dict[Tuple[Optional[str], GapCategory], CoverageGap] = {}
        if gaps:
            for g in gaps:
                gap_map[(g.param_name, g.category)] = g

        # 5. Iterative Diversity-Aware Selection (Marginal Utility)
        # Select candidates one by one. In each step, the candidate that provides
        # the highest marginal utility (base value + novelty - redundancy) is selected.
        selected_candidates: List[TestCase] = []
        ranked_candidates: List[RankedCandidate] = []
        explanations: List[str] = []

        selected_params: Set[str] = set()
        selected_gaps: Set[GapCategory] = set()
        selected_partitions: Dict[Tuple[Optional[str], Optional[GapCategory]], int] = {}
        redundant_penalized_count = 0

        remaining = list(deduped_candidates)
        rank_counter = 1

        while remaining:
            best_candidate: Optional[TestCase] = None
            best_score_breakdown: Optional[RankingScore] = None
            best_score = -1.0
            best_index = -1

            for idx, cand in enumerate(remaining):
                param_name = self._extract_param_name(cand)
                score_breakdown = self._calculate_candidate_score(
                    cand,
                    param_name=param_name,
                    gap_map=gap_map,
                    selected_params=selected_params,
                    selected_gaps=selected_gaps,
                    selected_partitions=selected_partitions,
                )

                if score_breakdown.diversity_penalty > 0:
                    redundant_penalized_count += 1

                # Deterministic comparison:
                # 1. Total score descending
                # 2. Target gap value alphabetical
                # 3. Candidate ID alphabetical
                # 4. Canonical signature alphabetical
                is_better = False
                if score_breakdown.total_score > best_score:
                    is_better = True
                elif score_breakdown.total_score == best_score and best_candidate is not None:
                    cand_gap_val = cand.target_gap.value if cand.target_gap else ""
                    best_gap_val = best_candidate.target_gap.value if best_candidate.target_gap else ""
                    if cand_gap_val < best_gap_val:
                        is_better = True
                    elif cand_gap_val == best_gap_val:
                        if cand.id < best_candidate.id:
                            is_better = True
                        elif cand.id == best_candidate.id:
                            is_better = canonical_input_signature(cand.input_data) < canonical_input_signature(best_candidate.input_data)

                if is_better:
                    best_score = score_breakdown.total_score
                    best_score_breakdown = score_breakdown
                    best_candidate = cand
                    best_index = idx

            if best_candidate is None or best_score_breakdown is None:
                break

            # Remove best candidate from remaining pool
            chosen_cand = remaining.pop(best_index)
            param_name = self._extract_param_name(chosen_cand)
            sig = canonical_input_signature(chosen_cand.input_data)

            # Update selection history
            if param_name:
                selected_params.add(param_name)
            if chosen_cand.target_gap:
                selected_gaps.add(chosen_cand.target_gap)
            if chosen_cand.target_gap in (
                GapCategory.TREE_STRUCTURE,
                GapCategory.BRACKET_PATTERN,
                GapCategory.NESTED_BRACKETS,
                GapCategory.SLIDING_WINDOW_PATTERN,
            ):
                part_key = (param_name, chosen_cand.target_gap, chosen_cand.label)
            else:
                part_key = (param_name, chosen_cand.target_gap)
            selected_partitions[part_key] = selected_partitions.get(part_key, 0) + 1

            # Format rank explanation
            expl = (
                f"Rank {rank_counter} (Score: {best_score:.1f}): Candidate '{chosen_cand.id}' "
                f"targeting {chosen_cand.target_gap.value if chosen_cand.target_gap else 'UNSPECIFIED'} "
                f"on param '{param_name or 'global'}'. {best_score_breakdown.explanation}"
            )
            explanations.append(expl)

            ranked_item = RankedCandidate(
                candidate=chosen_cand,
                rank=rank_counter,
                score=best_score,
                score_breakdown=best_score_breakdown,
                explanation=expl,
                canonical_signature=sig,
            )
            ranked_candidates.append(ranked_item)

            # Check if this candidate is within selection limit
            if limit is None or len(selected_candidates) < limit:
                # Invariant: Preserve candidate provenance; do not silently rewrite non-generated tests
                if not getattr(chosen_cand, "source", None):
                    chosen_cand.source = TestCaseSource.GENERATED_TEST
                if chosen_cand.source == TestCaseSource.GENERATED_TEST and chosen_cand.expected_output is None:
                    chosen_cand.is_expected_output_verified = False
                selected_candidates.append(chosen_cand)

            rank_counter += 1

        return CandidateRankingResult(
            selected_candidates=selected_candidates,
            ranked_candidates=ranked_candidates,
            total_evaluated=len(working_candidates),
            exact_duplicates_removed=exact_duplicates_count,
            redundant_candidates_penalized=redundant_penalized_count,
            selection_limit=limit,
            explanations=explanations,
        )

    # =========================================================================
    # Scoring Engine
    # =========================================================================

    def _calculate_candidate_score(
        self,
        candidate: TestCase,
        param_name: Optional[str],
        gap_map: Dict[Tuple[Optional[str], GapCategory], CoverageGap],
        selected_params: Set[str],
        selected_gaps: Set[GapCategory],
        selected_partitions: Dict[Tuple[Optional[str], Optional[GapCategory]], int],
    ) -> RankingScore:
        """
        Calculate the deterministic score breakdown for a single candidate.
        """
        import math
        w = self.weights

        # 1. Gap Severity Score
        sev = self._determine_gap_severity(candidate, param_name, gap_map)
        if sev == GapSeverity.HIGH:
            sev_score = w.severity_high
        elif sev == GapSeverity.MEDIUM:
            sev_score = w.severity_medium
        elif sev == GapSeverity.LOW:
            sev_score = w.severity_low
        else:
            sev_score = w.severity_default

        # 2. Relevance Score (safeguarded against None, NaN, inf, or out-of-range values)
        try:
            rel = float(candidate.relevance_score) if candidate.relevance_score is not None else 0.5
            if math.isnan(rel) or math.isinf(rel):
                rel = 0.5
        except (TypeError, ValueError):
            rel = 0.5
        rel = max(0.0, min(1.0, rel))
        rel_score = rel * w.relevance_multiplier

        # 3. Structural Feature Bonuses
        bound_score = w.boundary_bonus if candidate.is_boundary else 0.0

        is_fail = (
            candidate.target_gap == GapCategory.FAILURE_FAMILY_EXTRAPOLATION
            or "fail" in candidate.id.lower()
        )
        fail_score = w.failure_family_bonus if is_fail else 0.0

        perf_score = w.performance_bonus if candidate.is_performance else 0.0

        # 4. Novelty Bonuses
        nov_score = 0.0
        novel_reasons = []
        if param_name and param_name not in selected_params:
            nov_score += w.novel_param_bonus
            novel_reasons.append(f"new param '{param_name}'")
        if candidate.target_gap and candidate.target_gap not in selected_gaps:
            nov_score += w.novel_gap_bonus
            novel_reasons.append(f"new gap '{candidate.target_gap.value}'")

        # 5. Diversity / Redundant Partition Penalty
        if candidate.target_gap in (
            GapCategory.TREE_STRUCTURE,
            GapCategory.BRACKET_PATTERN,
            GapCategory.NESTED_BRACKETS,
            GapCategory.SLIDING_WINDOW_PATTERN,
        ):
            part_key = (param_name, candidate.target_gap, candidate.label)
        else:
            part_key = (param_name, candidate.target_gap)
        prior_count = selected_partitions.get(part_key, 0)
        div_penalty = prior_count * w.redundant_partition_penalty

        # 6. Total Calculation
        total = max(0.0, sev_score + rel_score + bound_score + fail_score + perf_score + nov_score - div_penalty)

        # 7. Descriptive Explanation
        sev_label = sev.value if sev else "DEFAULT"
        parts = [f"Severity: {sev_label} (+{sev_score:.1f})", f"Relevance: {rel:.2f} (+{rel_score:.1f})"]
        if bound_score > 0:
            parts.append(f"Boundary (+{bound_score:.1f})")
        if fail_score > 0:
            parts.append(f"Failure Family (+{fail_score:.1f})")
        if perf_score > 0:
            parts.append(f"Scale/Perf (+{perf_score:.1f})")
        if nov_score > 0:
            parts.append(f"Novelty: {', '.join(novel_reasons)} (+{nov_score:.1f})")
        if div_penalty > 0:
            parts.append(f"Redundant Partition Penalty (-{div_penalty:.1f})")

        explanation = "; ".join(parts)

        return RankingScore(
            severity_score=sev_score,
            relevance_score=rel_score,
            boundary_score=bound_score,
            failure_family_score=fail_score,
            performance_score=perf_score,
            novelty_score=nov_score,
            diversity_penalty=div_penalty,
            total_score=total,
            explanation=explanation,
        )

    def _determine_gap_severity(
        self,
        candidate: TestCase,
        param_name: Optional[str],
        gap_map: Dict[Tuple[Optional[str], GapCategory], CoverageGap],
    ) -> Optional[GapSeverity]:
        """
        Look up gap severity from pre-evaluated gaps, or infer from GapCategory hierarchy.
        Returns None if candidate has no target_gap.
        """
        if not candidate.target_gap:
            return None

        # Look up explicit gap metadata
        lookup = gap_map.get((param_name, candidate.target_gap))
        if lookup:
            return lookup.severity
        lookup_any = [g.severity for (p, cat), g in gap_map.items() if cat == candidate.target_gap]
        if lookup_any:
            return lookup_any[0]

        # Domain taxonomy fallback
        if candidate.target_gap in (
            GapCategory.EMPTY_COLLECTION,
            GapCategory.UPPER_CONSTRAINT_BOUND,
            GapCategory.LOWER_CONSTRAINT_BOUND,
            GapCategory.FAILURE_FAMILY_EXTRAPOLATION,
            GapCategory.TREE_STRUCTURE,
            GapCategory.SLIDING_WINDOW_PATTERN,
        ):
            return GapSeverity.HIGH

        if candidate.target_gap in (
            GapCategory.SINGLETON,
            GapCategory.ZERO_VALUE,
            GapCategory.NEGATIVE_VALUES,
            GapCategory.DUPLICATE_ELEMENTS,
            GapCategory.IDENTICAL_ALL,
            GapCategory.REVERSE_SORTED,
            GapCategory.ALREADY_SORTED,
            GapCategory.UNSORTED_SEQUENCE,
            GapCategory.TARGET_NOT_FOUND,
            GapCategory.TARGET_AT_BOUNDARIES,
            GapCategory.NESTED_BRACKETS,
            GapCategory.BRACKET_PATTERN,
            GapCategory.REPEATED_PATTERN,
        ):
            return GapSeverity.MEDIUM

        return GapSeverity.LOW

    def _extract_param_name(self, candidate: TestCase) -> Optional[str]:
        """
        Extract the target parameter name from candidate metadata, rationale, or ID.
        """
        # 1. From candidate rationale: "for parameter 'foo'"
        if candidate.rationale and "parameter '" in candidate.rationale:
            try:
                return candidate.rationale.split("parameter '")[1].split("'")[0]
            except Exception:
                pass

        # 2. From candidate id: e.g. "gen-empty-nums" -> "nums"
        parts = candidate.id.split("-")
        if len(parts) >= 3 and parts[0] == "gen":
            return parts[-1]

        # 3. Single key in input_data
        if len(candidate.input_data) == 1:
            return next(iter(candidate.input_data.keys()))

        return None
