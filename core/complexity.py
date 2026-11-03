import ast


def check_complexity(code):
    issues = []

    try:
        tree = ast.parse(code)
    except (SyntaxError, TypeError, ValueError):
        return issues

    def calculate(node):
        complexity = 1

        def visit(current):
            nonlocal complexity

            # Do not count nested functions as part
            # of the current function's complexity.
            if current is not node and isinstance(
                current,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            ):
                return

            if isinstance(current, (ast.If, ast.For, ast.AsyncFor,
                                    ast.While, ast.ExceptHandler,
                                    ast.IfExp)):
                complexity += 1

            elif isinstance(current, ast.BoolOp):
                complexity += len(current.values) - 1

            for child in ast.iter_child_nodes(current):
                visit(child)

        visit(node)
        return complexity

    for node in ast.walk(tree):

        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue

        complexity = calculate(node)

        if complexity >= 10:
            issues.append({
                "type": "HighComplexity",
                "line": node.lineno,
                "message": (
                    f"Function '{node.name}' has "
                    f"high complexity ({complexity})."
                ),
                "why": (
                    "Highly complex functions are harder to understand, "
                    "test, debug, and maintain."
                ),
                "fix": (
                    "Break the function into smaller functions "
                    "and simplify the conditions."
                ),
                "concept": "Cyclomatic Complexity"
            })

        elif complexity >= 6:
            issues.append({
                "type": "MediumComplexity",
                "line": node.lineno,
                "message": (
                    f"Function '{node.name}' has "
                    f"medium complexity ({complexity})."
                ),
                "why": (
                    "The function contains several decision paths "
                    "that can make maintenance harder."
                ),
                "fix": (
                    "Consider simplifying conditions "
                    "or splitting the function."
                ),
                "concept": "Cyclomatic Complexity"
            })

    return issues