import json
import sys
from typing import Any, Dict, List, Optional

from core.models import AnalysisReport, ReportFinding


def _get_field(obj: Any, field_name: str, default: Any = None) -> Any:
    """Safely extract a field from either a dict or an object."""
    if isinstance(obj, dict):
        val = obj.get(field_name)
        return val if val is not None else default
    return getattr(obj, field_name, default)


def serialize_finding(finding: Any) -> Dict[str, Any]:
    """
    Convert an issue finding into a standardized dictionary.
    Handles missing optional fields safely.
    """
    raw_type = _get_field(finding, "type", "Unknown") or "Unknown"
    
    raw_line = _get_field(finding, "line", _get_field(finding, "line_number", 0))
    try:
        line_num = int(raw_line) if raw_line is not None else 0
    except (ValueError, TypeError):
        line_num = 0

    message = _get_field(finding, "message", "") or ""
    
    # Explanation / why
    explanation = (
        _get_field(finding, "explanation")
        or _get_field(finding, "why")
        or ""
    )

    # Fix / suggested fix
    suggested_fix = (
        _get_field(finding, "suggested_fix")
        or _get_field(finding, "fix")
        or ""
    )

    concept = _get_field(finding, "concept", "General") or "General"

    finding_obj = ReportFinding(
        type=str(raw_type),
        line=line_num,
        line_number=line_num,
        message=str(message),
        why=str(explanation),
        explanation=str(explanation),
        fix=str(suggested_fix),
        suggested_fix=str(suggested_fix),
        concept=str(concept),
    )
    return finding_obj.to_dict()


def create_report_dict(
    filename: str,
    results: Optional[List[Any]] = None,
    ai_reasoning: Optional[Dict[str, Any]] = None,
    static_only: bool = False,
) -> Dict[str, Any]:
    """
    Build a structured report dictionary from analysis results.
    Reuses existing results if provided to avoid re-analyzing the file.
    Includes ai_reasoning if provided.
    """
    from core.analyzer import WARNING_TYPES, analyze_file, is_error

    is_static = static_only or getattr(results, "static_only", False)
    if results is None:
        results = analyze_file(filename, static_only=is_static)
        is_static = is_static or getattr(results, "static_only", False)

    errors = [r for r in results if is_error(r)]
    warnings = [r for r in results if not is_error(r)]

    total_errors = len(errors)
    total_warnings = len(warnings)

    score = 100 - (total_errors * 20) - (total_warnings * 5)
    score = max(0, min(100, score))

    if total_errors:
        overall_status = "FAIL"
    elif total_warnings:
        overall_status = "PASS WITH WARNINGS"
    else:
        overall_status = "PASS"

    syntax_errors = [
        r for r in results
        if _get_field(r, "type") in {"SyntaxError", "IndentationError"}
    ]
    runtime_errors = [
        r for r in results
        if is_error(r)
        and _get_field(r, "type") not in {"SyntaxError", "IndentationError"}
    ]

    syntax_status = "FAIL" if syntax_errors else "PASS"
    runtime_status = "SKIPPED" if is_static else ("FAIL" if runtime_errors else "PASS")
    logic_status = (
        "WARNING"
        if any(
            _get_field(r, "type") in {"LogicError", "Possible Logic Error"}
            for r in results
        )
        else "PASS"
    )
    quality_status = (
        "WARNING"
        if any(_get_field(r, "type") in WARNING_TYPES for r in results)
        else "PASS"
    )
    complexity_status = (
        "WARNING"
        if any(
            _get_field(r, "type") in {"MediumComplexity", "HighComplexity"}
            for r in results
        )
        else "PASS"
    )

    serialized_errors = [serialize_finding(e) for e in errors]
    serialized_warnings = [serialize_finding(w) for w in warnings]

    summary = {
        "syntax": syntax_status,
        "runtime": runtime_status,
        "logic": logic_status,
        "quality": quality_status,
        "complexity": complexity_status,
    }

    report = AnalysisReport(
        file_path=str(filename),
        file=str(filename),
        overall_status=overall_status,
        status=overall_status,
        score=score,
        total_errors=total_errors,
        total_warnings=total_warnings,
        syntax_status=syntax_status,
        runtime_status=runtime_status,
        logic_status=logic_status,
        quality_status=quality_status,
        complexity_status=complexity_status,
        detailed_errors=serialized_errors,
        errors=serialized_errors,
        detailed_warnings=serialized_warnings,
        warnings=serialized_warnings,
        summary=summary,
        ai_reasoning=ai_reasoning,
    )
    return report.to_dict()


def generate_json_report(
    filename: str,
    results: Optional[List[Any]] = None,
    indent: Optional[int] = 2,
    ai_reasoning: Optional[Dict[str, Any]] = None,
    static_only: bool = False,
) -> str:
    """Serialize the analysis report dictionary as a JSON string."""
    report_dict = create_report_dict(
        filename, results=results, ai_reasoning=ai_reasoning, static_only=static_only
    )
    return json.dumps(report_dict, indent=indent)


def print_json_report(
    filename: str,
    results: Optional[List[Any]] = None,
    indent: Optional[int] = 2,
    file: Optional[Any] = None,
    ai_reasoning: Optional[Dict[str, Any]] = None,
    static_only: bool = False,
) -> None:
    """Print the serialized JSON report to the specified stream (stdout by default)."""
    output_stream = file if file is not None else sys.stdout
    output_stream.write(
        generate_json_report(
            filename,
            results=results,
            indent=indent,
            ai_reasoning=ai_reasoning,
            static_only=static_only,
        )
        + "\n"
    )
