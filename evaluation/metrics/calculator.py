"""
Metric Calculators for LLM Evaluation Sets.

Implements the 8 evaluation metrics required by EdgeMind:
1. Constraint extraction accuracy
2. Tool-selection precision
3. Tool-selection recall
4. Tool-selection F1
5. Edge-case coverage recall
6. Structured response validity
7. Evaluation completion rate
8. Provider error rate
"""

import re
from typing import Any, Dict, List, Set, Tuple

from evaluation.schemas.dataset import ExpectedResponseStructure
from evaluation.schemas.results import AggregateMetrics, ExampleMetricScores, ExampleEvaluationResult


def normalize_constraint(c: str) -> str:
    """Normalize a constraint string for canonical comparison."""
    # Remove whitespace, lowercase, normalize common symbols
    s = c.strip().lower()
    s = re.sub(r"\s+", "", s)
    s = s.replace("≤", "<=").replace("≥", ">=")
    return s


def calculate_constraint_accuracy(
    expected_constraints: List[str],
    extracted_constraints: List[str],
) -> float:
    """
    Calculate constraint extraction accuracy.
    Measures the proportion of ground-truth constraints successfully extracted.
    """
    if not expected_constraints:
        return 1.0

    if not extracted_constraints:
        return 0.0

    normalized_extracted = [normalize_constraint(c) for c in extracted_constraints]

    matched_count = 0
    for expected in expected_constraints:
        norm_exp = normalize_constraint(expected)
        # 1. Direct exact or substring match
        if any(norm_exp == ext or norm_exp in ext or ext in norm_exp for ext in normalized_extracted):
            matched_count += 1
            continue

        # 2. Variable and bound token overlap match
        var_tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_\.\[\]]*", norm_exp)
        num_tokens = re.findall(r"\d+", norm_exp)
        all_tokens = var_tokens + num_tokens

        if not all_tokens:
            continue

        best_overlap_ratio = 0.0
        for ext in normalized_extracted:
            # Variable token must match if variables exist
            var_match = True
            if var_tokens:
                var_match = any(v in ext for v in var_tokens)
            if not var_match:
                continue

            num_overlap = sum(1 for n in num_tokens if n in ext) if num_tokens else 1
            total_overlap = (sum(1 for v in var_tokens if v in ext) + num_overlap)
            ratio = total_overlap / len(all_tokens)
            if ratio > best_overlap_ratio:
                best_overlap_ratio = ratio

        if best_overlap_ratio >= 0.75:
            matched_count += 1

    return min(1.0, max(0.0, matched_count / len(expected_constraints)))


def calculate_tool_precision_recall_f1(
    expected_tools: List[str],
    selected_tools: List[str],
) -> Tuple[float, float, float]:
    """
    Calculate tool-selection precision, recall, and F1 score.
    Returns: (precision, recall, f1)
    """
    exp_set: Set[str] = set(expected_tools)
    sel_set: Set[str] = set(selected_tools)

    if not exp_set and not sel_set:
        return (1.0, 1.0, 1.0)
    if not sel_set:
        return (0.0, 0.0, 0.0)
    if not exp_set:
        return (0.0, 1.0, 0.0)

    intersection = exp_set.intersection(sel_set)
    precision = len(intersection) / len(sel_set)
    recall = len(intersection) / len(exp_set)

    if precision + recall > 0.0:
        f1 = (2.0 * precision * recall) / (precision + recall)
    else:
        f1 = 0.0

    return (round(precision, 4), round(recall, 4), round(f1, 4))


# Synonym mappings for coverage gaps
CATEGORY_SYNONYMS: Dict[str, str] = {
    "EMPTY_ARRAY": "EMPTY_COLLECTION",
    "EMPTY_STRING": "EMPTY_COLLECTION",
    "EMPTY_LIST": "EMPTY_COLLECTION",
    "EMPTY_INPUT": "EMPTY_COLLECTION",
    "ZERO": "ZERO_VALUE",
    "ZEROS": "ZERO_VALUE",
    "NEGATIVE": "NEGATIVE_VALUES",
    "NEGATIVES": "NEGATIVE_VALUES",
    "DUPLICATE": "DUPLICATE_ELEMENTS",
    "DUPLICATES": "DUPLICATE_ELEMENTS",
    "SINGLE_ELEMENT": "SINGLETON",
    "SINGLE_ITEM": "SINGLETON",
    "BOUNDARIES": "UPPER_CONSTRAINT_BOUND",
    "UPPER_BOUND": "UPPER_CONSTRAINT_BOUND",
    "LOWER_BOUND": "LOWER_CONSTRAINT_BOUND",
    "SORTED": "ALREADY_SORTED",
    "REVERSED": "REVERSE_SORTED",
}


