"""
EdgeMind Adaptive Test Intelligence - Context-Based Intelligence Engine (Mode B).

Activated automatically when zero public baseline examples are extracted.
Derives deterministic, bounded edge-case candidates from available problem context:
- Function signature & AST type annotations
- Problem title, description, URL, and ID
- Parsed numerical and collection length constraints
- Recognized problem-specific relationships (e.g. Two Sum)

Guarantees:
- Never invents parameter structures when available context is insufficient.
- Reports clear limitations when parameter types/structures are ambiguous.
- Employs strict three-tier classification:
  * VALID: All applicable supported validity checks succeed.
  * ROBUSTNESS PROBE: Deliberately violates a known constraint.
  * CONSTRAINT VALIDITY UNKNOWN: Required constraints or logical invariants cannot be established.
- Never reports context-derived candidate categories as observed coverage gaps.
- Strictly unverified: expected_output=None, is_expected_output_verified=False, source=GENERATED_TEST.
- Zero runtime execution of code or candidates.
"""

import ast
import copy
from dataclasses import dataclass, field, asdict
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    GapCategory,
    ProblemContext,
    TestCase,
    TestCaseSource,
)
from core.test_intelligence.constraint_parser import (
    count_valid_pairs,
    is_two_sum_context,
    normalize_collapsed_exponents,
    normalize_latex,
    normalize_superscripts,
    parse_constraint_expressions,
    parse_number_expression,
)
from core.test_intelligence.synthesizer import (
    canonical_input_signature,
    is_additive_relationship,
)
from core.test_intelligence.ranker import CandidateRanker, RankedCandidate


@dataclass
class InferredParameter:
    """Structured representation of an inferred function parameter."""
    name: str
    param_type: str = "unknown"  # "int", "float", "str", "bool", "unknown"
    structure: str = "unknown"   # "scalar", "array_1d", "matrix_2d", "unknown"
    element_type: Optional[str] = None  # for collections: "int", "float", "str", "bool"
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    allowed_characters: Optional[str] = None
    min_rows: Optional[int] = None
    max_rows: Optional[int] = None
    min_cols: Optional[int] = None
    max_cols: Optional[int] = None
    allowed_values: Optional[List[Union[int, float]]] = None
    source: str = "AST_SIGNATURE"  # "AST_SIGNATURE", "EXPLICIT_METADATA", "BASELINE_SAMPLE"
    is_ambiguous: bool = False
    ambiguity_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_ast_type_annotation(
    node: Optional[ast.AST],
) -> Tuple[str, str, Optional[str], bool, Optional[str]]:
    """
    Parse a Python AST type annotation node.

    Returns:
        (param_type, structure, element_type, is_ambiguous, ambiguity_reason)
    """
    if node is None:
        return "unknown", "unknown", None, False, None

    # Handle string literal annotations: e.g. "List[int]"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            expr_ast = ast.parse(node.value, mode="eval")
            return _parse_ast_type_annotation(expr_ast.body)
        except Exception:
            return "unknown", "unknown", None, False, None

    # Handle simple identifier: e.g. int, float, str, bool, list
    if isinstance(node, ast.Name):
        type_name = node.id
        if type_name in ("int", "Integer"):
            return "int", "scalar", None, False, None
        if type_name in ("float", "Float"):
            return "float", "scalar", None, False, None
        if type_name in ("str", "String"):
            return "str", "scalar", None, False, None
        if type_name in ("bool", "Boolean"):
            return "bool", "scalar", None, False, None
        if type_name in ("list", "List", "Sequence", "Iterable"):
            return "unknown", "array_1d", "unknown", False, None
        # Complex / custom types not supported in MVP
        if type_name in ("TreeNode", "ListNode", "Node", "Any"):
            return (
                "unknown",
                "unknown",
                None,
                True,
                f"Custom or non-primitive object type '{type_name}' is not currently supported.",
            )
        return (
            "unknown",
            "unknown",
            None,
            True,
            f"Unrecognized type annotation identifier '{type_name}'.",
        )

    # Handle subscripted type annotations: List[int], List[List[int]], Optional[int]
    if isinstance(node, ast.Subscript):
        base_name = ""
        if isinstance(node.value, ast.Name):
            base_name = node.value.id
        elif isinstance(node.value, ast.Attribute):
            base_name = node.value.attr

        # Unwrap Optional[T] / Union[T, None]
        if base_name in ("Optional", "Union"):
            slice_node = node.slice
            if isinstance(slice_node, ast.Tuple):
                # find non-None element
                for elem in slice_node.elts:
                    if not (isinstance(elem, ast.Constant) and elem.value is None):
                        return _parse_ast_type_annotation(elem)
            else:
                return _parse_ast_type_annotation(slice_node)

        if base_name in ("List", "list", "Sequence", "Iterable"):
            slice_node = node.slice

            # Check for matrix: List[List[T]]
            if isinstance(slice_node, ast.Subscript):
                inner_base = ""
                if isinstance(slice_node.value, ast.Name):
                    inner_base = slice_node.value.id
                elif isinstance(slice_node.value, ast.Attribute):
                    inner_base = slice_node.value.attr

                if inner_base in ("List", "list", "Sequence", "Iterable"):
                    inner_type, _, _, is_amb, reason = _parse_ast_type_annotation(slice_node.slice)
                    if is_amb:
                        return "unknown", "unknown", None, True, reason
                    elem_t = inner_type if inner_type != "unknown" else "int"
                    return elem_t, "matrix_2d", elem_t, False, None

            # 1D array: List[T]
            inner_type, _, _, is_amb, reason = _parse_ast_type_annotation(slice_node)
            if is_amb:
                return "unknown", "unknown", None, True, reason
            elem_t = inner_type if inner_type != "unknown" else "int"
            return elem_t, "array_1d", elem_t, False, None

        if base_name in ("Tuple", "tuple"):
            return "unknown", "array_1d", "unknown", False, None

        return (
            "unknown",
            "unknown",
            None,
            True,
            f"Unsupported parameterized type '{base_name}'.",
        )

    return "unknown", "unknown", None, False, None


def _extract_ast_signature(code: str) -> Dict[str, Any]:
    """
    Extract function name, parameters, annotations, and return type from Python source AST.
    """
    res: Dict[str, Any] = {
        "function_name": None,
        "return_type": None,
        "parameters": [],
        "annotations": {},
    }
    if not code or not code.strip():
        return res

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return res

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("__") and node.name.endswith("__"):
                continue

            res["function_name"] = node.name

            # Return type
            if node.returns:
                try:
                    res["return_type"] = ast.unparse(node.returns)
                except Exception:
                    res["return_type"] = None

            # Parameters (exclude 'self' and 'cls')
            params = []
            for arg in node.args.args:
                if arg.arg in ("self", "cls"):
                    continue
                p_name = arg.arg
                params.append(p_name)
                res["annotations"][p_name] = arg.annotation

            res["parameters"] = params
            break

    return res


