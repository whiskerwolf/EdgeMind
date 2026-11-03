"""
EdgeMind Analysis Service.

Provides a reusable, programmatic in-memory analysis interface for Python source code.
Guarantees static-only analysis with zero execution of submitted user code,
zero temporary files, and strict input validation.
"""

import os
from typing import Any, Dict, List, Optional

from core.analyzer import AnalysisResultList, deduplicate_results
from core.complexity import check_complexity
from core.json_reporter import create_report_dict
from core.logic import check_logic
from core.quality import check_quality
from core.smells import check_smells
from core.static_check import static_checks

# Maximum allowed source size: 64 KiB (65,536 bytes)
MAX_SOURCE_SIZE = 64 * 1024
DEFAULT_FILENAME = "snippet.py"


def validate_filename(filename: str) -> str:
    """
    Validate that the provided filename is a display label only.
    Prevents path traversal, directory paths, and non-string inputs.
    """
    if not isinstance(filename, str):
        raise TypeError(f"Filename must be a string, got {type(filename).__name__}.")

    cleaned = filename.strip()
    if not cleaned:
        raise ValueError("Filename must not be empty or whitespace-only.")

    # Reject directory traversal, absolute paths, or paths with directory separators
    if (
        ".." in cleaned
        or "/" in cleaned
        or "\\" in cleaned
        or (len(cleaned) > 1 and cleaned[1] == ":")
    ):
        raise ValueError(
            f"Invalid filename '{filename}': filename must be a simple display label "
            "and cannot contain directory separators, drive letters, or path traversal components."
        )

    return cleaned


def analyze_code(
    code: str,
    filename: str = DEFAULT_FILENAME,
    static_only: bool = True,
) -> Dict[str, Any]:
    """
    Analyze Python source code provided as an in-memory string.

    Parameters:
        code: Python source code string to analyze.
        filename: Optional display label for reporting (defaults to "snippet.py").
                  Validated strictly as a label, never as a filesystem path.
        static_only: Must be True. The service strictly performs static analysis
                     and does not execute submitted code.

    Returns:
        A standardized AnalysisReport dictionary suitable for JSON serialization.

    Raises:
        TypeError: If code or filename is not a string.
        ValueError: If code is empty/whitespace-only, exceeds MAX_SOURCE_SIZE,
                    filename contains path traversal or invalid characters,
                    or static_only is False.
    """
    # 1. Enforce static-only mode
    if static_only is not True:
        raise ValueError(
            "Runtime execution is disabled in the analysis service. "
            "Only static analysis is supported (static_only must be True)."
        )

    # 2. Validate source code type and content
    if not isinstance(code, str):
        raise TypeError(f"Source code must be a string, got {type(code).__name__}.")

    if not code.strip():
        raise ValueError("Source code must not be empty or whitespace-only.")

    encoded_bytes = code.encode("utf-8")
    if len(encoded_bytes) > MAX_SOURCE_SIZE:
        raise ValueError(
            f"Source code size ({len(encoded_bytes)} bytes) exceeds "
            f"the maximum allowed limit of {MAX_SOURCE_SIZE} bytes (64 KiB)."
        )

    # 3. Validate filename as a display label
    display_name = validate_filename(filename)

    # 4. Perform syntax validation without executing source code
    try:
        compile(code, display_name, "exec")
    except SyntaxError as error:
        syntax_finding = {
            "type": "SyntaxError",
            "line": error.lineno or 0,
            "message": error.msg or "Invalid syntax.",
            "why": "Python could not understand the code structure.",
            "fix": "Check the reported line for syntax mistakes.",
            "concept": "Python Syntax",
        }
        return create_report_dict(
            filename=display_name,
            results=[syntax_finding],
            static_only=True,
        )

    # 5. Run static analysis engines
    results = AnalysisResultList([], static_only=True)

    # Static checks (literal bounds, dict keys, zero division)
    results.extend(static_checks(code))

    # Logic analysis
    for item in check_logic(code):
        if isinstance(item, dict):
            results.append(item)
        else:
            results.append({
                "type": getattr(item, "type", "LogicError"),
                "line": getattr(item, "line", 0),
                "message": getattr(item, "message", ""),
                "why": getattr(item, "why", ""),
                "fix": getattr(item, "fix", ""),
                "concept": "Logic",
            })

    # Code quality
    results.extend(check_quality(code))

    # Complexity analysis
    results.extend(check_complexity(code))

    # Code smell detection
    results.extend(check_smells(code))

    # 6. Deduplicate results while preserving order
    deduped = deduplicate_results(results, static_only=True)

    # 7. Build structured report dictionary
    return create_report_dict(
        filename=display_name,
        results=deduped,
        static_only=True,
    )


