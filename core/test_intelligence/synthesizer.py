"""
EdgeMind Adaptive Test Intelligence - Targeted Adaptive Test Generator.

Synthesizes deterministic, constraint-compliant test cases specifically targeting
uncovered equivalence partitions and boundary conditions identified by CoverageGapEvaluator.
Guarantees strict provenance (GENERATED_TEST), untrusted expected output (None),
canonical deduplication, type preservation, and input immutability.
"""

import copy
import json
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from core.test_intelligence.extractor import (
    FeatureProfileExtractor,
    FeatureStatus,
    InputFeatureProfile,
)
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
from core.test_intelligence.constraint_parser import (
    count_valid_pairs,
    is_two_sum_context,
    parse_constraint_expressions,
)


def canonical_input_signature(input_data: Dict[str, Any]) -> str:
    """
    Produce a deterministic canonical string representation of input_data
    for deduplication across existing and candidate test cases.
    Distinguishes distinct structural types (list vs tuple vs set) while
    normalizing equivalent numeric values and key orderings.
    """
    def serialize_obj(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                str(k): serialize_obj(obj[k])
                for k in sorted(obj.keys(), key=lambda x: str(x))
            }
        if isinstance(obj, list):
            return [serialize_obj(x) for x in obj]
        if isinstance(obj, tuple):
            return {"__py_type__": "tuple", "__val__": [serialize_obj(x) for x in obj]}
        if isinstance(obj, set):
            serialized_set = [serialize_obj(x) for x in obj]
            return {
                "__py_type__": "set",
                "__val__": sorted(
                    serialized_set,
                    key=lambda x: (type(x).__name__, json.dumps(x, sort_keys=True) if isinstance(x, (dict, list)) else repr(x)),
                ),
            }
        if isinstance(obj, float) and obj.is_integer():
            return int(obj)
        return obj

    try:
        normalized = serialize_obj(input_data)
        return json.dumps(normalized, sort_keys=True)
    except Exception:
        return repr(input_data)


def is_additive_relationship(
    context: Optional[ProblemContext],
    relational_metadata: Optional[Dict[str, Any]],
) -> bool:
    """
    Determine whether additive semantics (e.g. elements summing to a target companion parameter)
    are explicitly supported by reliable problem context or explicit relational metadata.
    Never infers mathematical relationships solely from parameter names.
    """
    # 1. Check explicit relational metadata
    if relational_metadata and isinstance(relational_metadata, dict):
        rel_type = str(
            relational_metadata.get("type")
            or relational_metadata.get("relationship")
            or relational_metadata.get("semantics")
            or relational_metadata.get("operation")
            or ""
        ).strip().upper()

        if rel_type in ("CONTAINMENT", "SEARCH", "BINARY_SEARCH", "MEMBERSHIP"):
            return False

        if rel_type in ("SUM", "PAIR_SUM", "ADDITIVE", "TWO_SUM", "ADD"):
            return True

    # 2. Check reliable problem context
    if context and isinstance(context, ProblemContext):
        title = (context.title or "").strip().lower()
        additive_titles = (
            "two sum",
            "2 sum",
            "3sum",
            "three sum",
            "4sum",
            "four sum",
            "target sum",
            "combination sum",
            "pair sum",
        )
        if any(kw in title for kw in additive_titles):
            return True

        fn = (context.function_name or "").strip().lower()
        additive_functions = (
            "twosum",
            "threesum",
            "foursum",
            "targetsum",
            "combinationsum",
            "pairsum",
        )
        if fn in additive_functions:
            return True

        desc = (context.description or "").strip().lower()
        additive_desc_cues = (
            "add up to target",
            "sum to target",
            "sum of two numbers",
            "two numbers such that they add up",
            "pair of numbers whose sum",
        )
        if any(cue in desc for cue in additive_desc_cues):
            return True

    return False


