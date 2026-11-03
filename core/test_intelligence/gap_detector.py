"""
EdgeMind Adaptive Test Intelligence - Constraint-Aware Coverage-Gap Detector.

Analyzes extracted input-feature profiles against problem constraints and domain metadata
to identify meaningful untested equivalence partitions and boundary conditions.
Suppresses irrelevant or constraint-prohibited gaps and explains rationale deterministically.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from core.test_intelligence.extractor import (
    FeatureProfileExtractor,
    FeatureStatus,
    InputFeatureProfile,
    ParameterProfile,
    RelationalProfile,
)
from core.test_intelligence.models import (
    ConstraintSpec,
    ParamConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)


class GapSeverity(str, Enum):
    """Priority / severity of an identified coverage gap."""
    HIGH = "HIGH"        # Critical boundary condition (e.g. empty collection, upper bound, failure family)
    MEDIUM = "MEDIUM"    # Significant algorithmic scenario (e.g. duplicates, reversed sequence, zero)
    LOW = "LOW"          # Secondary structural variation (e.g. rectangular matrix, subtle parity)

    @property
    def rank(self) -> int:
        """Numerical ranking for deterministic sorting: HIGH (0), MEDIUM (1), LOW (2)."""
        return {"HIGH": 0, "MEDIUM": 1, "LOW": 2}.get(self.value, 99)


class ConstraintValidity(str, Enum):
    """
    Indicates whether generating a test for this gap is permitted by known problem constraints:
    - VALID: Explicitly permitted by verified constraint bounds.
    - PROHIBITED: Explicitly forbidden by verified constraint bounds (must be suppressed).
    - UNKNOWN: Constraint bounds are not specified; validity cannot be guaranteed.
    """
    VALID = "VALID"
    PROHIBITED = "PROHIBITED"
    UNKNOWN = "UNKNOWN"


@dataclass
class CoverageGap:
    """Structured representation of an identified input coverage gap."""
    category: GapCategory
    param_name: Optional[str] = None
    severity: GapSeverity = GapSeverity.MEDIUM
    constraint_validity: ConstraintValidity = ConstraintValidity.UNKNOWN
    relevance_score: float = 0.5
    rationale: str = ""
    risk_explained: str = ""
    suggested_action: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "param_name": self.param_name,
            "severity": self.severity.value,
            "constraint_validity": self.constraint_validity.value,
            "relevance_score": round(self.relevance_score, 3),
            "rationale": self.rationale,
            "risk_explained": self.risk_explained,
            "suggested_action": self.suggested_action,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CoverageGap":
        return cls(
            category=GapCategory(data["category"]),
            param_name=data.get("param_name"),
            severity=GapSeverity(data.get("severity", "MEDIUM")),
            constraint_validity=ConstraintValidity(data.get("constraint_validity", "UNKNOWN")),
            relevance_score=float(data.get("relevance_score", 0.5)),
            rationale=str(data.get("rationale", "")),
            risk_explained=str(data.get("risk_explained", "")),
            suggested_action=str(data.get("suggested_action", "")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class CoverageGapResult:
    """Comprehensive result of coverage gap evaluation."""
    gaps: List[CoverageGap] = field(default_factory=list)
    total_gaps: int = 0
    evaluated_parameters: List[str] = field(default_factory=list)
    constraint_spec_present: bool = False
    coverage_disclaimer: str = (
        "Input-pattern domain coverage only (black-box partition analysis); "
        "identifying an unobserved partition does not prove the program contains a bug, "
        "nor does covering it prove code branch coverage."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gaps": [g.to_dict() for g in self.gaps],
            "total_gaps": self.total_gaps,
            "evaluated_parameters": list(self.evaluated_parameters),
            "constraint_spec_present": self.constraint_spec_present,
            "coverage_disclaimer": self.coverage_disclaimer,
        }


class CoverageGapEvaluator:
    """
    Evaluates existing test case profiles against problem constraints and domain rules
    to detect meaningful, actionable coverage gaps.
    """

    def __init__(self, extractor: Optional[FeatureProfileExtractor] = None):
        self.extractor = extractor or FeatureProfileExtractor()

    def _get_param_spec(self, name: str, spec: Optional[ConstraintSpec]) -> Optional[ParamConstraintSpec]:
        if not spec:
            return None
        if spec.param_specs and name.lower() in spec.param_specs:
            return spec.param_specs[name.lower()]
        return None

    def evaluate(
        self,
        test_cases: List[TestCase],
        context: Optional[ProblemContext] = None,
        profile: Optional[InputFeatureProfile] = None,
        relational_metadata: Optional[Dict[str, Any]] = None,
    ) -> CoverageGapResult:
        """
        Evaluate test cases and identify coverage gaps.

        Parameters:
            test_cases: List of TestCase models.
            context: ProblemContext containing ConstraintSpec and metadata.
            profile: Optional pre-extracted InputFeatureProfile (if already available).
            relational_metadata: Optional explicit parameter relationship specifications.

        Returns:
            CoverageGapResult containing categorized, ranked, and explained gaps.
        """
        ctx = context or getattr(self.extractor, "context", None)
        spec = ctx.constraint_spec if ctx else None

        # 1. Use existing extractor if profile was not pre-computed
        feature_profile = profile or self.extractor.extract(
            test_cases, context=ctx, relational_metadata=relational_metadata
        )

        gaps: List[CoverageGap] = []
        evaluated_params = sorted(list(feature_profile.parameters.keys()))

        # 2. Evaluate per-parameter rules
        for p_name, param_prof in feature_profile.parameters.items():
            gaps.extend(self._evaluate_parameter_gaps(p_name, param_prof, spec))

        # 3. Evaluate relational rules
        gaps.extend(self._evaluate_relational_gaps(feature_profile.relational, spec))

        # 4. Evaluate failure extrapolation rules
        gaps.extend(self._evaluate_failure_extrapolation_gaps(test_cases, feature_profile))

        # 5. Deduplicate and sort deterministically
        unique_gaps = self._deduplicate_gaps(gaps)
        sorted_gaps = sorted(
            unique_gaps,
            key=lambda g: (
                g.severity.rank,
                -g.relevance_score,
                g.category.value,
                g.param_name or "",
            ),
        )

        return CoverageGapResult(
            gaps=sorted_gaps,
            total_gaps=len(sorted_gaps),
            evaluated_parameters=evaluated_params,
            constraint_spec_present=spec is not None,
        )

    # =========================================================================
    # Parameter Gap Evaluation Rules
    # =========================================================================

    def _evaluate_parameter_gaps(
        self,
        name: str,
        param: ParameterProfile,
        spec: Optional[ConstraintSpec],
    ) -> List[CoverageGap]:
        gaps: List[CoverageGap] = []

        # 1. Empty Collection
        empty_gap = self._check_empty_collection(name, param, spec)
        if empty_gap:
            gaps.append(empty_gap)

        # 2. Singleton Collection
        singleton_gap = self._check_singleton_collection(name, param, spec)
        if singleton_gap:
            gaps.append(singleton_gap)

        # 3. Zero Value
        zero_gap = self._check_zero_value(name, param, spec)
        if zero_gap:
            gaps.append(zero_gap)

        # 4. Negative Values
        neg_gap = self._check_negative_values(name, param, spec)
        if neg_gap:
            gaps.append(neg_gap)

        # 5. Duplicates
        dup_gap = self._check_duplicates(name, param, spec)
        if dup_gap:
            gaps.append(dup_gap)

        # 6. All-Identical
        ident_gap = self._check_all_identical(name, param, spec)
        if ident_gap:
            gaps.append(ident_gap)

        # 7. Ordering (Sorted, Reversed, Unsorted)
        gaps.extend(self._check_ordering_gaps(name, param, spec))

        # 8. Constraint Boundaries
        gaps.extend(self._check_constraint_boundaries(name, param, spec))

        # 9. Matrix Dimensions
        matrix_gaps = self._check_matrix_dimensions(name, param, spec)
        gaps.extend(matrix_gaps)

        # 10. String Special Characters
        str_gaps = self._check_string_gaps(name, param, spec)
        gaps.extend(str_gaps)

        return gaps

    # --- Rule Implementations ---

    def _check_empty_collection(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> Optional[CoverageGap]:
        coll = param.collection
        if not coll.has_empty.is_applicable():
            return None

        if coll.has_empty == FeatureStatus.OBSERVED:
            return None  # Already covered

        p_spec = self._get_param_spec(name, spec)
        if p_spec:
            if p_spec.is_non_empty or (p_spec.min_length is not None and p_spec.min_length > 0) or (p_spec.min_rows is not None and p_spec.min_rows > 0):
                return None  # Suppress prohibited gap per parameter spec
            if p_spec.min_length is not None and p_spec.min_length == 0:
                validity = ConstraintValidity.VALID

        # Global constraint check: If min_length > 0 or min_rows > 0, empty is PROHIBITED by constraints!
        if spec and (
            (spec.min_length is not None and spec.min_length > 0)
            or (spec.min_rows is not None and spec.min_rows > 0)
        ):
            return None  # Suppress prohibited gap

        validity = ConstraintValidity.UNKNOWN
        if spec and spec.min_length is not None and spec.min_length == 0:
            validity = ConstraintValidity.VALID

        return CoverageGap(
            category=GapCategory.EMPTY_COLLECTION,
            param_name=name,
            severity=GapSeverity.HIGH,
            constraint_validity=validity,
            relevance_score=0.90,
            rationale=(
                f"Collection parameter '{name}' was never tested with an empty collection (length 0)."
            ),
            risk_explained=(
                f"Algorithms iterating or indexing '{name}' frequently raise IndexError or ZeroDivisionError on empty inputs."
            ),
            suggested_action=f"Add a test case where '{name}' is empty (e.g. [] or '').",
            metadata={"observed_lengths": coll.observed_lengths},
        )

    def _check_singleton_collection(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> Optional[CoverageGap]:
        coll = param.collection
        if not coll.has_singleton.is_applicable():
            return None

        if coll.has_singleton == FeatureStatus.OBSERVED:
            return None  # Already covered

        p_spec = self._get_param_spec(name, spec)
        eff_min_l = p_spec.min_length if (p_spec and p_spec.min_length is not None) else (spec.min_length if spec else None)
        eff_max_l = p_spec.max_length if (p_spec and p_spec.max_length is not None) else (spec.max_length if spec else None)
        eff_min_r = p_spec.min_rows if (p_spec and p_spec.min_rows is not None) else (spec.min_rows if spec else None)

        # Constraint check: If min_length > 1 or max_length < 1 or min_rows > 1, singleton prohibited
        if (eff_min_l is not None and eff_min_l > 1) or (eff_min_r is not None and eff_min_r > 1):
            return None
        if eff_max_l is not None and eff_max_l < 1:
            return None

        # If minimum constraint length is 1, LOWER_CONSTRAINT_BOUND already covers length 1.
        # Suppress redundant SINGLETON gap to avoid duplicate reporting.
        if eff_min_l is not None and eff_min_l == 1:
            return None

        validity = ConstraintValidity.UNKNOWN
        if eff_min_l is not None and eff_min_l <= 1:
            if eff_max_l is None or eff_max_l >= 1:
                validity = ConstraintValidity.VALID

        return CoverageGap(
            category=GapCategory.SINGLETON,
            param_name=name,
            severity=GapSeverity.MEDIUM,
            constraint_validity=validity,
            relevance_score=0.75,
            rationale=f"Collection parameter '{name}' was never tested with a single-element input (length 1).",
            risk_explained=(
                f"Two-pointer loops, sliding windows, and divide-and-conquer steps often assume at least two elements and fail on singletons."
            ),
            suggested_action=f"Add a test case where '{name}' contains exactly one element.",
            metadata={"observed_lengths": coll.observed_lengths},
        )

    def _check_zero_value(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> Optional[CoverageGap]:
        num = param.numeric
        if not num.has_zero.is_applicable():
            return None

        if num.has_zero == FeatureStatus.OBSERVED:
            return None  # Already covered

        p_spec = self._get_param_spec(name, spec)
        eff_min_v = p_spec.min_value if (p_spec and p_spec.min_value is not None) else (spec.min_value if spec else None)
        eff_max_v = p_spec.max_value if (p_spec and p_spec.max_value is not None) else (spec.max_value if spec else None)

        # Constraint check: If min_value > 0 or max_value < 0, zero is prohibited
        if eff_min_v is not None and eff_min_v > 0:
            return None
        if eff_max_v is not None and eff_max_v < 0:
            return None

        validity = ConstraintValidity.UNKNOWN
        if eff_min_v is not None and eff_max_v is not None:
            if eff_min_v <= 0 <= eff_max_v:
                validity = ConstraintValidity.VALID

        return CoverageGap(
            category=GapCategory.ZERO_VALUE,
            param_name=name,
            severity=GapSeverity.HIGH,
            constraint_validity=validity,
            relevance_score=0.85,
            rationale=f"Numeric parameter or sequence '{name}' was never tested with a value of zero (0).",
            risk_explained=(
                f"Zero values expose division-by-zero, multiplication by zero, falsy condition bugs (if not x:), and base-case omissions."
            ),
            suggested_action=f"Add a test case where '{name}' is or contains 0.",
            metadata={"min_observed": num.min_value, "max_observed": num.max_value},
        )

    def _check_negative_values(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> Optional[CoverageGap]:
        num = param.numeric
        if not num.has_negative.is_applicable():
            return None

        if num.has_negative == FeatureStatus.OBSERVED:
            return None  # Already covered

        p_spec = self._get_param_spec(name, spec)
        eff_min_v = p_spec.min_value if (p_spec and p_spec.min_value is not None) else (spec.min_value if spec else None)

        # Constraint check: If min_value >= 0, negative values are PROHIBITED
        if eff_min_v is not None and eff_min_v >= 0:
            return None  # Suppress prohibited gap

        validity = ConstraintValidity.UNKNOWN
        if eff_min_v is not None and eff_min_v < 0:
            validity = ConstraintValidity.VALID

        return CoverageGap(
            category=GapCategory.NEGATIVE_VALUES,
            param_name=name,
            severity=GapSeverity.HIGH,
            constraint_validity=validity,
            relevance_score=0.85,
            rationale=f"Numeric parameter or sequence '{name}' was never tested with negative values.",
            risk_explained=(
                f"Negative numbers expose unsigned integer assumptions, inverted comparison logic, and Python negative-modulo behavior."
            ),
            suggested_action=f"Add a test case where '{name}' is or contains negative values.",
            metadata={"min_observed": num.min_value, "max_observed": num.max_value},
        )

    def _check_duplicates(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> Optional[CoverageGap]:
        mult = param.multiplicity
        if not mult.has_duplicates.is_applicable():
            return None

        if mult.has_duplicates == FeatureStatus.OBSERVED:
            return None  # Already covered

        p_spec = self._get_param_spec(name, spec)
        is_unique = (p_spec and p_spec.unique_elements) or (spec and spec.unique_elements)
        if is_unique:
            return None  # Suppress duplicates if problem requires unique/distinct elements

        eff_max_l = p_spec.max_length if (p_spec and p_spec.max_length is not None) else (spec.max_length if spec else None)
        # Constraint check: If max_length < 2, duplicates are impossible
        if eff_max_l is not None and eff_max_l < 2:
            return None

        validity = ConstraintValidity.UNKNOWN
        if spec and spec.max_length is not None and spec.max_length >= 2:
            validity = ConstraintValidity.VALID

        return CoverageGap(
            category=GapCategory.DUPLICATE_ELEMENTS,
            param_name=name,
            severity=GapSeverity.HIGH,
            constraint_validity=validity,
            relevance_score=0.80,
            rationale=f"Sequence parameter '{name}' was never tested with duplicate/repeated elements.",
            risk_explained=(
                f"Duplicate items often cause hash-map key collisions/overwrites, multi-set counting bugs, and binary-search pointer stagnation."
            ),
            suggested_action=f"Add a test case where '{name}' contains duplicate values (e.g. [x, x]).",
            metadata={"sample_count": param.sample_count},
        )

    def _check_all_identical(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> Optional[CoverageGap]:
        mult = param.multiplicity
        if not mult.has_all_identical.is_applicable():
            return None

        if mult.has_all_identical == FeatureStatus.OBSERVED:
            return None  # Already covered

        p_spec = self._get_param_spec(name, spec)
        is_unique = (p_spec and p_spec.unique_elements) or (spec and spec.unique_elements)
        if is_unique:
            return None  # Suppress all-identical if problem requires unique/distinct elements

        eff_max_l = p_spec.max_length if (p_spec and p_spec.max_length is not None) else (spec.max_length if spec else None)
        if eff_max_l is not None and eff_max_l < 2:
            return None

        return CoverageGap(
            category=GapCategory.IDENTICAL_ALL,
            param_name=name,
            severity=GapSeverity.MEDIUM,
            constraint_validity=ConstraintValidity.VALID if (spec and spec.max_length and spec.max_length >= 2) else ConstraintValidity.UNKNOWN,
            relevance_score=0.70,
            rationale=f"Sequence parameter '{name}' was never tested where all elements are identical (e.g. [5, 5, 5]).",
            risk_explained=(
                f"Zero-entropy arrays trigger worst-case O(N^2) partitioning in un-randomized quicksort algorithms and infinite loop loops."
            ),
            suggested_action=f"Add a test case where all elements in '{name}' are identical.",
        )

    def _check_ordering_gaps(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> List[CoverageGap]:
        # Domain-aware rule: Suppress sequence ordering gaps (sorted, reversed)
        # for string parameters unless string sorting is explicitly relevant.
        if "str" in param.types_observed and "list" not in param.types_observed:
            return []

        order = param.order
        gaps: List[CoverageGap] = []
        if not order.has_strictly_increasing.is_applicable():
            return gaps

        # If sortedness is explicitly required by problem constraints,
        # unsorted sequences and reverse sorted sequences are NOT valid inputs.
        p_spec = self._get_param_spec(name, spec)
        is_sorted_required = False
        if p_spec and p_spec.is_sorted_ascending:
            is_sorted_required = True
        elif spec and spec.is_sorted_ascending:
            if spec.sorted_param is None or spec.sorted_param == name.lower():
                is_sorted_required = True

        # If already sorted was never tested
        if (
            order.has_strictly_increasing == FeatureStatus.UNOBSERVED
            and order.has_non_decreasing == FeatureStatus.UNOBSERVED
        ):
            gaps.append(
                CoverageGap(
                    category=GapCategory.ALREADY_SORTED,
                    param_name=name,
                    severity=GapSeverity.MEDIUM,
                    constraint_validity=ConstraintValidity.UNKNOWN,
                    relevance_score=0.65,
                    rationale=f"Sequence parameter '{name}' was never tested in strictly sorted ascending order.",
                    risk_explained="Tests best-case/worst-case sorting paths and early-exit branch optimizations.",
                    suggested_action=f"Add a test case where '{name}' is already sorted.",
                )
            )

        # If reverse sorted was never tested
        if (
            not is_sorted_required
            and order.has_strictly_decreasing == FeatureStatus.UNOBSERVED
            and order.has_non_increasing == FeatureStatus.UNOBSERVED
        ):
            gaps.append(
                CoverageGap(
                    category=GapCategory.REVERSE_SORTED,
                    param_name=name,
                    severity=GapSeverity.MEDIUM,
                    constraint_validity=ConstraintValidity.UNKNOWN,
                    relevance_score=0.70,
                    rationale=f"Sequence parameter '{name}' was never tested in reverse sorted descending order.",
                    risk_explained="Exposes monotonic stack/queue boundary limits and descending comparison oversights.",
                    suggested_action=f"Add a test case where '{name}' is reverse-sorted.",
                )
            )

        # If unsorted was never tested (only sorted inputs were provided!)
        if not is_sorted_required and order.has_unsorted == FeatureStatus.UNOBSERVED:
            gaps.append(
                CoverageGap(
                    category=GapCategory.UNSORTED_SEQUENCE,
                    param_name=name,
                    severity=GapSeverity.HIGH,
                    constraint_validity=ConstraintValidity.UNKNOWN,
                    relevance_score=0.85,
                    rationale=f"Sequence parameter '{name}' was only tested on sorted data; arbitrary unsorted order was never tested.",
                    risk_explained=(
                        f"Solutions accidentally assuming pre-sorted inputs will pass existing samples but fail on arbitrary permutations."
                    ),
                    suggested_action=f"Add a test case where '{name}' contains arbitrary unsorted data.",
                )
            )

        return gaps

    def _check_constraint_boundaries(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> List[CoverageGap]:
        if not spec:
            return []

        p_spec = self._get_param_spec(name, spec)
        eff_min_v = p_spec.min_value if (p_spec and p_spec.min_value is not None) else spec.min_value
        eff_max_v = p_spec.max_value if (p_spec and p_spec.max_value is not None) else spec.max_value
        eff_min_l = p_spec.min_length if (p_spec and p_spec.min_length is not None) else spec.min_length
        eff_max_l = p_spec.max_length if (p_spec and p_spec.max_length is not None) else spec.max_length

        is_collection = any(t in ("list", "str", "tuple", "dict", "set") for t in param.types_observed)
        is_scalar = any(t in ("int", "float") for t in param.types_observed) and not is_collection

        gaps: List[CoverageGap] = []

        # Numeric value lower bound
        if eff_min_v is not None and (is_scalar or param.numeric.has_zero != FeatureStatus.NOT_APPLICABLE):
            already_has_min = (
                param.numeric.includes_constraint_min == FeatureStatus.OBSERVED
                or param.numeric.min_value == eff_min_v
            )
            if not already_has_min:
                gaps.append(
                    CoverageGap(
                        category=GapCategory.LOWER_CONSTRAINT_BOUND,
                        param_name=name,
                        severity=GapSeverity.HIGH,
                        constraint_validity=ConstraintValidity.VALID,
                        relevance_score=0.90,
                        rationale=f"Parameter '{name}' was never tested at the exact minimum value bound ({eff_min_v}).",
                        risk_explained="Edge boundary conditions at the minimum constraint limit often expose off-by-one bounds.",
                        suggested_action=f"Add a test case containing the exact minimum constraint value {eff_min_v}.",
                        metadata={"constraint_min_value": eff_min_v},
                    )
                )

        # Collection length lower bound
        if is_collection and eff_min_l is not None and eff_min_l > 0:
            already_has_min_l = (
                param.collection.includes_constraint_min_length == FeatureStatus.OBSERVED
                or (param.collection.min_length is not None and param.collection.min_length <= eff_min_l)
                or (eff_min_l in param.collection.observed_lengths)
            )
            if not already_has_min_l:
                gaps.append(
                    CoverageGap(
                        category=GapCategory.LOWER_CONSTRAINT_BOUND,
                        param_name=name,
                        severity=GapSeverity.HIGH,
                        constraint_validity=ConstraintValidity.VALID,
                        relevance_score=0.85,
                        rationale=f"Collection '{name}' was never tested at the exact minimum length bound ({eff_min_l}).",
                        risk_explained="Exposes initialization and indexing limits at the minimum supported size.",
                        suggested_action=f"Add a test case where '{name}' has length {eff_min_l}.",
                        metadata={"constraint_min_length": eff_min_l},
                    )
                )

        # Numeric value upper bound
        if eff_max_v is not None and (is_scalar or param.numeric.has_zero != FeatureStatus.NOT_APPLICABLE):
            if param.numeric.includes_constraint_max == FeatureStatus.UNOBSERVED:
                gaps.append(
                    CoverageGap(
                        category=GapCategory.UPPER_CONSTRAINT_BOUND,
                        param_name=name,
                        severity=GapSeverity.HIGH,
                        constraint_validity=ConstraintValidity.VALID,
                        relevance_score=0.90,
                        rationale=f"Parameter '{name}' was never tested at the exact maximum value bound ({eff_max_v}).",
                        risk_explained="Large values expose integer overflow limits and extreme accumulator values.",
                        suggested_action=f"Add a test case containing the exact maximum constraint value {eff_max_v}.",
                        metadata={"constraint_max_value": eff_max_v},
                    )
                )

        # Collection length upper bound
        if is_collection and eff_max_l is not None:
            if param.collection.includes_constraint_max_length == FeatureStatus.UNOBSERVED:
                gaps.append(
                    CoverageGap(
                        category=GapCategory.UPPER_CONSTRAINT_BOUND,
                        param_name=name,
                        severity=GapSeverity.HIGH,
                        constraint_validity=ConstraintValidity.VALID,
                        relevance_score=0.95,
                        rationale=f"Collection '{name}' was never tested at the maximum length bound ({eff_max_l}).",
                        risk_explained="Large input scales expose O(N^2) Time Limit Exceeded (TLE) and recursion depth limits.",
                        suggested_action=f"Add a scale test case where '{name}' has length {eff_max_l}.",
                        metadata={"constraint_max_length": eff_max_l},
                    )
                )

        return gaps

    def _check_matrix_dimensions(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> List[CoverageGap]:
        coll = param.collection
        if not coll.is_matrix.is_applicable() or coll.is_matrix != FeatureStatus.OBSERVED:
            return []

        gaps: List[CoverageGap] = []

        # If only square matrices were tested, flag rectangular gap
        if (
            coll.is_square_matrix == FeatureStatus.OBSERVED
            and coll.is_rectangular_matrix == FeatureStatus.UNOBSERVED
        ):
            gaps.append(
                CoverageGap(
                    category=GapCategory.MATRIX_DIMENSIONS,
                    param_name=name,
                    severity=GapSeverity.MEDIUM,
                    constraint_validity=ConstraintValidity.UNKNOWN,
                    relevance_score=0.75,
                    rationale=f"Matrix parameter '{name}' was only tested on square matrices (N x N); rectangular matrices (M x N) are untested.",
                    risk_explained="Algorithms often accidentally swap row and column bounds (e.g. matrix[col][row] or using len(matrix) for both dimensions).",
                    suggested_action=f"Add a test case with a non-square rectangular matrix where rows != columns (e.g. 2x3 or 3x1).",
                    metadata={"observed_dimensions": coll.matrix_dimensions},
                )
            )

        return gaps

    def _check_string_gaps(
        self, name: str, param: ParameterProfile, spec: Optional[ConstraintSpec]
    ) -> List[CoverageGap]:
        if "str" not in param.types_observed:
            return []

        gaps: List[CoverageGap] = []
        # Check if special characters are permitted
        if spec and spec.allowed_characters:
            if spec.allowed_characters.lower() in ("a-z", "a-za-z", "alphanumeric", "digits"):
                return []  # Prohibited by constraint

        return gaps

    # =========================================================================
    # Relational Gap Evaluation Rules
    # =========================================================================

    def _evaluate_relational_gaps(
        self,
        relational_profiles: List[RelationalProfile],
        spec: Optional[ConstraintSpec],
    ) -> List[CoverageGap]:
        gaps: List[CoverageGap] = []

        for rel in relational_profiles:
            # Strictly skip if relationship is UNKNOWN or metadata was missing
            if rel.relationship_type == "UNKNOWN" or not rel.collection_param or not rel.target_param:
                continue

            c_name = rel.collection_param
            t_name = rel.target_param

            # 1. Target Not Found
            if rel.target_absent == FeatureStatus.UNOBSERVED:
                gaps.append(
                    CoverageGap(
                        category=GapCategory.TARGET_NOT_FOUND,
                        param_name=t_name,
                        severity=GapSeverity.HIGH,
                        constraint_validity=ConstraintValidity.UNKNOWN,
                        relevance_score=0.90,
                        rationale=(
                            f"Target parameter '{t_name}' was always present in collection '{c_name}'; "
                            f"the absent/not-found scenario was never tested."
                        ),
                        risk_explained="Search algorithms often fail to return standard sentinel values (-1, None, False) or raise IndexError when target is missing.",
                        suggested_action=f"Add a test case where '{t_name}' does not exist inside '{c_name}'.",
                        metadata={"collection_param": c_name, "target_param": t_name},
                    )
                )

            # 2. Target at Boundaries
            if (
                rel.target_at_first_index == FeatureStatus.UNOBSERVED
                or rel.target_at_last_index == FeatureStatus.UNOBSERVED
            ):
                gaps.append(
                    CoverageGap(
                        category=GapCategory.TARGET_AT_BOUNDARIES,
                        param_name=t_name,
                        severity=GapSeverity.MEDIUM,
                        constraint_validity=ConstraintValidity.UNKNOWN,
                        relevance_score=0.75,
                        rationale=(
                            f"Target parameter '{t_name}' was never tested at the exact first index (0) "
                            f"or last index (N-1) of collection '{c_name}'."
                        ),
                        risk_explained="Binary search and pointer traversal logic frequently contain fencepost bugs at index 0 and index N-1.",
                        suggested_action=f"Add test cases where '{t_name}' is located strictly at index 0 and index len({c_name})-1.",
                        metadata={"collection_param": c_name, "target_param": t_name},
                    )
                )

        return gaps

    # =========================================================================
    # Failure Extrapolation Rules
    # =========================================================================

    def _evaluate_failure_extrapolation_gaps(
        self,
        test_cases: List[TestCase],
        profile: InputFeatureProfile,
    ) -> List[CoverageGap]:
        gaps: List[CoverageGap] = []
        failure_cases = [
            tc for tc in test_cases if tc.source == TestCaseSource.PLATFORM_REVEALED_FAILURE
        ]

        if not failure_cases:
            return gaps

        for idx, fc in enumerate(failure_cases):
            gaps.append(
                CoverageGap(
                    category=GapCategory.FAILURE_FAMILY_EXTRAPOLATION,
                    param_name=None,
                    severity=GapSeverity.HIGH,
                    constraint_validity=ConstraintValidity.VALID,
                    relevance_score=0.98,
                    rationale=(
                        f"Test case '{fc.id or idx+1}' was flagged as a PLATFORM_REVEALED_FAILURE on the platform judge. "
                        f"Related boundary variants must be tested to ensure the algorithmic fix generalizes."
                    ),
                    risk_explained="Single-case fixes often result in superficial hardcoded patches (e.g. if x == ...: return) rather than robust logic.",
                    suggested_action="Generate and test a family of boundary variants derived from the failing input structure.",
                    metadata={"failing_case_id": fc.id, "failing_input": fc.input_data},
                )
            )

        return gaps

    # =========================================================================
    # Helper & Deduplication
    # =========================================================================

    def _deduplicate_gaps(self, gaps: List[CoverageGap]) -> List[CoverageGap]:
        seen: Set[Tuple[str, Optional[str], str]] = set()
        deduped: List[CoverageGap] = []

        for g in gaps:
            sub_type = ""
            if g.metadata:
                if "constraint_min_length" in g.metadata or "constraint_max_length" in g.metadata:
                    sub_type = "length"
                elif "constraint_min_value" in g.metadata or "constraint_max_value" in g.metadata:
                    sub_type = "value"
            key = (g.category.value, g.param_name, sub_type)
            if key not in seen:
                seen.add(key)
                deduped.append(g)

        return deduped