def _bind_parameter_constraints(
    param: InferredParameter,
    raw_constraints: List[str],
    global_spec: Optional[ConstraintSpec],
) -> None:
    """
    Bind parameter-specific constraint bounds from raw constraint strings and global spec.
    """
    p_name = param.name.lower()

    for line in raw_constraints:
        cleaned = normalize_latex(line)
        cleaned = normalize_superscripts(cleaned).strip().replace("\u2264", "<=").replace("\u2265", ">=").replace("\u2212", "-")
        cleaned = normalize_collapsed_exponents(cleaned)
        line_lower = cleaned.lower()

        # Check collection length constraints: e.g. "2 <= nums.length <= 10^4", "nums.length <= 10^4"
        is_length_constraint = (
            f"{p_name}.length" in line_lower
            or f"{p_name}.size" in line_lower
            or f"len({p_name})" in line_lower
            or (param.structure in ("array_1d", "matrix_2d", "str") and any(
                w in line_lower for w in ("length", "len", "size")
            ) and p_name in line_lower)
        )
        if is_length_constraint:
            sub_spec, _ = parse_constraint_expressions([cleaned], known_parameters=[param.name])
            if sub_spec.min_length is not None:
                param.min_length = (
                    max(param.min_length, sub_spec.min_length) if param.min_length is not None else sub_spec.min_length
                )
            if sub_spec.max_length is not None:
                param.max_length = (
                    min(param.max_length, sub_spec.max_length) if param.max_length is not None else sub_spec.max_length
                )

        # Check element/scalar value constraints: e.g. "-10^9 <= nums[i] <= 10^9", "-10^9 <= target <= 10^9"
        is_val_constraint = (
            f"{p_name}[i]" in line_lower
            or f"{p_name}[j]" in line_lower
            or f"{p_name}[i][j]" in line_lower
            or re.search(rf"\b{re.escape(p_name)}\b", line_lower)
        )
        if is_val_constraint and not is_length_constraint:
            sub_spec, _ = parse_constraint_expressions([cleaned], known_parameters=[param.name])
            if sub_spec.min_value is not None:
                param.min_value = (
                    max(param.min_value, sub_spec.min_value) if param.min_value is not None else sub_spec.min_value
                )
            if sub_spec.max_value is not None:
                param.max_value = (
                    min(param.max_value, sub_spec.max_value) if param.max_value is not None else sub_spec.max_value
                )

        # Character set constraints: e.g. "s consists of lowercase English letters"
        if p_name in line_lower and "lowercase english letter" in line_lower:
            param.allowed_characters = "a-z"
        elif p_name in line_lower and "uppercase english letter" in line_lower:
            param.allowed_characters = "A-Z"
        elif p_name in line_lower and "english letter" in line_lower:
            param.allowed_characters = "a-zA-Z"

    # Fallback to global spec where parameter has no specific bounds
    if global_spec:
        if param.structure in ("array_1d", "matrix_2d") or param.param_type == "str":
            if param.min_length is None and global_spec.min_length is not None:
                param.min_length = global_spec.min_length
            if param.max_length is None and global_spec.max_length is not None:
                param.max_length = global_spec.max_length

        if param.structure == "matrix_2d":
            if param.min_rows is None and global_spec.min_rows is not None:
                param.min_rows = global_spec.min_rows
            if param.max_rows is None and global_spec.max_rows is not None:
                param.max_rows = global_spec.max_rows
            if param.min_cols is None and global_spec.min_cols is not None:
                param.min_cols = global_spec.min_cols
            if param.max_cols is None and global_spec.max_cols is not None:
                param.max_cols = global_spec.max_cols
            if param.allowed_values is None and global_spec.allowed_values is not None:
                param.allowed_values = global_spec.allowed_values
            if param.min_length is None and param.min_rows is not None:
                param.min_length = param.min_rows
            if param.max_length is None and param.max_rows is not None:
                param.max_length = param.max_rows

        if param.param_type in ("int", "float") or param.element_type in ("int", "float"):
            if param.min_value is None and global_spec.min_value is not None:
                param.min_value = global_spec.min_value
            if param.max_value is None and global_spec.max_value is not None:
                param.max_value = global_spec.max_value

        if param.allowed_characters is None and global_spec.allowed_characters is not None:
            param.allowed_characters = global_spec.allowed_characters


