import ast


def check_smells(code):
    """
    Analyze Python code for common code smells.

    Detectors:
    1. Magic numbers
    2. Excessive print statements
    3. Long conditions
    4. Empty functions
    5. Duplicate calculations
    6. Nested loops

    Returns:
        A list of dictionaries compatible with EdgeMind's analyzer.
    """

    issues = []

    # --------------------------------------------------
    # 1. PARSE SOURCE CODE
    # --------------------------------------------------

    try:
        tree = ast.parse(code)
    except (SyntaxError, TypeError, ValueError):
        return issues

    # Build parent relationships for AST nodes.
    # This allows detectors to understand the context
    # in which a number or expression is used.

    parents = {}

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    # --------------------------------------------------
    # HELPER: ADD AN ISSUE
    # --------------------------------------------------

    def add_issue(
        issue_type,
        line,
        message,
        why,
        fix,
        concept
    ):
        issues.append({
            "type": issue_type,
            "line": line,
            "message": message,
            "why": why,
            "fix": fix,
            "concept": concept
        })

    # --------------------------------------------------
    # 2. SMART MAGIC NUMBER DETECTION
    # --------------------------------------------------

    common_values = {0, 1, -1, 2, 5, 10, 100}

    for node in ast.walk(tree):

        if not isinstance(node, ast.Constant):
            continue

        value = node.value

        # Ignore booleans, strings, None, and other
        # non-numeric constants.
        if isinstance(value, bool):
            continue

        if not isinstance(value, (int, float, complex)):
            continue

        # Ignore common values.
        if value in common_values:
            continue

        # Ignore numbers inside assertions (e.g., test expectations and invariant checks).
        curr = node
        in_assert = False
        while curr in parents:
            curr = parents[curr]
            if isinstance(curr, ast.Assert):
                in_assert = True
                break

        if in_assert:
            continue

        parent = parents.get(node)

        # Ignore ordinary numeric values inside list literals.
        if isinstance(parent, ast.List):
           continue

        # Ignore ordinary numeric values inside tuple literals.
        if isinstance(parent, ast.Tuple):
           continue

        # Ignore ordinary numeric values inside set literals.
        if isinstance(parent, ast.Set):
           continue

        # Ignore ordinary numeric values inside dictionary literals.
        if isinstance(parent, ast.Dict):
            continue

        # Ignore numbers used as indexes.
        if isinstance(parent, ast.Subscript):
            continue

        # Ignore numbers used directly in range() or print().
        if isinstance(parent, ast.Call):
            if isinstance(parent.func, ast.Name):
                if parent.func.id in {"range", "print"}:
                    continue

        # Ignore direct numeric arguments to function calls at module level
        # (e.g., driver scripts, example invocations, and manual test calls).
        is_call_arg = False
        if isinstance(parent, ast.Call) and node in parent.args:
            is_call_arg = True
        elif isinstance(parent, ast.keyword) and parent.value is node:
            call_ancestor = parents.get(parent)
            if isinstance(call_ancestor, ast.Call):
                is_call_arg = True

        if is_call_arg:
            curr_scope = parent
            in_func_or_class = False
            while curr_scope in parents:
                curr_scope = parents[curr_scope]
                if isinstance(curr_scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    in_func_or_class = True
                    break
            if not in_func_or_class:
                continue

        # Ignore a number that is the complete value
        # of a simple assignment, such as:
        #
        # price = 500
        # width = 750
        #
        # This is a heuristic, not a guarantee that
        # the number has no special meaning.

        if isinstance(parent, ast.Assign):
            if parent.value is node:
                continue

        if isinstance(parent, ast.AnnAssign):
            if parent.value is node:
                continue

        if isinstance(parent, ast.NamedExpr):
            if parent.value is node:
                continue

        # Report numeric literals in other contexts,
        # such as comparisons and calculations.
        add_issue(
            issue_type="MagicNumber",
            line=node.lineno,
            message=f"Potential magic number '{value}' detected.",
            why=(
                "This numeric value may represent a hard-coded "
                "rule or configuration value."
            ),
            fix=(
                f"If {value} has special meaning, consider "
                "storing it in a clearly named constant."
            ),
            concept="Code Smells"
        )

    # --------------------------------------------------
    # 3. EXCESSIVE PRINT DETECTION
    # --------------------------------------------------

    print_nodes = []

    for node in ast.walk(tree):

        if not isinstance(node, ast.Call):
            continue

        # Match print(...)
        if isinstance(node.func, ast.Name):
            if node.func.id == "print":
                print_nodes.append(node)

        # Also match builtins.print(...)
        elif isinstance(node.func, ast.Attribute):
            if (
                node.func.attr == "print"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "builtins"
            ):
                print_nodes.append(node)

    if len(print_nodes) > 5:

        add_issue(
            issue_type="ExcessivePrint",
            line=min(node.lineno for node in print_nodes),
            message=(
                f"Code contains {len(print_nodes)} print statements."
            ),
            why=(
                "Many print statements may indicate leftover debugging "
                "output or excessive console output."
            ),
            fix=(
                "Remove unnecessary debugging output or consider "
                "using the logging module where appropriate."
            ),
            concept="Code Smells"
        )

    # --------------------------------------------------
    # 4. LONG CONDITION DETECTION
    # --------------------------------------------------

    for node in ast.walk(tree):

        if not isinstance(node, (ast.If, ast.While)):
            continue

        logical_operations = 0

        for child in ast.walk(node.test):

            if isinstance(child, ast.BoolOp):
                logical_operations += len(child.values) - 1

        if logical_operations >= 4:

            add_issue(
                issue_type="LongCondition",
                line=node.lineno,
                message=(
                    "This condition contains "
                    f"{logical_operations} logical operations."
                ),
                why=(
                    "Many combined logical operations can make "
                    "conditions difficult to understand."
                ),
                fix=(
                    "Consider extracting meaningful parts into "
                    "boolean variables or helper functions."
                ),
                concept="Code Readability"
            )

    # --------------------------------------------------
    # 5. EMPTY FUNCTION DETECTION
    # --------------------------------------------------

    for node in ast.walk(tree):

        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue

        # Ignore a docstring when checking whether the
        # function contains executable statements.

        body = list(node.body)

        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]

        # An empty body or a body containing only pass
        # is a possible unfinished function.

        if not body or all(
            isinstance(statement, ast.Pass)
            for statement in body
        ):

            add_issue(
                issue_type="EmptyFunction",
                line=node.lineno,
                message=(
                    f"Function '{node.name}' appears to be empty."
                ),
                why=(
                    "The function contains no meaningful "
                    "implementation and may be unfinished."
                ),
                fix=(
                    "Implement the function if required, or remove "
                    "it if it is unnecessary. Empty methods may be "
                    "intentional interface or placeholder methods."
                ),
                concept="Code Design"
            )

    # --------------------------------------------------
    # 6. DUPLICATE CALCULATION DETECTION
    # --------------------------------------------------

    # Store calculation structures and their source lines.
    #
    # Example:
    # total = price * quantity
    # amount = price * quantity
    #
    # The target variable is excluded from the fingerprint,
    # so both calculations have the same fingerprint.

    expressions = {}

    assignment_types = (
        ast.Assign,
        ast.AnnAssign
    )

    for node in ast.walk(tree):

        if not isinstance(node, assignment_types):
            continue

        value = node.value

        # Ignore missing values and simple constants.
        if value is None:
            continue

        if isinstance(value, ast.Constant):
            continue

        # Ignore simple variable references.
        if isinstance(value, ast.Name):
            continue

        # Only inspect meaningful calculation expressions.
        # Avoid reporting every repeated function call,
        # comparison, container, or attribute access.

        if not isinstance(
            value,
            (
                ast.BinOp,
                ast.UnaryOp,
                ast.BoolOp
            )
        ):
            continue

        # Create a structural fingerprint of the expression.
        # Variable names are preserved so unrelated calculations
        # are not incorrectly treated as duplicates.

        fingerprint = ast.dump(
            value,
            annotate_fields=True,
            include_attributes=False
        )

        expressions.setdefault(
            fingerprint,
            []
        ).append(node.lineno)

    # Report each repeated calculation once.

    for fingerprint, lines in expressions.items():

        unique_lines = sorted(set(lines))

        if len(unique_lines) < 2:
            continue

        add_issue(
            issue_type="DuplicateCode",
            line=unique_lines[1],
            message=(
                "The same calculation appears more than once."
            ),
            why=(
                "Repeated calculations can increase maintenance "
                "effort and may lead to inconsistent changes."
            ),
            fix=(
                "Consider calculating the result once and reusing "
                "it when that improves clarity and maintainability."
            ),
            concept="Code Duplication"
        )

    # --------------------------------------------------
    # 7. NESTED LOOP PERFORMANCE SMELL
    # --------------------------------------------------

    loop_types = (ast.For, ast.AsyncFor, ast.While)
    reported_inner_loops = set()

    for outer_loop in ast.walk(tree):
        if not isinstance(outer_loop, loop_types):
            continue

        for inner_node in outer_loop.body:
            for inner_loop in ast.walk(inner_node):
                if inner_loop is outer_loop or not isinstance(inner_loop, loop_types):
                    continue
                if inner_loop in reported_inner_loops:
                    continue

                # Ignore loops inside nested function definitions
                parent_check = inner_loop
                is_in_nested_func = False
                while parent_check is not outer_loop and parent_check in parents:
                    parent_check = parents[parent_check]
                    if isinstance(parent_check, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        is_in_nested_func = True
                        break
                if is_in_nested_func:
                    continue

                # Ignore 2D row-unrolling where inner loop iterates over outer target
                if (
                    isinstance(outer_loop, ast.For)
                    and isinstance(inner_loop, ast.For)
                    and isinstance(outer_loop.target, ast.Name)
                    and isinstance(inner_loop.iter, ast.Name)
                    and inner_loop.iter.id == outer_loop.target.id
                ):
                    continue

                # Ignore small constant ranges (e.g. 3x3 kernel: range(3))
                if (
                    isinstance(inner_loop, ast.For)
                    and isinstance(inner_loop.iter, ast.Call)
                    and isinstance(inner_loop.iter.func, ast.Name)
                    and inner_loop.iter.func.id == "range"
                    and inner_loop.iter.args
                    and isinstance(inner_loop.iter.args[0], ast.Constant)
                    and isinstance(inner_loop.iter.args[0].value, int)
                    and inner_loop.iter.args[0].value <= 5
                ):
                    continue

                reported_inner_loops.add(inner_loop)

                # Check if both loops iterate over the same collection
                iter_name = None
                same_collection = False
                if isinstance(outer_loop, ast.For) and isinstance(inner_loop, ast.For):
                    outer_dump = ast.dump(outer_loop.iter)
                    inner_dump = ast.dump(inner_loop.iter)
                    if outer_dump == inner_dump:
                        same_collection = True
                        if isinstance(outer_loop.iter, ast.Name):
                            iter_name = outer_loop.iter.id
                        elif isinstance(outer_loop.iter, ast.Attribute):
                            iter_name = outer_loop.iter.attr

                if same_collection and iter_name:
                    add_issue(
                        issue_type="NestedLoops",
                        line=inner_loop.lineno,
                        message=f"Nested loop iterates over the same collection '{iter_name}'.",
                        why=(
                            f"Iterating over '{iter_name}' inside another loop over '{iter_name}' results in "
                            "quadratic O(n^2) operations, which may cause performance issues on larger inputs."
                        ),
                        fix=(
                            f"Verify whether pairwise iteration over '{iter_name}' is necessary, "
                            "or consider using a set, dictionary, or single-pass algorithm."
                        ),
                        concept="Performance"
                    )
                else:
                    add_issue(
                        issue_type="NestedLoops",
                        line=inner_loop.lineno,
                        message="Nested loop detected.",
                        why=(
                            "Nested loops multiply iteration counts, which may become a "
                            "performance concern if the input collections grow large."
                        ),
                        fix=(
                            "Check whether nested iteration is required or if lookups "
                            "can be optimized using a dictionary or pre-indexing."
                        ),
                        concept="Performance"
                    )

    # --------------------------------------------------
    # 8. REMOVE DUPLICATE FINDINGS
    # --------------------------------------------------

    unique_issues = []
    seen = set()

    for issue in issues:

        key = (
            issue["type"],
            issue["line"],
            issue["message"]
        )

        if key not in seen:
            seen.add(key)
            unique_issues.append(issue)

    # Always return a list.
    return unique_issues