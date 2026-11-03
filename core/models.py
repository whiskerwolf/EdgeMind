from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


@dataclass
class Diagnostic:
    type: str
    severity: str
    line: int
    message: str
    why: str
    fix: str
    source: str


@dataclass
class ReportFinding:
    type: str = "Unknown"
    line: int = 0
    line_number: int = 0
    message: str = ""
    why: str = ""
    explanation: str = ""
    fix: str = ""
    suggested_fix: str = ""
    concept: str = "General"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisReport:
    file_path: str
    file: str
    overall_status: str
    status: str
    score: int
    total_errors: int
    total_warnings: int
    syntax_status: str
    runtime_status: str
    logic_status: str
    quality_status: str
    complexity_status: str
    detailed_errors: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    detailed_warnings: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    summary: Dict[str, str] = field(default_factory=dict)
    ai_reasoning: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        if self.ai_reasoning is None:
            res.pop("ai_reasoning", None)
        return res


@dataclass
class AIInsight:
    finding_type: str = "Unknown"
    line: int = 0
    line_number: int = 0
    explanation: str = ""
    suggested_fix: str = ""
    confidence: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AIRequest:
    file_path: str = ""
    code: str = ""
    findings: List[Dict[str, Any]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    user_consent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AIResponse:
    status: str = "disabled"  # "success", "disabled", "skipped", "failed"
    provider: str = "null"
    summary: str = ""
    insights: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Re-export Adaptive Test Intelligence models for unified model namespace
from core.test_intelligence.models import (
    AdaptiveTestReport,
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)

