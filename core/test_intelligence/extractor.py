"""
EdgeMind Adaptive Test Intelligence - Feature Profile Extractor.

Deterministically analyzes existing test cases to extract structural, numeric,
multiplicity, ordering, and relational patterns across input parameters.
Distinguishes observed, unobserved, and not-applicable features without side-effects.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from core.test_intelligence.models import ConstraintSpec, ProblemContext, TestCase


class FeatureStatus(str, Enum):
    """
    3-state status for an input pattern:
    - OBSERVED: Present in at least one analyzed test case.
    - UNOBSERVED: Applicable to the input domain, but not present in any analyzed test case.
    - NOT_APPLICABLE: Cannot be determined or does not apply to this parameter's type/structure.
    """
    OBSERVED = "OBSERVED"
    UNOBSERVED = "UNOBSERVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

    def is_observed(self) -> bool:
        return self == FeatureStatus.OBSERVED

    def is_unobserved(self) -> bool:
        return self == FeatureStatus.UNOBSERVED

    def is_applicable(self) -> bool:
        return self != FeatureStatus.NOT_APPLICABLE


@dataclass
class CollectionProfile:
    """Observed collection cardinality and structural properties."""
    observed_lengths: List[int] = field(default_factory=list)
    has_empty: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_singleton: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    includes_constraint_min_length: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    includes_constraint_max_length: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    # Nested and Matrix features
    is_nested: bool = False
    is_matrix: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    matrix_dimensions: List[List[int]] = field(default_factory=list)  # [rows, cols]
    has_empty_subcollections: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    is_square_matrix: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    is_rectangular_matrix: FeatureStatus = FeatureStatus.NOT_APPLICABLE

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        for k, v in list(res.items()):
            if isinstance(getattr(self, k), FeatureStatus):
                res[k] = getattr(self, k).value
        return res


@dataclass
class NumericProfile:
    """Observed numeric signs, ranges, and boundary coverage."""
    has_negative: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_zero: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_positive: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    includes_constraint_min: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    includes_constraint_max: FeatureStatus = FeatureStatus.NOT_APPLICABLE

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        for k, v in list(res.items()):
            if isinstance(getattr(self, k), FeatureStatus):
                res[k] = getattr(self, k).value
        return res


@dataclass
class MultiplicityProfile:
    """Observed uniqueness, duplication, and uniformity properties."""
    has_duplicates: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_all_identical: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_all_unique: FeatureStatus = FeatureStatus.NOT_APPLICABLE

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        for k, v in list(res.items()):
            if isinstance(getattr(self, k), FeatureStatus):
                res[k] = getattr(self, k).value
        return res


@dataclass
class OrderProfile:
    """Observed sequence ordering and monotonicity properties."""
    has_strictly_increasing: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_non_decreasing: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_strictly_decreasing: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_non_increasing: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_constant: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    has_unsorted: FeatureStatus = FeatureStatus.NOT_APPLICABLE

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        for k, v in list(res.items()):
            if isinstance(getattr(self, k), FeatureStatus):
                res[k] = getattr(self, k).value
        return res


@dataclass
class RelationalProfile:
    """Observed relationships between multiple input parameters."""
    collection_param: Optional[str] = None
    target_param: Optional[str] = None
    relationship_type: str = "UNKNOWN"
    target_present: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    target_absent: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    target_at_first_index: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    target_at_last_index: FeatureStatus = FeatureStatus.NOT_APPLICABLE
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        for k in ("target_present", "target_absent", "target_at_first_index", "target_at_last_index"):
            res[k] = getattr(self, k).value
        return res


@dataclass
class ParameterProfile:
    """Composite feature profile for an individual named parameter."""
    name: str
    types_observed: List[str] = field(default_factory=list)
    collection: CollectionProfile = field(default_factory=CollectionProfile)
    numeric: NumericProfile = field(default_factory=NumericProfile)
    multiplicity: MultiplicityProfile = field(default_factory=MultiplicityProfile)
    order: OrderProfile = field(default_factory=OrderProfile)
    sample_count: int = 0
    missing_in_samples: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "types_observed": list(self.types_observed),
            "collection": self.collection.to_dict(),
            "numeric": self.numeric.to_dict(),
            "multiplicity": self.multiplicity.to_dict(),
            "order": self.order.to_dict(),
            "sample_count": self.sample_count,
            "missing_in_samples": self.missing_in_samples,
        }


@dataclass
class InputFeatureProfile:
    """Comprehensive input-feature profile across all analyzed test cases."""
    test_cases_analyzed: int = 0
    parameters: Dict[str, ParameterProfile] = field(default_factory=dict)
    relational: List[RelationalProfile] = field(default_factory=list)
    overall_collection: CollectionProfile = field(default_factory=CollectionProfile)
    overall_numeric: NumericProfile = field(default_factory=NumericProfile)
    overall_multiplicity: MultiplicityProfile = field(default_factory=MultiplicityProfile)
    overall_order: OrderProfile = field(default_factory=OrderProfile)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_cases_analyzed": self.test_cases_analyzed,
            "parameters": {k: v.to_dict() for k, v in self.parameters.items()},
            "relational": [r.to_dict() for r in self.relational],
            "overall_collection": self.overall_collection.to_dict(),
            "overall_numeric": self.overall_numeric.to_dict(),
            "overall_multiplicity": self.overall_multiplicity.to_dict(),
            "overall_order": self.overall_order.to_dict(),
            "metadata": dict(self.metadata),
        }


class FeatureProfileExtractor:
    """
    Analyzes a collection of TestCase inputs and produces a structured,
    deterministic InputFeatureProfile without mutating inputs or executing code.
    """

    def __init__(self, context: Optional[ProblemContext] = None):
        self.context = context

    def extract(
        self,
        test_cases: List[TestCase],
        context: Optional[ProblemContext] = None,
        relational_metadata: Optional[Dict[str, Any]] = None,
    ) -> InputFeatureProfile:
        """
        Extract input-domain feature profile from existing test cases.

        Parameters:
            test_cases: List of TestCase models to analyze.
            context: Optional ProblemContext containing constraints and metadata.
            relational_metadata: Optional explicit specification of parameter relationships.
                                 e.g. {"type": "CONTAINMENT", "collection_param": "arr", "target_param": "val"}

        Returns:
            InputFeatureProfile summarizing all observed, unobserved, and not-applicable patterns.
        """
        ctx = context or self.context
        spec = ctx.constraint_spec if ctx else None

        if not test_cases:
            return InputFeatureProfile(test_cases_analyzed=0)

        # 1. Discover all parameter names across all test cases (deterministic sorted order)
        all_param_names: Set[str] = set()
        for tc in test_cases:
            if isinstance(tc.input_data, dict):
                all_param_names.update(tc.input_data.keys())

        sorted_param_names = sorted(list(all_param_names))

        # 2. Extract profile for each parameter
        param_profiles: Dict[str, ParameterProfile] = {}
        for p_name in sorted_param_names:
            values: List[Any] = []
            missing_count = 0
            for tc in test_cases:
                if isinstance(tc.input_data, dict) and p_name in tc.input_data:
                    values.append(tc.input_data[p_name])
                else:
                    missing_count += 1

            param_profiles[p_name] = self._extract_parameter_profile(
                p_name, values, missing_count, spec
            )

        # 3. Extract relational features if explicit metadata is provided
        relational_profiles = self._extract_relational_profiles(
            test_cases, relational_metadata or getattr(ctx, "relational_spec", None)
        )

        # 4. Compute overall aggregate profiles
        overall_collection = self._aggregate_collection_profiles(
            [p.collection for p in param_profiles.values()]
        )
        overall_numeric = self._aggregate_numeric_profiles(
            [p.numeric for p in param_profiles.values()]
        )
        overall_multiplicity = self._aggregate_multiplicity_profiles(
            [p.multiplicity for p in param_profiles.values()]
        )
        overall_order = self._aggregate_order_profiles(
            [p.order for p in param_profiles.values()]
        )

        return InputFeatureProfile(
            test_cases_analyzed=len(test_cases),
            parameters=param_profiles,
            relational=relational_profiles,
            overall_collection=overall_collection,
            overall_numeric=overall_numeric,
            overall_multiplicity=overall_multiplicity,
            overall_order=overall_order,
            metadata={
                "constraint_spec_present": spec is not None,
                "platform": ctx.platform if ctx else "unknown",
            },
        )

    # =========================================================================
    # Parameter-Level Profile Extraction
    # =========================================================================

    def _extract_parameter_profile(
        self,
        name: str,
        values: List[Any],
        missing_count: int,
        spec: Optional[ConstraintSpec],
    ) -> ParameterProfile:
        types_observed = sorted(list({type(v).__name__ for v in values}))

        p_spec = spec.param_specs.get(name.lower()) if (spec and spec.param_specs) else None
        collection_profile = self._extract_collection_features(values, spec, p_spec)
        numeric_profile = self._extract_numeric_features(values, spec, p_spec)
        multiplicity_profile = self._extract_multiplicity_features(values)
        order_profile = self._extract_order_features(values)

        return ParameterProfile(
            name=name,
            types_observed=types_observed,
            collection=collection_profile,
            numeric=numeric_profile,
            multiplicity=multiplicity_profile,
            order=order_profile,
            sample_count=len(values),
            missing_in_samples=missing_count,
        )

    # =========================================================================
    # Collection Features
    # =========================================================================

    def _extract_collection_features(
        self, values: List[Any], spec: Optional[ConstraintSpec], p_spec: Optional[Any] = None
    ) -> CollectionProfile:
        collection_values = [
            v for v in values if isinstance(v, (list, tuple, set, dict, str))
        ]

        if not collection_values:
            return CollectionProfile()

        lengths = [len(v) for v in collection_values]
        unique_lengths = sorted(list(set(lengths)))

        has_empty = FeatureStatus.OBSERVED if (0 in unique_lengths) else FeatureStatus.UNOBSERVED
        has_singleton = FeatureStatus.OBSERVED if (1 in unique_lengths) else FeatureStatus.UNOBSERVED
        min_len = min(lengths) if lengths else None
        max_len = max(lengths) if lengths else None

        # Check constraint limits on length
        inc_min_len = FeatureStatus.NOT_APPLICABLE
        inc_max_len = FeatureStatus.NOT_APPLICABLE
        eff_min_l = p_spec.min_length if (p_spec and p_spec.min_length is not None) else (spec.min_length if spec else None)
        eff_max_l = p_spec.max_length if (p_spec and p_spec.max_length is not None) else (spec.max_length if spec else None)

        if eff_min_l is not None:
            inc_min_len = (
                FeatureStatus.OBSERVED
                if (eff_min_l in unique_lengths)
                else FeatureStatus.UNOBSERVED
            )
        if eff_max_l is not None:
            inc_max_len = (
                FeatureStatus.OBSERVED
                if (eff_max_l in unique_lengths)
                else FeatureStatus.UNOBSERVED
            )

        # Inspect nested collections and matrices
        is_nested = False
        is_matrix = FeatureStatus.NOT_APPLICABLE
        matrix_dims: List[List[int]] = []
        has_empty_sub = FeatureStatus.NOT_APPLICABLE
        is_square = FeatureStatus.NOT_APPLICABLE
        is_rect = FeatureStatus.NOT_APPLICABLE

        nested_candidates = [
            v for v in collection_values if isinstance(v, (list, tuple))
        ]

        if nested_candidates:
            # Check if any element inside is a collection
            has_sub_collections = any(
                any(isinstance(elem, (list, tuple, set, dict)) for elem in seq)
                for seq in nested_candidates
            )
            if has_sub_collections:
                is_nested = True
                has_empty_sub = FeatureStatus.UNOBSERVED
                is_square = FeatureStatus.UNOBSERVED
                is_rect = FeatureStatus.UNOBSERVED
                is_matrix = FeatureStatus.UNOBSERVED

                for seq in nested_candidates:
                    if not seq:
                        continue
                    # Check if all rows are lists/tuples
                    if all(isinstance(row, (list, tuple)) for row in seq):
                        is_matrix = FeatureStatus.OBSERVED
                        num_rows = len(seq)
                        row_lens = [len(r) for r in seq]
                        if any(l == 0 for l in row_lens):
                            has_empty_sub = FeatureStatus.OBSERVED

                        # If non-empty uniform row lengths, evaluate matrix dimensions
                        if row_lens and len(set(row_lens)) == 1:
                            num_cols = row_lens[0]
                            matrix_dims.append([num_rows, num_cols])
                            if num_rows == num_cols and num_rows > 0:
                                is_square = FeatureStatus.OBSERVED
                            elif num_rows > 0 and num_cols > 0 and num_rows != num_cols:
                                is_rect = FeatureStatus.OBSERVED

        return CollectionProfile(
            observed_lengths=unique_lengths,
            has_empty=has_empty,
            has_singleton=has_singleton,
            min_length=min_len,
            max_length=max_len,
            includes_constraint_min_length=inc_min_len,
            includes_constraint_max_length=inc_max_len,
            is_nested=is_nested,
            is_matrix=is_matrix,
            matrix_dimensions=matrix_dims,
            has_empty_subcollections=has_empty_sub,
            is_square_matrix=is_square,
            is_rectangular_matrix=is_rect,
        )

    # =========================================================================
    # Numeric Features
    # =========================================================================

    def _extract_numeric_features(
        self, values: List[Any], spec: Optional[ConstraintSpec], p_spec: Optional[Any] = None
    ) -> NumericProfile:
        numbers: List[Union[int, float]] = []

        def collect_numbers(item: Any):
            # Exclude booleans because in Python bool subclasses int (isinstance(True, int) is True)
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                if not (math.isnan(item) or math.isinf(item)):
                    numbers.append(item)
            elif isinstance(item, (list, tuple, set)):
                for sub in item:
                    collect_numbers(sub)
            elif isinstance(item, dict):
                for val in item.values():
                    collect_numbers(val)

        for v in values:
            collect_numbers(v)

        if not numbers:
            return NumericProfile()

        has_neg = FeatureStatus.OBSERVED if any(n < 0 for n in numbers) else FeatureStatus.UNOBSERVED
        has_z = FeatureStatus.OBSERVED if any(n == 0 for n in numbers) else FeatureStatus.UNOBSERVED
        has_pos = FeatureStatus.OBSERVED if any(n > 0 for n in numbers) else FeatureStatus.UNOBSERVED
        min_v = min(numbers)
        max_v = max(numbers)

        inc_min = FeatureStatus.NOT_APPLICABLE
        inc_max = FeatureStatus.NOT_APPLICABLE
        eff_min_v = p_spec.min_value if (p_spec and p_spec.min_value is not None) else (spec.min_value if spec else None)
        eff_max_v = p_spec.max_value if (p_spec and p_spec.max_value is not None) else (spec.max_value if spec else None)

        if eff_min_v is not None:
            inc_min = (
                FeatureStatus.OBSERVED
                if any(n == eff_min_v for n in numbers)
                else FeatureStatus.UNOBSERVED
            )
        if eff_max_v is not None:
            inc_max = (
                FeatureStatus.OBSERVED
                if any(n == eff_max_v for n in numbers)
                else FeatureStatus.UNOBSERVED
            )

        return NumericProfile(
            has_negative=has_neg,
            has_zero=has_z,
            has_positive=has_pos,
            min_value=min_v,
            max_value=max_v,
            includes_constraint_min=inc_min,
            includes_constraint_max=inc_max,
        )

    # =========================================================================
    # Multiplicity Features
    # =========================================================================

    def _extract_multiplicity_features(self, values: List[Any]) -> MultiplicityProfile:
        sequences = [
            v for v in values if isinstance(v, (list, tuple, str)) and len(v) >= 2
        ]

        if not sequences:
            return MultiplicityProfile()

        has_dup = FeatureStatus.UNOBSERVED
        has_all_ident = FeatureStatus.UNOBSERVED
        has_all_uniq = FeatureStatus.UNOBSERVED

        for seq in sequences:
            # Check all identical
            try:
                first = seq[0]
                if all(item == first for item in seq):
                    has_all_ident = FeatureStatus.OBSERVED
            except Exception:
                pass

            # Check uniqueness and duplicates
            try:
                uniq_count = len(set(seq))
                if uniq_count != len(seq):
                    has_dup = FeatureStatus.OBSERVED
                if uniq_count == len(seq):
                    has_all_uniq = FeatureStatus.OBSERVED
            except TypeError:
                # Unhashable elements fallback
                seen: List[Any] = []
                found_dup = False
                for item in seq:
                    if item in seen:
                        found_dup = True
                        break
                    seen.append(item)

                if found_dup:
                    has_dup = FeatureStatus.OBSERVED
                else:
                    has_all_uniq = FeatureStatus.OBSERVED

        return MultiplicityProfile(
            has_duplicates=has_dup,
            has_all_identical=has_all_ident,
            has_all_unique=has_all_uniq,
        )

    # =========================================================================
    # Order Features
    # =========================================================================

    def _extract_order_features(self, values: List[Any]) -> OrderProfile:
        sequences = [
            v for v in values if isinstance(v, (list, tuple, str)) and len(v) >= 2
        ]

        if not sequences:
            return OrderProfile()

        strictly_inc = FeatureStatus.UNOBSERVED
        non_dec = FeatureStatus.UNOBSERVED
        strictly_dec = FeatureStatus.UNOBSERVED
        non_inc = FeatureStatus.UNOBSERVED
        constant = FeatureStatus.UNOBSERVED
        unsorted = FeatureStatus.UNOBSERVED

        comparable_found = False

        for seq in sequences:
            try:
                is_s_inc = True
                is_n_dec = True
                is_s_dec = True
                is_n_inc = True
                is_const = True

                for i in range(len(seq) - 1):
                    a = seq[i]
                    b = seq[i + 1]

                    if not (a < b):
                        is_s_inc = False
                    if not (a <= b):
                        is_n_dec = False
                    if not (a > b):
                        is_s_dec = False
                    if not (a >= b):
                        is_n_inc = False
                    if a != b:
                        is_const = False

                comparable_found = True

                if is_s_inc:
                    strictly_inc = FeatureStatus.OBSERVED
                if is_n_dec:
                    non_dec = FeatureStatus.OBSERVED
                if is_s_dec:
                    strictly_dec = FeatureStatus.OBSERVED
                if is_n_inc:
                    non_inc = FeatureStatus.OBSERVED
                if is_const:
                    constant = FeatureStatus.OBSERVED
                if not (is_n_dec or is_n_inc):
                    unsorted = FeatureStatus.OBSERVED

            except TypeError:
                # Incomparable elements (e.g. mixed types or complex structures)
                continue

        if not comparable_found:
            return OrderProfile()

        return OrderProfile(
            has_strictly_increasing=strictly_inc,
            has_non_decreasing=non_dec,
            has_strictly_decreasing=strictly_dec,
            has_non_increasing=non_inc,
            has_constant=constant,
            has_unsorted=unsorted,
        )

    # =========================================================================
    # Relational Features
    # =========================================================================

    def _extract_relational_profiles(
        self,
        test_cases: List[TestCase],
        relational_spec: Optional[Dict[str, Any]],
    ) -> List[RelationalProfile]:
        """
        Extract relationships only when explicit relational metadata is provided.
        Never infers or guesses parameter relationships without explicit specification.
        """
        if not relational_spec or not isinstance(relational_spec, dict):
            return [
                RelationalProfile(
                    relationship_type="UNKNOWN",
                    details={"reason": "No explicit relational metadata provided."},
                )
            ]

        coll_name = relational_spec.get("collection_param")
        target_name = relational_spec.get("target_param")
        rel_type = relational_spec.get("type", "CONTAINMENT")

        if not coll_name or not target_name:
            return [
                RelationalProfile(
                    relationship_type="UNKNOWN",
                    details={"reason": "Relational metadata missing parameter names."},
                )
            ]

        # Check containment relationship
        target_present = FeatureStatus.UNOBSERVED
        target_absent = FeatureStatus.UNOBSERVED
        target_first = FeatureStatus.UNOBSERVED
        target_last = FeatureStatus.UNOBSERVED
        evaluated_cases = 0

        for tc in test_cases:
            if not isinstance(tc.input_data, dict):
                continue
            if coll_name in tc.input_data and target_name in tc.input_data:
                coll = tc.input_data[coll_name]
                target = tc.input_data[target_name]

                if isinstance(coll, (list, tuple, str)):
                    evaluated_cases += 1
                    try:
                        if target in coll:
                            target_present = FeatureStatus.OBSERVED
                        else:
                            target_absent = FeatureStatus.OBSERVED

                        if len(coll) > 0 and coll[0] == target:
                            target_first = FeatureStatus.OBSERVED

                        if len(coll) > 0 and coll[-1] == target:
                            target_last = FeatureStatus.OBSERVED
                    except Exception:
                        pass

        if evaluated_cases == 0:
            return [
                RelationalProfile(
                    collection_param=coll_name,
                    target_param=target_name,
                    relationship_type=rel_type,
                    details={"reason": "Specified relational parameters not found together in test cases."},
                )
            ]

        return [
            RelationalProfile(
                collection_param=coll_name,
                target_param=target_name,
                relationship_type=rel_type,
                target_present=target_present,
                target_absent=target_absent,
                target_at_first_index=target_first,
                target_at_last_index=target_last,
                details={"evaluated_cases": evaluated_cases},
            )
        ]

    # =========================================================================
    # Aggregators
    # =========================================================================

    def _aggregate_collection_profiles(
        self, profiles: List[CollectionProfile]
    ) -> CollectionProfile:
        applicable = [p for p in profiles if p.observed_lengths or p.has_empty.is_applicable()]
        if not applicable:
            return CollectionProfile()

        all_lengths: Set[int] = set()
        for p in applicable:
            all_lengths.update(p.observed_lengths)
        sorted_lengths = sorted(list(all_lengths))

        has_empty = FeatureStatus.OBSERVED if any(p.has_empty.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        has_single = FeatureStatus.OBSERVED if any(p.has_singleton.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        is_matrix = FeatureStatus.OBSERVED if any(p.is_matrix.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        is_square = FeatureStatus.OBSERVED if any(p.is_square_matrix.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        is_rect = FeatureStatus.OBSERVED if any(p.is_rectangular_matrix.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED

        return CollectionProfile(
            observed_lengths=sorted_lengths,
            has_empty=has_empty,
            has_singleton=has_single,
            min_length=min(sorted_lengths) if sorted_lengths else None,
            max_length=max(sorted_lengths) if sorted_lengths else None,
            is_matrix=is_matrix,
            is_square_matrix=is_square,
            is_rectangular_matrix=is_rect,
        )

    def _aggregate_numeric_profiles(self, profiles: List[NumericProfile]) -> NumericProfile:
        applicable = [p for p in profiles if p.has_negative.is_applicable()]
        if not applicable:
            return NumericProfile()

        has_neg = FeatureStatus.OBSERVED if any(p.has_negative.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        has_z = FeatureStatus.OBSERVED if any(p.has_zero.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        has_pos = FeatureStatus.OBSERVED if any(p.has_positive.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED

        min_candidates = [p.min_value for p in applicable if p.min_value is not None]
        max_candidates = [p.max_value for p in applicable if p.max_value is not None]

        return NumericProfile(
            has_negative=has_neg,
            has_zero=has_z,
            has_positive=has_pos,
            min_value=min(min_candidates) if min_candidates else None,
            max_value=max(max_candidates) if max_candidates else None,
        )

    def _aggregate_multiplicity_profiles(
        self, profiles: List[MultiplicityProfile]
    ) -> MultiplicityProfile:
        applicable = [p for p in profiles if p.has_duplicates.is_applicable()]
        if not applicable:
            return MultiplicityProfile()

        has_dup = FeatureStatus.OBSERVED if any(p.has_duplicates.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        has_all_ident = FeatureStatus.OBSERVED if any(p.has_all_identical.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED
        has_all_uniq = FeatureStatus.OBSERVED if any(p.has_all_unique.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED

        return MultiplicityProfile(
            has_duplicates=has_dup,
            has_all_identical=has_all_ident,
            has_all_unique=has_all_uniq,
        )

    def _aggregate_order_profiles(self, profiles: List[OrderProfile]) -> OrderProfile:
        applicable = [p for p in profiles if p.has_strictly_increasing.is_applicable()]
        if not applicable:
            return OrderProfile()

        return OrderProfile(
            has_strictly_increasing=FeatureStatus.OBSERVED if any(p.has_strictly_increasing.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED,
            has_non_decreasing=FeatureStatus.OBSERVED if any(p.has_non_decreasing.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED,
            has_strictly_decreasing=FeatureStatus.OBSERVED if any(p.has_strictly_decreasing.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED,
            has_non_increasing=FeatureStatus.OBSERVED if any(p.has_non_increasing.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED,
            has_constant=FeatureStatus.OBSERVED if any(p.has_constant.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED,
            has_unsorted=FeatureStatus.OBSERVED if any(p.has_unsorted.is_observed() for p in applicable) else FeatureStatus.UNOBSERVED,
        )
