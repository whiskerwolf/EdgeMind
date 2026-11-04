"""
EdgeMind Adaptive Test Intelligence - Data Models & Provenance.

Defines strictly typed models, provenance enums, and validation logic for
test-case intelligence, problem constraints, and coverage-gap reporting.
Guarantees strict provenance tracking, disclaimers, and immutable source labeling.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class TestCaseSource(str, Enum):
    """
    Defines the origin of every test case in EdgeMind.
    Prevents synthetic or unverified tests from being misrepresented as platform tests.
    """
    PUBLIC_SAMPLE = "PUBLIC_SAMPLE"
    # Published examples from problem statements or editor initial consoles.

    AUTHORIZED_PLATFORM_TEST = "AUTHORIZED_PLATFORM_TEST"
    # Obtained via documented, authorized platform APIs (if any).

    GENERATED_TEST = "GENERATED_TEST"
    # Synthesized deterministically by EdgeMind's adaptive test engine.

    PLATFORM_REVEALED_FAILURE = "PLATFORM_REVEALED_FAILURE"
    # An actual failing case returned by a platform judge after a user submission.

    USER_PROVIDED_TEST = "USER_PROVIDED_TEST"
    # Custom test input explicitly provided by the developer.

    def is_generated(self) -> bool:
        return self == TestCaseSource.GENERATED_TEST

    def is_platform_native(self) -> bool:
        return self in (
            TestCaseSource.PUBLIC_SAMPLE,
            TestCaseSource.AUTHORIZED_PLATFORM_TEST,
            TestCaseSource.PLATFORM_REVEALED_FAILURE,
        )


# Tell pytest that TestCaseSource is a domain model, not a test suite
TestCaseSource.__test__ = False


class GapCategory(str, Enum):
    """
    Taxonomy of input-domain coverage gaps (black-box domain partitioning).
    Note: These reflect input-domain partitions, not program code branch coverage.
    """
    EMPTY_COLLECTION = "EMPTY_COLLECTION"
    SINGLETON = "SINGLETON"
    ZERO_VALUE = "ZERO_VALUE"
    NEGATIVE_VALUES = "NEGATIVE_VALUES"
    DUPLICATE_ELEMENTS = "DUPLICATE_ELEMENTS"
    IDENTICAL_ALL = "IDENTICAL_ALL"
    REVERSE_SORTED = "REVERSE_SORTED"
    ALREADY_SORTED = "ALREADY_SORTED"
    UNSORTED_SEQUENCE = "UNSORTED_SEQUENCE"
    UPPER_CONSTRAINT_BOUND = "UPPER_CONSTRAINT_BOUND"
    LOWER_CONSTRAINT_BOUND = "LOWER_CONSTRAINT_BOUND"
    TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
    TARGET_AT_BOUNDARIES = "TARGET_AT_BOUNDARIES"
    FAILURE_FAMILY_EXTRAPOLATION = "FAILURE_FAMILY_EXTRAPOLATION"
    SPECIAL_CHARACTERS = "SPECIAL_CHARACTERS"
    PARITY_ALTERNATION = "PARITY_ALTERNATION"
    MATRIX_DIMENSIONS = "MATRIX_DIMENSIONS"
    NESTED_BRACKETS = "NESTED_BRACKETS"
    BRACKET_PATTERN = "BRACKET_PATTERN"
    REPEATED_PATTERN = "REPEATED_PATTERN"
    TREE_STRUCTURE = "TREE_STRUCTURE"
    SLIDING_WINDOW_PATTERN = "SLIDING_WINDOW_PATTERN"


class CandidateClassification(str, Enum):
    """
    Three-tier candidate classification:
    - VALID: satisfies all supported supplied constraints.
    - ROBUSTNESS_PROBE: deliberately violates a known constraint.
    - CONSTRAINT_VALIDITY_UNKNOWN: insufficient information to determine validity.
    """
    VALID = "VALID"
    ROBUSTNESS_PROBE = "ROBUSTNESS PROBE"
    CONSTRAINT_VALIDITY_UNKNOWN = "CONSTRAINT VALIDITY UNKNOWN"


CandidateClassification.__test__ = False


@dataclass
class ParamConstraintSpec:
    """Machine-readable constraint bounds specific to an individual parameter."""
    name: str
    param_type: str = "unknown"
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_rows: Optional[int] = None
    max_rows: Optional[int] = None
    min_cols: Optional[int] = None
    max_cols: Optional[int] = None
    allowed_characters: Optional[str] = None
    allowed_values: Optional[List[Union[int, float]]] = None
    is_sorted_ascending: bool = False
    is_strictly_increasing: bool = False
    unique_elements: bool = False
    is_non_empty: bool = False
    no_leading_zero: bool = False
    endpoints_zero: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ParamConstraintSpec":
        if not data:
            return cls(name="")
        return cls(
            name=str(data.get("name", "")),
            param_type=str(data.get("param_type", "unknown")),
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            min_length=data.get("min_length"),
            max_length=data.get("max_length"),
            min_rows=data.get("min_rows"),
            max_rows=data.get("max_rows"),
            min_cols=data.get("min_cols"),
            max_cols=data.get("max_cols"),
            allowed_characters=data.get("allowed_characters"),
            allowed_values=data.get("allowed_values"),
            is_sorted_ascending=bool(data.get("is_sorted_ascending", False)),
            is_strictly_increasing=bool(data.get("is_strictly_increasing", False)),
            unique_elements=bool(data.get("unique_elements", False)),
            is_non_empty=bool(data.get("is_non_empty", False)),
            no_leading_zero=bool(data.get("no_leading_zero", False)),
            endpoints_zero=bool(data.get("endpoints_zero", False)),
        )


@dataclass
class ParsedConstraint:
    """Structured representation of a single parsed constraint with full provenance."""
    raw_text: str
    normalized_text: str
    parameter_name: Optional[str] = None
    constraint_type: str = "UNKNOWN"
    lower_bound: Optional[Union[int, float]] = None
    upper_bound: Optional[Union[int, float]] = None
    is_lower_inclusive: bool = True
    is_upper_inclusive: bool = True
    is_unresolved: bool = False
    unresolved_reason: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ParsedConstraint":
        if not data:
            return cls(raw_text="", normalized_text="")
        return cls(
            raw_text=str(data.get("raw_text", "")),
            normalized_text=str(data.get("normalized_text", "")),
            parameter_name=data.get("parameter_name"),
            constraint_type=str(data.get("constraint_type", "UNKNOWN")),
            lower_bound=data.get("lower_bound"),
            upper_bound=data.get("upper_bound"),
            is_lower_inclusive=bool(data.get("is_lower_inclusive", True)),
            is_upper_inclusive=bool(data.get("is_upper_inclusive", True)),
            is_unresolved=bool(data.get("is_unresolved", False)),
            unresolved_reason=data.get("unresolved_reason"),
            confidence=float(data.get("confidence", 1.0)),
        )


@dataclass
class CrossParameterConstraint:
    """Structural relationship between two or more parameters."""
    name: str
    description: str
    parameters_involved: List[str]
    relation_type: str
    expression: Optional[str] = None
    is_enforceable: bool = True
    is_unresolved: bool = False
    unresolved_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "CrossParameterConstraint":
        if not data:
            return cls(name="", description="", parameters_involved=[], relation_type="")
        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            parameters_involved=list(data.get("parameters_involved", [])),
            relation_type=str(data.get("relation_type", "")),
            expression=data.get("expression"),
            is_enforceable=bool(data.get("is_enforceable", True)),
            is_unresolved=bool(data.get("is_unresolved", False)),
            unresolved_reason=data.get("unresolved_reason"),
        )


@dataclass
class ConstraintSpec:
    """Parsed machine-readable constraint bounds for a problem with per-parameter tracking."""
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_characters: Optional[str] = None
    min_rows: Optional[int] = None
    max_rows: Optional[int] = None
    min_cols: Optional[int] = None
    max_cols: Optional[int] = None
    allowed_values: Optional[List[Union[int, float]]] = None
    endpoints_zero: bool = False
    is_sorted_ascending: bool = False
    is_strictly_increasing: bool = False
    sorted_param: Optional[str] = None
    unique_elements: bool = False
    raw_constraints: List[str] = field(default_factory=list)
    # Granular per-parameter specifications and provenance
    param_specs: Dict[str, ParamConstraintSpec] = field(default_factory=dict)
    parsed_constraints: List[ParsedConstraint] = field(default_factory=list)
    cross_constraints: List[CrossParameterConstraint] = field(default_factory=list)
    unresolved_reasons: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["param_specs"] = {k: v.to_dict() for k, v in self.param_specs.items()}
        res["parsed_constraints"] = [c.to_dict() for c in self.parsed_constraints]
        res["cross_constraints"] = [c.to_dict() for c in self.cross_constraints]
        res["unresolved_reasons"] = dict(self.unresolved_reasons)
        return res

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ConstraintSpec":
        if not data:
            return cls()
        raw_p_specs = data.get("param_specs", {})
        p_specs = {k: ParamConstraintSpec.from_dict(v) for k, v in raw_p_specs.items()}
        raw_pcs = data.get("parsed_constraints", [])
        pcs = [ParsedConstraint.from_dict(c) for c in raw_pcs]
        raw_ccs = data.get("cross_constraints", [])
        ccs = [CrossParameterConstraint.from_dict(c) for c in raw_ccs]

        return cls(
            min_value=data.get("min_value"),
            max_value=data.get("max_value"),
            min_length=data.get("min_length"),
            max_length=data.get("max_length"),
            allowed_characters=data.get("allowed_characters"),
            min_rows=data.get("min_rows"),
            max_rows=data.get("max_rows"),
            min_cols=data.get("min_cols"),
            max_cols=data.get("max_cols"),
            allowed_values=data.get("allowed_values"),
            endpoints_zero=bool(data.get("endpoints_zero", False)),
            is_sorted_ascending=bool(data.get("is_sorted_ascending", False)),
            is_strictly_increasing=bool(data.get("is_strictly_increasing", False)),
            sorted_param=data.get("sorted_param"),
            unique_elements=bool(data.get("unique_elements", False)),
            raw_constraints=list(data.get("raw_constraints", [])),
            param_specs=p_specs,
            parsed_constraints=pcs,
            cross_constraints=ccs,
            unresolved_reasons=dict(data.get("unresolved_reasons", {})),
        )


@dataclass
class ProblemContext:
    """Problem metadata, environment parameters, and platform context."""
    platform: str = "local"
    problem_id: str = ""
    title: str = ""
    description: str = ""
    constraints: List[str] = field(default_factory=list)
    constraint_spec: Optional[ConstraintSpec] = None
    time_limit_seconds: float = 1.0
    memory_limit_mb: int = 256
    function_name: Optional[str] = None
    parameters: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        if self.constraint_spec:
            res["constraint_spec"] = self.constraint_spec.to_dict()
        return res

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ProblemContext":
        if not data:
            return cls()
        spec_data = data.get("constraint_spec")
        spec = ConstraintSpec.from_dict(spec_data) if spec_data else None

        raw_params = data.get("parameters", [])
        norm_params: List[str] = []
        for p in raw_params:
            if isinstance(p, dict) and "name" in p:
                norm_params.append(str(p["name"]))
            elif hasattr(p, "name"):
                norm_params.append(str(p.name))
            elif isinstance(p, str):
                norm_params.append(p)
            elif p is not None:
                norm_params.append(str(p))

        return cls(
            platform=str(data.get("platform", "local")),
            problem_id=str(data.get("problem_id", "")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            constraints=list(data.get("constraints", [])),
            constraint_spec=spec,
            time_limit_seconds=float(data.get("time_limit_seconds", 1.0)),
            memory_limit_mb=int(data.get("memory_limit_mb", 256)),
            function_name=data.get("function_name"),
            parameters=norm_params,
        )


@dataclass
class TestCase:
    """
    Representation of an individual test case with strict provenance tracking.
    """
    id: str
    source: TestCaseSource
    input_data: Dict[str, Any]
    expected_output: Optional[Any] = None
    is_expected_output_verified: bool = False
    label: str = ""
    rationale: str = ""
    target_gap: Optional[GapCategory] = None
    relevance_score: float = 0.0
    is_boundary: bool = False
    is_performance: bool = False
    classification: Optional[str] = None
    classification_reason: Optional[str] = None

    def __post_init__(self):
        # 1. Enforce TestCaseSource type
        if isinstance(self.source, str):
            try:
                self.source = TestCaseSource(self.source)
            except ValueError:
                valid_sources = [s.value for s in TestCaseSource]
                raise ValueError(
                    f"Invalid test case source '{self.source}'. Must be one of {valid_sources}."
                )

        if not isinstance(self.source, TestCaseSource):
            raise TypeError(f"source must be an instance of TestCaseSource, got {type(self.source).__name__}")

        # 2. Enforce target_gap type if present
        if isinstance(self.target_gap, str):
            try:
                self.target_gap = GapCategory(self.target_gap)
            except ValueError:
                valid_gaps = [g.value for g in GapCategory]
                raise ValueError(
                    f"Invalid target_gap '{self.target_gap}'. Must be one of {valid_gaps}."
                )

        # 3. Enforce input_data is a dictionary
        if not isinstance(self.input_data, dict):
            raise TypeError(f"input_data must be a dict, got {type(self.input_data).__name__}")

        # 4. Strict expected_output invariant:
        # If expected_output is None, it can never be marked verified.
        if self.expected_output is None:
            self.is_expected_output_verified = False

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["source"] = self.source.value
        if self.target_gap is not None:
            res["target_gap"] = self.target_gap.value
        if self.classification is not None:
            res["classification"] = (
                self.classification.value
                if isinstance(self.classification, CandidateClassification)
                else str(self.classification)
            )
        else:
            res["classification"] = CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value
        if self.classification_reason:
            res["classification_reason"] = str(self.classification_reason)
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestCase":
        raw_source = data.get("source", TestCaseSource.USER_PROVIDED_TEST.value)
        raw_gap = data.get("target_gap")
        return cls(
            id=str(data.get("id", "")),
            source=TestCaseSource(raw_source) if isinstance(raw_source, str) else raw_source,
            input_data=dict(data.get("input_data", {})),
            expected_output=data.get("expected_output"),
            is_expected_output_verified=bool(data.get("is_expected_output_verified", False)),
            label=str(data.get("label", "")),
            rationale=str(data.get("rationale", "")),
            target_gap=GapCategory(raw_gap) if raw_gap else None,
            relevance_score=float(data.get("relevance_score", 0.0)),
            is_boundary=bool(data.get("is_boundary", False)),
            is_performance=bool(data.get("is_performance", False)),
            classification=data.get("classification"),
            classification_reason=data.get("classification_reason"),
        )


# Tell pytest that TestCase is a domain model, not a test suite
TestCase.__test__ = False



@dataclass
class AdaptiveTestReport:
    """
    Summary report of existing-test coverage analysis and newly suggested cases.
    Explicitly states that input-pattern coverage does not prove code branch coverage,
    and that execution remains disabled.
    """
    existing_tests_analyzed: int = 0
    observed_features: Dict[str, Any] = field(default_factory=dict)
    identified_gaps: List[str] = field(default_factory=list)
    suggested_tests: List[TestCase] = field(default_factory=list)
    execution_available: bool = False
    coverage_disclaimer: str = (
        "Input-pattern domain coverage only (black-box partition analysis); "
        "does not prove program code statement or branch coverage."
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "existing_tests_analyzed": self.existing_tests_analyzed,
            "observed_features": dict(self.observed_features),
            "identified_gaps": list(self.identified_gaps),
            "suggested_tests": [t.to_dict() for t in self.suggested_tests],
            "execution_available": self.execution_available,
            "coverage_disclaimer": self.coverage_disclaimer,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdaptiveTestReport":
        suggested_raw = data.get("suggested_tests", [])
        suggested = [TestCase.from_dict(t) for t in suggested_raw]
        return cls(
            existing_tests_analyzed=int(data.get("existing_tests_analyzed", 0)),
            observed_features=dict(data.get("observed_features", {})),
            identified_gaps=list(data.get("identified_gaps", [])),
            suggested_tests=suggested,
            execution_available=bool(data.get("execution_available", False)),
            coverage_disclaimer=str(
                data.get("coverage_disclaimer", cls.coverage_disclaimer)
            ),
        )
