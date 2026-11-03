"""
EdgeMind Adaptive Test Intelligence - Deterministic Constraint Parser & Classifier.

Extracts machine-readable ConstraintSpec and per-parameter bounds from raw LeetCode constraint strings.
Handles:
- Double inequalities: LOW <= EXPR <= HIGH
- Single inequalities: EXPR >= LOW, EXPR <= HIGH, LOW <= EXPR
- Chained inequalities: LOW <= PARAM1 <= PARAM2 <= HIGH, 1 <= k <= n <= 10^5
- Range expressions: "number of nodes in each list is in the range [1, 100]"
- Exponent notation: 10^4, 10^9, -10^9, 2^31 - 1, -2^31
- Multiplicative notation: 2 * 10^4, 5 * 10^4
- Character sets: lowercase/uppercase English letters, parentheses '()[]{}'
- Sortedness and uniqueness constraints
- Matrix dimension and endpoint invariants
- Cross-parameter relationships: e.g. window size k <= len(nums), distinct pair sum
- Preserves unparsed expressions as unresolved constraints with specific human-readable explanations.
- Classifies candidate test cases into VALID, ROBUSTNESS PROBE, or CONSTRAINT VALIDITY UNKNOWN.
"""

import copy
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from core.test_intelligence.models import (
    CandidateClassification,
    ConstraintSpec,
    CrossParameterConstraint,
    ParamConstraintSpec,
    ParsedConstraint,
    TestCase,
)


_UNICODE_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")


def normalize_latex(text: str) -> str:
    """
    Deterministic normalization for LaTeX/KaTeX constraint expressions.
    Removes text/math formatting wrappers, normalizes LaTeX spacing commands and operators,
    and handles nested braces safely while preserving legitimate mathematical tokens.
    """
    if not text:
        return ""
    s = str(text)

    # 1. Iteratively unwrap \text{...}, text{...}, \mathbf{...}, \math...{...}
    wrapper_pattern = re.compile(
        r"\\?(?:text|textbf|textit|mathrm|mathbf|mathit|mathtt|operatorname|math[a-zA-Z]*)\{([^{}]*)\}"
    )
    for _ in range(10):
        new_s = wrapper_pattern.sub(r"\1", s)
        if new_s == s:
            break
        s = new_s

    # 2. LaTeX operators
    s = re.sub(r"\\le\b|\\leq\b", "<=", s)
    s = re.sub(r"\\ge\b|\\geq\b", ">=", s)
    s = re.sub(r"\\times\b|\\cdot\b", "*", s)
    s = re.sub(r"\\ne\b|\\neq\b", "!=", s)

    # 3. LaTeX whitespace commands
    s = re.sub(r"\\quad\b|\\qquad\b", " ", s)
    s = re.sub(r"\\([,;:! ])", " ", s)
    s = re.sub(r"~", " ", s)

    # 4. LaTeX powers with braces: e.g. 10^{9} -> 10^9, 2^{31} -> 2^31
    s = re.sub(r"\^\{([+-]?\d+)\}", r"^\1", s)

    # 5. Unicode mathematical operators
    s = (
        s.replace("≤", "<=")
        .replace("\u2264", "<=")
        .replace("≥", ">=")
        .replace("\u2265", ">=")
        .replace("−", "-")
        .replace("\u2212", "-")
    )

    # 6. Normalize whitespace
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def normalize_superscripts(text: str) -> str:
    """Normalize unicode superscript exponents (e.g. 10⁹ -> 10^9, 2³¹ -> 2^31)."""
    if not text:
        return ""
    return re.sub(
        r"([a-zA-Z0-9)])([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)",
        lambda m: m.group(1) + "^" + m.group(2).translate(_UNICODE_SUPERSCRIPTS),
        text,
    )


def normalize_collapsed_exponents(text: str) -> str:
    """
    Restore collapsed exponents from flattened DOM or scrapers:
    e.g. -109 -> -10^9, 109 -> 10^9, 104 -> 10^4, 231 -> 2^31.
    """
    if not text:
        return ""
    s = text
    s = re.sub(r"(^|[<>=,\s([*x\u00d7\u22c5\u2212-])231\b", r"\g<1>2^31", s)
    s = re.sub(r"(^|[<>=,\s([*x\u00d7\u22c5\u2212-])10([3-9])\b", r"\g<1>10^\2", s)
    return s


def parse_number_expression(text: str) -> Optional[Union[int, float]]:
    """
    Parse a numeric expression deterministically.

    Supports:
    - Standard integers & floats: "2", "-10", "0", "3.14"
    - Exponents: "10^4", "10^9", "-10^9", "10^5", "2^31", "-2^31"
    - Exponents with offset: "2^31 - 1", "2^31-1", "2^31 + 1", "-2^31 + 1"
    - Multiplication with exponent: "2 * 10^4", "5 * 10^4", "2*10^4"
    - Unicode superscripts: "10⁹", "-10⁹", "2³¹ - 1", "-2³¹"
    - Unicode minus characters: '−' (\u2212)
    """
    if not text:
        return None
    s = normalize_latex(str(text))
    s = normalize_superscripts(s).strip().replace(" ", "").replace("\u2212", "-")
    s = normalize_collapsed_exponents(s)

    # 1. Direct float/int parsing
    try:
        val = float(s)
        return int(val) if val.is_integer() else val
    except ValueError:
        pass

    # 2. Multiplication with exponent: e.g. "2*10^4", "2x10^4", "2 * 10^4", "-2 * 10^4"
    m_mult = re.match(r"^([+-]?\d+(?:\.\d+)?)[*x](\d+)\^(\d+)$", s)
    if m_mult:
        coeff = float(m_mult.group(1))
        base = float(m_mult.group(2))
        exp = float(m_mult.group(3))
        if exp <= 308:
            val = coeff * (base ** exp)
            return int(val) if val.is_integer() else val

    # 3. Exponent with offset: e.g. "2^31-1", "2^31+1", "-2^31+1", "-2^31-1"
    m_pow_offset = re.match(r"^([+-]?)(\d+)\^(\d+)([+-]\d+)$", s)
    if m_pow_offset:
        sign = -1 if m_pow_offset.group(1) == "-" else 1
        base = int(m_pow_offset.group(2))
        exp = int(m_pow_offset.group(3))
        offset = int(m_pow_offset.group(4))
        if exp <= 100:
            val = (sign * (base ** exp)) + offset
            return int(val)

    # 4. Standard exponent: e.g. "10^4", "-10^9", "2^31", "-2^31"
    m_pow = re.match(r"^([+-]?)(\d+)\^(\d+)$", s)
    if m_pow:
        sign = -1 if m_pow.group(1) == "-" else 1
        base = int(m_pow.group(2))
        exp = int(m_pow.group(3))
        if exp <= 308:
            val = sign * (base ** exp)
            return int(val)

    return None