def canonicalize_category(cat: str) -> str:
    """Map category alias or string to standard GapCategory format."""
    c = cat.strip().upper().replace(" ", "_").replace("-", "_")
    return CATEGORY_SYNONYMS.get(c, c)


def calculate_edge_case_recall(
    expected_categories: List[str],
    covered_categories: List[str],
) -> float:
    """
    Calculate edge-case coverage recall.
    Measures the proportion of expected edge-case categories identified or tested.
    """
    if not expected_categories:
        return 1.0

    if not covered_categories:
        return 0.0

    norm_covered = {canonicalize_category(c) for c in covered_categories}
    norm_expected = [canonicalize_category(c) for c in expected_categories]

    matched = 0
    for exp in norm_expected:
        if exp in norm_covered:
            matched += 1
        elif any(exp in cov or cov in exp for cov in norm_covered):
            matched += 1

    return min(1.0, max(0.0, round(matched / len(norm_expected), 4)))


def calculate_structured_response_validity(
    response_dict: Dict[str, Any],
    expected_structure: ExpectedResponseStructure,
) -> float:
    """
    Calculate structured response validity.
    Returns 1.0 if all structural invariants pass, 0.0 otherwise.
    """
    if not isinstance(response_dict, dict):
        return 0.0

    # 1. Required fields presence
    for req_field in expected_structure.required_fields:
        if req_field not in response_dict or response_dict[req_field] is None:
            return 0.0

    # 2. Status in allowed statuses
    status = response_dict.get("status")
    if status not in expected_structure.allowed_statuses:
        return 0.0

    # 3. Session ID valid non-empty string
    session_id = response_dict.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return 0.0

    # 4. Code analysis structure
    if expected_structure.require_code_analysis:
        code_analysis = response_dict.get("code_analysis")
        if not isinstance(code_analysis, dict):
            return 0.0
        if "metrics" not in code_analysis and "findings_count" not in code_analysis:
            return 0.0

    # 5. Test intelligence structure
    if expected_structure.require_test_intelligence:
        test_intelligence = response_dict.get("test_intelligence")
        if not isinstance(test_intelligence, dict):
            return 0.0
        if "coverage_gaps" not in test_intelligence or "generated_candidates" not in test_intelligence:
            return 0.0

        candidates = test_intelligence.get("generated_candidates", [])
        if len(candidates) < expected_structure.min_candidates:
            # Candidate count less than minimum invariant
            return 0.0

    return 1.0


def compute_aggregate_metrics(
    results: List[ExampleEvaluationResult],
) -> AggregateMetrics:
    """
    Compute aggregate benchmark metrics across all evaluated examples.
    """
    total = len(results)
    if total == 0:
        return AggregateMetrics(
            constraint_extraction_accuracy=0.0,
            tool_selection_precision=0.0,
            tool_selection_recall=0.0,
            tool_selection_f1=0.0,
            edge_case_coverage_recall=0.0,
            structured_response_validity=0.0,
            evaluation_completion_rate=0.0,
            provider_error_rate=0.0,
        )

    sum_constraint = sum(r.metrics.constraint_extraction_accuracy for r in results)
    sum_precision = sum(r.metrics.tool_selection_precision for r in results)
    sum_recall = sum(r.metrics.tool_selection_recall for r in results)
    sum_f1 = sum(r.metrics.tool_selection_f1 for r in results)
    sum_edge_case = sum(r.metrics.edge_case_coverage_recall for r in results)
    sum_validity = sum(r.metrics.structured_response_validity for r in results)
    completed_count = sum(1 for r in results if r.metrics.execution_success)
    provider_error_count = sum(1 for r in results if r.metrics.provider_error)

    return AggregateMetrics(
        constraint_extraction_accuracy=round(sum_constraint / total, 4),
        tool_selection_precision=round(sum_precision / total, 4),
        tool_selection_recall=round(sum_recall / total, 4),
        tool_selection_f1=round(sum_f1 / total, 4),
        edge_case_coverage_recall=round(sum_edge_case / total, 4),
        structured_response_validity=round(sum_validity / total, 4),
        evaluation_completion_rate=round(completed_count / total, 4),
        provider_error_rate=round(provider_error_count / total, 4),
    )