class TargetedTestSynthesizer:
    """
    Synthesizes targeted test cases for gaps identified by CoverageGapEvaluator.
    Does not execute code or invent expected outputs.
    """

    MAX_ARRAY_SCALE = 100000  # Ceiling for upper constraint boundary collections to avoid memory blowout

    def __init__(
        self,
        evaluator: Optional[CoverageGapEvaluator] = None,
        default_max_candidates: int = 15,
        ranker: Optional[Any] = None,
    ):
        self.evaluator = evaluator or CoverageGapEvaluator()
        self.default_max_candidates = default_max_candidates
        self.ranker = ranker

    def _extract_two_sum_params(
        self,
        base_inputs: Dict[str, Any],
        relational_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Identify sequence collection param and numeric target param for Two Sum."""
        col_param = None
        target_param = None
        if relational_metadata and isinstance(relational_metadata, dict):
            col_param = relational_metadata.get("collection_param")
            target_param = relational_metadata.get("target_param")

        if not col_param or not target_param or col_param not in base_inputs or target_param not in base_inputs:
            for k, v in base_inputs.items():
                if isinstance(v, (list, tuple)) and col_param is None:
                    col_param = k
                elif isinstance(v, (int, float)) and not isinstance(v, bool) and target_param is None:
                    target_param = k
        return col_param, target_param

    def _build_two_sum_candidate(
        self,
        cid: str,
        label: str,
        rationale: str,
        gap: CoverageGap,
        col_param: str,
        target_param: str,
        nums: Any,
        target: Union[int, float],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        is_boundary: bool = True,
        is_performance: bool = False,
        is_scale: bool = False,
    ) -> Optional[TestCase]:
        """Build and validate a Two Sum candidate, preserving exactly one valid pair."""
        if count_valid_pairs(nums, target) != 1:
            return None

        if spec:
            if spec.min_length is not None and len(nums) < spec.min_length:
                return None
            if spec.max_length is not None and len(nums) > spec.max_length:
                return None
            if spec.min_value is not None:
                if target < spec.min_value or any(x < spec.min_value for x in nums):
                    return None
            if spec.max_value is not None:
                if target > spec.max_value or any(x > spec.max_value for x in nums):
                    return None

        inputs = copy.deepcopy(base_inputs)
        inputs[col_param] = nums
        inputs[target_param] = target

        return TestCase(
            id=cid,
            source=TestCaseSource.GENERATED_TEST,
            input_data=inputs,
            expected_output=None,
            is_expected_output_verified=False,
            label=label,
            rationale=rationale,
            target_gap=gap.category,
            relevance_score=gap.relevance_score,
            is_boundary=is_boundary,
            is_performance=is_performance or is_scale,
            classification=CandidateClassification.VALID.value,
            classification_reason="Satisfies all supported supplied problem constraints and contains exactly one valid pair summing to target.",
        )


    # =========================================================================
    # Problem-Specific Benchmark Structural Generators
    # =========================================================================

    def _is_bracket_context(
        self,
        context: Optional[ProblemContext],
        spec: Optional[ConstraintSpec],
        base_inputs: Dict[str, Any],
    ) -> bool:
        """Identify if this problem tests bracket string validation (e.g. Valid Parentheses)."""
        if context and context.title:
            t = context.title.lower()
            if "parenthes" in t or "bracket" in t:
                return True
        if spec and spec.allowed_characters:
            if any(ch in spec.allowed_characters for ch in "()[]{}"):
                return True
        for k, v in base_inputs.items():
            if isinstance(v, str) and v and all(c in "()[]{}" for c in v):
                return True
        return False

    def _gen_bracket_patterns(
        self,
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        target_gaps: List[CoverageGap],
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        """Synthesize required structural bracket patterns for Valid Parentheses."""
        str_param = None
        for k, v in base_inputs.items():
            if isinstance(v, str):
                str_param = k
                break
        if not str_param:
            str_param = "s"

        p_spec = spec.param_specs.get(str_param.lower()) if (spec and spec.param_specs) else None
        eff_max_l = p_spec.max_length if (p_spec and p_spec.max_length is not None) else (spec.max_length if spec else 10000)

        # 5 required bracket patterns + exact max length (10,000)
        patterns = [
            ("gen-bracket-balanced", "Balanced nested brackets", "{[()]}", "Tests multi-character balanced nesting ({[()]})."),
            ("gen-bracket-mismatched", "Mismatched bracket pair", "(]", "Tests single open bracket paired with different closing type ((])."),
            ("gen-bracket-interleaved", "Interleaved incorrect nesting", "([)]", "Tests interleaved incorrect nesting order (([)]). Valid input syntax."),
            ("gen-bracket-consecutive", "Consecutive independent pairs", "()[]{}", "Tests sequential consecutive valid bracket pairs (()[]{})."),
            ("gen-bracket-singleton", "Singleton bracket", "(", "Tests singleton open bracket without closing companion (()."),
        ]

        if eff_max_l and eff_max_l >= 10:
            scale_l = min(eff_max_l, 10000)
            max_s = "()" * (scale_l // 2) if scale_l % 2 == 0 else "(" * scale_l
            patterns.append((
                "gen-bracket-max-len",
                f"Maximum constraint length ({scale_l} characters)",
                max_s,
                f"Tests exact maximum constraint length string of {scale_l} valid bracket characters.",
            ))

        cases: List[TestCase] = []
        for cid, label, val_str, rat in patterns:
            inp = copy.deepcopy(base_inputs)
            inp[str_param] = val_str
            cases.append(
                TestCase(
                    id=cid,
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=inp,
                    expected_output=None,
                    is_expected_output_verified=False,
                    label=label,
                    rationale=rat,
                    target_gap=GapCategory.UPPER_CONSTRAINT_BOUND if "max-len" in cid else (
                        GapCategory.LOWER_CONSTRAINT_BOUND if "singleton" in cid else (
                            GapCategory.NESTED_BRACKETS if "balanced" in cid else GapCategory.BRACKET_PATTERN
                        )
                    ),
                    relevance_score=0.90 if "max-len" in cid else 0.85,
                    is_boundary="max-len" in cid or "singleton" in cid,
                    is_performance="max-len" in cid,
                    classification=CandidateClassification.VALID.value,
                    classification_reason="Satisfies all supported supplied problem constraints.",
                )
            )
        return cases

    def _is_binary_tree_context(
        self,
        context: Optional[ProblemContext],
        spec: Optional[ConstraintSpec],
        base_inputs: Dict[str, Any],
    ) -> bool:
        """Identify if this problem tests binary tree properties (e.g. Maximum Depth of Binary Tree)."""
        if context and context.title:
            t = context.title.lower()
            if "binary tree" in t or "maximum depth" in t or "tree" in t:
                return True
        if "root" in base_inputs:
            return True
        for k in base_inputs:
            if "root" in k.lower() or "tree" in k.lower():
                return True
        return False

    def _gen_tree_structural_variants(
        self,
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        target_gaps: List[CoverageGap],
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        """Synthesize 7 required binary tree structural variants distinguishing N, L, and D."""
        from core.test_intelligence.constraint_parser import validate_and_analyze_tree

        tree_param = None
        for k in base_inputs:
            if "root" in k.lower() or "tree" in k.lower():
                tree_param = k
                break
        if not tree_param:
            tree_param = "root"

        p_spec = spec.param_specs.get(tree_param.lower()) if (spec and spec.param_specs) else None
        eff_max_n = p_spec.max_length if (p_spec and p_spec.max_length is not None) else (spec.max_length if spec else 10000)

        # 7 structural variants: empty, single-node, left-skewed, right-skewed, balanced, sparse, max 10,000-node
        variants = [
            ("gen-tree-empty", "Empty binary tree", [], "Empty tree boundary (0 nodes)."),
            ("gen-tree-single", "Single-node binary tree", [1], "Single-node tree boundary (1 node)."),
            ("gen-tree-left-skewed", "Left-skewed linear binary tree", [1, 2, None, 3], "Left-skewed tree maximizing recursion depth."),
            ("gen-tree-right-skewed", "Right-skewed linear binary tree", [1, None, 2, None, 3], "Right-skewed tree maximizing right-branch traversal."),
            ("gen-tree-balanced", "Balanced binary tree", [1, 2, 3, 4, 5, 6, 7], "Complete balanced binary tree."),
            ("gen-tree-sparse", "Sparse binary tree", [1, 2, 3, None, 4, None, 5], "Sparse binary tree with alternating null placeholders."),
        ]

        if eff_max_n and eff_max_n >= 10:
            scale_n = min(eff_max_n, 10000)
            variants.append((
                "gen-tree-max-10000",
                f"Maximum constraint size binary tree ({scale_n} nodes)",
                [1] * scale_n,
                f"Maximum capacity {scale_n}-node binary tree for recursion and memory scale.",
            ))

        cases: List[TestCase] = []
        for cid, label, tree_arr, rat in variants:
            is_val, n_act, s_len, m_dep, err = validate_and_analyze_tree(tree_arr)
            inp = copy.deepcopy(base_inputs)
            inp[tree_param] = tree_arr
            cases.append(
                TestCase(
                    id=cid,
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=inp,
                    expected_output=None,
                    is_expected_output_verified=False,
                    label=label,
                    rationale=f"{rat} (actual nodes N={n_act}, serialized length L={s_len}, max depth D={m_dep}).",
                    target_gap=GapCategory.EMPTY_COLLECTION if len(tree_arr) == 0 else (
                        GapCategory.SINGLETON if len(tree_arr) == 1 else (
                            GapCategory.UPPER_CONSTRAINT_BOUND if "max" in cid else GapCategory.TREE_STRUCTURE
                        )
                    ),
                    relevance_score=0.96 if len(tree_arr) == 0 else (0.97 if "max" in cid else 0.95),
                    is_boundary=True,
                    is_performance="max" in cid,
                    classification=CandidateClassification.VALID.value,
                    classification_reason=f"Satisfies all supported supplied problem constraints (nodes N={n_act}, serialized length L={s_len}, depth D={m_dep}).",
                )
            )
        return cases

    def _is_sliding_window_substring_context(
        self,
        context: Optional[ProblemContext],
        spec: Optional[ConstraintSpec],
        base_inputs: Dict[str, Any],
    ) -> bool:
        """Identify if problem tests sliding-window substring properties."""
        if context and context.title:
            t = context.title.lower()
            if "longest substring" in t or "substring without repeating" in t:
                return True
        return False

    def _gen_sliding_window_patterns(
        self,
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        target_gaps: List[CoverageGap],
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        """Synthesize essential sliding-window string regression patterns (abba, dvdf, tmmzuxt)."""
        str_param = None
        for k, v in base_inputs.items():
            if isinstance(v, str):
                str_param = k
                break
        if not str_param:
            str_param = "s"

        patterns = [
            ("gen-sw-abba", "Re-encountered character outside window (abba)", "abba", "Tests that re-encountered character prior to window start does not improperly move left pointer backward (abba)."),
            ("gen-sw-dvdf", "Interleaved duplicate with contraction (dvdf)", "dvdf", "Tests window contraction and subsequent expansion across non-adjacent duplicate characters (dvdf)."),
            ("gen-sw-tmmzuxt", "Adjacent duplicate followed by recurrence (tmmzuxt)", "tmmzuxt", "Tests sliding-window state reset on consecutive identical characters followed by non-adjacent recurrence (tmmzuxt)."),
        ]

        cases: List[TestCase] = []
        for cid, label, val_str, rat in patterns:
            inp = copy.deepcopy(base_inputs)
            inp[str_param] = val_str
            cases.append(
                TestCase(
                    id=cid,
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=inp,
                    expected_output=None,
                    is_expected_output_verified=False,
                    label=label,
                    rationale=rat,
                    target_gap=GapCategory.SLIDING_WINDOW_PATTERN,
                    relevance_score=0.92,
                    is_boundary=False,
                    is_performance=False,
                    classification=CandidateClassification.VALID.value,
                    classification_reason="Satisfies all supported supplied problem constraints and character domain.",
                )
            )
        return cases

    def synthesize(
        self,
        test_cases: List[TestCase],
        context: Optional[ProblemContext] = None,
        gaps: Optional[List[CoverageGap]] = None,
        relational_metadata: Optional[Dict[str, Any]] = None,
        max_candidates: Optional[int] = None,
    ) -> List[TestCase]:
        """
        Generate targeted test cases addressing identified coverage gaps.

        Parameters:
            test_cases: Existing test cases (samples, user tests, failures).
            context: ProblemContext with ConstraintSpec and parameter metadata.
            gaps: Optional pre-evaluated gaps. If None, evaluator is invoked.
            relational_metadata: Explicit parameter relationships.
            max_candidates: Configurable ceiling on number of returned candidates.

        Returns:
            List of deduplicated, constraint-safe TestCase objects tagged GENERATED_TEST.
        """
        limit = max_candidates if max_candidates is not None else self.default_max_candidates
        ctx = context or getattr(self.evaluator.extractor, "context", None)
        spec = self._get_effective_spec(ctx)

        # Check for contradictory constraints (e.g. min_val > max_val or min_len > max_len)
        if spec:
            if spec.min_value is not None and spec.max_value is not None and spec.min_value > spec.max_value:
                return []
            if spec.min_length is not None and spec.max_length is not None and spec.min_length > spec.max_length:
                return []

        # 1. Identify gaps if not provided
        if gaps is None:
            gap_result = self.evaluator.evaluate(
                test_cases,
                context=ctx,
                relational_metadata=relational_metadata,
            )
            target_gaps = gap_result.gaps
        else:
            target_gaps = gaps

        if not target_gaps:
            return []

        # 2. Build template base inputs from existing samples without mutating them
        base_inputs = self._extract_base_inputs(test_cases, ctx, spec)

        # 3. Track canonical signatures of existing test cases to prevent duplicate generation
        seen_signatures: Set[str] = set()
        for tc in test_cases:
            if isinstance(tc.input_data, dict):
                seen_signatures.add(canonical_input_signature(tc.input_data))

        # 4. Generate candidates for each gap
        candidates: List[TestCase] = []
        for gap in target_gaps:
            synthesized = self._synthesize_for_gap(
                gap,
                base_inputs,
                spec,
                test_cases,
                relational_metadata,
                context=ctx,
            )
            for cand in synthesized:
                # Relationship preservation: e.g. k <= len(nums)
                if spec and spec.cross_constraints:
                    for cc in spec.cross_constraints:
                        if cc.relation_type in ("WINDOW_LEQ_ARRAY_LENGTH", "LEQ_LENGTH") and len(cc.parameters_involved) >= 2:
                            p_win = cc.parameters_involved[0]
                            p_arr = cc.parameters_involved[1]
                            if p_win in cand.input_data and p_arr in cand.input_data:
                                w_val = cand.input_data[p_win]
                                a_val = cand.input_data[p_arr]
                                if isinstance(w_val, (int, float)) and isinstance(a_val, list):
                                    if w_val > len(a_val):
                                        if "min-len" in cand.id:
                                            cand.input_data[p_win] = len(a_val)
                                            cand.label = f"Full-array window (k=n={len(a_val)}) for {p_arr}"
                                        else:
                                            elem = a_val[0] if a_val else 1
                                            cand.input_data[p_arr] = a_val + [elem] * (int(w_val) - len(a_val))
                                    elif w_val == len(a_val) and len(a_val) > 1:
                                        if "max-val" in cand.id:
                                            cand.label = f"Maximum constraint value for {p_win} (Full-array window k=n={len(a_val)})" 

                from core.test_intelligence.constraint_parser import classify_candidate
                c_cls, c_reason = classify_candidate(cand, spec, context=ctx, relational_metadata=relational_metadata)
                cand.classification = c_cls
                cand.classification_reason = c_reason

                # For binary tree context, suppress generic array candidates that duplicate structural tree forms
                skip_generic = False
                if self._is_binary_tree_context(ctx, spec, base_inputs):
                    if any(cand.id.startswith(pfx) for pfx in ("gen-bound-max-len", "gen-empty", "gen-singleton", "gen-sorted", "gen-reversed", "gen-duplicate", "gen-identical")):
                        skip_generic = True

                if not skip_generic:
                    sig = canonical_input_signature(cand.input_data)
                    if sig not in seen_signatures:
                        seen_signatures.add(sig)
                        candidates.append(cand)

        # Domain-specific structural benchmark candidates
        structural_candidates: List[TestCase] = []
        if self._is_bracket_context(ctx, spec, base_inputs):
            structural_candidates.extend(self._gen_bracket_patterns(base_inputs, spec, target_gaps, ctx))
        if self._is_binary_tree_context(ctx, spec, base_inputs):
            structural_candidates.extend(self._gen_tree_structural_variants(base_inputs, spec, target_gaps, ctx))
        if self._is_sliding_window_substring_context(ctx, spec, base_inputs):
            structural_candidates.extend(self._gen_sliding_window_patterns(base_inputs, spec, target_gaps, ctx))



        for cand in structural_candidates:
            from core.test_intelligence.constraint_parser import classify_candidate
            c_cls, c_reason = classify_candidate(cand, spec, context=ctx, relational_metadata=relational_metadata)
            cand.classification = c_cls
            cand.classification_reason = c_reason
            sig = canonical_input_signature(cand.input_data)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                candidates.append(cand)

        # 5. Rank and select candidates deterministically
        if self.ranker is not None:
            effective_limit = (
                max_candidates
                if max_candidates is not None
                else (self.ranker.default_max_selected if self.ranker.default_max_selected is not None else limit)
            )
            ranking_result = self.ranker.rank_and_select(
                candidates,
                existing_tests=test_cases,
                gaps=target_gaps,
                max_selected=effective_limit,
            )
            return ranking_result.selected_candidates

        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                -c.relevance_score,
                c.target_gap.value if c.target_gap else "",
                c.id,
            ),
        )

        return sorted_candidates[:limit]

    def synthesize_and_rank(
        self,
        test_cases: List[TestCase],
        context: Optional[ProblemContext] = None,
        gaps: Optional[List[CoverageGap]] = None,
        relational_metadata: Optional[Dict[str, Any]] = None,
        max_candidates: Optional[int] = None,
        ranker: Optional[Any] = None,
    ) -> Any:
        """
        Synthesize candidates and execute full semantic deduplication,
        ranking, and diversity-aware selection, returning a CandidateRankingResult.
        """
        from core.test_intelligence.ranker import CandidateRanker
        active_ranker = ranker or self.ranker or CandidateRanker()

        # Temporarily detach ranker during base candidate generation so all candidates are produced
        orig_ranker = self.ranker
        self.ranker = None
        try:
            raw_candidates = self.synthesize(
                test_cases=test_cases,
                context=context,
                gaps=gaps,
                relational_metadata=relational_metadata,
                max_candidates=1000,
            )
        finally:
            self.ranker = orig_ranker

        return active_ranker.rank_and_select(
            candidates=raw_candidates,
            existing_tests=test_cases,
            gaps=gaps,
            max_selected=max_candidates or self.default_max_candidates,
        )

    # =========================================================================
    # Constraint & Template Base Derivation
    # =========================================================================

    def _get_effective_spec(
        self, context: Optional[ProblemContext]
    ) -> Optional[ConstraintSpec]:
        """
        Derive effective machine-readable constraints by combining ConstraintSpec
        with raw problem context constraints to prevent assuming unrestricted input.
        """
        if not context:
            return None

        spec = copy.deepcopy(context.constraint_spec) if context.constraint_spec else ConstraintSpec()

        # Combine problem constraints with spec raw constraints
        raw_list = list(context.constraints)
        if spec.raw_constraints:
            raw_list.extend(spec.raw_constraints)

        # Parse expressions deterministically
        parsed_spec, _ = parse_constraint_expressions(
            raw_list, known_parameters=context.parameters if context else None
        )
        if spec.min_length is None:
            spec.min_length = parsed_spec.min_length
        if spec.max_length is None:
            spec.max_length = parsed_spec.max_length
        if spec.min_value is None:
            spec.min_value = parsed_spec.min_value
        if spec.max_value is None:
            spec.max_value = parsed_spec.max_value
        if spec.allowed_characters is None:
            spec.allowed_characters = parsed_spec.allowed_characters
        if spec.min_rows is None:
            spec.min_rows = parsed_spec.min_rows
        if spec.max_rows is None:
            spec.max_rows = parsed_spec.max_rows
        if spec.min_cols is None:
            spec.min_cols = parsed_spec.min_cols
        if spec.max_cols is None:
            spec.max_cols = parsed_spec.max_cols
        if spec.allowed_values is None:
            spec.allowed_values = parsed_spec.allowed_values
        if not spec.endpoints_zero:
            spec.endpoints_zero = parsed_spec.endpoints_zero
        if not spec.raw_constraints:
            spec.raw_constraints = raw_list
        if not spec.param_specs and parsed_spec.param_specs:
            spec.param_specs = parsed_spec.param_specs
        if not spec.cross_constraints and parsed_spec.cross_constraints:
            spec.cross_constraints = parsed_spec.cross_constraints
        if not spec.parsed_constraints and parsed_spec.parsed_constraints:
            spec.parsed_constraints = parsed_spec.parsed_constraints
        if not spec.unresolved_reasons and parsed_spec.unresolved_reasons:
            spec.unresolved_reasons = parsed_spec.unresolved_reasons
        if parsed_spec.is_sorted_ascending:
            spec.is_sorted_ascending = True
        if parsed_spec.unique_elements:
            spec.unique_elements = True
        if parsed_spec.is_strictly_increasing:
            spec.is_strictly_increasing = True
        if parsed_spec.sorted_param:
            spec.sorted_param = parsed_spec.sorted_param

        for line in raw_list:
            text = line.lower()
            # Non-empty / minimum collection length fallback
            if spec.min_length is None:
                if "non-empty" in text or "nonempty" in text:
                    spec.min_length = 1
                elif "1 <=" in text and any(w in text for w in ("len", "length", "size")):
                    spec.min_length = 1
            # Minimum numeric value fallback
            if spec.min_value is None:
                if "non-negative" in text or "nonnegative" in text or ">= 0" in text or "0 <=" in text:
                    spec.min_value = 0.0
                elif "positive" in text or "> 0" in text or "1 <=" in text:
                    spec.min_value = 1.0

        return spec

    def _extract_base_inputs(
        self,
        test_cases: List[TestCase],
        context: Optional[ProblemContext],
        spec: Optional[ConstraintSpec],
    ) -> Dict[str, Any]:
        """
        Derive safe base input templates from existing tests without mutating them.
        """
        base: Dict[str, Any] = {}
        for tc in test_cases:
            if isinstance(tc.input_data, dict):
                for k, v in tc.input_data.items():
                    if k not in base:
                        base[k] = copy.deepcopy(v)

        # If test cases were completely empty, populate minimal defaults from context
        if not base and context and context.parameters:
            for p in context.parameters:
                val = 1
                if spec and spec.min_value is not None:
                    val = int(spec.min_value)
                elif spec and spec.max_value is not None:
                    val = int(spec.max_value)
                base[p] = [val, val + 1] if (spec is None or spec.max_value is None or val + 1 <= spec.max_value) else [val]

        return base

    # =========================================================================
    # Gap Dispatcher
    # =========================================================================

    def _synthesize_for_gap(
        self,
        gap: CoverageGap,
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        existing_cases: List[TestCase],
        relational_metadata: Optional[Dict[str, Any]],
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        if gap.constraint_validity == ConstraintValidity.PROHIBITED:
            return []

        cat = gap.category
        p_name = gap.param_name

        if cat == GapCategory.EMPTY_COLLECTION:
            return self._gen_empty_collection(p_name, base_inputs, spec, gap)

        elif cat == GapCategory.SINGLETON:
            return self._gen_singleton(p_name, base_inputs, spec, gap)

        elif cat == GapCategory.ZERO_VALUE:
            return self._gen_zero_value(
                p_name,
                base_inputs,
                spec,
                gap,
                relational_metadata=relational_metadata,
                context=context,
            )

        elif cat == GapCategory.NEGATIVE_VALUES:
            return self._gen_negative_values(
                p_name,
                base_inputs,
                spec,
                gap,
                relational_metadata=relational_metadata,
                context=context,
            )

        elif cat == GapCategory.DUPLICATE_ELEMENTS:
            return self._gen_duplicates(
                p_name,
                base_inputs,
                spec,
                gap,
                relational_metadata=relational_metadata,
                context=context,
            )

        elif cat == GapCategory.IDENTICAL_ALL:
            return self._gen_all_identical(
                p_name,
                base_inputs,
                spec,
                gap,
                relational_metadata=relational_metadata,
                context=context,
            )

        elif cat in (GapCategory.ALREADY_SORTED, GapCategory.REVERSE_SORTED, GapCategory.UNSORTED_SEQUENCE):
            return self._gen_order_variant(p_name, base_inputs, spec, gap)

        elif cat in (GapCategory.LOWER_CONSTRAINT_BOUND, GapCategory.UPPER_CONSTRAINT_BOUND):
            return self._gen_constraint_boundary(
                p_name,
                base_inputs,
                spec,
                gap,
                relational_metadata=relational_metadata,
                context=context,
            )

        elif cat in (GapCategory.TARGET_NOT_FOUND, GapCategory.TARGET_AT_BOUNDARIES):
            return self._gen_relational_cases(gap, base_inputs, relational_metadata, spec)

        elif cat == GapCategory.MATRIX_DIMENSIONS:
            return self._gen_matrix_dimensions(p_name, base_inputs, spec, gap)

        elif cat == GapCategory.FAILURE_FAMILY_EXTRAPOLATION:
            return self._gen_failure_family(gap, existing_cases, spec)

        return []

    # =========================================================================
    # Focused Generators
    # =========================================================================

    def _gen_empty_collection(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        p_spec = spec.param_specs.get(name.lower()) if (spec and spec.param_specs) else None
        if p_spec:
            if p_spec.is_non_empty or (p_spec.min_length is not None and p_spec.min_length > 0) or (p_spec.min_rows is not None and p_spec.min_rows > 0):
                return []

        # Constraint check: min_length > 0 or min_rows > 0 strictly prohibits empty collection
        if spec and (
            (spec.min_length is not None and spec.min_length > 0)
            or (spec.min_rows is not None and spec.min_rows > 0)
        ):
            return []
        if spec and spec.max_length is not None and spec.max_length < 0:
            return []

        inputs = copy.deepcopy(base_inputs)
        orig = inputs[name]
        if isinstance(orig, list):
            inputs[name] = []
        elif isinstance(orig, str):
            inputs[name] = ""
        elif isinstance(orig, dict):
            inputs[name] = {}
        elif isinstance(orig, set):
            inputs[name] = set()
        elif isinstance(orig, tuple):
            inputs[name] = ()
        else:
            return []

        return [
            TestCase(
                id=f"gen-empty-{name}",
                source=TestCaseSource.GENERATED_TEST,
                input_data=inputs,
                expected_output=None,
                is_expected_output_verified=False,
                label=f"Empty {name}",
                rationale=gap.rationale,
                target_gap=GapCategory.EMPTY_COLLECTION,
                relevance_score=gap.relevance_score,
                is_boundary=True,
            )
        ]

    def _gen_singleton(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        # Constraint check: min_length > 1 or min_rows > 1 strictly prohibits singleton collection
        if spec and (
            (spec.min_length is not None and spec.min_length > 1)
            or (spec.min_rows is not None and spec.min_rows > 1)
        ):
            return []
        if spec and spec.max_length is not None and spec.max_length < 1:
            return []

        inputs = copy.deepcopy(base_inputs)
        orig = inputs[name]

        if isinstance(orig, list):
            if orig and isinstance(orig[0], list):
                # Matrix: preserve matrix structure with 1 row
                row = orig[0]
                inputs[name] = [row]
            else:
                val = orig[0] if orig else 1
                inputs[name] = [val]
        elif isinstance(orig, str):
            p_spec = spec.param_specs.get(name.lower()) if (spec and spec.param_specs) else None
            eff_chars = p_spec.allowed_characters if (p_spec and p_spec.allowed_characters) else (spec.allowed_characters if spec else None)
            if eff_chars and "()" in eff_chars:
                val = "("
            elif eff_chars and eff_chars == "a-z":
                val = orig[0] if (orig and "a" <= orig[0] <= "z") else "a"
            else:
                val = orig[0] if orig else "a"
            inputs[name] = val
        elif isinstance(orig, tuple):
            val = orig[0] if orig else 1
            inputs[name] = (val,)
        elif isinstance(orig, dict):
            if orig:
                k = next(iter(orig))
                inputs[name] = {k: orig[k]}
            else:
                inputs[name] = {"k": 1}
        elif isinstance(orig, set):
            val = next(iter(orig)) if orig else 1
            inputs[name] = {val}
        else:
            return []

        return [
            TestCase(
                id=f"gen-singleton-{name}",
                source=TestCaseSource.GENERATED_TEST,
                input_data=inputs,
                expected_output=None,
                is_expected_output_verified=False,
                label=f"Singleton {name}",
                rationale=gap.rationale,
                target_gap=GapCategory.SINGLETON,
                relevance_score=gap.relevance_score,
                is_boundary=True,
            )
        ]

    def _gen_zero_value(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
        relational_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        if spec and spec.min_value is not None and spec.min_value > 0:
            return []
        if spec and spec.max_value is not None and spec.max_value < 0:
            return []

        # Specialized Two Sum zero-value candidate generation
        if is_two_sum_context(context, relational_metadata):
            col_p, target_p = self._extract_two_sum_params(base_inputs, relational_metadata)
            if col_p and target_p and col_p in base_inputs and target_p in base_inputs:
                orig_target = base_inputs[target_p]
                orig_nums = base_inputs[col_p]
                if name == col_p and isinstance(orig_nums, (list, tuple)):
                    t_val = orig_target if isinstance(orig_target, (int, float)) and not isinstance(orig_target, bool) else 9
                    if t_val == 0:
                        cand_nums = [0, -5, 5]
                        cand_target = 0
                    else:
                        cand_target = t_val
                        filler = (t_val + 10) if (spec is None or spec.max_value is None or t_val + 10 <= spec.max_value) else (t_val - 10)
                        cand_nums = [0, cand_target, filler]
                    cand = self._build_two_sum_candidate(
                        cid=f"gen-zero-{name}",
                        label=f"Zero value element in {name}",
                        rationale=f"Sequence '{name}' contains a zero element paired with {cand_target} summing to target {cand_target}.",
                        gap=gap,
                        col_param=col_p,
                        target_param=target_p,
                        nums=cand_nums if isinstance(orig_nums, list) else tuple(cand_nums),
                        target=cand_target,
                        base_inputs=base_inputs,
                        spec=spec,
                    )
                    if cand:
                        return [cand]
                elif name == target_p and isinstance(orig_nums, (list, tuple)):
                    cand = self._build_two_sum_candidate(
                        cid=f"gen-zero-{name}",
                        label=f"Zero value for {name}",
                        rationale=f"Target parameter '{name}' is zero with distinct-index pair [-5, 5] summing to zero.",
                        gap=gap,
                        col_param=col_p,
                        target_param=target_p,
                        nums=[-5, 5, 20] if isinstance(orig_nums, list) else (-5, 5, 20),
                        target=0,
                        base_inputs=base_inputs,
                        spec=spec,
                    )
                    if cand:
                        return [cand]

        inputs = copy.deepcopy(base_inputs)
        orig = inputs[name]

        if isinstance(orig, (int, float)) and not isinstance(orig, bool):
            inputs[name] = 0.0 if isinstance(orig, float) else 0
        elif isinstance(orig, list) and orig and not isinstance(orig[0], bool) and isinstance(orig[0], (int, float)):
            mod = list(orig)
            mod[0] = 0.0 if isinstance(orig[0], float) else 0
            inputs[name] = mod
        elif isinstance(orig, tuple) and orig and not isinstance(orig[0], bool) and isinstance(orig[0], (int, float)):
            val = 0.0 if isinstance(orig[0], float) else 0
            inputs[name] = (val,) + orig[1:]
        elif isinstance(orig, list) and orig and isinstance(orig[0], list) and orig[0] and not isinstance(orig[0][0], bool) and isinstance(orig[0][0], (int, float)):
            # Matrix zero insertion
            mod = copy.deepcopy(orig)
            mod[0][0] = 0.0 if isinstance(orig[0][0], float) else 0
            inputs[name] = mod
        else:
            return []

        return [
            TestCase(
                id=f"gen-zero-{name}",
                source=TestCaseSource.GENERATED_TEST,
                input_data=inputs,
                expected_output=None,
                is_expected_output_verified=False,
                label=f"Zero value for {name}",
                rationale=gap.rationale,
                target_gap=GapCategory.ZERO_VALUE,
                relevance_score=gap.relevance_score,
                is_boundary=True,
            )
        ]

    def _gen_negative_values(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
        relational_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        # Constraint check: min_value >= 0 strictly forbids negative numbers
        if spec and spec.min_value is not None and spec.min_value >= 0:
            return []

        # Specialized Two Sum negative-value candidate generation
        if is_two_sum_context(context, relational_metadata):
            col_p, target_p = self._extract_two_sum_params(base_inputs, relational_metadata)
            if col_p and target_p and col_p in base_inputs and target_p in base_inputs:
                orig_target = base_inputs[target_p]
                orig_nums = base_inputs[col_p]
                if name == col_p and isinstance(orig_nums, (list, tuple)):
                    t_val = orig_target if isinstance(orig_target, (int, float)) and not isinstance(orig_target, bool) else 9
                    neg = -5
                    comp = t_val - neg
                    filler = t_val + 20
                    cand = self._build_two_sum_candidate(
                        cid=f"gen-negative-{name}",
                        label=f"Negative value for {name}",
                        rationale=f"Sequence '{name}' contains negative element {neg} with companion {comp} summing to target {t_val}.",
                        gap=gap,
                        col_param=col_p,
                        target_param=target_p,
                        nums=[neg, comp, filler] if isinstance(orig_nums, list) else (neg, comp, filler),
                        target=t_val,
                        base_inputs=base_inputs,
                        spec=spec,
                    )
                    if cand:
                        return [cand]
                elif name == target_p and isinstance(orig_nums, (list, tuple)):
                    t_neg = -10 if (spec is None or spec.min_value is None or spec.min_value <= -10) else int(spec.min_value)
                    v1, v2 = int(t_neg // 2), t_neg - int(t_neg // 2)
                    if v1 == v2:
                        v1 -= 1
                        v2 += 1
                    filler = 20
                    cand = self._build_two_sum_candidate(
                        cid=f"gen-negative-{name}",
                        label=f"Negative value for {name}",
                        rationale=f"Target parameter '{name}' is negative ({t_neg}) with pair [{v1}, {v2}] summing to target.",
                        gap=gap,
                        col_param=col_p,
                        target_param=target_p,
                        nums=[v1, v2, filler] if isinstance(orig_nums, list) else (v1, v2, filler),
                        target=t_neg,
                        base_inputs=base_inputs,
                        spec=spec,
                    )
                    if cand:
                        return [cand]

        # Safe negative number within constraints
        neg_val = -1
        if spec and spec.max_value is not None and spec.max_value < 0:
            neg_val = int(spec.max_value)
        elif spec and spec.min_value is not None:
            neg_val = int(spec.min_value) if spec.min_value > -10 else -5

        if spec and spec.min_value is not None and neg_val < spec.min_value:
            neg_val = int(spec.min_value)
        if spec and spec.max_value is not None and neg_val > spec.max_value:
            neg_val = int(spec.max_value)
        if neg_val >= 0:
            return []

        inputs = copy.deepcopy(base_inputs)
        orig = inputs[name]

        if isinstance(orig, (int, float)) and not isinstance(orig, bool):
            inputs[name] = float(neg_val) if isinstance(orig, float) else neg_val
        elif isinstance(orig, list) and orig and not isinstance(orig[0], bool) and isinstance(orig[0], (int, float)):
            mod = list(orig)
            mod[0] = float(neg_val) if isinstance(orig[0], float) else neg_val
            inputs[name] = mod
        elif isinstance(orig, tuple) and orig and not isinstance(orig[0], bool) and isinstance(orig[0], (int, float)):
            val = float(neg_val) if isinstance(orig[0], float) else neg_val
            inputs[name] = (val,) + orig[1:]
        elif isinstance(orig, list) and orig and isinstance(orig[0], list) and orig[0] and not isinstance(orig[0][0], bool) and isinstance(orig[0][0], (int, float)):
            mod = copy.deepcopy(orig)
            mod[0][0] = float(neg_val) if isinstance(orig[0][0], float) else neg_val
            inputs[name] = mod
        else:
            return []

        return [
            TestCase(
                id=f"gen-negative-{name}",
                source=TestCaseSource.GENERATED_TEST,
                input_data=inputs,
                expected_output=None,
                is_expected_output_verified=False,
                label=f"Negative value for {name}",
                rationale=gap.rationale,
                target_gap=GapCategory.NEGATIVE_VALUES,
                relevance_score=gap.relevance_score,
                is_boundary=True,
            )
        ]

    def _gen_duplicates(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
        relational_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        if spec and spec.max_length is not None and spec.max_length < 2:
            return []

        orig = base_inputs[name]

        # 1. Only identify and update companion sum targets when additive semantics
        # are explicitly supported by reliable problem context or metadata.
        # Do NOT infer mathematical relationships solely from parameter names.
        is_additive = is_additive_relationship(context, relational_metadata)
        target_param = None

        if is_additive:
            if relational_metadata and isinstance(relational_metadata, dict):
                if (
                    relational_metadata.get("collection_param") == name
                    and relational_metadata.get("target_param") in base_inputs
                ):
                    target_param = relational_metadata.get("target_param")

            if not target_param:
                for p, v in base_inputs.items():
                    if p != name and isinstance(v, (int, float)) and not isinstance(v, bool):
                        if p.lower() in ("target", "target_sum", "sum", "goal", "total"):
                            target_param = p
                            break

        # 2. Additive branch: Generates duplicate pair summing to target
        if is_additive and target_param is not None and isinstance(orig, (list, tuple)):
            v = 3
            if spec and spec.min_value is not None and v < spec.min_value:
                v = int(spec.min_value)
            if spec and spec.max_value is not None and 2 * v > spec.max_value:
                v = int(spec.max_value // 2)

            if spec is None or (
                (spec.min_value is None or v >= spec.min_value)
                and (spec.max_value is None or 2 * v <= spec.max_value)
            ):
                rel_inputs = copy.deepcopy(base_inputs)
                pair = [v, v] if isinstance(orig, list) else (v, v)
                rel_inputs[name] = pair
                rel_inputs[target_param] = 2 * v

                return [
                    TestCase(
                        id=f"gen-duplicate-relational-{name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=rel_inputs,
                        expected_output=None,
                        is_expected_output_verified=False,
                        label=f"Duplicate pair summing to target for {name}",
                        rationale=f"Sequence '{name}' contains duplicate values [{v}, {v}] summing to target {2 * v}.",
                        target_gap=GapCategory.DUPLICATE_ELEMENTS,
                        relevance_score=gap.relevance_score,
                        classification=CandidateClassification.VALID.value,
                        classification_reason="Satisfies all supported supplied problem constraints with preserved relational target.",
                    )
                ]

        # 3. Search or unknown relationships:
        # Do not modify the target using an assumed sum relationship.
        inputs = copy.deepcopy(base_inputs)
        if isinstance(orig, list):
            if len(orig) >= 2:
                mod = list(orig)
                mod[1] = mod[0]
            else:
                val = orig[0] if orig else (int(spec.min_value) if spec and spec.min_value is not None else 1)
                mod = [val, val]
            inputs[name] = mod
        elif isinstance(orig, tuple):
            if len(orig) >= 2:
                mod = list(orig)
                mod[1] = mod[0]
            else:
                val = orig[0] if orig else (int(spec.min_value) if spec and spec.min_value is not None else 1)
                mod = [val, val]
            inputs[name] = tuple(mod)
        elif isinstance(orig, str):
            char = orig[0] if orig else "a"
            inputs[name] = char + char + orig[1:] if len(orig) >= 2 else char + char
        else:
            return []

        is_str = isinstance(orig, str)
        cand = TestCase(
            id=f"gen-duplicate-{name}",
            source=TestCaseSource.GENERATED_TEST,
            input_data=inputs,
            expected_output=None,
            is_expected_output_verified=False,
            label=f"Repeated-character pattern in {name}" if is_str else f"Duplicate elements in {name}",
            rationale=gap.rationale,
            target_gap=GapCategory.REPEATED_PATTERN if is_str else GapCategory.DUPLICATE_ELEMENTS,
            relevance_score=gap.relevance_score,
            classification=CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
            classification_reason="Repeated character mutation; problem validity unknown." if is_str else "Generic duplicate mutation without recognized relational invariant; problem validity unknown.",
        )
        if spec and (
            spec.min_length is not None
            or spec.max_length is not None
            or spec.min_value is not None
            or spec.max_value is not None
            or spec.allowed_characters is not None
        ):
            from core.test_intelligence.constraint_parser import classify_candidate
            c_type, c_reason = classify_candidate(cand, spec)
            cand.classification = c_type
            cand.classification_reason = c_reason

        return [cand]

    def _gen_all_identical(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
        relational_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        if spec and spec.max_length is not None and spec.max_length < 2:
            return []

        if is_two_sum_context(context, relational_metadata):
            orig = base_inputs[name]
            if isinstance(orig, (list, tuple)) and len(orig) >= 2:
                elem = orig[0]
                inputs = copy.deepcopy(base_inputs)
                inputs[name] = [elem, elem] if isinstance(orig, list) else (elem, elem)
                return [
                    TestCase(
                        id=f"gen-identical-{name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=inputs,
                        expected_output=None,
                        is_expected_output_verified=False,
                        label=f"All-identical {name}",
                        rationale=gap.rationale,
                        target_gap=GapCategory.IDENTICAL_ALL,
                        relevance_score=gap.relevance_score,
                        classification=CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                        classification_reason="Violates problem logical invariant: all-identical elements cannot produce exactly one valid pair summing to target.",
                    )
                ]

        inputs = copy.deepcopy(base_inputs)
        orig = inputs[name]

        if isinstance(orig, (list, tuple)):
            if orig:
                elem = orig[0]
            elif spec and spec.min_value is not None:
                elem = int(spec.min_value)
            elif spec and spec.max_value is not None:
                elem = int(spec.max_value)
            else:
                elem = 1

            # Clamp element to numeric bounds if applicable
            if isinstance(elem, (int, float)) and not isinstance(elem, bool):
                if spec and spec.min_value is not None and elem < spec.min_value:
                    elem = int(spec.min_value)
                if spec and spec.max_value is not None and elem > spec.max_value:
                    elem = int(spec.max_value)

            length = max(len(orig), 3)
            if spec and spec.min_length is not None:
                length = max(length, spec.min_length)
            if spec and spec.max_length is not None:
                length = min(length, spec.max_length)
            if length < 2:
                return []
            res_list = [elem] * max(2, length)
            inputs[name] = res_list if isinstance(orig, list) else tuple(res_list)

        elif isinstance(orig, str):
            char = orig[0] if orig else "z"
            length = max(len(orig), 3)
            if spec and spec.min_length is not None:
                length = max(length, spec.min_length)
            if spec and spec.max_length is not None:
                length = min(length, spec.max_length)
            if length < 2:
                return []
            inputs[name] = char * length
        else:
            return []

        return [
            TestCase(
                id=f"gen-identical-{name}",
                source=TestCaseSource.GENERATED_TEST,
                input_data=inputs,
                expected_output=None,
                is_expected_output_verified=False,
                label=f"All-identical {name}",
                rationale=gap.rationale,
                target_gap=GapCategory.IDENTICAL_ALL,
                relevance_score=gap.relevance_score,
            )
        ]

    def _gen_order_variant(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        inputs = copy.deepcopy(base_inputs)
        orig = inputs[name]

        if not isinstance(orig, (list, tuple)) or len(orig) < 2:
            return []

        is_tup = isinstance(orig, tuple)
        orig_list = list(orig)

        try:
            if gap.category == GapCategory.ALREADY_SORTED:
                sorted_l = sorted(orig_list)
                inputs[name] = tuple(sorted_l) if is_tup else sorted_l
                label = f"Sorted {name}"
                cid = f"gen-sorted-{name}"
            elif gap.category == GapCategory.REVERSE_SORTED:
                rev_l = sorted(orig_list, reverse=True)
                inputs[name] = tuple(rev_l) if is_tup else rev_l
                label = f"Reverse-sorted {name}"
                cid = f"gen-reversed-{name}"
            elif gap.category == GapCategory.UNSORTED_SEQUENCE:
                if len(set(orig_list)) <= 1:
                    if (
                        spec
                        and spec.min_value is not None
                        and spec.max_value is not None
                        and spec.max_value > spec.min_value
                    ):
                        min_v = int(spec.min_value)
                        max_v = int(spec.max_value)
                        scrambled = [max_v, min_v, max_v]
                        inputs[name] = tuple(scrambled) if is_tup else scrambled
                    else:
                        return []
                else:
                    if len(orig_list) >= 3 and orig_list[0] != orig_list[1]:
                        scrambled = [orig_list[1], orig_list[0]] + orig_list[2:]
                    else:
                        scrambled = [orig_list[-1]] + orig_list[:-1]
                    inputs[name] = tuple(scrambled) if is_tup else scrambled

                label = f"Unsorted {name}"
                cid = f"gen-unsorted-{name}"
            else:
                return []
        except TypeError:
            return []

        cand = TestCase(
            id=cid,
            source=TestCaseSource.GENERATED_TEST,
            input_data=inputs,
            expected_output=None,
            is_expected_output_verified=False,
            label=label,
            rationale=gap.rationale,
            target_gap=gap.category,
            relevance_score=gap.relevance_score,
        )
        if spec and spec.is_sorted_ascending and gap.category in (GapCategory.UNSORTED_SEQUENCE, GapCategory.REVERSE_SORTED):
            cand.classification = CandidateClassification.ROBUSTNESS_PROBE.value
            cand.classification_reason = f"Violates problem constraint: '{name}' must be sorted in ascending order. Deliberate robustness probe."
        return [cand]

    def _gen_constraint_boundary(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
        relational_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[ProblemContext] = None,
    ) -> List[TestCase]:
        if not name or name not in base_inputs or not spec:
            return []

        orig = base_inputs[name]
        cases: List[TestCase] = []

        # Specialized Two Sum boundary generation
        if is_two_sum_context(context, relational_metadata):
            col_p, target_p = self._extract_two_sum_params(base_inputs, relational_metadata)
            if col_p and target_p and col_p in base_inputs and target_p in base_inputs:
                orig_nums = base_inputs[col_p]
                if gap.category == GapCategory.LOWER_CONSTRAINT_BOUND:
                    if name == target_p and spec.min_value is not None:
                        min_t = int(spec.min_value) if spec.min_value.is_integer() else spec.min_value
                        cand = self._build_two_sum_candidate(
                            cid=f"gen-bound-min-val-{name}",
                            label=f"Minimum constraint value for {name}",
                            rationale=gap.rationale,
                            gap=gap,
                            col_param=col_p,
                            target_param=target_p,
                            nums=[min_t, 0, 100] if isinstance(orig_nums, list) else (min_t, 0, 100),
                            target=min_t,
                            base_inputs=base_inputs,
                            spec=spec,
                        )
                        if cand:
                            cases.append(cand)
                            return cases
                    elif name == col_p and spec.min_value is not None and isinstance(orig_nums, (list, tuple)):
                        min_v = int(spec.min_value) if spec.min_value.is_integer() else spec.min_value
                        comp = 5
                        cand = self._build_two_sum_candidate(
                            cid=f"gen-bound-min-val-{name}",
                            label=f"Minimum constraint value for {name}",
                            rationale=gap.rationale,
                            gap=gap,
                            col_param=col_p,
                            target_param=target_p,
                            nums=[min_v, comp, 100] if isinstance(orig_nums, list) else (min_v, comp, 100),
                            target=min_v + comp,
                            base_inputs=base_inputs,
                            spec=spec,
                        )
                        if cand:
                            cases.append(cand)
                            return cases

                elif gap.category == GapCategory.UPPER_CONSTRAINT_BOUND:
                    if name == target_p and spec.max_value is not None:
                        max_t = int(spec.max_value) if spec.max_value.is_integer() else spec.max_value
                        cand = self._build_two_sum_candidate(
                            cid=f"gen-bound-max-val-{name}",
                            label=f"Maximum constraint value for {name}",
                            rationale=gap.rationale,
                            gap=gap,
                            col_param=col_p,
                            target_param=target_p,
                            nums=[max_t, 0, -100] if isinstance(orig_nums, list) else (max_t, 0, -100),
                            target=max_t,
                            base_inputs=base_inputs,
                            spec=spec,
                        )
                        if cand:
                            cases.append(cand)
                            return cases
                    elif name == col_p and isinstance(orig_nums, (list, tuple)):
                        if spec.max_value is not None:
                            max_v = int(spec.max_value) if spec.max_value.is_integer() else spec.max_value
                            comp = -5
                            cand = self._build_two_sum_candidate(
                                cid=f"gen-bound-max-val-{name}",
                                label=f"Maximum constraint value for {name}",
                                rationale=gap.rationale,
                                gap=gap,
                                col_param=col_p,
                                target_param=target_p,
                                nums=[max_v, comp, -100] if isinstance(orig_nums, list) else (max_v, comp, -100),
                                target=max_v + comp,
                                base_inputs=base_inputs,
                                spec=spec,
                            )
                            if cand:
                                cases.append(cand)

                        if spec.max_length is not None and spec.max_length >= 2:
                            scale_len = min(spec.max_length, self.MAX_ARRAY_SCALE)
                            if scale_len == spec.max_length:
                                scale_label = f"Maximum constraint length ({scale_len} elements) for {name}"
                            else:
                                scale_label = f"Stress scale ({scale_len} elements of {spec.max_length} max) for {name}"
                            t_val = base_inputs[target_p]
                            if isinstance(t_val, (int, float)) and not isinstance(t_val, bool):
                                p1, p2 = 2, t_val - 2
                                filler = 1 if (t_val != 2 and t_val != 3 and t_val != p2 + 1) else (0 if t_val != 0 else -1)
                                scaled_nums = [filler] * (scale_len - 2) + [p1, p2]
                                cand_scale = self._build_two_sum_candidate(
                                    cid=f"gen-bound-scale-{name}",
                                    label=scale_label,
                                    rationale=gap.rationale,
                                    gap=gap,
                                    col_param=col_p,
                                    target_param=target_p,
                                    nums=scaled_nums if isinstance(orig_nums, list) else tuple(scaled_nums),
                                    target=t_val,
                                    base_inputs=base_inputs,
                                    spec=spec,
                                    is_scale=True,
                                )
                                if cand_scale:
                                    cases.append(cand_scale)

                        if cases:
                            return cases

        # Resolve granular per-parameter specification
        p_spec = spec.param_specs.get(name.lower()) if (spec and spec.param_specs) else None
        eff_min_v = p_spec.min_value if (p_spec and p_spec.min_value is not None) else spec.min_value
        eff_max_v = p_spec.max_value if (p_spec and p_spec.max_value is not None) else spec.max_value
        eff_min_l = p_spec.min_length if (p_spec and p_spec.min_length is not None) else spec.min_length
        eff_max_l = p_spec.max_length if (p_spec and p_spec.max_length is not None) else spec.max_length

        meta = gap.metadata or {}
        is_len_gap = (
            "constraint_min_length" in meta
            or "constraint_max_length" in meta
            or "length" in gap.rationale.lower()
            or "length" in gap.suggested_action.lower()
        )
        is_val_gap = (
            "constraint_min_value" in meta
            or "constraint_max_value" in meta
            or "value bound" in gap.rationale.lower()
            or "minimum constraint value" in gap.rationale.lower()
            or "maximum constraint value" in gap.rationale.lower()
            or "exact minimum value" in gap.rationale.lower()
            or "exact maximum value" in gap.rationale.lower()
        )

        if gap.category == GapCategory.LOWER_CONSTRAINT_BOUND:
            if (is_val_gap or not is_len_gap) and eff_min_v is not None:
                min_v = int(eff_min_v) if eff_min_v.is_integer() else eff_min_v
                if isinstance(orig, (int, float)) and not isinstance(orig, bool):
                    inputs_val = copy.deepcopy(base_inputs)
                    inputs_val[name] = min_v
                    cases.append(
                        TestCase(
                            id=f"gen-bound-min-val-{name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=inputs_val,
                            expected_output=None,
                            is_expected_output_verified=False,
                            label=f"Minimum constraint value for {name}",
                            rationale=gap.rationale,
                            target_gap=GapCategory.LOWER_CONSTRAINT_BOUND,
                            relevance_score=gap.relevance_score,
                            is_boundary=True,
                        )
                    )
                elif isinstance(orig, (list, tuple)) and orig and not isinstance(orig[0], bool) and isinstance(orig[0], (int, float)):
                    inputs_val = copy.deepcopy(base_inputs)
                    mod = list(orig)
                    if spec and spec.is_sorted_ascending:
                        mod[0] = min_v
                        mod.sort()
                    else:
                        mod[0] = min_v
                    inputs_val[name] = tuple(mod) if isinstance(orig, tuple) else mod
                    cases.append(
                        TestCase(
                            id=f"gen-bound-min-val-{name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=inputs_val,
                            expected_output=None,
                            is_expected_output_verified=False,
                            label=f"Minimum constraint value for {name}",
                            rationale=gap.rationale,
                            target_gap=GapCategory.LOWER_CONSTRAINT_BOUND,
                            relevance_score=gap.relevance_score,
                            is_boundary=True,
                        )
                    )

            if (is_len_gap or not is_val_gap) and eff_min_l is not None and isinstance(orig, (list, tuple, str)):
                if eff_min_l > 0:
                    inputs_len = copy.deepcopy(base_inputs)
                    if isinstance(orig, str):
                        eff_chars = p_spec.allowed_characters if (p_spec and p_spec.allowed_characters) else (spec.allowed_characters if spec else None)
                        if eff_chars and any(c in eff_chars for c in "()[]{}"):
                            elem = "("
                        elif orig:
                            elem = orig[0]
                        else:
                            elem = eff_chars[0] if eff_chars else "a"
                        inputs_len[name] = elem * eff_min_l
                    elif isinstance(orig, tuple):
                        elem = orig[0] if orig else 1
                        inputs_len[name] = tuple([elem] * eff_min_l)
                    else:
                        elem = orig[0] if orig else 1
                        inputs_len[name] = [elem] * eff_min_l
                    cases.append(
                        TestCase(
                            id=f"gen-bound-min-len-{name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=inputs_len,
                            expected_output=None,
                            is_expected_output_verified=False,
                            label=f"Minimum constraint length for {name}",
                            rationale=gap.rationale,
                            target_gap=GapCategory.LOWER_CONSTRAINT_BOUND,
                            relevance_score=gap.relevance_score,
                            is_boundary=True,
                        )
                    )

        elif gap.category == GapCategory.UPPER_CONSTRAINT_BOUND:
            if (is_val_gap or not is_len_gap) and eff_max_v is not None:
                max_v = int(eff_max_v) if eff_max_v.is_integer() else eff_max_v
                if isinstance(orig, (int, float)) and not isinstance(orig, bool):
                    inputs_val = copy.deepcopy(base_inputs)
                    inputs_val[name] = max_v
                    cases.append(
                        TestCase(
                            id=f"gen-bound-max-val-{name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=inputs_val,
                            expected_output=None,
                            is_expected_output_verified=False,
                            label=f"Maximum constraint value for {name}",
                            rationale=gap.rationale,
                            target_gap=GapCategory.UPPER_CONSTRAINT_BOUND,
                            relevance_score=gap.relevance_score,
                            is_boundary=True,
                        )
                    )
                elif isinstance(orig, (list, tuple)) and orig and not isinstance(orig[0], bool) and isinstance(orig[0], (int, float)):
                    inputs_val = copy.deepcopy(base_inputs)
                    mod = list(orig)
                    if spec and spec.is_sorted_ascending:
                        mod[-1] = max_v
                        mod.sort()
                    else:
                        mod[0] = max_v
                    inputs_val[name] = tuple(mod) if isinstance(orig, tuple) else mod
                    cases.append(
                        TestCase(
                            id=f"gen-bound-max-val-{name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=inputs_val,
                            expected_output=None,
                            is_expected_output_verified=False,
                            label=f"Maximum constraint value for {name}",
                            rationale=gap.rationale,
                            target_gap=GapCategory.UPPER_CONSTRAINT_BOUND,
                            relevance_score=gap.relevance_score,
                            is_boundary=True,
                        )
                    )

            if (is_len_gap or not is_val_gap) and eff_max_l is not None and isinstance(orig, (list, tuple, str)):
                min_l = eff_min_l if eff_min_l is not None else 1
                scale_len = min(eff_max_l, max(min_l, self.MAX_ARRAY_SCALE))
                if scale_len == eff_max_l:
                    scale_label = f"Maximum constraint length ({scale_len} elements) for {name}"
                else:
                    scale_label = f"Stress scale ({scale_len} elements of {eff_max_l} max) for {name}"

                # Two Sum specialized array length scale preserving exactly one valid pair
                if is_two_sum_context(context, relational_metadata):
                    col_p, target_p = self._extract_two_sum_params(base_inputs, relational_metadata)
                    if col_p == name and target_p and target_p in base_inputs:
                        t_val = base_inputs[target_p]
                        if isinstance(t_val, (int, float)) and not isinstance(t_val, bool):
                            p1, p2 = 2, t_val - 2
                            filler = 1 if (t_val != 2 and t_val != 3 and t_val != p2 + 1) else (0 if t_val != 0 else -1)
                            scaled_nums = [filler] * (scale_len - 2) + [p1, p2]
                            cand = self._build_two_sum_candidate(
                                cid=f"gen-bound-max-len-{name}",
                                label=scale_label,
                                rationale=gap.rationale,
                                gap=gap,
                                col_param=col_p,
                                target_param=target_p,
                                nums=scaled_nums if isinstance(orig, list) else tuple(scaled_nums),
                                target=t_val,
                                base_inputs=base_inputs,
                                spec=spec,
                                is_performance=True,
                            )
                            if cand:
                                cases.append(cand)
                                return cases

                inputs_len = copy.deepcopy(base_inputs)
                if isinstance(orig, str):
                    eff_chars = p_spec.allowed_characters if (p_spec and p_spec.allowed_characters) else (spec.allowed_characters if spec else None)
                    if eff_chars and any(c in eff_chars for c in "()[]{}"):
                        if scale_len % 2 == 0:
                            inputs_len[name] = "()" * (scale_len // 2)
                        else:
                            inputs_len[name] = "(" * scale_len
                    elif orig:
                        elem = orig[0]
                        inputs_len[name] = elem * scale_len
                    else:
                        elem = eff_chars[0] if eff_chars else "a"
                        inputs_len[name] = elem * scale_len
                elif isinstance(orig, tuple):
                    if spec and (spec.is_sorted_ascending or spec.unique_elements):
                        min_v = int(eff_min_v) if eff_min_v is not None else 0
                        inputs_len[name] = tuple(range(min_v, min_v + scale_len))
                    else:
                        elem = orig[0] if orig else 1
                        inputs_len[name] = tuple([elem] * scale_len)
                else:
                    if spec and (spec.is_sorted_ascending or spec.unique_elements):
                        min_v = int(eff_min_v) if eff_min_v is not None else 0
                        max_v = int(eff_max_v) if eff_max_v is not None else (min_v + scale_len)
                        start_v = min_v if (max_v - scale_len >= min_v) else min_v
                        inputs_len[name] = list(range(start_v, start_v + scale_len))
                        # Clamp any companion scalar parameters within valid bounds
                        for pk, pv in inputs_len.items():
                            if pk != name and isinstance(pv, (int, float)) and not isinstance(pv, bool):
                                pk_spec = spec.param_specs.get(pk.lower()) if (spec and spec.param_specs) else None
                                p_min = pk_spec.min_value if (pk_spec and pk_spec.min_value is not None) else spec.min_value
                                p_max = pk_spec.max_value if (pk_spec and pk_spec.max_value is not None) else spec.max_value
                                if p_min is not None and pv < p_min:
                                    inputs_len[pk] = p_min
                                elif p_max is not None and pv > p_max:
                                    inputs_len[pk] = p_max
                    else:
                        elem = orig[0] if orig else 1
                        inputs_len[name] = [elem] * scale_len

                # Cross-parameter relation handling: e.g. WINDOW_LEQ_ARRAY_LENGTH (k <= len(nums))
                if spec and spec.cross_constraints:
                    for cc in spec.cross_constraints:
                        if cc.relation_type in ("WINDOW_LEQ_ARRAY_LENGTH", "LEQ_LENGTH") and len(cc.parameters_involved) >= 2:
                            p_win = cc.parameters_involved[0]
                            p_arr = cc.parameters_involved[1]
                            if p_win in inputs_len and p_arr in inputs_len:
                                if name == p_arr and scale_len == eff_max_l:
                                    p_win_spec = spec.param_specs.get(p_win.lower()) if spec.param_specs else None
                                    if p_win_spec and p_win_spec.max_value is not None:
                                        inputs_len[p_win] = int(p_win_spec.max_value)
                                    else:
                                        inputs_len[p_win] = scale_len

                cases.append(
                    TestCase(
                        id=f"gen-bound-max-len-{name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=inputs_len,
                        expected_output=None,
                        is_expected_output_verified=False,
                        label=scale_label,
                        rationale=gap.rationale,
                        target_gap=GapCategory.UPPER_CONSTRAINT_BOUND,
                        relevance_score=gap.relevance_score,
                        is_boundary=True,
                        is_performance=True,
                    )
                )

        return cases

    def _gen_relational_cases(
        self,
        gap: CoverageGap,
        base_inputs: Dict[str, Any],
        relational_metadata: Optional[Dict[str, Any]],
        spec: Optional[ConstraintSpec] = None,
    ) -> List[TestCase]:
        if not relational_metadata or not isinstance(relational_metadata, dict):
            return []

        coll_name = relational_metadata.get("collection_param")
        t_name = relational_metadata.get("target_param")

        if not isinstance(coll_name, str) or not isinstance(t_name, str):
            return []
        if coll_name not in base_inputs or t_name not in base_inputs:
            return []

        coll_val = base_inputs[coll_name]
        if not isinstance(coll_val, (list, tuple)) or not coll_val:
            return []

        cases: List[TestCase] = []

        if gap.category == GapCategory.TARGET_NOT_FOUND:
            inputs = copy.deepcopy(base_inputs)
            absent_val = None

            # Numeric collections (int/float, not bool)
            if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in coll_val):
                max_v = max(coll_val)
                min_v = min(coll_val)
                if spec is None or spec.max_value is None or max_v + 1 <= spec.max_value:
                    absent_val = int(max_v + 1)
                elif spec.min_value is None or min_v - 1 >= spec.min_value:
                    absent_val = int(min_v - 1)
                else:
                    coll_set = set(coll_val)
                    for cand_v in range(int(min_v), int(max_v)):
                        if cand_v not in coll_set:
                            absent_val = cand_v
                            break
            # String collections
            elif all(isinstance(x, str) for x in coll_val):
                orig_t = str(base_inputs[t_name]) if isinstance(base_inputs[t_name], str) else "target"
                cand_str = orig_t + "_absent"
                if cand_str not in coll_val:
                    absent_val = cand_str
                else:
                    absent_val = cand_str + "_unique"
            # Boolean collections
            elif all(isinstance(x, bool) for x in coll_val):
                if True not in coll_val:
                    absent_val = True
                elif False not in coll_val:
                    absent_val = False

            # Strict relational check: absent_val must be found and truly absent from coll_val
            if absent_val is None or absent_val in coll_val:
                return []

            # Check bounds on absent_val
            if isinstance(absent_val, (int, float)) and not isinstance(absent_val, bool):
                if spec and spec.min_value is not None and absent_val < spec.min_value:
                    return []
                if spec and spec.max_value is not None and absent_val > spec.max_value:
                    return []

            inputs[t_name] = absent_val

            cases.append(
                TestCase(
                    id=f"gen-rel-absent-{t_name}",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=inputs,
                    expected_output=None,
                    is_expected_output_verified=False,
                    label=f"Absent target '{t_name}'",
                    rationale=gap.rationale,
                    target_gap=GapCategory.TARGET_NOT_FOUND,
                    relevance_score=gap.relevance_score,
                )
            )

        elif gap.category == GapCategory.TARGET_AT_BOUNDARIES:
            # First index
            inputs_first = copy.deepcopy(base_inputs)
            inputs_first[t_name] = coll_val[0]
            cases.append(
                TestCase(
                    id=f"gen-rel-first-idx-{t_name}",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=inputs_first,
                    expected_output=None,
                    is_expected_output_verified=False,
                    label=f"Target '{t_name}' at first index (0)",
                    rationale=gap.rationale,
                    target_gap=GapCategory.TARGET_AT_BOUNDARIES,
                    relevance_score=gap.relevance_score,
                    is_boundary=True,
                )
            )

            # Last index only if length > 1
            if len(coll_val) > 1:
                inputs_last = copy.deepcopy(base_inputs)
                inputs_last[t_name] = coll_val[-1]
                cases.append(
                    TestCase(
                        id=f"gen-rel-last-idx-{t_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=inputs_last,
                        expected_output=None,
                        is_expected_output_verified=False,
                        label=f"Target '{t_name}' at last index (N-1)",
                        rationale=gap.rationale,
                        target_gap=GapCategory.TARGET_AT_BOUNDARIES,
                        relevance_score=gap.relevance_score,
                        is_boundary=True,
                    )
                )

        return cases

    def _gen_matrix_dimensions(
        self,
        name: Optional[str],
        base_inputs: Dict[str, Any],
        spec: Optional[ConstraintSpec],
        gap: CoverageGap,
    ) -> List[TestCase]:
        if not name or name not in base_inputs:
            return []

        orig = base_inputs[name]
        if not isinstance(orig, list) or not orig or not isinstance(orig[0], list):
            return []

        inputs = copy.deepcopy(base_inputs)
        min_r = spec.min_rows if (spec and spec.min_rows is not None) else (spec.min_length if (spec and spec.min_length is not None) else 1)
        max_r = spec.max_rows if (spec and spec.max_rows is not None) else (spec.max_length if (spec and spec.max_length is not None) else 100)
        min_c = spec.min_cols if (spec and spec.min_cols is not None) else 1
        max_c = spec.max_cols if (spec and spec.max_cols is not None) else 100
        allowed_vals = spec.allowed_values if spec else None

        # Determine cell sample and value
        sample_cell = orig[0][0] if (orig[0] and len(orig[0]) > 0) else 0
        cell_val = sample_cell

        if allowed_vals:
            if cell_val not in allowed_vals:
                cell_val = allowed_vals[0]
        elif isinstance(cell_val, (int, float)) and not isinstance(cell_val, bool):
            if spec and spec.min_value is not None and cell_val < spec.min_value:
                cell_val = int(spec.min_value)
            if spec and spec.max_value is not None and cell_val > spec.max_value:
                cell_val = int(spec.max_value)

        # Decide rectangular dimensions rows != cols
        rows = max(min_r, 2)
        cols = max(min_c, 3)
        if rows == cols:
            cols = rows + 1
        if max_r and rows > max_r:
            rows = max_r
        if max_c and cols > max_c:
            cols = max_c
        if rows == cols and rows > min_r:
            rows = min_r

        alt_val = (
            allowed_vals[1] if (allowed_vals and len(allowed_vals) > 1)
            else (cell_val + 1 if (spec and spec.max_value is not None and cell_val < spec.max_value) else cell_val)
        )
        grid_data = [[(cell_val if (r + c) % 2 == 0 else alt_val) for c in range(cols)] for r in range(rows)]
        if spec and spec.endpoints_zero:
            grid_data[0][0] = 0
            grid_data[rows - 1][cols - 1] = 0

        inputs[name] = grid_data

        return [
            TestCase(
                id=f"gen-matrix-rect-{name}",
                source=TestCaseSource.GENERATED_TEST,
                input_data=inputs,
                expected_output=None,
                is_expected_output_verified=False,
                label=f"Rectangular matrix for {name}",
                rationale=gap.rationale,
                target_gap=GapCategory.MATRIX_DIMENSIONS,
                relevance_score=gap.relevance_score,
            )
        ]

    def _gen_failure_family(
        self,
        gap: CoverageGap,
        existing_cases: List[TestCase],
        spec: Optional[ConstraintSpec],
    ) -> List[TestCase]:
        failing_cases = [
            tc for tc in existing_cases if tc.source == TestCaseSource.PLATFORM_REVEALED_FAILURE
        ]
        if not failing_cases:
            return []

        cases: List[TestCase] = []
        for idx, fc in enumerate(failing_cases):
            inputs_orig = copy.deepcopy(fc.input_data)
            for p_name, val in list(inputs_orig.items()):
                if isinstance(val, (list, tuple, str)) and len(val) >= 2:
                    min_l = spec.min_length if (spec and spec.min_length is not None) else 1
                    target_l = max(min_l, len(val) - 1)
                    if target_l < len(val):
                        variant_inputs = copy.deepcopy(inputs_orig)
                        variant_inputs[p_name] = val[:target_l]
                        cases.append(
                            TestCase(
                                id=f"gen-fail-family-scaled-{idx+1}-{p_name}",
                                source=TestCaseSource.GENERATED_TEST,
                                input_data=variant_inputs,
                                expected_output=None,
                                is_expected_output_verified=False,
                                label=f"Failure Family Variant ({p_name})",
                                rationale=gap.rationale,
                                target_gap=GapCategory.FAILURE_FAMILY_EXTRAPOLATION,
                                relevance_score=gap.relevance_score,
                            )
                        )

        return cases
