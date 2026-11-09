"""
MongoDB Document Builder for EdgeMind Analysis Reports.

Transforms analysis results into standardized MongoDB document structures:
- Enforces canonical schema_version "1.0.0".
- Maps PostgreSQL UUID foreign keys as standard string IDs.
- Permanently excludes passwords, JWTs, and full source code.
- Preserves expected_output=None and is_expected_output_verified=False invariants.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def build_analysis_report_doc(
    report: Dict[str, Any],
    session_id: str,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
    problem_id: Optional[str] = None,
    problem_context: Optional[Dict[str, Any]] = None,
    language: str = "python",
    duration_ms: float = 0.0,
) -> Dict[str, Any]:
    """
    Construct an analysis report document adhering to the Phase 4 schema.
    """
    prob_ctx = problem_context or {}
    prob_title = str(prob_ctx.get("title") or "").strip()
    prob_slug = str(prob_ctx.get("slug") or prob_ctx.get("problem_slug") or "").strip().lower()
    if prob_title and not prob_slug:
        prob_slug = prob_title.lower().replace(" ", "-")
    prob_platform = str(prob_ctx.get("platform") or "leetcode").strip().lower()
    prob_difficulty = prob_ctx.get("difficulty")

    ti_section = report.get("test_intelligence", {}) if isinstance(report.get("test_intelligence"), dict) else {}
    generated_candidates = ti_section.get("generated_candidates", [])
    coverage_gaps = ti_section.get("coverage_gaps", [])

    # Strict invariant validation: ensure generated candidates do not falsely claim oracle verification
    cleaned_candidates: List[Dict[str, Any]] = []
    candidate_classifications: Dict[str, int] = {}
    for cand in generated_candidates:
        cand_dict = dict(cand)
        cand_dict["expected_output"] = None
        cand_dict["is_expected_output_verified"] = False
        cls_name = cand_dict.get("classification") or "UNCLASSIFIED"
        candidate_classifications[cls_name] = candidate_classifications.get(cls_name, 0) + 1
        cleaned_candidates.append(cand_dict)

    # Sanitize code analysis metadata (exclude raw user source code)
    code_analysis = report.get("code_analysis", {})
    code_metrics = code_analysis.get("metrics") or {}
    code_summary = code_analysis.get("summary") or {}

    analysis_metadata = {
        "duration_ms": max(0.0, float(duration_ms)),
        "gaps_detected": len(coverage_gaps),
        "candidates_generated": len(cleaned_candidates),
        "existing_tests_analyzed": ti_section.get("existing_tests_analyzed", 0),
        "ranking_summary": ti_section.get("ranking_summary", {}),
        "provenance": report.get("provenance", {}),
        "code_metrics": code_metrics,
        "code_summary": code_summary,
    }

    explanations = {
        "limitations": report.get("limitations", []),
        "warnings": report.get("warnings", []),
        "unresolved_constraints": ti_section.get("unresolved_constraints", []),
    }

    now = datetime.now(timezone.utc)
    return {
        "analysis_session_id": str(session_id),
        "user_id": str(user_id) if user_id else None,
        "project_id": str(project_id) if project_id else None,
        "problem_id": str(problem_id) if problem_id else None,
        "problem": {
            "title": prob_title,
            "slug": prob_slug,
            "platform": prob_platform,
            "difficulty": prob_difficulty,
        },
        "problem_slug": prob_slug,
        "platform": prob_platform,
        "language": language or "python",
        "analysis_mode": report.get("analysis_mode", "BASELINE_DRIVEN"),
        "analysis_status": report.get("status", "SUCCESS"),
        "generated_candidates": cleaned_candidates,
        "candidate_classifications": candidate_classifications,
        "constraints": report.get("parsed_constraints", {}),
        "coverage_gaps": coverage_gaps,
        "explanations": explanations,
        "analysis_metadata": analysis_metadata,
        "created_at": now,
        "updated_at": now,
        "schema_version": "1.0.0",
    }