def parse_constraint_expressions(
    raw_constraints: List[str],
    known_parameters: Optional[List[str]] = None,
) -> Tuple[ConstraintSpec, List[str]]:
    """
    Deterministic parser for supported constraint expressions with per-parameter tracking
    and cross-parameter relationship inference.

    Returns:
        (spec, unresolved_constraints)
        spec: ConstraintSpec containing globally aggregated bounds, granular param_specs,
              cross_constraints, and explanations of unresolved items.
        unresolved_constraints: List of raw constraint lines that could not be mapped.
    """
    spec = ConstraintSpec(raw_constraints=list(raw_constraints))
    unresolved: List[str] = []
    unresolved_reasons: Dict[str, str] = {}
    parsed_constraints: List[ParsedConstraint] = []
    cross_constraints: List[CrossParameterConstraint] = []

    known_params: List[str] = []
    for p in (known_parameters or []):
        if isinstance(p, str):
            known_params.append(p.lower())
        elif isinstance(p, dict) and "name" in p:
            known_params.append(str(p["name"]).lower())
        elif hasattr(p, "name"):
            known_params.append(str(p.name).lower())
        elif p is not None:
            known_params.append(str(p).lower())

    param_specs: Dict[str, ParamConstraintSpec] = {
        p: ParamConstraintSpec(name=p) for p in known_params
    }

    # 0. Contextual heuristic: detect if this problem involves a 2D matrix
    is_matrix_problem = any(p in ("matrix", "grid", "board") for p in known_params)
    for line in raw_constraints:
        c_lower = line.lower()
        if any(kw in c_lower for kw in (
            "matrix", "grid", "board", "matrix[", "grid[", "board[", "[i][j]",
            "matrix.length", "grid.length", "matrix[0].length", "grid[0].length"
        )):
            is_matrix_problem = True

    row_vars: Set[str] = {"m", "rows", "r"} if is_matrix_problem else set()
    col_vars: Set[str] = {"n", "cols", "c"} if is_matrix_problem else set()

    length_aliases: Dict[str, str] = {}
    length_indicators = (".length", ".size", "len(", "length of", "size of")

    # Regular expression patterns
    double_ineq_pattern = re.compile(
        r"^\s*([^<=\u2264]+?)\s*(<=|<|\u2264)\s*(.+?)\s*(<=|<|\u2264)\s*([^<=\u2264]+?)\s*$",
        re.IGNORECASE,
    )
    single_ineq_pattern = re.compile(
        r"^\s*([^<>=]+?)\s*(>=|>|\u2265|<=|<|\u2264)\s*([^<>=]+?)\s*$",
        re.IGNORECASE,
    )

    # Pre-scan for dimension equality aliases: e.g. "m == grid.length", "n == grid[i].length", "n == nums.length"
    for line in raw_constraints:
        c_clean = normalize_latex(line)
        c_clean = normalize_superscripts(c_clean).strip().replace("\u2264", "<=").replace("\u2265", ">=").replace("\u2212", "-")
        c_clean = normalize_collapsed_exponents(c_clean)

        m_row_alias = re.match(r"^\s*([a-zA-Z_]\w*)\s*={1,2}\s*([a-zA-Z_]\w*)\s*\.\s*(?:length|size)\s*$", c_clean, re.IGNORECASE)
        if m_row_alias:
            alias_v = m_row_alias.group(1).lower()
            target_v = m_row_alias.group(2).lower()
            length_aliases[alias_v] = target_v
            if is_matrix_problem:
                row_vars.add(alias_v)

        m_col_alias = re.match(r"^\s*([a-zA-Z_]\w*)\s*={1,2}\s*([a-zA-Z_]\w*)\s*\[.*?\]\s*\.\s*(?:length|size)\s*$", c_clean, re.IGNORECASE)
        if m_col_alias:
            alias_v = m_col_alias.group(1).lower()
            target_v = m_col_alias.group(2).lower()
            length_aliases[alias_v] = target_v
            if is_matrix_problem:
                col_vars.add(alias_v)

    for line in raw_constraints:
        cleaned = normalize_latex(line)
        cleaned = normalize_superscripts(cleaned).strip().replace("\u2264", "<=").replace("\u2265", ">=").replace("\u2212", "-")
        cleaned = normalize_collapsed_exponents(cleaned)
        if not cleaned:
            continue

        matched = False

        # 1. Dimension / length equality definitions: e.g. "m == grid.length", "n == grid[i].length", "n == nums.length"
        m_dim_eq = re.match(r"^\s*([a-zA-Z_]\w*)\s*={1,2}\s*([a-zA-Z_]\w*)(?:\[.*?\])?\s*\.\s*(?:length|size)\s*$", cleaned, re.IGNORECASE)
        if m_dim_eq:
            v_name = m_dim_eq.group(1).lower()
            tgt_name = m_dim_eq.group(2).lower()
            length_aliases[v_name] = tgt_name
            if is_matrix_problem:
                if "[" in cleaned:
                    col_vars.add(v_name)
                else:
                    row_vars.add(v_name)
            matched = True
            parsed_constraints.append(ParsedConstraint(
                raw_text=line, normalized_text=cleaned, constraint_type="ALIAS_DEFINITION", confidence=1.0
            ))

        # 2. Discrete cell / scalar value domain (e.g. "grid[i][j] is either 0 or 1", "grid[i][j] in {0, 1}")
        if not matched:
            m_domain = re.search(
                r"(?:\w+(?:\[.*?\])*)\s+(?:is\s+)?(?:either\s+)?(-?\d+)\s+or\s+(-?\d+)",
                cleaned,
                re.IGNORECASE,
            ) or re.search(
                r"(?:\w+(?:\[.*?\])*)\s*(?:in|==|\u2208)\s*\{?\s*(-?\d+)\s*,\s*(-?\d+)\s*\}?",
                cleaned,
                re.IGNORECASE,
            )
            if m_domain:
                v1 = int(m_domain.group(1))
                v2 = int(m_domain.group(2))
                vals = sorted([v1, v2])
                spec.allowed_values = vals
                spec.min_value = min(v1, v2)
                spec.max_value = max(v1, v2)
                for p in known_params:
                    if p in ("grid", "matrix", "board") or is_matrix_problem:
                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                        param_specs[p].allowed_values = vals
                        param_specs[p].min_value = vals[0]
                        param_specs[p].max_value = vals[-1]
                matched = True
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line, normalized_text=cleaned, constraint_type="ALLOWED_VALUES",
                    lower_bound=vals[0], upper_bound=vals[-1], confidence=1.0
                ))

        # 3. Matrix endpoint invariants (e.g. "grid[0][0] == grid[m-1][n-1] == 0")
        if not matched:
            cleaned_nospace = cleaned.replace(" ", "")
            m_end1 = re.search(r"([a-zA-Z_]\w*)\[0\]\[0\]={1,2}([a-zA-Z_]\w*)\[.*?-1\]\[.*?-1\]={1,2}0", cleaned_nospace)
            m_end2_start = re.search(r"([a-zA-Z_]\w*)\[0\]\[0\]={1,2}0", cleaned_nospace)
            m_end2_end = re.search(r"([a-zA-Z_]\w*)\[.*?-1\]\[.*?-1\]={1,2}0", cleaned_nospace)
            if (m_end1 and m_end1.group(1).lower() == m_end1.group(2).lower()) or (
                m_end2_start and m_end2_end and m_end2_start.group(1).lower() == m_end2_end.group(1).lower()
            ):
                spec.endpoints_zero = True
                for p in known_params:
                    if p in ("grid", "matrix", "board") or is_matrix_problem:
                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                        param_specs[p].endpoints_zero = True
                matched = True
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line, normalized_text=cleaned, constraint_type="ENDPOINTS_INVARIANT", confidence=1.0
                ))

        # 4. Node count range in tree / list: e.g. "The number of nodes in each list is in the range [1, 100]."
        if not matched:
            m_range = re.search(
                r"(?:number\s+of\s+nodes\s+(?:in\s+(?:each\s+|the\s+)?(?:list|tree|linked\s+list)?)?\s*|.*?)\bin\s+the\s+range\s*\[\s*([^,]+?)\s*,\s*([^\]]+?)\s*\]",
                cleaned,
                re.IGNORECASE,
            )
            if m_range:
                low_val = parse_number_expression(m_range.group(1))
                high_val = parse_number_expression(m_range.group(2))
                if low_val is not None and high_val is not None:
                    int_low = int(low_val)
                    int_high = int(high_val)
                    spec.min_length = int_low if spec.min_length is None else min(spec.min_length, int_low)
                    spec.max_length = int_high if spec.max_length is None else max(spec.max_length, int_high)
                    c_lower = cleaned.lower()
                    target_params = []
                    if "list" in c_lower:
                        target_params = [p for p in known_params if p in ("l1", "l2", "head", "list", "nums") or "list" in p]
                        if not target_params: target_params = known_params
                    elif "tree" in c_lower:
                        target_params = [p for p in known_params if p in ("root", "tree", "node")]
                        if not target_params: target_params = known_params
                    else:
                        target_params = known_params

                    for p in target_params:
                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                        param_specs[p].min_length = int_low
                        param_specs[p].max_length = int_high
                        if int_low >= 1:
                            param_specs[p].is_non_empty = True

                    matched = True
                    parsed_constraints.append(ParsedConstraint(
                        raw_text=line, normalized_text=cleaned, constraint_type="RANGE_SYNTAX",
                        lower_bound=int_low, upper_bound=int_high, confidence=1.0
                    ))

        # 5. Chained inequality with alias or length: e.g. "1 <= k <= n <= 10^5", "1 <= k <= nums.length <= 10^5"
        if not matched:
            m_chain4 = re.match(
                r"^\s*([^<=\s]+?)\s*(<=|<|\u2264)\s*([a-zA-Z_]\w*)\s*(<=|<|\u2264)\s*([a-zA-Z_]\w*)\s*(<=|<|\u2264)\s*([^<=\s]+?)\s*$",
                cleaned,
            )
            if m_chain4:
                low_s, op1, mid1, op2, mid2, op3, high_s = m_chain4.groups()
                low_val = parse_number_expression(low_s)
                high_val = parse_number_expression(high_s)
                if low_val is not None and high_val is not None:
                    if op1 == "<": low_val += 1
                    if op3 == "<": high_val -= 1
                    mid1_low = mid1.lower()
                    mid2_low = mid2.lower()
                    arr_target = length_aliases.get(mid2_low, mid2_low)
                    matched = True

                    # mid1 is scalar bound (e.g. k)
                    if mid1_low not in param_specs: param_specs[mid1_low] = ParamConstraintSpec(name=mid1_low)
                    param_specs[mid1_low].min_value = int(low_val)
                    param_specs[mid1_low].max_value = int(high_val)

                    # arr_target is array length bound (e.g. nums)
                    if arr_target not in param_specs: param_specs[arr_target] = ParamConstraintSpec(name=arr_target)
                    param_specs[arr_target].min_length = int(low_val)
                    param_specs[arr_target].max_length = int(high_val)
                    spec.min_length = int(low_val) if spec.min_length is None else min(spec.min_length, int(low_val))
                    spec.max_length = int(high_val) if spec.max_length is None else max(spec.max_length, int(high_val))

                    cross_constraints.append(CrossParameterConstraint(
                        name="WINDOW_LEQ_ARRAY_LENGTH",
                        description=f"Parameter '{mid1_low}' must not exceed length of '{arr_target}' ({low_s} <= {mid1_low} <= len({arr_target}))",
                        parameters_involved=[mid1_low, arr_target],
                        relation_type="LEQ_LENGTH",
                        expression=f"{mid1_low} <= len({arr_target})"
                    ))
                    parsed_constraints.append(ParsedConstraint(
                        raw_text=line, normalized_text=cleaned, constraint_type="CHAINED_INEQUALITY",
                        lower_bound=int(low_val), upper_bound=int(high_val), confidence=1.0
                    ))

        # 6. Multi-variable length/value: e.g. "1 <= s.length, t.length <= 5 * 10^4", "-10^4 < nums[i], target < 10^4", "1 <= m, n <= 200"
        if not matched:
            m_multi = re.match(
                r"^\s*([^<=\s]+?)\s*(<=|<|\u2264)\s*([a-zA-Z0-9_.,\s\[\]]+?)\s*(<=|<|\u2264)\s*([^<=\s]+?)\s*$",
                cleaned,
            )
            if m_multi:
                low_s, op1, mid_expr, op2, high_s = m_multi.groups()
                low_val = parse_number_expression(low_s)
                high_val = parse_number_expression(high_s)
                if low_val is not None and high_val is not None:
                    if op1 == "<": low_val += 1
                    if op2 == "<": high_val -= 1
                    mid_tokens = [t.strip().lower() for t in mid_expr.split(",") if t.strip()]

                    # Check if this is "1 <= m, n <= 200" in matrix problem
                    if is_matrix_problem and all(v in row_vars or v in col_vars or v in ("m", "n", "r", "c", "rows", "cols") for v in mid_tokens):
                        int_low = int(low_val)
                        int_high = int(high_val)
                        spec.min_rows = max(spec.min_rows, int_low) if spec.min_rows is not None else int_low
                        spec.max_rows = min(spec.max_rows, int_high) if spec.max_rows is not None else int_high
                        spec.min_cols = max(spec.min_cols, int_low) if spec.min_cols is not None else int_low
                        spec.max_cols = min(spec.max_cols, int_high) if spec.max_cols is not None else int_high
                        spec.min_length = max(spec.min_length, int_low) if spec.min_length is not None else int_low
                        spec.max_length = min(spec.max_length, int_high) if spec.max_length is not None else int_high
                        for p in known_params:
                            if p in ("matrix", "grid", "board") or is_matrix_problem:
                                if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                param_specs[p].min_rows = int_low
                                param_specs[p].max_rows = int_high
                                param_specs[p].min_cols = int_low
                                param_specs[p].max_cols = int_high
                        matched = True
                        parsed_constraints.append(ParsedConstraint(
                            raw_text=line, normalized_text=cleaned, constraint_type="MATRIX_DIMENSIONS",
                            lower_bound=int_low, upper_bound=int_high, confidence=1.0
                        ))
                    elif len(mid_tokens) > 1:
                        matched = True
                        for token in mid_tokens:
                            if any(token.endswith(sfx) for sfx in (".length", ".size")):
                                p = token.split(".")[0].strip()
                                if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                param_specs[p].min_length = int(low_val)
                                param_specs[p].max_length = int(high_val)
                                spec.min_length = int(low_val) if spec.min_length is None else min(spec.min_length, int(low_val))
                                spec.max_length = int(high_val) if spec.max_length is None else max(spec.max_length, int(high_val))
                            elif "[" in token:
                                p = token.split("[")[0].strip()
                                if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                param_specs[p].min_value = low_val
                                param_specs[p].max_value = high_val
                                spec.min_value = low_val if spec.min_value is None else min(spec.min_value, low_val)
                                spec.max_value = high_val if spec.max_value is None else max(spec.max_value, high_val)
                            else:
                                p = token
                                if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                param_specs[p].min_value = low_val
                                param_specs[p].max_value = high_val
                                spec.min_value = low_val if spec.min_value is None else min(spec.min_value, low_val)
                                spec.max_value = high_val if spec.max_value is None else max(spec.max_value, high_val)
                        parsed_constraints.append(ParsedConstraint(
                            raw_text=line, normalized_text=cleaned, constraint_type="MULTI_VARIABLE_INEQUALITY",
                            lower_bound=low_val, upper_bound=high_val, confidence=1.0
                        ))

        # 7. Standard double inequality: LOW <= EXPR <= HIGH
        if not matched:
            m_double = double_ineq_pattern.match(cleaned)
            if m_double:
                low_str, op1, expr, op2, high_str = m_double.groups()
                low_val = parse_number_expression(low_str)
                high_val = parse_number_expression(high_str)

                if low_val is not None and high_val is not None:
                    if op1 in ("<", "\u2264") and op1 == "<":
                        low_val = low_val + 1
                    if op2 in ("<", "\u2264") and op2 == "<":
                        high_val = high_val - 1

                    expr_clean = expr.strip()
                    expr_lower = expr_clean.lower()

                    # Matrix dimensions (m, n in matrix context only)
                    var_parts = [p.strip().lower() for p in re.split(r"[,;\s]+|\band\b", expr_lower) if p.strip()]
                    if is_matrix_problem and any(v in row_vars for v in var_parts):
                        int_low = int(low_val)
                        int_high = int(high_val)
                        spec.min_rows = max(spec.min_rows, int_low) if spec.min_rows is not None else int_low
                        spec.max_rows = min(spec.max_rows, int_high) if spec.max_rows is not None else int_high
                        spec.min_length = max(spec.min_length, int_low) if spec.min_length is not None else int_low
                        spec.max_length = min(spec.max_length, int_high) if spec.max_length is not None else int_high
                        matched = True
                    elif is_matrix_problem and any(v in col_vars for v in var_parts):
                        int_low = int(low_val)
                        int_high = int(high_val)
                        spec.min_cols = max(spec.min_cols, int_low) if spec.min_cols is not None else int_low
                        spec.max_cols = min(spec.max_cols, int_high) if spec.max_cols is not None else int_high
                        matched = True
                    else:
                        is_length = any(ind in expr_lower for ind in length_indicators) or (
                            expr_lower in ("length", "len")
                        )
                        if is_length:
                            int_low = int(low_val)
                            int_high = int(high_val)
                            spec.min_length = (
                                max(spec.min_length, int_low) if spec.min_length is not None else int_low
                            )
                            spec.max_length = (
                                min(spec.max_length, int_high) if spec.max_length is not None else int_high
                            )
                            for p in known_params:
                                if p in expr_lower:
                                    if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                    param_specs[p].min_length = int_low
                                    param_specs[p].max_length = int_high
                                    if int_low >= 1: param_specs[p].is_non_empty = True
                            matched = True
                        else:
                            is_elem = any(ind in expr_lower for ind in ("[i]", "[j]", "[k]", "node.val", "val"))
                            matched_param = None
                            for p in known_params:
                                if p in expr_lower:
                                    matched_param = p
                                    break

                            if is_elem:
                                spec.min_value = low_val
                                spec.max_value = high_val
                            elif not is_matrix_problem and spec.min_value is None:
                                spec.min_value = low_val
                                spec.max_value = high_val

                            if matched_param:
                                if matched_param not in param_specs: param_specs[matched_param] = ParamConstraintSpec(name=matched_param)
                                param_specs[matched_param].min_value = low_val
                                param_specs[matched_param].max_value = high_val

                            matched = True

                    parsed_constraints.append(ParsedConstraint(
                        raw_text=line, normalized_text=cleaned, constraint_type="DOUBLE_INEQUALITY",
                        lower_bound=low_val, upper_bound=high_val, confidence=1.0
                    ))

        # 8. Single inequality patterns: handles both "EXPR op BOUND" and "BOUND op EXPR"
        if not matched:
            m_single = single_ineq_pattern.match(cleaned)
            if m_single:
                left_str, op, right_str = m_single.groups()
                val_right = parse_number_expression(right_str)
                val_left = parse_number_expression(left_str)

                # Case A: left is variable, right is number (e.g. nums.length <= 10^4)
                if val_right is not None and val_left is None:
                    expr_lower = left_str.strip().lower()
                    var_parts = [p.strip().lower() for p in re.split(r"[,;\s]+|\band\b", expr_lower) if p.strip()]
                    if is_matrix_problem and (any(v in row_vars for v in var_parts) or any(v in col_vars for v in var_parts)):
                        bound = val_right
                        if op in (">=", ">"):
                            b = int(bound + 1) if op == ">" else int(bound)
                            if any(v in row_vars for v in var_parts):
                                spec.min_rows = max(spec.min_rows, b) if spec.min_rows is not None else b
                                spec.min_length = max(spec.min_length, b) if spec.min_length is not None else b
                            if any(v in col_vars for v in var_parts):
                                spec.min_cols = max(spec.min_cols, b) if spec.min_cols is not None else b
                            matched = True
                        elif op in ("<=", "<"):
                            b = int(bound - 1) if op == "<" else int(bound)
                            if any(v in row_vars for v in var_parts):
                                spec.max_rows = min(spec.max_rows, b) if spec.max_rows is not None else b
                                spec.max_length = min(spec.max_length, b) if spec.max_length is not None else b
                            if any(v in col_vars for v in var_parts):
                                spec.max_cols = min(spec.max_cols, b) if spec.max_cols is not None else b
                            matched = True
                    else:
                        is_length = any(ind in expr_lower for ind in length_indicators) or (
                            expr_lower in ("length", "len")
                        )
                        bound = val_right
                        if op in (">=", ">"):
                            b = int(bound + 1) if (op == ">" and is_length) else (bound if op == ">=" else bound + 1)
                            if is_length:
                                spec.min_length = (
                                    max(spec.min_length, int(b)) if spec.min_length is not None else int(b)
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].min_length = int(b)
                                matched = True
                            else:
                                spec.min_value = (
                                    max(spec.min_value, b) if spec.min_value is not None else b
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].min_value = b
                                matched = True
                        elif op in ("<=", "<"):
                            b = int(bound - 1) if (op == "<" and is_length) else (bound if op == "<=" else bound - 1)
                            if is_length:
                                spec.max_length = (
                                    min(spec.max_length, int(b)) if spec.max_length is not None else int(b)
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].max_length = int(b)
                                matched = True
                            else:
                                spec.max_value = (
                                    min(spec.max_value, b) if spec.max_value is not None else b
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].max_value = b
                                matched = True

                # Case B: left is number, right is variable (e.g. 2 <= nums.length)
                elif val_left is not None and val_right is None:
                    expr_lower = right_str.strip().lower()
                    var_parts = [p.strip().lower() for p in re.split(r"[,;\s]+|\band\b", expr_lower) if p.strip()]
                    if is_matrix_problem and (any(v in row_vars for v in var_parts) or any(v in col_vars for v in var_parts)):
                        bound = val_left
                        if op in ("<=", "<"):
                            b = int(bound + 1) if op == "<" else int(bound)
                            if any(v in row_vars for v in var_parts):
                                spec.min_rows = max(spec.min_rows, b) if spec.min_rows is not None else b
                                spec.min_length = max(spec.min_length, b) if spec.min_length is not None else b
                            if any(v in col_vars for v in var_parts):
                                spec.min_cols = max(spec.min_cols, b) if spec.min_cols is not None else b
                            matched = True
                        elif op in (">=", ">"):
                            b = int(bound - 1) if op == ">" else int(bound)
                            if any(v in row_vars for v in var_parts):
                                spec.max_rows = min(spec.max_rows, b) if spec.max_rows is not None else b
                                spec.max_length = min(spec.max_length, b) if spec.max_length is not None else b
                            if any(v in col_vars for v in var_parts):
                                spec.max_cols = min(spec.max_cols, b) if spec.max_cols is not None else b
                            matched = True
                    else:
                        is_length = any(ind in expr_lower for ind in length_indicators) or (
                            expr_lower in ("length", "len")
                        )
                        bound = val_left
                        if op in ("<=", "<"):
                            b = int(bound + 1) if (op == "<" and is_length) else (bound if op == "<=" else bound + 1)
                            if is_length:
                                spec.min_length = (
                                    max(spec.min_length, int(b)) if spec.min_length is not None else int(b)
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].min_length = int(b)
                                matched = True
                            else:
                                spec.min_value = (
                                    max(spec.min_value, b) if spec.min_value is not None else b
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].min_value = b
                                matched = True
                        elif op in (">=", ">"):
                            b = int(bound - 1) if (op == ">" and is_length) else (bound if op == ">=" else bound - 1)
                            if is_length:
                                spec.max_length = (
                                    min(spec.max_length, int(b)) if spec.max_length is not None else int(b)
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].max_length = int(b)
                                matched = True
                            else:
                                spec.max_value = (
                                    min(spec.max_value, b) if spec.max_value is not None else b
                                )
                                for p in known_params:
                                    if p in expr_lower:
                                        if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                                        param_specs[p].max_value = b
                                matched = True

        # 9. Character sets & Parentheses
        if not matched:
            line_lower = cleaned.lower()
            m_paren = re.search(r'consists\s+of\s+parentheses\s+only\s*[\'"]([^\'"]+)[\'"]', cleaned, re.IGNORECASE)
            if m_paren:
                chars = m_paren.group(1)
                spec.allowed_characters = chars
                for p in known_params:
                    if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                    param_specs[p].allowed_characters = chars
                matched = True
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line, normalized_text=cleaned, constraint_type="CHARACTER_SET", confidence=1.0
                ))
            elif "lowercase english letter" in line_lower:
                spec.allowed_characters = "a-z"
                for p in known_params:
                    if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                    param_specs[p].allowed_characters = "a-z"
                matched = True
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line, normalized_text=cleaned, constraint_type="CHARACTER_SET", confidence=1.0
                ))
            elif "english letters, digits, symbols and spaces" in line_lower:
                spec.allowed_characters = "ascii_printable"
                matched = True
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line, normalized_text=cleaned, constraint_type="CHARACTER_SET", confidence=1.0
                ))

        # 10. Sortedness and Uniqueness
        if not matched:
            m_dist_sort = re.search(r"([a-zA-Z_]\w*)\s+contains\s+distinct\s+values\s+sorted\s+in\s+ascending\s+order", cleaned, re.IGNORECASE)
            if m_dist_sort:
                p_name = m_dist_sort.group(1).lower()
                spec.is_sorted_ascending = True
                spec.unique_elements = True
                spec.is_strictly_increasing = True
                spec.sorted_param = p_name
                if p_name not in param_specs: param_specs[p_name] = ParamConstraintSpec(name=p_name)
                param_specs[p_name].is_sorted_ascending = True
                param_specs[p_name].unique_elements = True
                param_specs[p_name].is_strictly_increasing = True
                matched = True
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line, normalized_text=cleaned, parameter_name=p_name, constraint_type="SORTED_UNIQUE", confidence=1.0
                ))
            else:
                m_sorted = re.search(
                    r"\b([a-zA-Z_]\w*)\s+is\s+sorted(?:\s+in\s+(strictly\s+increasing|strictly\s+ascending|non[- ]decreasing|ascending|descending)\s+order)?\b",
                    cleaned,
                    re.IGNORECASE,
                )
                if m_sorted:
                    p_name = m_sorted.group(1).lower()
                    order_type = (m_sorted.group(2) or "ascending").lower()
                    if "descending" not in order_type:
                        spec.is_sorted_ascending = True
                        spec.sorted_param = p_name
                        if p_name not in param_specs: param_specs[p_name] = ParamConstraintSpec(name=p_name)
                        param_specs[p_name].is_sorted_ascending = True
                        if "strictly" in order_type:
                            spec.is_strictly_increasing = True
                            param_specs[p_name].is_strictly_increasing = True
                        matched = True
                        parsed_constraints.append(ParsedConstraint(
                            raw_text=line, normalized_text=cleaned, parameter_name=p_name, constraint_type="SORTEDNESS", confidence=1.0
                        ))

                m_unique = re.search(
                    r"\ball\s+(?:the\s+)?(?:integers|elements|values|numbers)?\s*(?:in|of)\s+([a-zA-Z_]\w*)\s+are\s+unique\b",
                    cleaned,
                    re.IGNORECASE,
                )
                if m_unique:
                    p_name = m_unique.group(1).lower()
                    spec.unique_elements = True
                    spec.sorted_param = spec.sorted_param or p_name
                    if p_name not in param_specs: param_specs[p_name] = ParamConstraintSpec(name=p_name)
                    param_specs[p_name].unique_elements = True
                    if spec.is_sorted_ascending:
                        spec.is_strictly_increasing = True
                        param_specs[p_name].is_strictly_increasing = True
                    matched = True
                    parsed_constraints.append(ParsedConstraint(
                        raw_text=line, normalized_text=cleaned, parameter_name=p_name, constraint_type="UNIQUENESS", confidence=1.0
                    ))

        # 11. Leading zeros invariant
        if not matched:
            if "does not have leading zeros" in cleaned.lower() or "no leading zero" in cleaned.lower():
                matched = True
                spec.no_leading_zero = True
                for p in known_params:
                    if p not in param_specs: param_specs[p] = ParamConstraintSpec(name=p)
                    param_specs[p].no_leading_zero = True
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line, normalized_text=cleaned, constraint_type="NO_LEADING_ZEROS", confidence=1.0
                ))

        # 12. Informational guarantees (Two sum single answer, etc.)
        if not matched:
            c_low = cleaned.lower()
            if any(cue in c_low for cue in ("only one valid answer exists", "exactly one solution", "may not use the same element twice")):
                matched = True
                unresolved.append(line)
                spec.unresolved_reasons[line] = "Problem-level semantic constraint: guarantee_type='unique_solution', scope='global'."
                cross_constraints.append(CrossParameterConstraint(
                    name="EXACTLY_ONE_VALID_PAIR",
                    description="Problem guarantees exactly one pair formed by distinct indices satisfies target.",
                    parameters_involved=known_params,
                    relation_type="PAIR_SUM",
                    expression="unique_solution",
                    is_enforceable=True
                ))
                parsed_constraints.append(ParsedConstraint(
                    raw_text=line,
                    normalized_text=cleaned,
                    constraint_type="PROBLEM_GUARANTEE",
                    is_unresolved=True,
                    unresolved_reason="Problem-level semantic constraint: guarantee_type='unique_solution', scope='global'.",
                    confidence=1.0
                ))

        if not matched:
            unresolved.append(line)
            unresolved_reasons[line] = f"Constraint '{cleaned}' could not be deterministically parsed into supported numerical or relational bounds."

    if spec.is_sorted_ascending and spec.unique_elements:
        spec.is_strictly_increasing = True

    spec.param_specs = param_specs
    spec.cross_constraints = cross_constraints
    spec.parsed_constraints = parsed_constraints
    spec.unresolved_reasons = unresolved_reasons

    return spec, unresolved


