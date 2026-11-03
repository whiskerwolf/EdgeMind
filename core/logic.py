import ast
from core.models import Diagnostic


def is_average_expression(expr):
    """
    Check if an AST expression represents an unparenthesized average calculation,
    such as a + b / 2 or a / 2 + b.
    """
    if not isinstance(expr, ast.BinOp):
        return False

    if isinstance(expr.op, ast.Add):
        # Case 1: right side is b / 2
        if isinstance(expr.right, ast.BinOp) and isinstance(expr.right.op, ast.Div):
            div = expr.right
            if isinstance(div.right, ast.Constant) and div.right.value in {2, 2.0}:
                return True
        # Case 2: left side is a / 2
        if isinstance(expr.left, ast.BinOp) and isinstance(expr.left.op, ast.Div):
            div = expr.left
            if isinstance(div.right, ast.Constant) and div.right.value in {2, 2.0}:
                return True

    return False


def is_average_context(func_name, target_name, func_node):
    """
    Check whether context (function name, target variable name, or 2-parameter function)
    suggests an intended average/mean calculation.
    """
    avg_keywords = ("avg", "average", "mean")
    if func_name and any(kw in func_name.lower() for kw in avg_keywords):
        return True
    if target_name and any(kw in target_name.lower() for kw in avg_keywords):
        return True
    if func_node and isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = func_node.args
        total_args = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
        if total_args == 2:
            return True
    return False


def check_logic(code):
    warnings = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return warnings

    seen_warnings = set()

    def add_warning(diag):
        key = (diag.type, diag.line, diag.message)
        if key not in seen_warnings:
            seen_warnings.add(key)
            warnings.append(diag)

    # 1. DETECT UNPARENTHESIZED AVERAGE CALCULATIONS
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name

            for item in ast.walk(node):
                if isinstance(item, ast.Return) and item.value:
                    if is_average_expression(item.value) and is_average_context(func_name, None, node):
                        add_warning(
                            Diagnostic(
                                type="Possible Logic Error",
                                severity="warning",
                                line=item.lineno,
                                message="This average calculation may be incorrect.",
                                why="Division happens before addition, so only one term is divided by 2.",
                                fix="Use (a + b) / 2 to divide the total sum.",
                                source="LogicDoctor",
                            )
                        )
                elif isinstance(item, (ast.Assign, ast.AnnAssign)):
                    val = item.value if isinstance(item, ast.Assign) else item.value
                    if val and is_average_expression(val):
                        target_name = None
                        if isinstance(item, ast.Assign) and item.targets and isinstance(item.targets[0], ast.Name):
                            target_name = item.targets[0].id
                        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                            target_name = item.target.id

                        if is_average_context(func_name, target_name, node):
                            add_warning(
                                Diagnostic(
                                    type="Possible Logic Error",
                                    severity="warning",
                                    line=item.lineno,
                                    message="This average calculation may be incorrect.",
                                    why="Division happens before addition, so only one term is divided by 2.",
                                    fix="Use (a + b) / 2 to divide the total sum.",
                                    source="LogicDoctor",
                                )
                            )

        # Module-level assignments (outside any function): e.g. avg = a + b / 2
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            val = node.value if isinstance(node, ast.Assign) else node.value
            if val and is_average_expression(val):
                target_name = None
                if isinstance(node, ast.Assign) and node.targets and isinstance(node.targets[0], ast.Name):
                    target_name = node.targets[0].id
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    target_name = node.target.id

                if target_name and any(kw in target_name.lower() for kw in ("avg", "average", "mean")):
                    add_warning(
                        Diagnostic(
                            type="Possible Logic Error",
                            severity="warning",
                            line=node.lineno,
                            message="This average calculation may be incorrect.",
                            why="Division happens before addition, so only one term is divided by 2.",
                            fix="Use (a + b) / 2 to divide the total sum.",
                            source="LogicDoctor",
                        )
                    )

    # 2. DETECT OFF-BY-ONE RANGE ACCUMULATION BUGS
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        param_names = {arg.arg for arg in (node.args.posonlyargs + node.args.args + node.args.kwonlyargs)}
        func_name_lower = node.name.lower()
        has_sum_intent = any(kw in func_name_lower for kw in ("sum", "total", "factorial", "product", "accumulate"))

        for child in ast.walk(node):
            if not isinstance(child, (ast.For, ast.AsyncFor)):
                continue

            iter_node = child.iter
            # Match range(1, param_name)
            if (
                isinstance(iter_node, ast.Call)
                and isinstance(iter_node.func, ast.Name)
                and iter_node.func.id == "range"
                and len(iter_node.args) == 2
                and isinstance(iter_node.args[0], ast.Constant)
                and iter_node.args[0].value == 1
                and isinstance(iter_node.args[1], ast.Name)
                and iter_node.args[1].id in param_names
            ):
                bound_param = iter_node.args[1].id

                # Check if loop variable is accumulated
                loop_var_id = child.target.id if isinstance(child.target, ast.Name) else None
                accumulates_loop_var = False

                if loop_var_id:
                    for body_stmt in ast.walk(child):
                        if isinstance(body_stmt, ast.AugAssign) and isinstance(body_stmt.value, ast.Name):
                            if body_stmt.value.id == loop_var_id:
                                accumulates_loop_var = True
                                break
                        elif isinstance(body_stmt, ast.Assign) and isinstance(body_stmt.value, ast.BinOp):
                            if isinstance(body_stmt.value.right, ast.Name) and body_stmt.value.right.id == loop_var_id:
                                accumulates_loop_var = True
                                break

                if has_sum_intent or accumulates_loop_var:
                    add_warning(
                        Diagnostic(
                            type="Possible Logic Error",
                            severity="warning",
                            line=child.lineno,
                            message=f"Possible off-by-one error in range(1, {bound_param}).",
                            why=(
                                f"range(1, {bound_param}) generates values from 1 up to {bound_param} - 1. "
                                f"If an inclusive calculation up to {bound_param} is intended, the boundary value {bound_param} is excluded."
                            ),
                            fix=f"Use range(1, {bound_param} + 1) if {bound_param} should be included in the calculation.",
                            source="LogicDoctor",
                        )
                    )

    return warnings


if __name__ == "__main__":
    with open("tests/test.py", "r", encoding="utf-8") as file:
        code = file.read()

    warnings = check_logic(code)

    for warning in warnings:
        print("\n🧠 LogicDoctor")
        print("⚠️", warning.type)
        print("📍 Line:", warning.line)
        print("🔴", warning.message)
        print("❓", warning.why)
        print("💊", warning.fix)