def extract_context_from_code(code: str) -> Dict[str, Any]:
    """
    Extract function name and parameter names from Python AST if possible.
    Never invents constraints or parameter types.
    """
    import ast

    context: Dict[str, Any] = {"function_name": None, "parameters": []}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return context

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Exclude special/dunder methods
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            params = [arg.arg for arg in node.args.args if arg.arg != "self"]
            context["function_name"] = node.name
            context["parameters"] = params
            break
    return context


def parse_test_cases(raw_cases: Any) -> List[Any]:
    """
    Parse raw test cases into TestCase domain models.
    Supports full TestCase dictionary format or raw parameter mappings.
    """
    from core.test_intelligence.models import TestCase, TestCaseSource

    if not isinstance(raw_cases, list):
        raise TypeError(f"test_cases must be a list, got {type(raw_cases).__name__}.")

    parsed_cases: List[TestCase] = []
    for idx, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise TypeError(
                f"Test case at index {idx} must be a dictionary, got {type(item).__name__}."
            )

        if "input_data" in item:
            raw_input = item.get("input_data")
            if not isinstance(raw_input, dict):
                raise TypeError(
                    f"Test case at index {idx} 'input_data' must be a dictionary, got {type(raw_input).__name__}."
                )
            tc = TestCase.from_dict(item)
            if not tc.id:
                tc.id = f"test_{idx + 1}"
            parsed_cases.append(tc)
        else:
            # Raw parameter mapping, e.g. {"nums": [1, 2, 3]}
            tc = TestCase(
                id=f"test_{idx + 1}",
                source=TestCaseSource.USER_PROVIDED_TEST,
                input_data=dict(item),
                expected_output=None,
                is_expected_output_verified=False,
                label=f"User Test {idx + 1}",
                rationale="Supplied as input test sample.",
            )
            parsed_cases.append(tc)

    return parsed_cases


