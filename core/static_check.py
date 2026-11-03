import ast


def static_checks(code):
    issues = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    variables = {}

    for node in ast.walk(tree):

        # Remember simple list, tuple and dictionary variables
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):

                name = node.targets[0].id

                if isinstance(node.value, (ast.List, ast.Tuple)):
                    variables[name] = node.value

                elif isinstance(node.value, ast.Dict):
                    variables[name] = node.value

        # Check indexing
        if isinstance(node, ast.Subscript):

            if isinstance(node.value, ast.Name):
                name = node.value.id

                if name in variables:

                    value = variables[name]

                    # List / Tuple index checking
                    if isinstance(value, (ast.List, ast.Tuple)):
                        index = node.slice

                        if isinstance(index, ast.Constant):
                            if isinstance(index.value, int):

                                i = index.value
                                size = len(value.elts)

                                if i >= size or i < -size:
                                    issues.append({
                                        "type": "IndexError",
                                        "line": node.lineno,
                                        "message": f"Index {i} is outside the valid range.",
                                        "why": f"The list contains {size} elements.",
                                        "fix": f"Use an index from {-size} to {size - 1}.",
                                        "concept": "List Indexing"
                                    })

                    # Dictionary key checking
                    elif isinstance(value, ast.Dict):

                        key = node.slice

                        if isinstance(key, ast.Constant):

                            existing_keys = []

                            for k in value.keys:
                                if isinstance(k, ast.Constant):
                                    existing_keys.append(k.value)

                            if key.value not in existing_keys:
                                issues.append({
                                    "type": "KeyError",
                                    "line": node.lineno,
                                    "message": f"The key '{key.value}' does not exist.",
                                    "why": "The requested key is not present in the dictionary.",
                                    "fix": "Check whether the key exists before accessing it.",
                                    "concept": "Dictionary Keys"
                                })

        # Check obvious division by zero
        if isinstance(node, ast.BinOp):

            if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):

                if isinstance(node.right, ast.Constant):
                    if node.right.value == 0:

                        issues.append({
                            "type": "ZeroDivisionError",
                            "line": node.lineno,
                            "message": "You are trying to divide a number by zero.",
                            "why": "The denominator has a value of 0.",
                            "fix": "Make sure the denominator is not zero before dividing.",
                            "concept": "Division and Error Handling"
                        })

        # Check obvious type mismatch
        if isinstance(node, ast.BinOp):

            if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):

                left = node.left
                right = node.right

                if isinstance(left, ast.Constant) and isinstance(right, ast.Constant):

                    if isinstance(left.value, str) and isinstance(right.value, int):
                        issues.append({
                            "type": "TypeError",
                            "line": node.lineno,
                            "message": "Incompatible data types are being used.",
                            "why": "A string and integer cannot be used together with this operation.",
                            "fix": "Convert the values to compatible data types.",
                            "concept": "Data Types"
                        })

                    elif isinstance(left.value, int) and isinstance(right.value, str):
                        issues.append({
                            "type": "TypeError",
                            "line": node.lineno,
                            "message": "Incompatible data types are being used.",
                            "why": "An integer and string cannot be used together with this operation.",
                            "fix": "Convert the values to compatible data types.",
                            "concept": "Data Types"
                        })

    return issues