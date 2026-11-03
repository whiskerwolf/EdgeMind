import ast


def check_quality(code):
    issues = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return issues

    # ==========================================
    # SCOPE-AWARE UNUSED IMPORTS
    # ==========================================

    class ImportScope:
        def __init__(self, owner, parent=None):
            self.owner = owner
            self.parent = parent
            self.imports = {}
            self.bound_names = set()
            self.used_imports = set()

    class ImportAnalyzer(ast.NodeVisitor):
        def __init__(self):
            self.scope_stack = []
            self.scope_data = []

        @property
        def current(self):
            return self.scope_stack[-1] if self.scope_stack else None

        def _collect_target(self, target, scope):
            if isinstance(target, ast.Name):
                scope.bound_names.add(target.id)
            elif isinstance(target, (ast.Tuple, ast.List)):
                for item in target.elts:
                    self._collect_target(item, scope)
            elif isinstance(target, ast.Starred):
                self._collect_target(target.value, scope)

        def _collect_bound_names(self, node, scope):
            # A nested definition creates its own scope.
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope.bound_names.add(node.name)
                return
            if isinstance(node, ast.Lambda):
                return
            if isinstance(node, ast.Import):
                for item in node.names:
                    scope.bound_names.add(item.asname or item.name.split(".")[0])
                return
            if isinstance(node, ast.ImportFrom):
                for item in node.names:
                    if item.name != "*":
                        scope.bound_names.add(item.asname or item.name)
                return
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                return
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    self._collect_target(target, scope)
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
                self._collect_target(node.target, scope)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                scope.bound_names.add(node.id)

            for child in ast.iter_child_nodes(node):
                self._collect_bound_names(child, scope)

        def _new_scope(self, owner, statements):
            scope = ImportScope(owner, self.current)
            self.scope_data.append(scope)
            self.scope_stack.append(scope)

            if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                args = owner.args
                for arg in (
                    args.posonlyargs + args.args + args.kwonlyargs
                ):
                    scope.bound_names.add(arg.arg)
                if args.vararg:
                    scope.bound_names.add(args.vararg.arg)
                if args.kwarg:
                    scope.bound_names.add(args.kwarg.arg)

            for statement in statements:
                self._collect_bound_names(statement, scope)

            for statement in statements:
                self.visit(statement)

            self.scope_stack.pop()

        def visit_Module(self, node):
            self._new_scope(node, node.body)

        def _visit_function_header(self, node):
            # These expressions execute in the enclosing scope.
            for decorator in node.decorator_list:
                self.visit(decorator)
            for default in node.args.defaults:
                self.visit(default)
            for default in node.args.kw_defaults:
                if default is not None:
                    self.visit(default)
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            if node.args.vararg:
                args.append(node.args.vararg)
            if node.args.kwarg:
                args.append(node.args.kwarg)
            for arg in args:
                if arg.annotation is not None:
                    self.visit(arg.annotation)
            if node.returns is not None:
                self.visit(node.returns)

        def visit_FunctionDef(self, node):
            self._visit_function_header(node)
            self._new_scope(node, node.body)

        def visit_AsyncFunctionDef(self, node):
            self._visit_function_header(node)
            self._new_scope(node, node.body)

        def visit_ClassDef(self, node):
            for decorator in node.decorator_list:
                self.visit(decorator)
            for base in node.bases:
                self.visit(base)
            for keyword in node.keywords:
                self.visit(keyword.value)
            self._new_scope(node, node.body)

        def visit_Lambda(self, node):
            for default in node.args.defaults:
                self.visit(default)
            for default in node.args.kw_defaults:
                if default is not None:
                    self.visit(default)
            self._new_scope(node, [ast.Expr(value=node.body)])

        def visit_Import(self, node):
            scope = self.current
            if scope is None:
                return
            for item in node.names:
                name = item.asname or item.name.split(".")[0]
                scope.imports.setdefault(name, node.lineno)
                scope.bound_names.add(name)

        def visit_ImportFrom(self, node):
            scope = self.current
            if scope is None:
                return
            for item in node.names:
                if item.name != "*":
                    name = item.asname or item.name
                    scope.imports.setdefault(name, node.lineno)
                    scope.bound_names.add(name)

        def visit_Name(self, node):
            if not isinstance(node.ctx, ast.Load) or not self.scope_stack:
                return

            # Resolve the name to the nearest scope that binds it. Only count
            # the import that Python's lexical lookup would reach first.
            scope = self.current
            while scope is not None:
                if node.id in scope.imports:
                    scope.used_imports.add(node.id)
                    return
                if node.id in scope.bound_names:
                    return
                scope = scope.parent

        def visit_Global(self, node):
            if self.current:
                for name in node.names:
                    self.current.bound_names.discard(name)

        def visit_Nonlocal(self, node):
            if self.current:
                for name in node.names:
                    self.current.bound_names.discard(name)

    import_analyzer = ImportAnalyzer()
    import_analyzer.visit(tree)

    for scope in import_analyzer.scope_data:
        for name, line in scope.imports.items():
            if name not in scope.used_imports:
                issues.append({
                    "type": "UnusedImport",
                    "line": line,
                    "message": f"'{name}' is imported but never used.",
                    "why": "Unused imports make code harder to maintain.",
                    "fix": f"Remove the unused import '{name}'.",
                    "concept": "Code Quality",
                })

    # ==========================================
    # SCOPE-AWARE UNUSED VARIABLES
    # ==========================================

    class ScopeAnalyzer(ast.NodeVisitor):

        def __init__(self):
            self.scopes = []
            self.scope_data = []

        def visit_Module(self, node):
            self._analyze_scope(node.body, node)

        def visit_FunctionDef(self, node):
            self._analyze_scope(node.body, node)

        def visit_AsyncFunctionDef(self, node):
            self._analyze_scope(node.body, node)

        def visit_Lambda(self, node):
            self._analyze_scope([], node)

        def _analyze_scope(self, statements, owner):
            parent_owner = self.scopes[-1]["owner"] if self.scopes else None
            data = {
                "owner": owner,
                "assigned": {},
                "used": set(),
                "global": set(),
                "nonlocal": set(),
            }

            self.scope_data.append(data)
            self.scopes.append(data)

            if isinstance(
                owner,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
            ):
                args = owner.args
                parameters = (
                    args.posonlyargs
                    + args.args
                    + args.kwonlyargs
                )

                exempt_first_param = False
                if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    parent_is_class = isinstance(parent_owner, ast.ClassDef)

                    is_static = False
                    is_classmethod_dec = False
                    for dec in getattr(owner, "decorator_list", []):
                        dec_name = None
                        if isinstance(dec, ast.Name):
                            dec_name = dec.id
                        elif isinstance(dec, ast.Attribute):
                            dec_name = dec.attr
                        elif isinstance(dec, ast.Call):
                            if isinstance(dec.func, ast.Name):
                                dec_name = dec.func.id
                            elif isinstance(dec.func, ast.Attribute):
                                dec_name = dec.func.attr

                        if dec_name == "staticmethod":
                            is_static = True
                        elif dec_name == "classmethod":
                            is_classmethod_dec = True

                    pos_args = args.posonlyargs + args.args
                    if pos_args and not is_static:
                        first_arg_name = pos_args[0].arg
                        # Conventional instance-method receiver: 'self' inside a class
                        if parent_is_class and first_arg_name == "self" and not is_classmethod_dec:
                            exempt_first_param = True
                        # Conventional class-method receiver: 'cls' in @classmethod or inside a class
                        elif first_arg_name == "cls" and (is_classmethod_dec or parent_is_class):
                            exempt_first_param = True

                for i, arg in enumerate(parameters):
                    if i == 0 and exempt_first_param:
                        continue
                    data["assigned"].setdefault(arg.arg, arg.lineno)

                if args.vararg:
                    data["assigned"].setdefault(
                        args.vararg.arg, args.vararg.lineno
                    )

                if args.kwarg:
                    data["assigned"].setdefault(
                        args.kwarg.arg, args.kwarg.lineno
                    )

            for statement in statements:
                self.visit(statement)

            self.scopes.pop()

        def visit_Name(self, node):
            if not self.scopes:
                return

            current = self.scopes[-1]

            if isinstance(node.ctx, ast.Store):
                current["assigned"].setdefault(
                    node.id, node.lineno
                )

            elif isinstance(node.ctx, ast.Load):
                current["used"].add(node.id)

                # Recognize variables captured from enclosing scopes.
                for parent in reversed(self.scopes[:-1]):
                    if node.id in parent["assigned"]:
                        parent["used"].add(node.id)
                        break

        def visit_Global(self, node):
            if self.scopes:
                self.scopes[-1]["global"].update(node.names)

        def visit_Nonlocal(self, node):
            if self.scopes:
                self.scopes[-1]["nonlocal"].update(node.names)

        def visit_ClassDef(self, node):
            self._analyze_scope(node.body, node)

        def visit_Import(self, node):
            if not self.scopes:
                return

            current = self.scopes[-1]

            for item in node.names:
                name = item.asname or item.name.split(".")[0]
                current["assigned"].setdefault(name, node.lineno)

        def visit_ImportFrom(self, node):
            if not self.scopes:
                return

            current = self.scopes[-1]

            for item in node.names:
                if item.name != "*":
                    name = item.asname or item.name
                    current["assigned"].setdefault(name, node.lineno)

        def visit_Assign(self, node):
            self.visit(node.value)

            for target in node.targets:
                self.visit(target)

        def visit_AnnAssign(self, node):
            if node.value:
                self.visit(node.value)

            self.visit(node.target)

        def visit_AugAssign(self, node):
            self.visit(node.target)
            self.visit(node.value)

        def visit_NamedExpr(self, node):
            self.visit(node.value)
            self.visit(node.target)

    analyzer = ScopeAnalyzer()
    analyzer.visit(tree)

    for data in analyzer.scope_data:
        assigned = data["assigned"]
        used = data["used"]
        excluded = data["global"] | data["nonlocal"]

        for name, line in assigned.items():
            if name == "_" or name in excluded:
                continue

            if name not in used:
                issues.append({
                    "type": "UnusedVariable",
                    "line": line,
                    "message": (
                        f"Variable '{name}' is assigned but never used."
                    ),
                    "why": (
                        "Unused variables may indicate unnecessary code."
                    ),
                    "fix": (
                        f"Remove '{name}' if it is not needed, or use it."
                    ),
                    "concept": "Code Quality"
                })

    # ==========================================
    # UNREACHABLE CODE
    # ==========================================

    TRY_NODES = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)

    def block_terminates(statements):
        """Check whether a block always returns or raises."""
        for node in statements:
            if isinstance(node, (ast.Return, ast.Raise)):
                return True

            if isinstance(node, ast.If):
                if (
                    node.orelse
                    and block_terminates(node.body)
                    and block_terminates(node.orelse)
                ):
                    return True

            if isinstance(node, TRY_NODES):
                if try_terminates(node):
                    return True

        return False

    def block_leaves(statements):
        """Check whether a block always returns, raises, breaks, or continues."""
        for node in statements:
            if isinstance(node, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                return True

            if isinstance(node, ast.If):
                if (
                    node.orelse
                    and block_leaves(node.body)
                    and block_leaves(node.orelse)
                ):
                    return True

            if isinstance(node, TRY_NODES):
                if try_leaves(node):
                    return True

        return False

    def try_terminates(node):
        """Check whether a try statement always returns or raises."""
        if node.finalbody:
            if block_terminates(node.finalbody):
                return True
            if block_leaves(node.finalbody):
                return False

        normal_terminates = block_terminates(node.body) or (
            bool(node.orelse)
            and not block_leaves(node.body)
            and block_terminates(node.orelse)
        )
        handlers_terminate = all(
            block_terminates(handler.body) for handler in node.handlers
        )
        return normal_terminates and handlers_terminate

    def try_leaves(node):
        """Check whether a try statement always returns, raises, breaks, or continues."""
        if node.finalbody and block_leaves(node.finalbody):
            return True

        normal_leaves = block_leaves(node.body) or (
            bool(node.orelse) and block_leaves(node.orelse)
        )
        handlers_leave = all(
            block_leaves(handler.body) for handler in node.handlers
        )
        return normal_leaves and handlers_leave

    def check_block(statements, stopped=False):
        for node in statements:
            if stopped:
                issues.append({
                    "type": "UnreachableCode",
                    "line": node.lineno,
                    "message": "This code can never be executed.",
                    "why": (
                        "A preceding statement or conditional branches "
                        "always terminate execution."
                    ),
                    "fix": (
                        "Remove the unreachable code or move it "
                        "before the terminating statement."
                    ),
                    "concept": "Control Flow"
                })
                continue

            if isinstance(
                node,
                (ast.Return, ast.Raise, ast.Break, ast.Continue)
            ):
                stopped = True

            elif isinstance(node, ast.If):
                check_block(node.body)
                check_block(node.orelse)

                if (
                    node.orelse
                    and block_leaves(node.body)
                    and block_leaves(node.orelse)
                ):
                    stopped = True

            elif isinstance(
                node,
                (ast.For, ast.AsyncFor, ast.While)
            ):
                check_block(node.body)
                check_block(node.orelse)

            elif isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                check_block(node.body)

            elif isinstance(node, TRY_NODES):
                check_block(node.body)
                orelse_stopped = block_leaves(node.body)
                check_block(node.orelse, stopped=orelse_stopped)
                check_block(node.finalbody)

                for handler in node.handlers:
                    check_block(handler.body)

                if try_leaves(node):
                    stopped = True

            elif isinstance(node, (ast.With, ast.AsyncWith)):
                check_block(node.body)

    # Analyze module-level statements.
    check_block(tree.body)

    

    # ==========================================
    # FUNCTION QUALITY
    # ==========================================

    def max_depth(statements, depth=0):
        maximum = depth

        for node in statements:
            if isinstance(
                node,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.Try,
                    ast.With,
                    ast.AsyncWith,
                ),
            ):
                maximum = max(maximum, depth + 1)
                branches = [node.body]

                if hasattr(node, "orelse"):
                    branches.append(node.orelse)

                if isinstance(node, ast.Try):
                    branches.extend(
                        handler.body for handler in node.handlers
                    )
                    branches.append(node.finalbody)

                for branch in branches:
                    maximum = max(
                        maximum,
                        max_depth(branch, depth + 1)
                    )

        return maximum

    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue

        # Long function
        if len(node.body) > 20:
            issues.append({
                "type": "LongFunction",
                "line": node.lineno,
                "message": f"Function '{node.name}' is too long.",
                "why": (
                    "Large functions are harder to understand, "
                    "test, and maintain."
                ),
                "fix": "Split the function into smaller functions.",
                "concept": "Function Design"
            })

        # Too many parameters
        parameter_count = (
            len(node.args.posonlyargs)
            + len(node.args.args)
            + len(node.args.kwonlyargs)
            + (1 if node.args.vararg else 0)
            + (1 if node.args.kwarg else 0)
        )

        if parameter_count > 5:
            issues.append({
                "type": "TooManyParameters",
                "line": node.lineno,
                "message": (
                    f"Function '{node.name}' has "
                    f"{parameter_count} parameters."
                ),
                "why": (
                    "Functions with many parameters can be harder "
                    "to use and maintain."
                ),
                "fix": (
                    "Group related values or simplify the interface."
                ),
                "concept": "Function Design"
            })

        # Deep nesting
        if max_depth(node.body) > 3:
            issues.append({
                "type": "DeepNesting",
                "line": node.lineno,
                "message": (
                    f"Function '{node.name}' has deeply nested code."
                ),
                "why": (
                    "Deep nesting makes control flow difficult "
                    "to understand."
                ),
                "fix": (
                    "Use helper functions, early returns, "
                    "or simpler conditions."
                ),
                "concept": "Code Readability"
            })

    # Remove duplicate findings while preserving their original order.
    unique_issues = []
    seen_issues = set()

    for issue in issues:
        key = (
            issue.get("type"),
            issue.get("line"),
            issue.get("message"),
        )

        if key not in seen_issues:
            seen_issues.add(key)
            unique_issues.append(issue)

    return unique_issues