def analyze_edgemind(
    code: str,
    problem_context: Optional[Dict[str, Any]] = None,
    test_cases: Optional[List[Any]] = None,
    filename: str = DEFAULT_FILENAME,
    max_candidates: int = 10,
    static_only: bool = True,
) -> Dict[str, Any]:
    """
    Analyze code with static analysis and run the EdgeMind Adaptive
    Test Intelligence pipeline to detect coverage gaps and synthesize edge-case candidates.

    Guarantees:
    - Pure static analysis and candidate synthesis with zero runtime execution.
    - Zero temporary files.
    - Strict provenance tracking: all synthesized cases tagged GENERATED_TEST with null expected output.
    - Never invents or fabricates constraints.
    """
    from core.test_intelligence.models import (
        ProblemContext,
        TestCase,
        TestCaseSource,
    )
    from core.test_intelligence.extractor import FeatureProfileExtractor
    from core.test_intelligence.gap_detector import CoverageGapEvaluator
    from core.test_intelligence.synthesizer import TargetedTestSynthesizer
    from core.test_intelligence.ranker import CandidateRanker

    # 1. Enforce static-only mode
    if static_only is not True:
        raise ValueError(
            "Runtime execution is disabled in the analysis service. "
            "Only static analysis is supported (static_only must be True)."
        )

    # 2. Validate source code
    if not isinstance(code, str):
        raise TypeError(f"Source code must be a string, got {type(code).__name__}.")

    if not code.strip():
        raise ValueError("Source code must not be empty or whitespace-only.")

    encoded_bytes = code.encode("utf-8")
    if len(encoded_bytes) > MAX_SOURCE_SIZE:
        raise ValueError(
            f"Source code size ({len(encoded_bytes)} bytes) exceeds "
            f"the maximum allowed limit of {MAX_SOURCE_SIZE} bytes (64 KiB)."
        )

    # 3. Validate filename
    display_name = validate_filename(filename)

    # 4. Validate max_candidates
    try:
        max_candidates = int(max_candidates)
    except (ValueError, TypeError):
        max_candidates = 10
    if max_candidates <= 0:
        max_candidates = 10

    # 5. Run static code analysis
    code_report = analyze_code(code=code, filename=display_name, static_only=True)

    # 6. Parse problem context
    # 6. Parse problem context & constraints
    from core.test_intelligence.constraint_parser import (
        classify_candidate,
        parse_constraint_expressions,
    )

    extracted_ctx = extract_context_from_code(code)
    if problem_context is not None:
        if not isinstance(problem_context, dict):
            raise TypeError(
                f"problem_context must be a dictionary, got {type(problem_context).__name__}."
            )
        ctx = ProblemContext.from_dict(problem_context)
        if not ctx.function_name and extracted_ctx.get("function_name"):
            ctx.function_name = extracted_ctx["function_name"]
        if not ctx.parameters and extracted_ctx.get("parameters"):
            ctx.parameters = extracted_ctx["parameters"]
    else:
        ctx = ProblemContext(
            function_name=extracted_ctx.get("function_name"),
            parameters=extracted_ctx.get("parameters", []),
        )

    # Parse supplied raw constraint expressions without fabricating bounds
    unresolved_constraints: List[str] = []
    raw_constraints: List[str] = list(ctx.constraints) if ctx.constraints else []
    if ctx.constraint_spec and ctx.constraint_spec.raw_constraints:
        for rc in ctx.constraint_spec.raw_constraints:
            if rc not in raw_constraints:
                raw_constraints.append(rc)

    if raw_constraints:
        parsed_spec, unresolved_constraints = parse_constraint_expressions(
            raw_constraints, known_parameters=ctx.parameters
        )
        if ctx.constraint_spec is None:
            ctx.constraint_spec = parsed_spec
        else:
            if ctx.constraint_spec.min_length is None:
                ctx.constraint_spec.min_length = parsed_spec.min_length
            if ctx.constraint_spec.max_length is None:
                ctx.constraint_spec.max_length = parsed_spec.max_length
            if ctx.constraint_spec.min_value is None:
                ctx.constraint_spec.min_value = parsed_spec.min_value
            if ctx.constraint_spec.max_value is None:
                ctx.constraint_spec.max_value = parsed_spec.max_value
            if ctx.constraint_spec.allowed_characters is None:
                ctx.constraint_spec.allowed_characters = parsed_spec.allowed_characters
            if ctx.constraint_spec.min_rows is None:
                ctx.constraint_spec.min_rows = parsed_spec.min_rows
            if ctx.constraint_spec.max_rows is None:
                ctx.constraint_spec.max_rows = parsed_spec.max_rows
            if ctx.constraint_spec.min_cols is None:
                ctx.constraint_spec.min_cols = parsed_spec.min_cols
            if ctx.constraint_spec.max_cols is None:
                ctx.constraint_spec.max_cols = parsed_spec.max_cols
            if ctx.constraint_spec.allowed_values is None:
                ctx.constraint_spec.allowed_values = parsed_spec.allowed_values
            if not ctx.constraint_spec.endpoints_zero:
                ctx.constraint_spec.endpoints_zero = parsed_spec.endpoints_zero
            if not ctx.constraint_spec.raw_constraints:
                ctx.constraint_spec.raw_constraints = raw_constraints
            if parsed_spec.param_specs:
                ctx.constraint_spec.param_specs.update(parsed_spec.param_specs)
            if parsed_spec.cross_constraints:
                ctx.constraint_spec.cross_constraints.extend(parsed_spec.cross_constraints)
            if parsed_spec.parsed_constraints:
                ctx.constraint_spec.parsed_constraints.extend(parsed_spec.parsed_constraints)
            if parsed_spec.unresolved_reasons:
                ctx.constraint_spec.unresolved_reasons.update(parsed_spec.unresolved_reasons)

    # 7. Parse test cases
    parsed_test_cases: List[TestCase] = []
    if test_cases is not None:
        parsed_test_cases = parse_test_cases(test_cases)

    # 8. Disclaimers & Provenance guarantees
    provenance_meta = {
        "source": TestCaseSource.GENERATED_TEST.value,
        "execution_performed": False,
        "expected_outputs_known": False,
        "guarantees": [
            "All generated candidates are labeled with source GENERATED_TEST.",
            "Zero user code or candidate inputs were executed at runtime.",
            "Expected outputs are null (None) and explicitly unverified.",
            "Input-pattern coverage reflects black-box domain partitions, not program branch coverage.",
        ],
    }

    limitations = [
        "Generated test cases are candidates targeting domain gaps, not confirmed failures or platform hidden tests.",
        "Runtime execution is disabled; candidates have not been evaluated against a reference oracle.",
        "Coverage analysis is heuristic black-box input-domain partitioning.",
    ]

    warnings: List[str] = []

    # 9. Extract parameter & constraint context metadata
    from core.test_intelligence.context_intelligence import (
        infer_parameter_context,
        synthesize_context_candidates,
    )

    inferred_params, param_limitations, completeness = infer_parameter_context(
        code=code, problem_context=ctx, spec=ctx.constraint_spec, test_cases=parsed_test_cases
    )
    constraint_status = (
        "PARSED" if (raw_constraints and not unresolved_constraints)
        else ("PARTIALLY_PARSED" if (raw_constraints and unresolved_constraints) else "UNAVAILABLE")
    )
    unresolved_explanations = {}
    if ctx.constraint_spec and ctx.constraint_spec.unresolved_reasons:
        unresolved_explanations = ctx.constraint_spec.unresolved_reasons

    parsed_constraints_meta = {
        "status": constraint_status,
        "total_raw": len(raw_constraints),
        "unresolved": unresolved_constraints,
        "unresolved_explanations": unresolved_explanations,
        "cross_constraints": [
            c.to_dict() for c in (ctx.constraint_spec.cross_constraints if ctx.constraint_spec else [])
        ],
    }

    # =========================================================================
    # MODE B: CONTEXT-BASED INTELLIGENCE (Zero baseline public examples)
    # =========================================================================
    if not parsed_test_cases:
        has_ambiguity = (
            not inferred_params
            or any(p.is_ambiguous for p in inferred_params)
            or completeness == "INSUFFICIENT"
        )
        if has_ambiguity:
            warnings.append(
                "No existing test cases or input samples were provided. "
                "Adaptive test intelligence requires at least one existing test input to observe "
                "parameter structures and synthesize targeted edge-case candidates."
            )
            if not ctx.constraint_spec or not raw_constraints:
                warnings.append(
                    "No problem constraints were supplied. EdgeMind does not invent constraint bounds."
                )
            for lim in param_limitations:
                if lim not in limitations:
                    limitations.append(lim)

            return {
                "status": "INSUFFICIENT_CONTEXT",
                "product": "EdgeMind",
                "version": "1.0.0",
                "analysis_mode": "CONTEXT_BASED",
                "baseline_available": False,
                "context_completeness": "INSUFFICIENT",
                "identified_parameters": [p.to_dict() for p in inferred_params],
                "parsed_constraints": parsed_constraints_meta,
                "generation_status": "INSUFFICIENT_CONTEXT",
                "code_analysis": code_report,
                "test_intelligence": {
                    "existing_tests_analyzed": 0,
                    "detected_patterns": {},
                    "coverage_gaps": [],
                    "total_gaps": 0,
                    "unresolved_constraints": unresolved_constraints,
                    "ranking_summary": {
                        "total_evaluated": 0,
                        "exact_duplicates_removed": 0,
                        "redundant_candidates_penalized": 0,
                        "selection_limit": max_candidates,
                    },
                    "generated_candidates": [],
                    "ranked_candidates": [],
                },
                "provenance": provenance_meta,
                "limitations": limitations,
                "warnings": warnings,
            }

        # Parameters are determinable -> synthesize context-derived candidates
        selected_cands, ranked_cands, rank_summary = synthesize_context_candidates(
            parameters=inferred_params,
            context=ctx,
            spec=ctx.constraint_spec,
            max_candidates=max_candidates,
            unresolved_constraints=unresolved_constraints,
        )

        context_disclaimer = (
            "These candidates are generated from available problem context. "
            "No public baseline examples were available. "
            "Expected outputs are unverified, and no generated inputs have been executed."
        )
        warnings.append(context_disclaimer)
        limitations.append(
            "Generated test cases are candidates targeting domain boundaries derived from context, not confirmed failures or platform hidden tests."
        )
        limitations.append(
            "Runtime execution is disabled; candidates have not been evaluated against a reference oracle."
        )
        limitations.append(
            "No baseline examples were available; input domain coverage partitions cannot be observed."
        )

        return {
            "status": "SUCCESS",
            "product": "EdgeMind",
            "version": "1.0.0",
            "analysis_mode": "CONTEXT_BASED",
            "baseline_available": False,
            "context_completeness": completeness,
            "identified_parameters": [p.to_dict() for p in inferred_params],
            "parsed_constraints": parsed_constraints_meta,
            "generation_status": "SUCCESS",
            "code_analysis": code_report,
            "test_intelligence": {
                "existing_tests_analyzed": 0,
                "detected_patterns": {},
                "coverage_gaps": [],
                "total_gaps": 0,
                "unresolved_constraints": unresolved_constraints,
                "ranking_summary": rank_summary,
                "generated_candidates": [c.to_dict() for c in selected_cands],
                "ranked_candidates": [r.to_dict() for r in ranked_cands],
            },
            "provenance": provenance_meta,
            "limitations": limitations,
            "warnings": warnings,
        }

    # =========================================================================
    # MODE A: BASELINE-DRIVEN INTELLIGENCE (One or more public examples present)
    # =========================================================================
    extractor = FeatureProfileExtractor(context=ctx)
    profile = extractor.extract(parsed_test_cases, context=ctx)

    evaluator = CoverageGapEvaluator(extractor=extractor)
    gap_result = evaluator.evaluate(parsed_test_cases, context=ctx, profile=profile)

    synthesizer = TargetedTestSynthesizer(evaluator=evaluator)
    raw_candidates = synthesizer.synthesize(
        test_cases=parsed_test_cases,
        context=ctx,
        gaps=gap_result.gaps,
        max_candidates=1000,
    )

    ranker = CandidateRanker()
    ranking_result = ranker.rank_and_select(
        candidates=raw_candidates,
        existing_tests=parsed_test_cases,
        gaps=gap_result.gaps,
        max_selected=max_candidates,
    )

    has_supplied_constraints = bool(raw_constraints or (ctx.constraint_spec and (
        ctx.constraint_spec.min_length is not None
        or ctx.constraint_spec.max_length is not None
        or ctx.constraint_spec.min_value is not None
        or ctx.constraint_spec.max_value is not None
        or ctx.constraint_spec.allowed_characters is not None
    )))

    # Classify candidates into VALID, ROBUSTNESS PROBE, or CONSTRAINT VALIDITY UNKNOWN
    for cand in ranking_result.selected_candidates:
        classification, reason = classify_candidate(
            cand,
            ctx.constraint_spec,
            has_supplied_constraints=has_supplied_constraints,
            context=ctx,
            unresolved_constraints=unresolved_constraints,
        )
        cand.classification = classification
        cand.classification_reason = reason

    for ranked in ranking_result.ranked_candidates:
        classification, reason = classify_candidate(
            ranked.candidate,
            ctx.constraint_spec,
            has_supplied_constraints=has_supplied_constraints,
            context=ctx,
            unresolved_constraints=unresolved_constraints,
        )
        ranked.candidate.classification = classification
        ranked.candidate.classification_reason = reason

    if not ctx.constraint_spec or not has_supplied_constraints:
        warnings.append(
            "No explicit constraint specification was supplied. Edge-case candidates were "
            "generated using observed input domain types and standard partition heuristics "
            "without boundary constraint enforcement."
        )

    return {
        "status": "SUCCESS",
        "product": "EdgeMind",
        "version": "1.0.0",
        "analysis_mode": "BASELINE_DRIVEN",
        "baseline_available": True,
        "context_completeness": completeness,
        "identified_parameters": [p.to_dict() for p in inferred_params],
        "parsed_constraints": parsed_constraints_meta,
        "generation_status": "SUCCESS",
        "code_analysis": code_report,
        "test_intelligence": {
            "existing_tests_analyzed": len(parsed_test_cases),
            "detected_patterns": profile.to_dict(),
            "coverage_gaps": [g.to_dict() for g in gap_result.gaps],
            "total_gaps": gap_result.total_gaps,
            "unresolved_constraints": unresolved_constraints,
            "ranking_summary": {
                "total_evaluated": ranking_result.total_evaluated,
                "exact_duplicates_removed": ranking_result.exact_duplicates_removed,
                "redundant_candidates_penalized": ranking_result.redundant_candidates_penalized,
                "selection_limit": ranking_result.selection_limit,
            },
            "generated_candidates": [c.to_dict() for c in ranking_result.selected_candidates],
            "ranked_candidates": [r.to_dict() for r in ranking_result.ranked_candidates],
        },
        "provenance": provenance_meta,
        "limitations": limitations,
        "warnings": warnings,
    }