def infer_parameter_context(
    code: str,
    problem_context: Optional[ProblemContext],
    spec: Optional[ConstraintSpec] = None,
    test_cases: Optional[Sequence[Any]] = None,
) -> Tuple[List[InferredParameter], List[str], str]:
    """
    Extract parameter structures, types, and constraints from code, problem context,
    or baseline sample test cases.

    Returns:
        (inferred_parameters, limitations, context_completeness)
        context_completeness: "DETECTED" | "PARTIAL" | "INSUFFICIENT"
    """
    limitations: List[str] = []
    ast_info = _extract_ast_signature(code)

    param_names = list(ast_info.get("parameters") or [])
    inference_source = "AST_SIGNATURE"

    if not param_names and problem_context and problem_context.parameters:
        param_names = list(problem_context.parameters)
        inference_source = "EXPLICIT_METADATA"

    if not param_names and test_cases:
        first_tc = test_cases[0]
        if hasattr(first_tc, "input_data"):
            in_data = first_tc.input_data
        elif isinstance(first_tc, dict):
            in_data = first_tc.get("input_data") if "input_data" in first_tc else first_tc
        else:
            in_data = {}

        if in_data and isinstance(in_data, dict):
            param_names = [k for k in in_data.keys() if k not in ("id", "source", "expected_output", "label", "rationale")]
            inference_source = "BASELINE_SAMPLE"

    if not param_names:
        limitations.append("No function parameters could be identified from code AST, problem context, or baseline samples.")
        return [], limitations, "INSUFFICIENT"

    raw_constraints: List[str] = []
    if problem_context and problem_context.constraints:
        raw_constraints.extend(problem_context.constraints)
    if spec and spec.raw_constraints:
        for rc in spec.raw_constraints:
            if rc not in raw_constraints:
                raw_constraints.append(rc)

    description = (problem_context.description if problem_context else "") or ""
    desc_lower = description.lower()
    title_lower = (problem_context.title if problem_context else "").lower()

    inferred_list: List[InferredParameter] = []
    has_ambiguity = False

    for p_name in param_names:
        p_lower = p_name.lower()
        annot_node = ast_info.get("annotations", {}).get(p_name)

        p_type, p_struct, elem_t, is_amb, amb_reason = _parse_ast_type_annotation(annot_node)

        # Infer from baseline sample shape if source is BASELINE_SAMPLE or AST type was unresolved
        if (inference_source == "BASELINE_SAMPLE" or p_struct == "unknown" or p_type == "unknown") and test_cases:
            sample_vals = []
            for tc in test_cases:
                if hasattr(tc, "input_data"):
                    tc_data = tc.input_data
                elif isinstance(tc, dict):
                    tc_data = tc.get("input_data") if "input_data" in tc else tc
                else:
                    tc_data = {}
                if isinstance(tc_data, dict) and p_name in tc_data:
                    sample_vals.append(tc_data[p_name])

            if sample_vals:
                first_val = sample_vals[0]
                if isinstance(first_val, (list, tuple)):
                    if first_val and all(isinstance(r, (list, tuple)) for r in first_val):
                        p_struct = "matrix_2d"
                        inner_cell = first_val[0][0] if (first_val[0] and len(first_val[0]) > 0) else 0
                        elem_t = "bool" if isinstance(inner_cell, bool) else ("int" if isinstance(inner_cell, int) else ("float" if isinstance(inner_cell, float) else "str"))
                        p_type = elem_t
                        is_amb = False
                        amb_reason = None
                    else:
                        p_struct = "array_1d"
                        inner_item = first_val[0] if len(first_val) > 0 else 0
                        elem_t = "bool" if isinstance(inner_item, bool) else ("int" if isinstance(inner_item, int) else ("float" if isinstance(inner_item, float) else "str"))
                        p_type = elem_t
                        is_amb = False
                        amb_reason = None
                elif isinstance(first_val, str):
                    p_struct = "scalar"
                    p_type = "str"
                    elem_t = None
                    is_amb = False
                    amb_reason = None
                elif isinstance(first_val, bool):
                    p_struct = "scalar"
                    p_type = "bool"
                    elem_t = None
                    is_amb = False
                    amb_reason = None
                elif isinstance(first_val, (int, float)):
                    p_struct = "scalar"
                    p_type = "int" if isinstance(first_val, int) else "float"
                    elem_t = None
                    is_amb = False
                    amb_reason = None

        # If annotation was missing or incomplete, fall back to constraints & description
        if p_struct == "unknown" or p_type == "unknown":
            # 1. Check for 2D Matrix patterns
            matrix_cues = (
                f"{p_lower}.length" in " ".join(raw_constraints).lower()
                and f"{p_lower}[i].length" in " ".join(raw_constraints).lower()
            ) or (
                f"{p_lower}[i][j]" in " ".join(raw_constraints).lower()
            ) or (
                re.search(rf"\bm\s*x\s*n\s+(?:binary\s+)?(?:grid|matrix)\b.*?\b{re.escape(p_lower)}\b", desc_lower)
            ) or (
                re.search(rf"\b(?:matrix|grid)\s+{re.escape(p_lower)}\b", desc_lower)
            )

            if matrix_cues:
                p_struct = "matrix_2d"
                elem_t = "int"
                p_type = "int"
                is_amb = False
                amb_reason = None

            # 2. Check for 1D Array patterns
            elif (
                any(f"{p_lower}.length" in c.lower() or f"{p_lower}.size" in c.lower() or f"len({p_lower})" in c.lower() for c in raw_constraints)
                or any(f"{p_lower}[i]" in c.lower() for c in raw_constraints)
                or re.search(rf"\b(?:array of integers|integer array|array of numbers)\s+{re.escape(p_lower)}\b", desc_lower)
                or re.search(rf"\b{re.escape(p_lower)}\s+is an array\b", desc_lower)
                or ((raw_constraints or desc_lower) and p_lower in ("nums", "arr", "digits", "elements", "vals", "items", "nums1", "nums2"))
            ):
                p_struct = "array_1d"
                elem_t = "int"
                p_type = "int"
                is_amb = False
                amb_reason = None

            # 3. Check for String patterns
            elif (
                any(f"{p_lower} consists of" in c.lower() for c in raw_constraints)
                or re.search(rf"\bstring\s+{re.escape(p_lower)}\b", desc_lower)
                or re.search(rf"\bgiven a string\s+{re.escape(p_lower)}\b", desc_lower)
                or ((raw_constraints or desc_lower) and p_lower in ("s", "word", "str", "needle", "haystack", "prefix", "suffix"))
            ):
                p_struct = "scalar"
                p_type = "str"
                elem_t = None
                is_amb = False
                amb_reason = None

            # 4. Check for Scalar Integer patterns
            elif (
                any(re.search(rf"\b{re.escape(p_lower)}\b", c.lower()) for c in raw_constraints)
                or re.search(rf"\binteger\s+{re.escape(p_lower)}\b", desc_lower)
                or ((raw_constraints or desc_lower) and p_lower in ("target", "k", "n", "m", "val", "x", "num", "idx", "index"))
            ):
                p_struct = "scalar"
                p_type = "int"
                elem_t = None
                is_amb = False
                amb_reason = None

        if is_amb or p_struct == "unknown" or p_type == "unknown":
            has_ambiguity = True
            reason = amb_reason or f"Type and structure for parameter '{p_name}' could not be reliably determined."
            inferred_list.append(
                InferredParameter(
                    name=p_name,
                    param_type="unknown",
                    structure="unknown",
                    source=inference_source,
                    is_ambiguous=True,
                    ambiguity_reason=reason,
                )
            )
            limitations.append(f"Ambiguous parameter '{p_name}': {reason}")
            continue

        param = InferredParameter(
            name=p_name,
            param_type=p_type,
            structure=p_struct,
            element_type=elem_t,
            source=inference_source,
        )

        _bind_parameter_constraints(param, raw_constraints, spec)
        inferred_list.append(param)

    if has_ambiguity:
        return inferred_list, limitations, "INSUFFICIENT"

    # Determine completeness: report PARTIAL if sample-derived or constraints missing/unresolved
    has_constraints = bool(raw_constraints or (spec and (
        spec.min_value is not None or spec.max_value is not None or spec.min_length is not None or spec.max_length is not None or spec.min_rows is not None
    )))
    if inference_source == "BASELINE_SAMPLE":
        completeness = "PARTIAL"
    else:
        completeness = "DETECTED" if has_constraints else "PARTIAL"

    return inferred_list, limitations, completeness


