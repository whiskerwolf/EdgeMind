"""
EdgeMind JavaScript Hoisting Static Analyzer.

Pure-Python, zero-dependency lexical tokenizer and scope-aware AST analyzer for
detecting JavaScript hoisting and Temporal Dead Zone (TDZ) hazards without
executing submitted code.

Analyzes:
1. `var` hoisting (accessing a `var`-declared binding before initialization)
2. Function declaration hoisting (permitting valid calls prior to declaration)
3. `let` and `const` Temporal Dead Zone (TDZ) references before initialization
4. Block scope vs. function scope boundaries (`let`/`const` vs. `var`)
5. Function expression and arrow function hoisting hazards
6. Class declaration and class expression TDZ instantiation/references
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

JS_KEYWORDS: Set[str] = {
    "var", "let", "const", "function", "class", "extends", "return", "if",
    "else", "for", "while", "do", "switch", "case", "default", "break",
    "continue", "try", "catch", "finally", "throw", "new", "typeof", "void",
    "delete", "in", "of", "instanceof", "async", "await", "export", "import",
    "from", "as", "static", "true", "false", "null", "this", "super", "yield",
}

JS_EXTENSIONS: Tuple[str, ...] = (".js", ".mjs", ".cjs", ".jsx")

_REGEX_PREDECESSOR_PUNCT = {
    "(", "[", "{", ",", ";", ":", "=", "+=", "-=", "*=", "/=", "%=",
    "&&", "||", "??", "!", "~", "?", "=>", "==", "===", "!=", "!==",
    "<", ">", "<=", ">=", "+", "-", "*", "/", "%", "&", "|", "^",
}
_REGEX_PREDECESSOR_KEYWORDS = {
    "return", "throw", "case", "typeof", "void", "delete", "in", "of",
    "instanceof", "await", "yield", "else", "do",
}
_EXPR_PREFIX_PUNCT = {
    "=", "+=", "-=", "*=", "/=", "%=", "(", "[", ",", ":", "?", "=>",
    "&&", "||", "??", "!", "~", "+", "-", "*", "/", "%", "==", "===",
    "!=", "!==", "<", ">", "<=", ">=", "&", "|", "^",
}
_EXPR_PREFIX_KEYWORDS = {
    "return", "throw", "new", "typeof", "void", "delete", "await",
    "yield", "case", "in", "of", "instanceof",
}
_ASSIGN_OPERATORS = {"=", "+=", "-=", "*=", "/=", "%=", "&&=", "||=", "??="}
_MULTI_CHAR_PUNCT = (
    "===", "!==", ">>>", "&&=", "||=", "??=", "?.", "=>", "...",
    "==", "!=", "<=", ">=", "&&", "||", "??", "++", "--", "+=", "-=",
    "*=", "/=", "%=", "**", "<<", ">>",
)


@dataclass
class JsToken:
    """Single lexical token with 1-based line and column metadata."""
    kind: str  # IDENT, KEYWORD, NUMBER, STRING, REGEX, PUNCT
    value: str
    line: int
    col: int


@dataclass
class JsSyntaxIssue:
    """Lexical or structural JavaScript syntax issue."""
    line: int
    message: str
    why: str
    fix: str


@dataclass
class JsDeclaration:
    """Hoisted or block-scoped binding metadata."""
    name: str
    kind: str  # var, let, const, function, class, param, catch_param, import
    scope_id: int
    decl_token_idx: int
    decl_line: int
    init_end_token_idx: int
    init_line: int
    init_kind: str = "value"  # value, function_expression, class_expression, none
    inside_block_in_function: bool = False
    declaring_block_id: int = 0
    has_initializer: bool = True


@dataclass
class JsScope:
    """Lexical/function/program scope node."""
    scope_id: int
    kind: str  # program, function, block, class
    parent: Optional["JsScope"]
    start_token_idx: int
    start_line: int
    end_token_idx: int = -1
    end_line: int = 0
    declarations: Dict[str, List[JsDeclaration]] = field(default_factory=dict)

    def add_declaration(self, decl: JsDeclaration) -> None:
        self.declarations.setdefault(decl.name, []).append(decl)


@dataclass
class _LexState:
    tokens: List[JsToken] = field(default_factory=list)
    syntax_issues: List[JsSyntaxIssue] = field(default_factory=list)
    line: int = 1
    col: int = 1


def _allows_regex_literal(tokens: List[JsToken]) -> bool:
    if not tokens:
        return True
    prev = tokens[-1]
    if prev.kind == "PUNCT":
        return prev.value in _REGEX_PREDECESSOR_PUNCT
    if prev.kind == "KEYWORD":
        return prev.value in _REGEX_PREDECESSOR_KEYWORDS
    return False


def _scan_string(code: str, idx: int, quote: str, state: _LexState) -> int:
    start_line, start_col = state.line, state.col
    n = len(code)
    j = idx + 1
    while j < n:
        ch = code[j]
        if ch == "\\":
            if j + 1 < n and code[j + 1] == "\n":
                state.line += 1
                state.col = 1
            else:
                state.col += 2
            j += 2
            continue
        if ch == quote:
            state.col += 1
            state.tokens.append(JsToken("STRING", code[idx : j + 1], start_line, start_col))
            return j + 1
        if ch == "\n":
            state.syntax_issues.append(
                JsSyntaxIssue(
                    line=start_line,
                    message=f"Unterminated string literal starting at line {start_line}.",
                    why="JavaScript single- and double-quoted strings must close before a newline.",
                    fix=f"Close the string with {quote} or escape newlines explicitly.",
                )
            )
            return j
        state.col += 1
        j += 1

    state.syntax_issues.append(
        JsSyntaxIssue(
            line=start_line,
            message=f"Unterminated string literal starting at line {start_line}.",
            why="End of file reached before the string literal was closed.",
            fix=f"Add a closing {quote} to complete the string literal.",
        )
    )
    return n


def _scan_regex(code: str, idx: int, state: _LexState) -> int:
    start_line, start_col = state.line, state.col
    n = len(code)
    j = idx + 1
    in_class = False
    while j < n:
        ch = code[j]
        if ch == "\\":
            j += 2
            state.col += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]" and in_class:
            in_class = False
        elif ch == "/" and not in_class:
            j += 1
            state.col += 1
            while j < n and code[j].isalpha():
                j += 1
                state.col += 1
            state.tokens.append(JsToken("REGEX", code[idx:j], start_line, start_col))
            return j
        elif ch == "\n":
            state.tokens.append(JsToken("PUNCT", "/", start_line, start_col))
            return idx + 1
        j += 1
        state.col += 1
    state.tokens.append(JsToken("PUNCT", "/", start_line, start_col))
    return idx + 1


def _scan_template_literal(code: str, idx: int, state: _LexState) -> int:
    start_line, start_col = state.line, state.col
    n = len(code)
    j = idx + 1
    state.col += 1
    while j < n:
        ch = code[j]
        if ch == "\\":
            if j + 1 < n and code[j + 1] == "\n":
                state.line += 1
                state.col = 1
            else:
                state.col += 2
            j += 2
            continue
        if ch == "`":
            state.col += 1
            state.tokens.append(JsToken("STRING", "`template`", start_line, start_col))
            return j + 1
        if ch == "$" and j + 1 < n and code[j + 1] == "{":
            state.tokens.append(JsToken("PUNCT", "(", state.line, state.col))
            j += 2
            state.col += 2
            j = _tokenize_range(code, j, state, stop_on_close_brace=True)
            state.tokens.append(JsToken("PUNCT", ")", state.line, state.col))
            continue
        if ch == "\n":
            state.line += 1
            state.col = 1
        else:
            state.col += 1
        j += 1

    state.syntax_issues.append(
        JsSyntaxIssue(
            line=start_line,
            message=f"Unterminated template literal starting at line {start_line}.",
            why="Backtick template literal reached end of input without closing '`'.",
            fix="Add a closing backtick '`' to complete the template literal.",
        )
    )
    return n


def _tokenize_range(
    code: str,
    start_idx: int,
    state: _LexState,
    stop_on_close_brace: bool = False,
) -> int:
    n = len(code)
    i = start_idx
    brace_depth = 0

    while i < n:
        ch = code[i]

        if stop_on_close_brace and ch == "}" and brace_depth == 0:
            state.col += 1
            return i + 1

        if ch == "\n":
            state.line += 1
            state.col = 1
            i += 1
            continue
        if ch in " \t\r\v\f":
            state.col += 1
            i += 1
            continue

        # Line comment
        if ch == "/" and i + 1 < n and code[i + 1] == "/":
            i += 2
            while i < n and code[i] != "\n":
                i += 1
            continue

        # Block comment
        if ch == "/" and i + 1 < n and code[i + 1] == "*":
            c_line = state.line
            i += 2
            state.col += 2
            closed = False
            while i < n:
                if code[i] == "*" and i + 1 < n and code[i + 1] == "/":
                    i += 2
                    state.col += 2
                    closed = True
                    break
                if code[i] == "\n":
                    state.line += 1
                    state.col = 1
                else:
                    state.col += 1
                i += 1
            if not closed:
                state.syntax_issues.append(
                    JsSyntaxIssue(
                        line=c_line,
                        message=f"Unterminated block comment starting at line {c_line}.",
                        why="Block comment '/*' was never closed with '*/'.",
                        fix="Add closing '*/' at the end of the comment.",
                    )
                )
                return n
            continue

        if ch in ("'", '"'):
            i = _scan_string(code, i, ch, state)
            continue

        if ch == "`":
            i = _scan_template_literal(code, i, state)
            continue

        if ch == "/" and _allows_regex_literal(state.tokens):
            i = _scan_regex(code, i, state)
            continue

        # Identifiers / Keywords
        if ch.isalpha() or ch in ("_", "$"):
            start_col = state.col
            j = i + 1
            while j < n and (code[j].isalnum() or code[j] in ("_", "$")):
                j += 1
            ident = code[i:j]
            kind = "KEYWORD" if ident in JS_KEYWORDS else "IDENT"
            state.tokens.append(JsToken(kind, ident, state.line, start_col))
            state.col += j - i
            i = j
            continue

        # Numbers
        if ch.isdigit():
            start_col = state.col
            j = i + 1
            while j < n and (code[j].isalnum() or code[j] in (".", "_")):
                j += 1
            state.tokens.append(JsToken("NUMBER", code[i:j], state.line, start_col))
            state.col += j - i
            i = j
            continue

        # Multi-character punctuation
        matched_punct = None
        for op in _MULTI_CHAR_PUNCT:
            if code.startswith(op, i):
                matched_punct = op
                break
        if matched_punct:
            state.tokens.append(JsToken("PUNCT", matched_punct, state.line, state.col))
            state.col += len(matched_punct)
            i += len(matched_punct)
            continue

        # Single-character punctuation
        if stop_on_close_brace:
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1

        state.tokens.append(JsToken("PUNCT", ch, state.line, state.col))
        state.col += 1
        i += 1

    return n


def tokenize_javascript(code: str) -> Tuple[List[JsToken], List[JsSyntaxIssue]]:
    """Tokenize JavaScript source code while tracking syntax and delimiter health."""
    state = _LexState()
    _tokenize_range(code, 0, state)

    # Validate bracket/brace/paren balance on non-template tokens
    stack: List[Tuple[str, int]] = []
    matching = {")": "(", "]": "[", "}": "{"}
    for tok in state.tokens:
        if tok.kind != "PUNCT":
            continue
        if tok.value in ("(", "[", "{"):
            stack.append((tok.value, tok.line))
        elif tok.value in matching:
            expected = matching[tok.value]
            if not stack or stack[-1][0] != expected:
                state.syntax_issues.append(
                    JsSyntaxIssue(
                        line=tok.line,
                        message=f"Unexpected closing '{tok.value}' on line {tok.line}.",
                        why="Delimiters must open and close in matching pairs.",
                        fix=f"Remove or pair the unmatched '{tok.value}'.",
                    )
                )
            else:
                stack.pop()

    for opener, open_line in stack:
        state.syntax_issues.append(
            JsSyntaxIssue(
                line=open_line,
                message=f"Unclosed '{opener}' opened on line {open_line}.",
                why="Every block, array, or parenthesized group must have a closing delimiter.",
                fix=f"Add a matching closing delimiter for '{opener}'.",
            )
        )

    return state.tokens, state.syntax_issues


class _JsHoistingAnalyzer:
    """Scope-building and hoisting/TDZ checker operating over JsTokens."""

    def __init__(self, tokens: List[JsToken]) -> None:
        self.tokens = tokens
        self.n = len(tokens)
        self.next_scope_id = 0
        self.program_scope = self._new_scope("program", None, 0, tokens[0].line if tokens else 1)
        self.token_scope: List[JsScope] = [self.program_scope] * self.n
        self.token_skip_refs: Set[int] = set()
        self.syntax_issues: List[JsSyntaxIssue] = []

        # Track binding declarations -> scope & span, plus function call sites
        self.all_declarations: List[JsDeclaration] = []
        self.fn_body_calls: Dict[int, List[Tuple[str, int, int]]] = {}  # fn_decl_scope_id -> calls? No:
        # Map function binding key `(scope_id, name)` -> earliest call index in same scope
        self.early_calls_by_fn_decl: Dict[Tuple[int, str], List[int]] = {}
        self.func_decl_body_scopes: Dict[int, Tuple[int, str]] = {}  # body_scope_id -> (hoist_scope_id, fn_name)
        self.decl_target_scopes: Dict[int, JsScope] = {}  # decl_id -> scope

    def _new_scope(
        self, kind: str, parent: Optional[JsScope], start_idx: int, start_line: int
    ) -> JsScope:
        sid = self.next_scope_id
        self.next_scope_id += 1
        return JsScope(
            scope_id=sid,
            kind=kind,
            parent=parent,
            start_token_idx=start_idx,
            start_line=start_line,
            end_token_idx=max(0, self.n - 1),
            end_line=self.tokens[-1].line if self.tokens else start_line,
        )

    @staticmethod
    def _var_target_scope(scope: JsScope) -> JsScope:
        cur = scope
        while cur.parent is not None and cur.kind not in ("function", "program"):
            cur = cur.parent
        return cur

    def _find_matching(self, open_idx: int, open_ch: str, close_ch: str) -> int:
        depth = 0
        i = open_idx
        while i < self.n:
            tok = self.tokens[i]
            if tok.kind == "PUNCT":
                if tok.value == open_ch:
                    depth += 1
                elif tok.value == close_ch:
                    depth -= 1
                    if depth == 0:
                        return i
            i += 1
        return self.n - 1

    def _is_expr_context(self, idx: int) -> bool:
        if idx <= 0:
            return False
        prev = self.tokens[idx - 1]
        if prev.kind == "PUNCT":
            return prev.value in _EXPR_PREFIX_PUNCT
        if prev.kind == "KEYWORD":
            return prev.value in _EXPR_PREFIX_KEYWORDS
        return False

    def _is_function_declaration(self, fn_idx: int) -> bool:
        check_idx = fn_idx - 1
        if fn_idx > 0 and self.tokens[fn_idx - 1].kind == "KEYWORD" and self.tokens[fn_idx - 1].value == "async":
            check_idx -= 1
        if check_idx < 0:
            return True
        prev = self.tokens[check_idx]
        if prev.kind == "PUNCT":
            return prev.value in (";", "{", "}")
        if prev.kind == "KEYWORD":
            return prev.value in ("export", "default")
        # Previous token on an earlier line without semicolon (ASI) followed by statement `function f()`
        return prev.line < self.tokens[fn_idx].line and not self._is_expr_context(check_idx + 1)

    def _register_binding_names(
        self,
        start_idx: int,
        end_idx: int,
        target_scope: JsScope,
        kind: str,
        decl_line: int,
        init_end_idx: int,
        init_line: int,
        decl_idx: int,
        inside_block_in_function: bool = False,
        declaring_block_id: int = 0,
        has_initializer: bool = True,
        init_kind: str = "value",
    ) -> None:
        """Extract simple or destructured identifier bindings within [start_idx, end_idx)."""
        i = start_idx
        while i < end_idx:
            tok = self.tokens[i]
            if tok.kind == "IDENT":
                # In `{ a: b }` object destructuring, `a:` is the property name and `b` is bound
                if i + 1 < end_idx and self.tokens[i + 1].kind == "PUNCT" and self.tokens[i + 1].value == ":":
                    self.token_skip_refs.add(i)
                    i += 1
                    continue
                self.token_skip_refs.add(i)
                decl = JsDeclaration(
                    name=tok.value,
                    kind=kind,
                    scope_id=target_scope.scope_id,
                    decl_token_idx=decl_idx,
                    decl_line=decl_line,
                    init_end_token_idx=init_end_idx,
                    init_line=init_line,
                    init_kind=init_kind,
                    inside_block_in_function=inside_block_in_function,
                    declaring_block_id=declaring_block_id,
                    has_initializer=has_initializer,
                )
                target_scope.add_declaration(decl)
                self.all_declarations.append(decl)
            elif tok.kind == "PUNCT" and tok.value == "=":
                # Skip default value RHS expression in destructuring `( { a = defaultVal } )`
                depth = 0
                i += 1
                while i < end_idx:
                    t = self.tokens[i]
                    if t.kind == "PUNCT":
                        if t.value in ("(", "[", "{"):
                            depth += 1
                        elif t.value in (")", "]", "}"):
                            if depth == 0:
                                break
                            depth -= 1
                        elif t.value == "," and depth == 0:
                            break
                    i += 1
                continue
            i += 1

    def _find_declaration_stmt_end(self, start_idx: int) -> int:
        """Find terminating `;`, newline ASI boundary, or closing `}` for a var/let/const statement."""
        i = start_idx
        paren = bracket = brace = 0
        while i < self.n:
            tok = self.tokens[i]
            if tok.kind == "PUNCT":
                if tok.value == "(":
                    paren += 1
                elif tok.value == ")":
                    if paren == 0 and bracket == 0 and brace == 0:
                        return i
                    paren = max(0, paren - 1)
                elif tok.value == "[":
                    bracket += 1
                elif tok.value == "]":
                    bracket = max(0, bracket - 1)
                elif tok.value == "{":
                    brace += 1
                elif tok.value == "}":
                    if brace == 0 and paren == 0 and bracket == 0:
                        return i
                    brace = max(0, brace - 1)
                elif tok.value == ";" and paren == 0 and bracket == 0 and brace == 0:
                    return i + 1
            if i + 1 < self.n and paren == 0 and bracket == 0 and brace == 0:
                nxt = self.tokens[i + 1]
                # Semicolon-less line break ending statement unless binary/comma continuation
                if nxt.line > tok.line:
                    cur_cont = tok.kind == "PUNCT" and tok.value in (",", "=", "+", "-", "*", "/", "&&", "||", "??", "=>", ".", "?.")
                    nxt_cont = nxt.kind == "PUNCT" and nxt.value in (".", "?.", "[", "(", "+", "-", "&&", "||", "??")
                    if not cur_cont and not nxt_cont and nxt.value not in ("}",):
                        return i + 1
            i += 1
        return self.n

    def _classify_initializer_kind(self, rhs_start: int, rhs_end: int) -> str:
        """Inspect RHS tokens of `=` to see if initializer creates a function or class."""
        if rhs_start >= rhs_end:
            return "none"
        first = self.tokens[rhs_start]
        if first.kind == "KEYWORD" and first.value == "function":
            return "function_expression"
        if (
            first.kind == "KEYWORD"
            and first.value == "async"
            and rhs_start + 1 < rhs_end
            and self.tokens[rhs_start + 1].kind == "KEYWORD"
            and self.tokens[rhs_start + 1].value == "function"
        ):
            return "function_expression"
        if first.kind == "KEYWORD" and first.value == "class":
            return "class_expression"
        # Detect arrow function `(...) =>` or `async (...) =>` or `arg =>`
        depth = 0
        for k in range(rhs_start, rhs_end):
            t = self.tokens[k]
            if t.kind == "PUNCT":
                if t.value in ("(", "[", "{"):
                    depth += 1
                elif t.value in (")", "]", "}"):
                    depth = max(0, depth - 1)
                elif t.value == "=>" and depth == 0:
                    return "function_expression"
        return "value"

    def _parse_var_let_const(self, kw_idx: int, scope: JsScope) -> int:
        kw_tok = self.tokens[kw_idx]
        kw = kw_tok.value
        stmt_end = self._find_declaration_stmt_end(kw_idx + 1)

        if kw_idx + 1 >= stmt_end:
            self.syntax_issues.append(
                JsSyntaxIssue(
                    line=kw_tok.line,
                    message=f"Incomplete '{kw}' declaration on line {kw_tok.line}.",
                    why=f"Keyword '{kw}' must be followed by an identifier or destructuring pattern.",
                    fix=f"Provide a valid variable name after '{kw}'.",
                )
            )
            return stmt_end

        nxt = self.tokens[kw_idx + 1]
        if nxt.kind not in ("IDENT",) and not (nxt.kind == "PUNCT" and nxt.value in ("{", "[")):
            self.syntax_issues.append(
                JsSyntaxIssue(
                    line=kw_tok.line,
                    message=f"Invalid '{kw}' declaration target on line {kw_tok.line}.",
                    why="Expected an identifier or destructuring pattern after variable declaration keyword.",
                    fix="Fix the variable name syntax.",
                )
            )
            return stmt_end

        target_scope = self._var_target_scope(scope) if kw == "var" else scope
        inside_block = kw == "var" and target_scope.scope_id != scope.scope_id

        # Walk comma-separated declarators `[pattern (= init)?]`
        cur = kw_idx + 1
        while cur < stmt_end:
            if self.tokens[cur].kind == "PUNCT" and self.tokens[cur].value in (";", ",", ")"):
                cur += 1
                continue

            # Identify pattern bounds before `=`, `,`, or stmt_end
            pat_start = cur
            depth = 0
            assign_idx: Optional[int] = None
            item_end = stmt_end

            p = pat_start
            while p < stmt_end:
                t = self.tokens[p]
                if t.kind == "PUNCT":
                    if t.value in ("(", "[", "{"):
                        depth += 1
                    elif t.value in (")", "]", "}"):
                        if depth == 0:
                            item_end = p
                            break
                        depth -= 1
                    elif depth == 0:
                        if t.value == "=" and assign_idx is None:
                            assign_idx = p
                        elif t.value in (",", ";"):
                            item_end = p
                            break
                p += 1

            pat_end = assign_idx if assign_idx is not None else item_end
            if assign_idx is not None:
                rhs_start = assign_idx + 1
                rhs_end = item_end
                init_kind = self._classify_initializer_kind(rhs_start, rhs_end)
                init_end_tok = max(rhs_start, rhs_end - 1)
                init_line = self.tokens[init_end_tok].line if init_end_tok < self.n else kw_tok.line
                has_init = True
            else:
                init_kind = "none"
                init_end_tok = max(pat_start, pat_end - 1)
                init_line = kw_tok.line
                has_init = False

            self._register_binding_names(
                start_idx=pat_start,
                end_idx=pat_end,
                target_scope=target_scope,
                kind=kw,
                decl_line=kw_tok.line,
                init_end_idx=init_end_tok,
                init_line=init_line,
                decl_idx=kw_idx,
                inside_block_in_function=inside_block,
                declaring_block_id=scope.scope_id,
                has_initializer=has_init,
                init_kind=init_kind,
            )

            # Parse expressions/scopes inside RHS (e.g. function expressions `{ ... }`) cleanly
            if assign_idx is not None:
                self._walk_range(assign_idx + 1, item_end, scope)

            cur = item_end + 1

        return stmt_end

    def _parse_function(self, fn_idx: int, scope: JsScope, is_declaration: bool) -> int:
        fn_tok = self.tokens[fn_idx]
        cur = fn_idx + 1
        if cur < self.n and self.tokens[cur].kind == "PUNCT" and self.tokens[cur].value == "*":
            cur += 1

        fn_name: Optional[str] = None
        if cur < self.n and self.tokens[cur].kind == "IDENT":
            fn_name = self.tokens[cur].value
            self.token_skip_refs.add(cur)
            cur += 1

        if is_declaration and fn_name:
            target_scope = self._var_target_scope(scope)
            target_scope.add_declaration(
                JsDeclaration(
                    name=fn_name,
                    kind="function",
                    scope_id=target_scope.scope_id,
                    decl_token_idx=fn_idx,
                    decl_line=fn_tok.line,
                    init_end_token_idx=target_scope.start_token_idx,
                    init_line=target_scope.start_line,
                    init_kind="function_declaration",
                    has_initializer=True,
                )
            )

        # Locate parameter list `(...)` and `{ ... }`
        while cur < self.n and not (self.tokens[cur].kind == "PUNCT" and self.tokens[cur].value == "("):
            if self.tokens[cur].kind == "PUNCT" and self.tokens[cur].value in ("{", ";"):
                return cur
            cur += 1

        if cur >= self.n or self.tokens[cur].value != "(":
            return cur

        paren_close = self._find_matching(cur, "(", ")")
        body_open = paren_close + 1
        while body_open < self.n and not (self.tokens[body_open].kind == "PUNCT" and self.tokens[body_open].value == "{"):
            body_open += 1

        if body_open >= self.n:
            return paren_close + 1

        body_close = self._find_matching(body_open, "{", "}")
        fn_scope = self._new_scope("function", scope, body_open, self.tokens[body_open].line)
        fn_scope.end_token_idx = body_close
        fn_scope.end_line = self.tokens[body_close].line

        if is_declaration and fn_name:
            self.func_decl_body_scopes[fn_scope.scope_id] = (self._var_target_scope(scope).scope_id, fn_name)

        # Register parameters inside fn_scope
        self._register_binding_names(
            start_idx=cur + 1,
            end_idx=paren_close,
            target_scope=fn_scope,
            kind="param",
            decl_line=fn_tok.line,
            init_end_idx=body_open,
            init_line=self.tokens[body_open].line,
            decl_idx=cur,
            has_initializer=True,
        )
        # Assign param tokens scope to fn_scope
        for k in range(cur, body_close + 1):
            self.token_scope[k] = fn_scope

        self._walk_range(body_open + 1, body_close, fn_scope)
        return body_close + 1

    def _parse_class(self, class_idx: int, scope: JsScope, is_declaration: bool) -> int:
        class_tok = self.tokens[class_idx]
        cur = class_idx + 1
        class_name: Optional[str] = None
        if cur < self.n and self.tokens[cur].kind == "IDENT":
            class_name = self.tokens[cur].value
            self.token_skip_refs.add(cur)
            cur += 1

        # Scan extends clause before `{`
        extends_start = cur
        while cur < self.n and not (self.tokens[cur].kind == "PUNCT" and self.tokens[cur].value == "{"):
            if self.tokens[cur].kind == "PUNCT" and self.tokens[cur].value == ";":
                return cur + 1
            cur += 1

        if cur >= self.n:
            self.syntax_issues.append(
                JsSyntaxIssue(
                    line=class_tok.line,
                    message=f"Incomplete 'class' definition starting at line {class_tok.line}.",
                    why="Class declaration is missing its '{ ... }' body.",
                    fix="Add a '{ ... }' class body.",
                )
            )
            return self.n

        body_close = self._find_matching(cur, "{", "}")
        if is_declaration and class_name:
            scope.add_declaration(
                JsDeclaration(
                    name=class_name,
                    kind="class",
                    scope_id=scope.scope_id,
                    decl_token_idx=class_idx,
                    decl_line=class_tok.line,
                    init_end_token_idx=body_close,
                    init_line=self.tokens[body_close].line,
                    init_kind="class_declaration",
                    has_initializer=True,
                )
            )

        # Allow extends expressions to be checked in enclosing scope
        if extends_start < cur:
            for k in range(extends_start, cur):
                if self.tokens[k].kind == "KEYWORD" and self.tokens[k].value == "extends":
                    self.token_skip_refs.add(k)

        class_scope = self._new_scope("class", scope, cur, self.tokens[cur].line)
        class_scope.end_token_idx = body_close
        class_scope.end_line = self.tokens[body_close].line
        for k in range(cur, body_close + 1):
            self.token_scope[k] = class_scope

        # Mark method names inside class body as skipped refs, walk method bodies as functions
        k = cur + 1
        while k < body_close:
            t = self.tokens[k]
            if t.kind == "IDENT" and k + 1 < body_close and self.tokens[k + 1].value == "(":
                self.token_skip_refs.add(k)
                paren_end = self._find_matching(k + 1, "(", ")")
                b_open = paren_end + 1
                if b_open < body_close and self.tokens[b_open].value == "{":
                    b_close = self._find_matching(b_open, "{", "}")
                    m_scope = self._new_scope("function", class_scope, b_open, self.tokens[b_open].line)
                    m_scope.end_token_idx = b_close
                    m_scope.end_line = self.tokens[b_close].line
                    self._register_binding_names(
                        k + 2, paren_end, m_scope, "param", t.line, b_open, self.tokens[b_open].line, k + 1
                    )
                    for mk in range(k + 1, b_close + 1):
                        self.token_scope[mk] = m_scope
                    self._walk_range(b_open + 1, b_close, m_scope)
                    k = b_close + 1
                    continue
            k += 1

        return body_close + 1

    def _walk_range(self, start_idx: int, end_idx: int, scope: JsScope) -> None:
        i = start_idx
        while i < end_idx:
            self.token_scope[i] = scope
            tok = self.tokens[i]

            if tok.kind == "KEYWORD" and tok.value in ("var", "let", "const"):
                next_i = self._parse_var_let_const(i, scope)
                i = max(i + 1, next_i)
                continue

            if tok.kind == "KEYWORD" and tok.value == "function":
                is_decl = self._is_function_declaration(i)
                next_i = self._parse_function(i, scope, is_declaration=is_decl)
                i = max(i + 1, next_i)
                continue

            if tok.kind == "KEYWORD" and tok.value == "class":
                is_decl = not self._is_expr_context(i)
                next_i = self._parse_class(i, scope, is_declaration=is_decl)
                i = max(i + 1, next_i)
                continue

            if tok.kind == "KEYWORD" and tok.value == "for" and i + 1 < end_idx and self.tokens[i + 1].value == "(":
                paren_close = self._find_matching(i + 1, "(", ")")
                for_scope = self._new_scope("block", scope, i + 1, tok.line)
                for k in range(i + 1, min(end_idx, paren_close + 1)):
                    self.token_scope[k] = for_scope
                self._walk_range(i + 2, paren_close, for_scope)
                body_idx = paren_close + 1
                if body_idx < end_idx and self.tokens[body_idx].value == "{":
                    body_close = self._find_matching(body_idx, "{", "}")
                    for_scope.end_token_idx = body_close
                    for_scope.end_line = self.tokens[body_close].line
                    for k in range(body_idx, body_close + 1):
                        self.token_scope[k] = for_scope
                    self._walk_range(body_idx + 1, body_close, for_scope)
                    i = body_close + 1
                    continue
                i = paren_close + 1
                continue

            if tok.kind == "KEYWORD" and tok.value == "catch" and i + 1 < end_idx and self.tokens[i + 1].value == "(":
                paren_close = self._find_matching(i + 1, "(", ")")
                body_idx = paren_close + 1
                if body_idx < end_idx and self.tokens[body_idx].value == "{":
                    body_close = self._find_matching(body_idx, "{", "}")
                    c_scope = self._new_scope("block", scope, body_idx, self.tokens[body_idx].line)
                    c_scope.end_token_idx = body_close
                    c_scope.end_line = self.tokens[body_close].line
                    self._register_binding_names(
                        i + 2, paren_close, c_scope, "catch_param", tok.line, body_idx, self.tokens[body_idx].line, i + 1
                    )
                    for k in range(i + 1, body_close + 1):
                        self.token_scope[k] = c_scope
                    self._walk_range(body_idx + 1, body_close, c_scope)
                    i = body_close + 1
                    continue

            if tok.kind == "KEYWORD" and tok.value in ("import", "export"):
                stmt_end = self._find_declaration_stmt_end(i + 1)
                for k in range(i, stmt_end):
                    self.token_skip_refs.add(k)
                i = stmt_end
                continue

            # Standalone `{ ... }` block statement vs object literal `{ a: 1 }`
            if tok.kind == "PUNCT" and tok.value == "{":
                close_brace = self._find_matching(i, "{", "}")
                if not self._is_expr_context(i):
                    b_scope = self._new_scope("block", scope, i, tok.line)
                    b_scope.end_token_idx = close_brace
                    b_scope.end_line = self.tokens[close_brace].line
                    for k in range(i, close_brace + 1):
                        self.token_scope[k] = b_scope
                    self._walk_range(i + 1, close_brace, b_scope)
                    i = close_brace + 1
                    continue
                # Object literal: mark keys `{ key: val }` as skipped references
                self._walk_range(i + 1, close_brace, scope)
                i = close_brace + 1
                continue

            i += 1

    def _is_non_variable_reference(self, idx: int) -> bool:
        if idx in self.token_skip_refs:
            return True
        if idx > 0 and self.tokens[idx - 1].kind == "PUNCT" and self.tokens[idx - 1].value in (".", "?."):
            return True
        # Object literal key `{ name: value }` -> skip `name` when followed by `:` inside expr/block?
        # Exclude ternary `cond ? a : b` by confirming previous token is `{` or `,`
        if (
            idx + 1 < self.n
            and self.tokens[idx + 1].kind == "PUNCT"
            and self.tokens[idx + 1].value == ":"
            and idx > 0
            and self.tokens[idx - 1].kind == "PUNCT"
            and self.tokens[idx - 1].value in ("{", ",")
        ):
            return True
        return False

    def _is_simple_assignment_target(self, idx: int) -> bool:
        """True only for plain write LHS `ident = expr` (not `==`, `+=`, etc.)."""
        if idx + 1 >= self.n:
            return False
        nxt = self.tokens[idx + 1]
        return nxt.kind == "PUNCT" and nxt.value == "="

    def _is_call_reference(self, idx: int) -> bool:
        return idx + 1 < self.n and self.tokens[idx + 1].kind == "PUNCT" and self.tokens[idx + 1].value == "("

    def _is_new_reference(self, idx: int) -> bool:
        return idx > 0 and self.tokens[idx - 1].kind == "KEYWORD" and self.tokens[idx - 1].value == "new"

    def _enclosing_function_scope(self, scope: JsScope) -> Optional[JsScope]:
        cur: Optional[JsScope] = scope
        while cur is not None:
            if cur.kind == "function":
                return cur
            cur = cur.parent
        return None

    def _resolve_binding(self, name: str, start_scope: JsScope) -> Optional[Tuple[JsScope, List[JsDeclaration]]]:
        cur: Optional[JsScope] = start_scope
        while cur is not None:
            if name in cur.declarations:
                return cur, cur.declarations[name]
            cur = cur.parent
        return None

    def _collect_early_calls(self) -> None:
        """Track calls to hoisted function declarations so early invocations can still surface TDZ bugs."""
        for idx, tok in enumerate(self.tokens):
            if tok.kind != "IDENT" or self._is_non_variable_reference(idx) or not self._is_call_reference(idx):
                continue
            scope = self.token_scope[idx]
            resolved = self._resolve_binding(tok.value, scope)
            if resolved:
                decl_scope, decls = resolved
                if any(d.kind == "function" for d in decls):
                    self.early_calls_by_fn_decl.setdefault((decl_scope.scope_id, tok.value), []).append(idx)

    def _check_out_of_block_references(
        self, idx: int, tok: JsToken, ref_scope: JsScope
    ) -> Optional[Dict[str, Any]]:
        """
        Detect references after a `{ ... }` block that target a `let`/`const` declared
        inside that earlier sibling block when no binding exists in the enclosing scope chain.
        """
        name = tok.value
        for decl in self.all_declarations:
            if decl.name != name or decl.kind not in ("let", "const", "class"):
                continue
            if decl.declaring_block_id and decl.scope_id == ref_scope.scope_id:
                continue
            # Check if decl lived in a child block that already closed before `idx`
            if decl.init_end_token_idx < idx and decl.decl_token_idx >= ref_scope.start_token_idx and idx <= ref_scope.end_token_idx:
                # Verify ref_scope is ancestor of decl's block (and decl isn't inside an unrelated function)
                d_scope = self.token_scope[decl.decl_token_idx]
                if d_scope.kind == "block" and d_scope.parent is not None and d_scope.parent.scope_id == ref_scope.scope_id:
                    return {
                        "type": "BlockScopeError",
                        "line": tok.line,
                        "message": (
                            f"'{name}' is {decl.kind}-declared inside a block (line {decl.decl_line}) "
                            f"and is referenced outside that block at line {tok.line}."
                        ),
                        "why": (
                            f"Unlike 'var' (which is function-scoped), '{decl.kind}' is strictly block-scoped "
                            f"and does not exist outside its enclosing '{{ ... }}' block, causing a ReferenceError."
                        ),
                        "fix": (
                            f"Declare '{decl.kind} {name}' in the outer scope before the block if it is needed "
                            "afterwards, or move this usage inside the block."
                        ),
                        "concept": "JavaScript Hoisting",
                    }
        return None

    def analyze(self) -> List[Dict[str, Any]]:
        """Run scope construction, hoisting resolution, and finding generation."""
        if self.n == 0:
            return []

        self._walk_range(0, self.n, self.program_scope)
        self._collect_early_calls()

        findings: List[Dict[str, Any]] = []
        for err in self.syntax_issues:
            findings.append({
                "type": "SyntaxError",
                "line": err.line,
                "message": err.message,
                "why": err.why,
                "fix": err.fix,
                "concept": "JavaScript Syntax",
            })

        for idx, tok in enumerate(self.tokens):
            if tok.kind != "IDENT" or self._is_non_variable_reference(idx):
                continue

            ref_scope = self.token_scope[idx]
            resolved = self._resolve_binding(tok.value, ref_scope)

            if resolved is None:
                if not self._is_simple_assignment_target(idx):
                    block_err = self._check_out_of_block_references(idx, tok, ref_scope)
                    if block_err:
                        findings.append(block_err)
                continue

            decl_scope, decls = resolved
            # Pick the earliest relevant declaration in that scope
            primary_decl = min(decls, key=lambda d: d.decl_token_idx)

            # Parameters, catch bindings, imports, and hoisted function declarations are ready at entry
            if primary_decl.kind in ("function", "param", "catch_param", "import"):
                continue

            # Determine if this reference executes strictly inside a nested function body
            ref_fn_scope = self._enclosing_function_scope(ref_scope)
            decl_fn_scope = self._enclosing_function_scope(decl_scope)

            if ref_fn_scope is not None and ref_fn_scope is not decl_fn_scope:
                # Reference is inside a nested function referencing an outer-scope variable.
                # Only flag if the function declaration itself is invoked BEFORE outer init completes!
                body_meta = self.func_decl_body_scopes.get(ref_fn_scope.scope_id)
                if not body_meta:
                    continue
                call_indices = self.early_calls_by_fn_decl.get(body_meta, [])
                early_call = next(
                    (c for c in call_indices if c < primary_decl.decl_token_idx),
                    None,
                )
                if early_call is None:
                    continue
                # Report on the offending early reference/call context cleanly
                report_line = self.tokens[early_call].line
            else:
                report_line = tok.line

            # Reference occurs AFTER initialization finished -> safe & valid!
            init_boundary = (
                primary_decl.init_end_token_idx
                if primary_decl.has_initializer
                else primary_decl.decl_token_idx
            )
            if idx > init_boundary:
                continue

            is_write_only = self._is_simple_assignment_target(idx)
            is_call = self._is_call_reference(idx)
            is_new = self._is_new_reference(idx)

            if primary_decl.kind == "class":
                action = f"instantiated with 'new {tok.value}()'" if is_new else f"referenced"
                findings.append({
                    "type": "ClassHoistingError",
                    "line": report_line,
                    "message": (
                        f"Class '{tok.value}' is {action} at line {report_line} before its class "
                        f"declaration at line {primary_decl.decl_line}."
                    ),
                    "why": (
                        "JavaScript class declarations are hoisted in scope binding only and remain in the "
                        "Temporal Dead Zone (TDZ) until evaluation completes, throwing a ReferenceError."
                    ),
                    "fix": f"Move the 'class {tok.value}' declaration above line {report_line}.",
                    "concept": "JavaScript Hoisting",
                })
                continue

            if primary_decl.kind == "var":
                if is_call and primary_decl.init_kind == "function_expression":
                    findings.append({
                        "type": "FunctionExpressionHoistingError",
                        "line": report_line,
                        "message": (
                            f"Function expression '{tok.value}' is called at line {report_line} before "
                            f"its 'var' initialization at line {primary_decl.decl_line}."
                        ),
                        "why": (
                            f"The 'var {tok.value}' declaration is hoisted with value 'undefined', while its "
                            "function expression assignment stays at line "
                            f"{primary_decl.decl_line}, causing a runtime TypeError ('{tok.value} is not a function')."
                        ),
                        "fix": (
                            f"Move the call below line {primary_decl.decl_line} or declare "
                            f"'function {tok.value}(...)' if hoisting is intended."
                        ),
                        "concept": "JavaScript Hoisting",
                    })
                elif not is_write_only:
                    scope_note = (
                        f"Even though 'var {tok.value}' is declared inside a '{{ ... }}' block at line "
                        f"{primary_decl.decl_line}, 'var' hoists out to the enclosing function/global scope"
                        if primary_decl.inside_block_in_function
                        else f"The 'var {tok.value}' declaration at line {primary_decl.decl_line} is hoisted "
                             "while its initialization remains in place"
                    )
                    findings.append({
                        "type": "VarHoistingWarning",
                        "line": report_line,
                        "message": (
                            f"Variable '{tok.value}' declared with 'var' at line {primary_decl.decl_line} "
                            f"is accessed before initialization at line {report_line}."
                        ),
                        "why": (
                            f"{scope_note}, so '{tok.value}' evaluates to 'undefined' rather than its assigned value."
                        ),
                        "fix": (
                            f"Declare and initialize '{tok.value}' before line {report_line}, and prefer "
                            "'const' or 'let' to avoid silent 'undefined' hoisting bugs."
                        ),
                        "concept": "JavaScript Hoisting",
                    })
                continue

            # `let` or `const` in Temporal Dead Zone (either read or assignment before decl line)
            if primary_decl.kind in ("let", "const"):
                if is_call and primary_decl.init_kind == "function_expression":
                    findings.append({
                        "type": "FunctionExpressionHoistingError",
                        "line": report_line,
                        "message": (
                            f"Function expression '{tok.value}' is called at line {report_line} before "
                            f"its '{primary_decl.kind}' initialization at line {primary_decl.decl_line}."
                        ),
                        "why": (
                            f"Unlike 'function' declarations, '{primary_decl.kind} {tok.value} = ...' is not "
                            "callable prior to evaluation and remains in the Temporal Dead Zone (TDZ), "
                            "throwing a ReferenceError."
                        ),
                        "fix": (
                            f"Call '{tok.value}()' after line {primary_decl.decl_line}, or convert it to a "
                            f"hoisted 'function {tok.value}(...)' declaration."
                        ),
                        "concept": "JavaScript Hoisting",
                    })
                elif primary_decl.init_kind == "class_expression" and (is_new or not is_write_only):
                    findings.append({
                        "type": "ClassHoistingError",
                        "line": report_line,
                        "message": (
                            f"Class expression '{tok.value}' is referenced at line {report_line} before "
                            f"its '{primary_decl.kind}' initialization at line {primary_decl.decl_line}."
                        ),
                        "why": (
                            f"The '{primary_decl.kind}' binding for class '{tok.value}' is in the Temporal "
                            "Dead Zone until line "
                            f"{primary_decl.decl_line}, throwing a ReferenceError."
                        ),
                        "fix": f"Define '{tok.value}' above line {report_line}.",
                        "concept": "JavaScript Hoisting",
                    })
                else:
                    findings.append({
                        "type": "TemporalDeadZoneError",
                        "line": report_line,
                        "message": (
                            f"'{primary_decl.kind}' variable '{tok.value}' is accessed in the Temporal Dead "
                            f"Zone (TDZ) at line {report_line} before initialization at line {primary_decl.decl_line}."
                        ),
                        "why": (
                            f"'{primary_decl.kind}' declarations are block-scoped and remain in the Temporal "
                            f"Dead Zone (TDZ) so they cannot be read or assigned before line "
                            f"{primary_decl.decl_line} completes, throwing a ReferenceError."
                        ),
                        "fix": (
                            f"Move the '{primary_decl.kind} {tok.value}' declaration above line {report_line}."
                        ),
                        "concept": "JavaScript Hoisting",
                    })

        return findings


def is_javascript_filename(filename: Optional[str]) -> bool:
    """Return True if filename carries a recognized JavaScript file extension."""
    if not filename or not isinstance(filename, str):
        return False
    lower = filename.strip().lower()
    return any(lower.endswith(ext) for ext in JS_EXTENSIONS)


def check_js_hoisting(code: str) -> List[Dict[str, Any]]:
    """
    Analyze JavaScript source code statically for hoisting, TDZ, block-scope,
    function expression, and class initialization issues.
    """
    if not isinstance(code, str) or not code.strip():
        return []
    tokens, lex_syntax_issues = tokenize_javascript(code)
    analyzer = _JsHoistingAnalyzer(tokens)
    analyzer.syntax_issues.extend(lex_syntax_issues)
    return analyzer.analyze()
