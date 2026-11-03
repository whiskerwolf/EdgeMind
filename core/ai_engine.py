import copy
from typing import Any, Dict, List, Optional

from adapters.base import AIAdapter
from adapters.null_adapter import NullAdapter
from core.models import AIInsight, AIRequest, AIResponse


class AIEngine:
    """
    AI Reasoning Engine for EdgeMind.
    Orchestrates communication between deterministic diagnostics and AI adapters.
    Guarantees that deterministic findings and metrics are never mutated or overridden.
    """

    MAX_SOURCE_LINES = 300
    MAX_SOURCE_CHARS = 12000

    def __init__(self, adapter: Optional[AIAdapter] = None):
        self.adapter = adapter or NullAdapter()

    def _bound_source_code(self, code: str) -> str:
        """Limit source code to a safe, bounded context length."""
        if not code:
            return ""

        if len(code) > self.MAX_SOURCE_CHARS:
            truncated = code[: self.MAX_SOURCE_CHARS]
            return truncated + "\n# ... [truncated: source length exceeded safety bounds]"

        lines = code.splitlines()
        if len(lines) > self.MAX_SOURCE_LINES:
            truncated_lines = lines[: self.MAX_SOURCE_LINES]
            return "\n".join(truncated_lines) + "\n# ... [truncated: line count exceeded safety bounds]"

        return code

    def _validate_response(self, response: Any) -> AIResponse:
        """Validate AIResponse structure and insights."""
        if not isinstance(response, AIResponse):
            return AIResponse(
                status="failed",
                provider=getattr(self.adapter, "name", "unknown"),
                summary="AI adapter returned an invalid response object.",
                insights=[],
                error="Invalid response object: expected AIResponse",
            )

        if response.status == "success":
            if not isinstance(response.insights, list):
                return AIResponse(
                    status="failed",
                    provider=response.provider,
                    summary="AI response contained malformed insights structure.",
                    insights=[],
                    error="Malformed insights: expected a list",
                )

            validated_insights = []
            for item in response.insights:
                if not isinstance(item, dict):
                    return AIResponse(
                        status="failed",
                        provider=response.provider,
                        summary="AI response contained an invalid insight element.",
                        insights=[],
                        error="Malformed insight item: expected a dictionary",
                    )

                finding_type = str(item.get("finding_type", item.get("type", "Unknown")))
                raw_line = item.get("line", item.get("line_number", 0))
                try:
                    line = int(raw_line) if raw_line is not None else 0
                except (ValueError, TypeError):
                    line = 0

                explanation = str(item.get("explanation", item.get("why", "")))
                suggested_fix = str(item.get("suggested_fix", item.get("fix", "")))
                confidence = str(item.get("confidence", "medium"))

                insight = AIInsight(
                    finding_type=finding_type,
                    line=line,
                    line_number=line,
                    explanation=explanation,
                    suggested_fix=suggested_fix,
                    confidence=confidence,
                )
                validated_insights.append(insight.to_dict())

            return AIResponse(
                status="success",
                provider=response.provider,
                summary=response.summary,
                insights=validated_insights,
                error=None,
            )

        return response

    def analyze(
        self,
        file_path: str,
        code: str,
        findings: List[Dict[str, Any]],
        user_consent: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> AIResponse:
        """
        Execute AI analysis for findings while preserving deterministic data.
        Source code is strictly withheld if user_consent is False.
        """
        # Deep-copy deterministic findings to guarantee non-mutation
        isolated_findings = copy.deepcopy(findings or [])

        # Strictly withhold source code if consent is not granted
        safe_code = self._bound_source_code(code) if user_consent else ""

        request = AIRequest(
            file_path=str(file_path or ""),
            code=safe_code,
            findings=isolated_findings,
            context=dict(context or {}),
            user_consent=bool(user_consent),
        )

        try:
            raw_response = self.adapter.analyze(request)
            return self._validate_response(raw_response)
        except Exception as exc:
            return AIResponse(
                status="failed",
                provider=getattr(self.adapter, "name", "unknown"),
                summary="AI reasoning encountered an unexpected internal error.",
                insights=[],
                error=f"Adapter execution error: {str(exc)}",
            )

    def enrich_report(
        self,
        report_dict: Dict[str, Any],
        code: str,
        user_consent: bool = False,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Non-destructively enrich an existing report dictionary by attaching 'ai_reasoning'.
        Guarantees that deterministic score, status, errors, and warnings remain unchanged.
        """
        # Snapshot original deterministic metrics
        original_score = report_dict.get("score")
        original_status = report_dict.get("status")
        original_overall_status = report_dict.get("overall_status")
        original_total_errors = report_dict.get("total_errors")
        original_total_warnings = report_dict.get("total_warnings")
        original_errors = copy.deepcopy(report_dict.get("detailed_errors", report_dict.get("errors", [])))
        original_warnings = copy.deepcopy(report_dict.get("detailed_warnings", report_dict.get("warnings", [])))

        file_path = str(report_dict.get("file_path", report_dict.get("file", "")))
        all_findings = original_errors + original_warnings

        ai_response = self.analyze(
            file_path=file_path,
            code=code,
            findings=all_findings,
            user_consent=user_consent,
            context=context,
        )

        # Build enriched copy preserving all original fields
        enriched = dict(report_dict)
        enriched["score"] = original_score
        enriched["status"] = original_status
        enriched["overall_status"] = original_overall_status
        enriched["total_errors"] = original_total_errors
        enriched["total_warnings"] = original_total_warnings
        enriched["detailed_errors"] = original_errors
        enriched["errors"] = original_errors
        enriched["detailed_warnings"] = original_warnings
        enriched["warnings"] = original_warnings

        # Store AI findings in a separate dedicated section
        enriched["ai_reasoning"] = ai_response.to_dict()

        return enriched