def classify_context_candidate(
    candidate: TestCase,
    spec: Optional[ConstraintSpec],
    context: Optional[ProblemContext],
    parameters: List[InferredParameter],
    unresolved_constraints: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Classify a context-derived candidate according to the strict three-tier taxonomy:
    1. Validate supported parameter types.
    2. Validate known numerical and collection constraints.
    3. Validate recognized logical invariants when reliable metadata or explicit problem semantics are available.
    4. Use VALID only when all applicable supported validity checks succeed.
    5. Use ROBUSTNESS PROBE when a candidate intentionally violates a known constraint.
    6. Use CONSTRAINT VALIDITY UNKNOWN when required constraints or logical conditions cannot be established.
    """
    input_data = candidate.input_data or {}
    param_map = {p.name: p for p in parameters}

    # 1. Validate supported parameter types
    for p_name, val in input_data.items():
        p_info = param_map.get(p_name)
        if not p_info or p_info.is_ambiguous:
            return (
                CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                f"Parameter '{p_name}' has ambiguous type or structure; validity cannot be established.",
            )

        if p_info.structure == "scalar":
            if p_info.param_type == "int" and not (isinstance(val, int) and not isinstance(val, bool)):
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Parameter '{p_name}' expected integer scalar, got {type(val).__name__}.",
                )
            elif p_info.param_type == "float" and not (isinstance(val, (int, float)) and not isinstance(val, bool)):
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Parameter '{p_name}' expected float scalar, got {type(val).__name__}.",
                )
            elif p_info.param_type == "str" and not isinstance(val, str):
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Parameter '{p_name}' expected string scalar, got {type(val).__name__}.",
                )
            elif p_info.param_type == "bool" and not isinstance(val, bool):
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Parameter '{p_name}' expected boolean scalar, got {type(val).__name__}.",
                )

        elif p_info.structure == "array_1d":
            if not isinstance(val, (list, tuple)):
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Parameter '{p_name}' expected 1D sequence, got {type(val).__name__}.",
                )

        elif p_info.structure == "matrix_2d":
            if not isinstance(val, (list, tuple)) or (val and not all(isinstance(r, (list, tuple)) for r in val)):
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Parameter '{p_name}' expected 2D matrix, got non-matrix structure.",
                )

    # 2. Validate known numerical and collection constraints (detect deliberate robustness probes)
    checked_constraints = False

    for p_name, val in input_data.items():
        p_info = param_map.get(p_name)
        if not p_info:
            continue

        min_len = p_info.min_length if p_info.min_length is not None else (spec.min_length if spec else None)
        max_len = p_info.max_length if p_info.max_length is not None else (spec.max_length if spec else None)
        min_v = p_info.min_value if p_info.min_value is not None else (spec.min_value if spec else None)
        max_v = p_info.max_value if p_info.max_value is not None else (spec.max_value if spec else None)
        min_r = p_info.min_rows if p_info.min_rows is not None else (spec.min_rows if spec and spec.min_rows is not None else min_len)
        max_r = p_info.max_rows if p_info.max_rows is not None else (spec.max_rows if spec and spec.max_rows is not None else max_len)
        min_c = p_info.min_cols if p_info.min_cols is not None else (spec.min_cols if spec else None)
        max_c = p_info.max_cols if p_info.max_cols is not None else (spec.max_cols if spec else None)
        allowed_v = p_info.allowed_values or (spec.allowed_values if spec else None)

        # 2D Matrix checks
        if p_info.structure == "matrix_2d":
            if isinstance(val, (list, tuple)):
                num_rows = len(val)
                if min_r is not None:
                    checked_constraints = True
                    if num_rows < min_r:
                        return (
                            CandidateClassification.ROBUSTNESS_PROBE.value,
                            f"Violates minimum rows constraint for '{p_name}' ({num_rows} < {min_r}). Deliberate robustness probe.",
                        )
                if max_r is not None:
                    checked_constraints = True
                    if num_rows > max_r:
                        return (
                            CandidateClassification.ROBUSTNESS_PROBE.value,
                            f"Violates maximum rows constraint for '{p_name}' ({num_rows} > {max_r}). Deliberate robustness probe.",
                        )

                for r_idx, row in enumerate(val):
                    if isinstance(row, (list, tuple)):
                        num_cols = len(row)
                        if min_c is not None:
                            checked_constraints = True
                            if num_cols < min_c:
                                return (
                                    CandidateClassification.ROBUSTNESS_PROBE.value,
                                    f"Violates minimum columns constraint for '{p_name}' row {r_idx} ({num_cols} < {min_c}). Deliberate robustness probe.",
                                )
                        if max_c is not None:
                            checked_constraints = True
                            if num_cols > max_c:
                                return (
                                    CandidateClassification.ROBUSTNESS_PROBE.value,
                                    f"Violates maximum columns constraint for '{p_name}' row {r_idx} ({num_cols} > {max_c}). Deliberate robustness probe.",
                                )

                        for c_idx, cell in enumerate(row):
                            if isinstance(cell, (int, float)) and not isinstance(cell, bool):
                                if allowed_v is not None:
                                    checked_constraints = True
                                    if cell not in allowed_v:
                                        return (
                                            CandidateClassification.ROBUSTNESS_PROBE.value,
                                            f"Contains cell {cell} at [{r_idx}][{c_idx}] outside allowed values {allowed_v}. Deliberate robustness probe.",
                                        )
                                if min_v is not None:
                                    checked_constraints = True
                                    if cell < min_v:
                                        return (
                                            CandidateClassification.ROBUSTNESS_PROBE.value,
                                            f"Contains cell {cell} at [{r_idx}][{c_idx}] below minimum value constraint ({min_v}). Deliberate robustness probe.",
                                        )
                                if max_v is not None:
                                    checked_constraints = True
                                    if cell > max_v:
                                        return (
                                            CandidateClassification.ROBUSTNESS_PROBE.value,
                                            f"Contains cell {cell} at [{r_idx}][{c_idx}] above maximum value constraint ({max_v}). Deliberate robustness probe.",
                                        )

                if spec and spec.endpoints_zero:
                    checked_constraints = True
                    if num_rows >= 1 and len(val[0]) >= 1 and len(val[-1]) >= 1:
                        if val[0][0] != 0 or val[-1][-1] != 0:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Violates required endpoint invariant: grid[0][0] and grid[m-1][n-1] must be 0. Deliberate robustness probe.",
                            )
                    else:
                        return (
                            CandidateClassification.ROBUSTNESS_PROBE.value,
                            f"Violates required endpoint invariant due to empty/insufficient matrix dimensions. Deliberate robustness probe.",
                        )
            continue

        # Length bounds
        if isinstance(val, (list, tuple, str)):
            length = len(val)
            if min_len is not None:
                checked_constraints = True
                if length < min_len:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates minimum length constraint for '{p_name}' ({length} < {min_len}). Deliberate robustness probe.",
                    )
            if max_len is not None:
                checked_constraints = True
                if length > max_len:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates maximum length constraint for '{p_name}' ({length} > {max_len}). Deliberate robustness probe.",
                    )

        # Scalar numeric bounds
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if min_v is not None:
                checked_constraints = True
                if val < min_v:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates minimum value constraint for '{p_name}' ({val} < {min_v}). Deliberate robustness probe.",
                    )
            if max_v is not None:
                checked_constraints = True
                if val > max_v:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates maximum value constraint for '{p_name}' ({val} > {max_v}). Deliberate robustness probe.",
                    )

        # Sequence element numeric bounds
        if isinstance(val, (list, tuple)):
            for idx, item in enumerate(val):
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    if min_v is not None:
                        checked_constraints = True
                        if item < min_v:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Contains element {item} at index {idx} below minimum value constraint ({min_v}). Deliberate robustness probe.",
                            )
                    if max_v is not None:
                        checked_constraints = True
                        if item > max_v:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Contains element {item} at index {idx} above maximum value constraint ({max_v}). Deliberate robustness probe.",
                            )

        # Character set bounds
        if isinstance(val, str) and p_info.allowed_characters:
            checked_constraints = True
            if p_info.allowed_characters == "a-z" and not all("a" <= ch <= "z" for ch in val):
                return (
                    CandidateClassification.ROBUSTNESS_PROBE.value,
                    f"String '{p_name}' contains characters outside allowed lowercase English alphabet (a-z). Deliberate robustness probe.",
                )
            elif p_info.allowed_characters == "A-Z" and not all("A" <= ch <= "Z" for ch in val):
                return (
                    CandidateClassification.ROBUSTNESS_PROBE.value,
                    f"String '{p_name}' contains characters outside allowed uppercase English alphabet (A-Z). Deliberate robustness probe.",
                )

    # 3. Validate recognized logical invariants (e.g. Two Sum)
    if is_two_sum_context(context):
        col_p = None
        target_p = None
        for p, v in input_data.items():
            if isinstance(v, (list, tuple)) and col_p is None:
                col_p = p
            elif isinstance(v, (int, float)) and not isinstance(v, bool) and target_p is None:
                target_p = p

        if col_p in input_data and target_p in input_data:
            pairs = count_valid_pairs(input_data[col_p], input_data[target_p])
            if pairs == 1:
                if not unresolved_constraints:
                    return (
                        CandidateClassification.VALID.value,
                        "Satisfies all supported supplied problem constraints and contains exactly one valid pair summing to target.",
                    )
                else:
                    return (
                        CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                        "Satisfies pair sum invariant and parsed bounds, but problem statement contains unresolved constraints.",
                    )
            elif pairs == 0:
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    "Violates problem logical invariant: no pair in collection sums to target.",
                )
            else:
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Violates problem logical invariant: contains {pairs} valid pairs summing to target instead of exactly one.",
                )

    # 4. For non-Two-Sum multi-parameter problems or problems with unresolved constraints:
    # Do not claim candidate is fully VALID merely because it satisfies numerical bounds.
    if len(input_data) > 1:
        return (
            CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
            "Satisfies numerical and collection bounds, but inter-parameter logical semantics are unverified without baseline oracle.",
        )

    if unresolved_constraints:
        return (
            CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
            "Satisfies parsed bounds, but problem statement contains unresolved constraints.",
        )

    if checked_constraints:
        return (
            CandidateClassification.VALID.value,
            "Satisfies all supported supplied problem constraints.",
        )

    return (
        CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
        "No verified constraints available to establish candidate validity.",
    )


def synthesize_context_candidates(
    parameters: List[InferredParameter],
    context: Optional[ProblemContext],
    spec: Optional[ConstraintSpec],
    max_candidates: int = 10,
    unresolved_constraints: Optional[List[str]] = None,
) -> Tuple[List[TestCase], List[RankedCandidate], Dict[str, Any]]:
    """
    Synthesize deterministic, bounded candidates targeting useful edge-case categories
    directly from inferred parameter structures and constraints.
    """
    # 1. Build canonical base input template
    base_inputs: Dict[str, Any] = {}
    is_two_sum = is_two_sum_context(context)

    col_param_name = None
    target_param_name = None

    if is_two_sum:
        for p in parameters:
            if p.structure == "array_1d" and col_param_name is None:
                col_param_name = p.name
            elif p.structure == "scalar" and p.param_type == "int" and target_param_name is None:
                target_param_name = p.name

    for p in parameters:
        min_v = int(p.min_value) if (p.min_value is not None and isinstance(p.min_value, (int, float))) else None
        max_v = int(p.max_value) if (p.max_value is not None and isinstance(p.max_value, (int, float))) else None
        min_l = p.min_length if p.min_length is not None else 1

        if is_two_sum and p.name == col_param_name:
            base_inputs[p.name] = [2, 7, 11, 15]
        elif is_two_sum and p.name == target_param_name:
            base_inputs[p.name] = 9
        elif p.structure == "scalar":
            if p.param_type == "int":
                if min_v is not None and min_v > 0:
                    base_inputs[p.name] = min_v
                elif max_v is not None and max_v < 0:
                    base_inputs[p.name] = max_v
                else:
                    base_inputs[p.name] = 1
            elif p.param_type == "float":
                base_inputs[p.name] = 1.0
            elif p.param_type == "str":
                base_inputs[p.name] = "abc"
            elif p.param_type == "bool":
                base_inputs[p.name] = True
            else:
                base_inputs[p.name] = 0
        elif p.structure == "array_1d":
            if p.element_type == "str":
                base_inputs[p.name] = ["a", "b", "c"]
            elif p.element_type == "bool":
                base_inputs[p.name] = [True, False]
            elif p.element_type == "float":
                base_inputs[p.name] = [1.0, 2.0]
            else:
                length = max(min_l, 2)
                start = min_v if min_v is not None else 1
                base_inputs[p.name] = [start + i for i in range(length)]
        elif p.structure == "matrix_2d":
            base_inputs[p.name] = [[1, 2], [3, 4]]
        else:
            base_inputs[p.name] = 1

    candidates: List[TestCase] = []

    # =========================================================================
    # Specialized Two Sum Synthesis
    # =========================================================================
    if is_two_sum and col_param_name and target_param_name:
        col_p = col_param_name
        target_p = target_param_name
        p_col = next((p for p in parameters if p.name == col_p), None)
        p_t = next((p for p in parameters if p.name == target_p), None)

        min_v = int(p_col.min_value) if p_col and p_col.min_value is not None else -1000000000
        max_v = int(p_col.max_value) if p_col and p_col.max_value is not None else 1000000000
        min_l = p_col.min_length if p_col and p_col.min_length is not None else 2
        max_l = p_col.max_length if p_col and p_col.max_length is not None else 10000

        # 1. Canonical baseline candidate
        c_base = copy.deepcopy(base_inputs)
        c_base[col_p] = [2, 7, 11, 15]
        c_base[target_p] = 9
        candidates.append(
            TestCase(
                id="ctx-twosum-standard",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_base,
                label=f"Standard valid pair for {col_p} and {target_p}",
                rationale="Valid sequence containing exactly one pair (2 + 7) summing to target 9.",
                is_boundary=False,
            )
        )

        # 2. Minimum permitted collection length
        c_min_len = copy.deepcopy(base_inputs)
        c_min_len[col_p] = [3, 4]
        c_min_len[target_p] = 7
        candidates.append(
            TestCase(
                id="ctx-twosum-min-length",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_min_len,
                label=f"Minimum permitted collection length ({min_l} elements) for {col_p}",
                rationale=f"Minimal boundary length sequence ({min_l} elements) with single valid pair (3 + 4 = 7).",
                is_boundary=True,
            )
        )

        # 3. Minimum target boundary
        if p_t and p_t.min_value is not None:
            min_t = int(p_t.min_value)
            c_min_t = copy.deepcopy(base_inputs)
            c_min_t[col_p] = [min_t, 0, 100]
            c_min_t[target_p] = min_t
            candidates.append(
                TestCase(
                    id="ctx-twosum-min-target",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=c_min_t,
                    label=f"Minimum constraint value for {target_p}",
                    rationale=f"Target parameter {target_p} set to extreme lower bound {min_t} with valid pair ({min_t} + 0).",
                    is_boundary=True,
                )
            )

        # 4. Maximum target boundary
        if p_t and p_t.max_value is not None:
            max_t = int(p_t.max_value)
            c_max_t = copy.deepcopy(base_inputs)
            c_max_t[col_p] = [max_t, 0, -100]
            c_max_t[target_p] = max_t
            candidates.append(
                TestCase(
                    id="ctx-twosum-max-target",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=c_max_t,
                    label=f"Maximum constraint value for {target_p}",
                    rationale=f"Target parameter {target_p} set to extreme upper bound {max_t} with valid pair ({max_t} + 0).",
                    is_boundary=True,
                )
            )

        # 5. Minimum element value boundary
        if p_col and p_col.min_value is not None:
            c_min_v = copy.deepcopy(base_inputs)
            c_min_v[col_p] = [min_v, 5, 100]
            c_min_v[target_p] = min_v + 5
            candidates.append(
                TestCase(
                    id="ctx-twosum-min-elem",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=c_min_v,
                    label=f"Minimum constraint value element in {col_p}",
                    rationale=f"Sequence {col_p} contains lower bound element {min_v} paired with 5 summing to target {min_v + 5}.",
                    is_boundary=True,
                )
            )

        # 6. Maximum element value boundary
        if p_col and p_col.max_value is not None:
            c_max_v = copy.deepcopy(base_inputs)
            c_max_v[col_p] = [max_v, -5, -100]
            c_max_v[target_p] = max_v - 5
            candidates.append(
                TestCase(
                    id="ctx-twosum-max-elem",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=c_max_v,
                    label=f"Maximum constraint value element in {col_p}",
                    rationale=f"Sequence {col_p} contains upper bound element {max_v} paired with -5 summing to target {max_v - 5}.",
                    is_boundary=True,
                )
            )

        # 7. Zero target value
        c_zero_t = copy.deepcopy(base_inputs)
        c_zero_t[col_p] = [-5, 5, 10]
        c_zero_t[target_p] = 0
        candidates.append(
            TestCase(
                id="ctx-twosum-zero-target",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_zero_t,
                label=f"Zero value for {target_p}",
                rationale="Zero target with symmetric negative/positive pair (-5 + 5 = 0).",
                is_boundary=True,
            )
        )

        # 8. Negative target value
        c_neg_t = copy.deepcopy(base_inputs)
        c_neg_t[col_p] = [-10, 3, 20]
        c_neg_t[target_p] = -7
        candidates.append(
            TestCase(
                id="ctx-twosum-neg-target",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_neg_t,
                label=f"Negative value for {target_p}",
                rationale="Negative target (-7) with valid pair (-10 + 3 = -7).",
                is_boundary=False,
            )
        )

        # 9. Negative array values
        c_neg_arr = copy.deepcopy(base_inputs)
        c_neg_arr[col_p] = [-20, -30, 50]
        c_neg_arr[target_p] = -50
        candidates.append(
            TestCase(
                id="ctx-twosum-neg-array",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_neg_arr,
                label=f"Negative values in {col_p}",
                rationale="Sequence containing strictly negative pair elements (-20 + -30 = -50).",
                is_boundary=False,
            )
        )

        # 10. Duplicate elements with single valid pair
        c_dup = copy.deepcopy(base_inputs)
        c_dup[col_p] = [3, 3, 4]
        c_dup[target_p] = 6
        candidates.append(
            TestCase(
                id="ctx-twosum-duplicates",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_dup,
                label=f"Duplicate elements forming target in {col_p}",
                rationale="Sequence containing duplicate elements (3, 3) at distinct indices summing to target 6.",
                is_boundary=False,
            )
        )

        # 11. Large scale test (stress boundary)
        scale_size = min(max_l, 10000)
        c_scale = copy.deepcopy(base_inputs)
        filler = [100 + i for i in range(scale_size - 2)]
        c_scale[col_p] = [2, 7] + filler
        c_scale[target_p] = 9
        candidates.append(
            TestCase(
                id="ctx-twosum-scale",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_scale,
                label=f"Maximum constraint length ({scale_size} elements) for {col_p}",
                rationale=f"Scale stress test of {scale_size} elements with valid pair (2, 7) summing to target 9.",
                is_performance=True,
            )
        )

        # 12. Deliberate robustness probe: empty collection
        if min_l > 0:
            c_empty = copy.deepcopy(base_inputs)
            c_empty[col_p] = []
            c_empty[target_p] = 0
            candidates.append(
                TestCase(
                    id="ctx-twosum-probe-empty",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=c_empty,
                    label=f"Empty {col_p} robustness probe",
                    rationale=f"Deliberately violates minimum length constraint ({min_l}) to probe handler resilience.",
                    is_boundary=True,
                )
            )

        # 13. Deliberate robustness probe: singleton collection
        if min_l > 1:
            c_single = copy.deepcopy(base_inputs)
            c_single[col_p] = [1]
            c_single[target_p] = 1
            candidates.append(
                TestCase(
                    id="ctx-twosum-probe-singleton",
                    source=TestCaseSource.GENERATED_TEST,
                    input_data=c_single,
                    label=f"Singleton {col_p} robustness probe",
                    rationale=f"Deliberately violates minimum length constraint ({min_l}) with a single-element list.",
                    is_boundary=True,
                )
            )

        # 14. Semantic invariant probe: all identical elements without valid pair
        c_ident = copy.deepcopy(base_inputs)
        c_ident[col_p] = [1, 1, 1]
        c_ident[target_p] = 5
        candidates.append(
            TestCase(
                id="ctx-twosum-probe-no-pair",
                source=TestCaseSource.GENERATED_TEST,
                input_data=c_ident,
                label=f"All identical elements without valid pair in {col_p}",
                rationale="Sequence where no two elements sum to target 5, probing logical invariant enforcement.",
                is_boundary=False,
            )
        )

    # =========================================================================
    # General Parameter Synthesis (Single & Multi-Parameter)
    # =========================================================================
    else:
        for p in parameters:
            p_name = p.name
            min_v = int(p.min_value) if p.min_value is not None else None
            max_v = int(p.max_value) if p.max_value is not None else None
            min_l = p.min_length if p.min_length is not None else 0
            max_l = p.max_length if p.max_length is not None else 10000

            # --- Scalar Integer ---
            if p.structure == "scalar" and p.param_type == "int":
                if min_v is not None:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = min_v
                    candidates.append(
                        TestCase(
                            id=f"ctx-min-val-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Minimum constraint value for {p_name}",
                            rationale=f"Boundary candidate targeting lower numerical bound ({min_v}) for {p_name}.",
                            is_boundary=True,
                        )
                    )
                if max_v is not None:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = max_v
                    candidates.append(
                        TestCase(
                            id=f"ctx-max-val-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Maximum constraint value for {p_name}",
                            rationale=f"Boundary candidate targeting upper numerical bound ({max_v}) for {p_name}.",
                            is_boundary=True,
                        )
                    )
                if (min_v is None or min_v <= 0) and (max_v is None or max_v >= 0):
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = 0
                    candidates.append(
                        TestCase(
                            id=f"ctx-zero-val-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Zero value for {p_name}",
                            rationale=f"Zero-value partition test for scalar parameter {p_name}.",
                            is_boundary=True,
                        )
                    )
                if min_v is None or min_v < 0:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = max(min_v, -10) if min_v is not None else -1
                    candidates.append(
                        TestCase(
                            id=f"ctx-neg-val-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Negative value for {p_name}",
                            rationale=f"Negative value partition test for scalar parameter {p_name}.",
                            is_boundary=False,
                        )
                    )
                # Robustness probes
                if min_v is not None:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = min_v - 1
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-underflow-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Underflow robustness probe for {p_name}",
                            rationale=f"Deliberately violates lower bound ({min_v}) with value {min_v - 1}.",
                            is_boundary=True,
                        )
                    )
                if max_v is not None:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = max_v + 1
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-overflow-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Overflow robustness probe for {p_name}",
                            rationale=f"Deliberately violates upper bound ({max_v}) with value {max_v + 1}.",
                            is_boundary=True,
                        )
                    )

            # --- Scalar String ---
            elif p.structure == "scalar" and p.param_type == "str":
                if min_l == 0:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = ""
                    candidates.append(
                        TestCase(
                            id=f"ctx-empty-str-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Empty string for {p_name}",
                            rationale=f"Empty string boundary test permitted by constraints for {p_name}.",
                            is_boundary=True,
                        )
                    )
                if min_l <= 1:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = "a"
                    candidates.append(
                        TestCase(
                            id=f"ctx-single-str-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Single character string for {p_name}",
                            rationale=f"Singleton string boundary test for {p_name}.",
                            is_boundary=True,
                        )
                    )
                c_rep = copy.deepcopy(base_inputs)
                c_rep[p_name] = "aaaa"
                candidates.append(
                    TestCase(
                        id=f"ctx-repeat-str-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_rep,
                        label=f"Repeated characters for {p_name}",
                        rationale=f"String containing all identical characters for {p_name}.",
                        is_boundary=False,
                    )
                )
                if min_l > 0:
                    c_probe = copy.deepcopy(base_inputs)
                    c_probe[p_name] = ""
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-empty-str-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_probe,
                            label=f"Empty string robustness probe for {p_name}",
                            rationale=f"Deliberately violates minimum length constraint ({min_l}) for {p_name}.",
                            is_boundary=True,
                        )
                    )

            # --- 1D Array ---
            elif p.structure == "array_1d":
                if min_l == 0:
                    c = copy.deepcopy(base_inputs)
                    c[p_name] = []
                    candidates.append(
                        TestCase(
                            id=f"ctx-empty-arr-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Empty collection for {p_name}",
                            rationale=f"Empty collection boundary test permitted by constraints for {p_name}.",
                            is_boundary=True,
                        )
                    )
                if min_l <= 1:
                    c = copy.deepcopy(base_inputs)
                    elem_val = min_v if min_v is not None else 1
                    c[p_name] = [elem_val]
                    candidates.append(
                        TestCase(
                            id=f"ctx-single-arr-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c,
                            label=f"Singleton collection for {p_name}",
                            rationale=f"Single-element collection boundary test for {p_name}.",
                            is_boundary=True,
                        )
                    )

                # Minimum permitted length
                len_target = max(min_l, 2)
                c_min_len = copy.deepcopy(base_inputs)
                start_val = min_v if min_v is not None else 1
                c_min_len[p_name] = [start_val + i for i in range(len_target)]
                candidates.append(
                    TestCase(
                        id=f"ctx-min-len-arr-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_min_len,
                        label=f"Minimum permitted length ({len_target} elements) for {p_name}",
                        rationale=f"Boundary candidate targeting lower collection length ({len_target}) for {p_name}.",
                        is_boundary=True,
                    )
                )

                # Maximum collection length scale test
                scale_len = min(max_l, 10000)
                c_max_len = copy.deepcopy(base_inputs)
                c_max_len[p_name] = [(i % 100) for i in range(scale_len)]
                candidates.append(
                    TestCase(
                        id=f"ctx-max-len-arr-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_max_len,
                        label=f"Maximum constraint length ({scale_len} elements) for {p_name}",
                        rationale=f"Scale stress test targeting upper collection length bound ({scale_len}) for {p_name}.",
                        is_performance=True,
                    )
                )

                # Duplicates
                c_dup = copy.deepcopy(base_inputs)
                d_val = min_v if min_v is not None else 1
                c_dup[p_name] = [d_val, d_val, d_val + 1, d_val + 2]
                candidates.append(
                    TestCase(
                        id=f"ctx-dup-arr-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_dup,
                        label=f"Duplicate elements in {p_name}",
                        rationale=f"Sequence containing adjacent duplicate elements ({d_val}, {d_val}) for {p_name}.",
                        is_boundary=False,
                    )
                )

                # All identical
                c_ident = copy.deepcopy(base_inputs)
                c_ident[p_name] = [d_val, d_val, d_val]
                candidates.append(
                    TestCase(
                        id=f"ctx-ident-arr-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_ident,
                        label=f"All identical elements in {p_name}",
                        rationale=f"Sequence where all elements are identical for {p_name}.",
                        is_boundary=False,
                    )
                )

                # Sorted & Reverse sorted
                c_sorted = copy.deepcopy(base_inputs)
                c_sorted[p_name] = [1, 2, 3, 4, 5]
                candidates.append(
                    TestCase(
                        id=f"ctx-sorted-arr-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_sorted,
                        label=f"Already sorted sequence for {p_name}",
                        rationale=f"Monotonically increasing sorted sequence for {p_name}.",
                        is_boundary=False,
                    )
                )

                c_rev = copy.deepcopy(base_inputs)
                c_rev[p_name] = [5, 4, 3, 2, 1]
                candidates.append(
                    TestCase(
                        id=f"ctx-rev-arr-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_rev,
                        label=f"Reverse sorted sequence for {p_name}",
                        rationale=f"Monotonically decreasing reverse-sorted sequence for {p_name}.",
                        is_boundary=False,
                    )
                )

                # Zero elements
                if (min_v is None or min_v <= 0) and (max_v is None or max_v >= 0):
                    c_zero = copy.deepcopy(base_inputs)
                    c_zero[p_name] = [0, 1, 2]
                    candidates.append(
                        TestCase(
                            id=f"ctx-zero-elem-arr-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_zero,
                            label=f"Zero value elements in {p_name}",
                            rationale=f"Sequence containing zero elements for {p_name}.",
                            is_boundary=True,
                        )
                    )

                # Negative elements
                if min_v is None or min_v < 0:
                    c_neg = copy.deepcopy(base_inputs)
                    c_neg[p_name] = [-1, -2, -3]
                    candidates.append(
                        TestCase(
                            id=f"ctx-neg-elem-arr-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_neg,
                            label=f"Negative value elements in {p_name}",
                            rationale=f"Sequence containing negative elements for {p_name}.",
                            is_boundary=False,
                        )
                    )

                # Deliberate robustness probe: empty array
                if min_l > 0:
                    c_probe_empty = copy.deepcopy(base_inputs)
                    c_probe_empty[p_name] = []
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-empty-arr-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_probe_empty,
                            label=f"Empty {p_name} robustness probe",
                            rationale=f"Deliberately violates minimum length constraint ({min_l}) for {p_name}.",
                            is_boundary=True,
                        )
                    )

            # --- 2D Matrix ---
            elif p.structure == "matrix_2d":
                min_r = p.min_rows if p.min_rows is not None else (spec.min_rows if spec and spec.min_rows is not None else (p.min_length if p.min_length is not None else (spec.min_length if spec and spec.min_length is not None else 1)))
                max_r = p.max_rows if p.max_rows is not None else (spec.max_rows if spec and spec.max_rows is not None else (p.max_length if p.max_length is not None else (spec.max_length if spec and spec.max_length is not None else 100)))
                min_c = p.min_cols if p.min_cols is not None else (spec.min_cols if spec and spec.min_cols is not None else 1)
                max_c = p.max_cols if p.max_cols is not None else (spec.max_cols if spec and spec.max_cols is not None else 100)
                allowed_vals = p.allowed_values or (spec.allowed_values if spec else None)
                endpoints_zero = spec.endpoints_zero if spec else False

                fill_val = allowed_vals[0] if allowed_vals else (int(min_v) if min_v is not None and min_v > 0 else 0)

                # 0. 1x1 Singleton Matrix when permitted (min_r <= 1 and min_c <= 1)
                if min_r <= 1 and min_c <= 1:
                    c_1x1 = copy.deepcopy(base_inputs)
                    c_1x1_val = 0 if endpoints_zero else (1 if (not allowed_vals or 1 in allowed_vals) else allowed_vals[0])
                    c_1x1[p_name] = [[c_1x1_val]]
                    candidates.append(
                        TestCase(
                            id=f"ctx-1x1-mat-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_1x1,
                            label=f"1x1 singleton matrix for {p_name}",
                            rationale=f"Singleton matrix boundary test for {p_name}.",
                            is_boundary=True,
                        )
                    )

                # 1. Compliant Minimum-Dimension Matrix (e.g. 2x2 when min_r=2, min_c=2)
                r_min = max(min_r, 1)
                c_min = max(min_c, 1)
                c_min_mat = copy.deepcopy(base_inputs)
                mat_grid = [[fill_val for _ in range(c_min)] for _ in range(r_min)]
                if endpoints_zero:
                    mat_grid[0][0] = 0
                    mat_grid[r_min - 1][c_min - 1] = 0
                c_min_mat[p_name] = mat_grid
                candidates.append(
                    TestCase(
                        id=f"ctx-min-mat-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_min_mat,
                        label=f"Minimum dimension matrix ({r_min}x{c_min}) for {p_name}",
                        rationale=f"Minimum valid boundary dimensions ({r_min}x{c_min}) for matrix {p_name}.",
                        is_boundary=True,
                    )
                )

                # 2. Compliant Rectangular Matrix (e.g. 2x3 or 3x2)
                r_rect = max(min_r, 2)
                c_rect = max(min_c, 3)
                if r_rect == c_rect:
                    c_rect = r_rect + 1
                if max_r and r_rect > max_r:
                    r_rect = max_r
                if max_c and c_rect > max_c:
                    c_rect = max_c
                if r_rect == c_rect and r_rect > min_r:
                    r_rect = min_r

                c_rect_mat = copy.deepcopy(base_inputs)
                alt_val = allowed_vals[1] if (allowed_vals and len(allowed_vals) > 1) else (fill_val + 1 if (max_v is None or fill_val < max_v) else fill_val)
                mat_rect = [[(fill_val if (i + j) % 2 == 0 else alt_val) for j in range(c_rect)] for i in range(r_rect)]
                if endpoints_zero:
                    mat_rect[0][0] = 0
                    mat_rect[r_rect - 1][c_rect - 1] = 0
                c_rect_mat[p_name] = mat_rect
                candidates.append(
                    TestCase(
                        id=f"ctx-rect-mat-{p_name}",
                        source=TestCaseSource.GENERATED_TEST,
                        input_data=c_rect_mat,
                        label=f"Rectangular matrix ({r_rect}x{c_rect}) for {p_name}",
                        rationale=f"Rectangular matrix boundary test ({r_rect}x{c_rect}) for {p_name}.",
                        is_boundary=True,
                    )
                )

                # 3. Deliberate Robustness Probes
                if min_r > 0:
                    c_probe_empty = copy.deepcopy(base_inputs)
                    c_probe_empty[p_name] = []
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-empty-mat-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_probe_empty,
                            label=f"Empty matrix robustness probe for {p_name}",
                            rationale=f"Deliberately violates minimum row count constraint ({min_r}) for {p_name}.",
                            is_boundary=True,
                        )
                    )

                if min_r > 1:
                    c_probe_row = copy.deepcopy(base_inputs)
                    c_probe_row[p_name] = [[fill_val for _ in range(max(min_c, 1))]]
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-single-row-mat-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_probe_row,
                            label=f"Single-row matrix robustness probe for {p_name}",
                            rationale=f"Deliberately violates minimum row count constraint ({min_r}) for {p_name}.",
                            is_boundary=True,
                        )
                    )

                if min_c > 1:
                    c_probe_col = copy.deepcopy(base_inputs)
                    c_probe_col[p_name] = [[fill_val] for _ in range(max(min_r, 1))]
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-single-col-mat-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_probe_col,
                            label=f"Single-column matrix robustness probe for {p_name}",
                            rationale=f"Deliberately violates minimum column count constraint ({min_c}) for {p_name}.",
                            is_boundary=True,
                        )
                    )

                if allowed_vals:
                    c_probe_domain = copy.deepcopy(base_inputs)
                    inv_val = max(allowed_vals) + 1
                    inv_grid = [[fill_val for _ in range(c_min)] for _ in range(r_min)]
                    inv_grid[0][0] = inv_val
                    c_probe_domain[p_name] = inv_grid
                    candidates.append(
                        TestCase(
                            id=f"ctx-probe-domain-mat-{p_name}",
                            source=TestCaseSource.GENERATED_TEST,
                            input_data=c_probe_domain,
                            label=f"Out-of-domain matrix cell robustness probe for {p_name}",
                            rationale=f"Deliberately violates allowed cell values {allowed_vals} for {p_name}.",
                            is_boundary=True,
                        )
                    )

    # 4. Canonical deduplication & ranking
    ranker = CandidateRanker(default_max_selected=max_candidates)
    ranking_result = ranker.rank_and_select(
        candidates=candidates,
        existing_tests=[],
        gaps=[],
        max_selected=max_candidates,
    )

    # 5. Classify selected and ranked candidates
    for cand in ranking_result.selected_candidates:
        classification, reason = classify_context_candidate(
            candidate=cand,
            spec=spec,
            context=context,
            parameters=parameters,
            unresolved_constraints=unresolved_constraints,
        )
        cand.classification = classification
        cand.classification_reason = reason

    for ranked in ranking_result.ranked_candidates:
        classification, reason = classify_context_candidate(
            candidate=ranked.candidate,
            spec=spec,
            context=context,
            parameters=parameters,
            unresolved_constraints=unresolved_constraints,
        )
        ranked.candidate.classification = classification
        ranked.candidate.classification_reason = reason

    ranking_summary = {
        "total_evaluated": ranking_result.total_evaluated,
        "exact_duplicates_removed": ranking_result.exact_duplicates_removed,
        "redundant_candidates_penalized": ranking_result.redundant_candidates_penalized,
        "selection_limit": ranking_result.selection_limit,
    }

    return ranking_result.selected_candidates, ranking_result.ranked_candidates, ranking_summary
