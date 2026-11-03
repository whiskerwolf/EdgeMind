"""
EdgeMind Adaptive Test Intelligence Package.
"""

from core.test_intelligence.context_intelligence import (
    InferredParameter,
    classify_context_candidate,
    infer_parameter_context,
    synthesize_context_candidates,
)
from core.test_intelligence.models import (
    AdaptiveTestReport,
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
    parse_number_expression,
)
from core.test_intelligence.extractor import (
    CollectionProfile,
    FeatureProfileExtractor,
    FeatureStatus,
    InputFeatureProfile,
    MultiplicityProfile,
    NumericProfile,
    OrderProfile,
    ParameterProfile,
    RelationalProfile,
)
from core.test_intelligence.gap_detector import (
    ConstraintValidity,
    CoverageGap,
    CoverageGapEvaluator,
    CoverageGapResult,
    GapSeverity,
)
from core.test_intelligence.synthesizer import (
    TargetedTestSynthesizer,
    canonical_input_signature,
)
from core.test_intelligence.ranker import (
    CandidateRanker,
    CandidateRankingResult,
    RankedCandidate,
    RankingScore,
    RankingWeights,
)

__all__ = [
    "AdaptiveTestReport",
    "CandidateClassification",
    "CandidateRanker",
    "CandidateRankingResult",
    "CollectionProfile",
    "ConstraintSpec",
    "ConstraintValidity",
    "CoverageGap",
    "CoverageGapEvaluator",
    "CoverageGapResult",
    "FeatureProfileExtractor",
    "FeatureStatus",
    "GapCategory",
    "GapSeverity",
    "InferredParameter",
    "InputFeatureProfile",
    "MultiplicityProfile",
    "NumericProfile",
    "OrderProfile",
    "ParameterProfile",
    "ProblemContext",
    "RankedCandidate",
    "RankingScore",
    "RankingWeights",
    "RelationalProfile",
    "TargetedTestSynthesizer",
    "TestCase",
    "TestCaseSource",
    "canonical_input_signature",
    "classify_candidate",
    "classify_context_candidate",
    "infer_parameter_context",
    "parse_constraint_expressions",
    "parse_number_expression",
    "synthesize_context_candidates",
]