def is_two_sum_context(
    context: Optional[Any] = None,
    relational_metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Deterministically check whether context or metadata specifies Two Sum problem semantics.
    Does NOT infer Two Sum solely from parameter names.
    Requires explicit problem context or reliable relationship metadata.
    """
    if relational_metadata and isinstance(relational_metadata, dict):
        rel_type = str(
            relational_metadata.get("relation_type")
            or relational_metadata.get("semantic_rule")
            or relational_metadata.get("relationship")
            or ""
        ).strip().upper()
        if rel_type in ("TWO_SUM", "PAIR_SUM", "EXACTLY_ONE_PAIR_SUM"):
            return True

    if context:
        title = (getattr(context, "title", None) or "").strip().lower()
        if any(kw in title for kw in ("two sum", "2 sum")):
            return True

        prob_id = (getattr(context, "problem_id", None) or "").strip().lower()
        if prob_id in ("two-sum", "two_sum", "1") or re.search(r"\btwo[-_]sum\b", prob_id):
            return True

        fn = (getattr(context, "function_name", None) or "").strip().lower()
        if fn in ("twosum", "two_sum"):
            return True

        desc = (getattr(context, "description", None) or "").strip().lower()
        has_sum_cue = any(c in desc for c in ("add up to", "sum to", "sum of two numbers", "two numbers such that they add up"))
        has_unique_cue = any(c in desc for c in ("exactly one", "only one valid answer", "may not use the same element twice", "cannot use the same element twice"))
        if has_sum_cue and has_unique_cue:
            return True

    return False


from collections import deque


def validate_and_analyze_tree(arr: Any) -> Tuple[bool, int, int, int, str]:
    """
    Validates a level-order serialized binary tree representation and computes metrics:
    - Distinguishes actual non-null nodes, serialized length, and maximum tree depth.
    - Validates tree serialization ensuring null placeholders do not have children.
    Returns:
        (is_valid, num_actual_nodes, serialized_length, max_depth, error_msg)
    """
    if arr is None or arr == []:
        return (True, 0, 0, 0, "")

    if not isinstance(arr, (list, tuple)):
        return (False, 0, 0, 0, "Tree serialization must be a list or tuple.")

    if not arr:
        return (True, 0, 0, 0, "")

    if arr[0] is None:
        return (False, 0, len(arr), 0, "Root node of a non-empty tree cannot be null/None.")

    actual_nodes = sum(1 for x in arr if x is not None)
    serialized_len = len(arr)

    queue = deque([(arr[0], 1)])
    idx = 1
    max_d = 1

    while queue and idx < len(arr):
        node, depth = queue.popleft()
        max_d = max(max_d, depth)

        # Left child
        if idx < len(arr):
            left_val = arr[idx]
            idx += 1
            if left_val is not None:
                queue.append((left_val, depth + 1))
                max_d = max(max_d, depth + 1)

        # Right child
        if idx < len(arr):
            right_val = arr[idx]
            idx += 1
            if right_val is not None:
                queue.append((right_val, depth + 1))
                max_d = max(max_d, depth + 1)

    if idx < len(arr):
        return (False, actual_nodes, serialized_len, max_d, f"Malformed tree serialization: {len(arr) - idx} extra orphan elements after tree was exhausted.")

    return (True, actual_nodes, serialized_len, max_d, "")


def count_valid_pairs(
    nums: Any,
    target: Any,
    max_elements_to_scan: int = 20000,
) -> int:
    """
    Deterministically count the number of distinct-index pairs (i < j)
    where nums[i] + nums[j] == target.
    Uses an O(N) frequency-hash approach without executing user code.
    """
    if not isinstance(nums, (list, tuple)):
        return -1
    if len(nums) < 2 or len(nums) > max_elements_to_scan:
        return 0
    if not isinstance(target, (int, float)) or isinstance(target, bool):
        return -1

    seen_counts: Dict[Union[int, float], int] = {}
    pair_count = 0

    for val in nums:
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            return -1
        complement = target - val
        pair_count += seen_counts.get(complement, 0)
        seen_counts[val] = seen_counts.get(val, 0) + 1

    return pair_count


def classify_candidate(
    candidate: TestCase,
    spec: Optional[ConstraintSpec],
    has_supplied_constraints: bool = True,
    context: Optional[Any] = None,
    relational_metadata: Optional[Dict[str, Any]] = None,
    unresolved_constraints: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """
    Classify a candidate test case against problem constraints and cross-parameter invariants:
    - VALID: satisfies all supported supplied constraints AND cross-parameter relationships.
    - ROBUSTNESS PROBE: deliberately violates a known constraint.
    - CONSTRAINT VALIDITY UNKNOWN: insufficient information to determine validity.
    """
    # If no constraints were supplied or spec has no fields
    if not has_supplied_constraints or spec is None:
        return (
            CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
            "No verified constraint specification available to determine validity.",
        )

    has_any_bound = (
        spec.min_length is not None
        or spec.max_length is not None
        or spec.min_value is not None
        or spec.max_value is not None
        or spec.allowed_characters is not None
        or spec.min_rows is not None
        or spec.max_rows is not None
        or spec.min_cols is not None
        or spec.max_cols is not None
        or spec.allowed_values is not None
        or spec.endpoints_zero
        or spec.is_sorted_ascending
        or spec.unique_elements
        or bool(spec.param_specs)
    )

    if not has_any_bound:
        return (
            CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
            "Supplied constraints did not specify supported machine-readable bounds.",
        )

    input_data = candidate.input_data or {}
    checked_at_least_one = False

    # 1. Evaluate per-parameter constraints
    for param_name, val in input_data.items():
        p_name_lower = param_name.lower()
        p_spec = spec.param_specs.get(p_name_lower) if spec.param_specs else None

        # Resolve effective bounds for this parameter
        eff_min_len = p_spec.min_length if (p_spec and p_spec.min_length is not None) else spec.min_length
        eff_max_len = p_spec.max_length if (p_spec and p_spec.max_length is not None) else spec.max_length
        eff_min_val = p_spec.min_value if (p_spec and p_spec.min_value is not None) else spec.min_value
        eff_max_val = p_spec.max_value if (p_spec and p_spec.max_value is not None) else spec.max_value
        eff_chars = p_spec.allowed_characters if (p_spec and p_spec.allowed_characters) else spec.allowed_characters
        eff_vals = p_spec.allowed_values if (p_spec and p_spec.allowed_values is not None) else spec.allowed_values
        eff_is_non_empty = p_spec.is_non_empty if (p_spec and p_spec.is_non_empty) else (eff_min_len is not None and eff_min_len >= 1)
        eff_no_leading_zero = p_spec.no_leading_zero if p_spec else getattr(spec, "no_leading_zero", False)
        eff_endpoints_zero = p_spec.endpoints_zero if p_spec else spec.endpoints_zero
        eff_sorted = p_spec.is_sorted_ascending if p_spec else spec.is_sorted_ascending
        eff_strictly_inc = p_spec.is_strictly_increasing if p_spec else spec.is_strictly_increasing
        eff_unique = p_spec.unique_elements if p_spec else spec.unique_elements

        # Check 2D Matrix structures
        if isinstance(val, (list, tuple)) and (val and all(isinstance(r, (list, tuple)) for r in val)):
            num_rows = len(val)
            eff_min_rows = (p_spec.min_rows if p_spec and p_spec.min_rows is not None else spec.min_rows) or eff_min_len
            eff_max_rows = (p_spec.max_rows if p_spec and p_spec.max_rows is not None else spec.max_rows) or eff_max_len

            if eff_min_rows is not None:
                checked_at_least_one = True
                if num_rows < eff_min_rows:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates minimum rows constraint for '{param_name}' ({num_rows} < {eff_min_rows}). Deliberate robustness probe.",
                    )
            if eff_max_rows is not None:
                checked_at_least_one = True
                if num_rows > eff_max_rows:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates maximum rows constraint for '{param_name}' ({num_rows} > {eff_max_rows}). Deliberate robustness probe.",
                    )

            eff_min_cols = (p_spec.min_cols if p_spec and p_spec.min_cols is not None else spec.min_cols)
            eff_max_cols = (p_spec.max_cols if p_spec and p_spec.max_cols is not None else spec.max_cols)

            for r_idx, row in enumerate(val):
                if isinstance(row, (list, tuple)):
                    num_cols = len(row)
                    if eff_min_cols is not None:
                        checked_at_least_one = True
                        if num_cols < eff_min_cols:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Violates minimum columns constraint for '{param_name}' row {r_idx} ({num_cols} < {eff_min_cols}). Deliberate robustness probe.",
                            )
                    if eff_max_cols is not None:
                        checked_at_least_one = True
                        if num_cols > eff_max_cols:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Violates maximum columns constraint for '{param_name}' row {r_idx} ({num_cols} > {eff_max_cols}). Deliberate robustness probe.",
                            )

                    for c_idx, cell in enumerate(row):
                        if isinstance(cell, (int, float)) and not isinstance(cell, bool):
                            if eff_vals is not None:
                                checked_at_least_one = True
                                if cell not in eff_vals:
                                    return (
                                        CandidateClassification.ROBUSTNESS_PROBE.value,
                                        f"Contains cell {cell} at [{r_idx}][{c_idx}] outside allowed values {eff_vals}. Deliberate robustness probe.",
                                    )
                            if eff_min_val is not None:
                                checked_at_least_one = True
                                if cell < eff_min_val:
                                    return (
                                        CandidateClassification.ROBUSTNESS_PROBE.value,
                                        f"Contains cell {cell} at [{r_idx}][{c_idx}] below minimum value constraint ({eff_min_val}). Deliberate robustness probe.",
                                    )
                            if eff_max_val is not None:
                                checked_at_least_one = True
                                if cell > eff_max_val:
                                    return (
                                        CandidateClassification.ROBUSTNESS_PROBE.value,
                                        f"Contains cell {cell} at [{r_idx}][{c_idx}] above maximum value constraint ({eff_max_val}). Deliberate robustness probe.",
                                    )

            # Endpoints invariant
            if eff_endpoints_zero:
                checked_at_least_one = True
                if num_rows >= 1 and len(val[0]) >= 1 and len(val[-1]) >= 1:
                    if val[0][0] != 0 or val[-1][-1] != 0:
                        return (
                            CandidateClassification.ROBUSTNESS_PROBE.value,
                            "Violates required endpoint invariant: grid[0][0] and grid[m-1][n-1] must be 0. Deliberate robustness probe.",
                        )
                else:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        "Violates required endpoint invariant due to empty or insufficient matrix dimensions. Deliberate robustness probe.",
                    )

        # Check Tree parameters
        elif p_name_lower in ("root", "tree", "rootnode") or (context and "tree" in getattr(context, "title", "").lower()):
            checked_at_least_one = True
            is_v_tree, n_act, s_len, m_dep, err_tree = validate_and_analyze_tree(val)
            if not is_v_tree:
                return (
                    CandidateClassification.ROBUSTNESS_PROBE.value,
                    f"Violates tree serialization structural validity for '{param_name}': {err_tree}. Deliberate robustness probe.",
                )
            if eff_max_len is not None and n_act > eff_max_len:
                return (
                    CandidateClassification.ROBUSTNESS_PROBE.value,
                    f"Violates tree node capacity for '{param_name}': {n_act} nodes exceeds maximum permitted ({eff_max_len}). Deliberate robustness probe.",
                )
            if eff_min_len is not None and n_act < eff_min_len:
                return (
                    CandidateClassification.ROBUSTNESS_PROBE.value,
                    f"Violates minimum tree nodes constraint for '{param_name}' ({n_act} < {eff_min_len}). Deliberate robustness probe.",
                )
            if isinstance(val, (list, tuple)):
                for idx, item in enumerate(val):
                    if item is not None and isinstance(item, (int, float)) and not isinstance(item, bool):
                        if eff_min_val is not None and item < eff_min_val:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Contains tree node value {item} at index {idx} below minimum value constraint ({eff_min_val}). Deliberate robustness probe.",
                            )
                        if eff_max_val is not None and item > eff_max_val:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Contains tree node value {item} at index {idx} above maximum value constraint ({eff_max_val}). Deliberate robustness probe.",
                            )

        # Check empty collection
        elif (isinstance(val, (list, tuple)) and len(val) == 0) or val is None:
            checked_at_least_one = True
            if eff_is_non_empty or (eff_min_len is not None and eff_min_len > 0):
                return (
                    CandidateClassification.ROBUSTNESS_PROBE.value,
                    f"Violates minimum length/rows constraint for '{param_name}' (0 < {eff_min_len or 1}). Deliberate robustness probe.",
                )

        # Check 1D collection length
        elif isinstance(val, (list, tuple, str, dict, set)):
            length = len(val)
            if eff_min_len is not None:
                checked_at_least_one = True
                if length < eff_min_len:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates minimum length constraint for '{param_name}' ({length} < {eff_min_len}). Deliberate robustness probe.",
                    )
            if eff_max_len is not None:
                checked_at_least_one = True
                if length > eff_max_len:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates maximum length constraint for '{param_name}' ({length} > {eff_max_len}). Deliberate robustness probe.",
                    )

        # Check numeric scalar values
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            if eff_min_val is not None:
                checked_at_least_one = True
                if val < eff_min_val:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates minimum value constraint for '{param_name}' ({val} < {eff_min_val}). Deliberate robustness probe.",
                    )
            if eff_max_val is not None:
                checked_at_least_one = True
                if val > eff_max_val:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates maximum value constraint for '{param_name}' ({val} > {eff_max_val}). Deliberate robustness probe.",
                    )

        # Check numeric elements inside 1D collection
        if isinstance(val, (list, tuple)) and not (val and isinstance(val[0], (list, tuple))):
            for idx, item in enumerate(val):
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    if eff_min_val is not None:
                        checked_at_least_one = True
                        if item < eff_min_val:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Contains element {item} at index {idx} below minimum value constraint ({eff_min_val}). Deliberate robustness probe.",
                            )
                    if eff_max_val is not None:
                        checked_at_least_one = True
                        if item > eff_max_val:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Contains element {item} at index {idx} above maximum value constraint ({eff_max_val}). Deliberate robustness probe.",
                            )

            # Check leading zeros on list/number
            if eff_no_leading_zero and len(val) > 1:
                checked_at_least_one = True
                if val[0] == 0:
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"Violates problem constraint: '{param_name}' must not have leading zeros when length > 1. Deliberate robustness probe.",
                    )

        # Check allowed characters in string
        if isinstance(val, str) and eff_chars:
            checked_at_least_one = True
            if eff_chars == "a-z":
                if not all("a" <= ch <= "z" for ch in val):
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"String '{param_name}' contains characters outside allowed lowercase English alphabet (a-z). Deliberate robustness probe.",
                    )
            elif eff_chars == "A-Z":
                if not all("A" <= ch <= "Z" for ch in val):
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"String '{param_name}' contains characters outside allowed uppercase English alphabet (A-Z). Deliberate robustness probe.",
                    )
            elif eff_chars in ("()[]{}", "'()[]{}'"):
                valid_chars = set("()[]{}")
                if not all(ch in valid_chars for ch in val):
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        f"String '{param_name}' contains characters outside allowed parentheses set '()[]{{}}'. Deliberate robustness probe.",
                    )

        # Check sortedness constraints on 1D collections
        if eff_sorted and isinstance(val, (list, tuple)) and not (val and isinstance(val[0], (list, tuple))):
            if spec.sorted_param is None or spec.sorted_param == p_name_lower or (p_spec and p_spec.is_sorted_ascending):
                checked_at_least_one = True
                if len(val) >= 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in val):
                    if eff_strictly_inc:
                        for idx in range(len(val) - 1):
                            if val[idx] >= val[idx + 1]:
                                return (
                                    CandidateClassification.ROBUSTNESS_PROBE.value,
                                    f"Violates problem constraint: '{param_name}' must be sorted in strictly increasing order (element at index {idx} >= index {idx+1}). Deliberate robustness probe.",
                                )
                    else:
                        for idx in range(len(val) - 1):
                            if val[idx] > val[idx + 1]:
                                return (
                                    CandidateClassification.ROBUSTNESS_PROBE.value,
                                    f"Violates problem constraint: '{param_name}' must be sorted in ascending order (element at index {idx} > index {idx+1}). Deliberate robustness probe.",
                                )

        # Check unique elements constraint on 1D collections
        if eff_unique and isinstance(val, (list, tuple)) and not (val and isinstance(val[0], (list, tuple))):
            if spec.sorted_param is None or spec.sorted_param == p_name_lower or (p_spec and p_spec.unique_elements):
                checked_at_least_one = True
                if len(val) >= 2:
                    seen = set()
                    for x in val:
                        if x in seen:
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Violates problem constraint: elements in '{param_name}' must be unique. Deliberate robustness probe.",
                            )
                        seen.add(x)

    # 2. Check cross-parameter constraints
    if "k" in input_data and "nums" in input_data:
        k_val = input_data["k"]
        nums_val = input_data["nums"]
        if isinstance(k_val, (int, float)) and not isinstance(k_val, bool) and isinstance(nums_val, (list, tuple, str)):
            checked_at_least_one = True
            if k_val > len(nums_val):
                return (
                    CandidateClassification.ROBUSTNESS_PROBE.value,
                    f"Violates cross-parameter constraint: window 'k' ({k_val}) exceeds array length ({len(nums_val)}). Deliberate robustness probe.",
                )

    if spec.cross_constraints:
        for cc in spec.cross_constraints:
            if cc.relation_type in ("LEQ_LENGTH", "WINDOW_LEQ_ARRAY_LENGTH") and len(cc.parameters_involved) >= 2:
                p_scalar = cc.parameters_involved[0]
                p_arr = cc.parameters_involved[1]
                if p_scalar in input_data and p_arr in input_data:
                    s_val = input_data[p_scalar]
                    a_val = input_data[p_arr]
                    if isinstance(s_val, (int, float)) and isinstance(a_val, (list, tuple, str)):
                        checked_at_least_one = True
                        if s_val > len(a_val):
                            return (
                                CandidateClassification.ROBUSTNESS_PROBE.value,
                                f"Violates cross-parameter constraint: '{p_scalar}' ({s_val}) exceeds length of '{p_arr}' ({len(a_val)}). Deliberate robustness probe.",
                            )

    # 3. Two Sum semantic validity check
    if is_two_sum_context(context, relational_metadata):
        col_param = None
        target_param = None
        if relational_metadata and isinstance(relational_metadata, dict):
            col_param = relational_metadata.get("collection_param")
            target_param = relational_metadata.get("target_param")

        if not col_param or not target_param:
            for p, v in input_data.items():
                if isinstance(v, (list, tuple)) and col_param is None:
                    col_param = p
                elif isinstance(v, (int, float)) and not isinstance(v, bool) and target_param is None:
                    target_param = p

        if col_param in input_data and target_param in input_data:
            pairs = count_valid_pairs(input_data[col_param], input_data[target_param])
            if pairs == 1:
                return (
                    CandidateClassification.VALID.value,
                    "Satisfies all supported supplied problem constraints and contains exactly one valid pair summing to target.",
                )
            elif pairs == 0:
                if str(getattr(candidate, "target_gap", "")) in ("TARGET_NOT_FOUND", "GapCategory.TARGET_NOT_FOUND"):
                    return (
                        CandidateClassification.ROBUSTNESS_PROBE.value,
                        "Violates problem logical invariant: no pair in collection sums to target. Deliberate robustness probe.",
                    )
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    "Violates problem logical invariant: no pair in collection sums to target.",
                )
            else:
                return (
                    CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
                    f"Violates problem logical invariant: contains {pairs} valid pairs summing to target instead of exactly one.",
                )

    # 4. Handle unresolved constraints
    blocking_unresolved = [
        u for u in (unresolved_constraints or [])
        if not any(k in u.lower() for k in (
            "follow up", "follow-up", "time complexity", "space complexity",
            "o(n)", "o(log", "o(1)", "o(n^2)", "only one valid answer exists"
        ))
    ]

    if blocking_unresolved and not checked_at_least_one:
        return (
            CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
            f"Satisfies parsed bounds, but problem statement contains unresolved constraints: {blocking_unresolved[:2]}.",
        )

    if checked_at_least_one:
        return (
            CandidateClassification.VALID.value,
            "Satisfies all supported supplied problem constraints.",
        )

    return (
        CandidateClassification.CONSTRAINT_VALIDITY_UNKNOWN.value,
        "Candidate parameters could not be evaluated against supplied constraints.",
    )
