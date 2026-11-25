# JavaScript Hoisting Analysis in EdgeMind

## What Is JavaScript Hoisting?

JavaScript evaluates scope declarations during compilation before executing statements line-by-line. **Hoisting** refers to binding a variable, function, or class name to its enclosing scope during compilation—while initialization behavior differs depending on how the identifier is declared (`var`, `function`, `let`, `const`, or `class`).

---

## Covered Hoisting & Scoping Behaviors

### 1. `var` Hoisting
- Declarations (`var user`) hoist to the nearest enclosing **function** or **program (global)** scope and are initialized with `undefined` at scope entry.
- Assignments (`= "Rithwik"`) stay at their original line.
- Reading a `var` variable before its initialization evaluates silently to `undefined`, producing subtle bugs.

```js
console.log(user); // VarHoistingWarning (line 1): evaluates to undefined
var user = "Rithwik";
```

### 2. Function Declaration Hoisting
- Function declarations (`function greet() { ... }`) are hoisted **with their full body/value** to their enclosing function or program scope.
- Calling a function declaration prior to its definition is **valid JavaScript** and EdgeMind does **not** report an error.

```js
greet(); // Valid: prints "Hello"

function greet() {
  console.log("Hello");
}
```

### 3. `let` and `const` Temporal Dead Zone (TDZ)
- `let` and `const` declarations are bound cleanly at block/function entry, **not initialized**, and remain inside the **Temporal Dead Zone (TDZ)** from the start of the enclosing scope until evaluation reaches the declaration line.
- Accessing or assigning a `let`/`const` identifier before its initialization line throws a `ReferenceError` at runtime (`TemporalDeadZoneError`).

```js
console.log(value); // TemporalDeadZoneError (line 1): ReferenceError in TDZ
let value = 10;
```

### 4. Block Scope vs. Function Scope
- `let` and `const` are **block-scoped** (`{ ... }`), whereas `var` is **function-scoped** and escapes `{ ... }` blocks to the enclosing function or global scope.
- Referencing a block-scoped `let`/`const` variable outside its `{ ... }` block fails with `ReferenceError` (`BlockScopeError`), while accessing a `var` before its block-level declaration yields `undefined` (`VarHoistingWarning`).
- Valid block-scoped code (using `let`/`const` inside `{ ... }` after initialization and `var` inside the function after initialization) produces zero findings.

### 5. Function Expression Hoisting
- Assigning a function expression or arrow function (`const run = function() {}`, `let run = () => {}`, `var run = function() {}`) follows variable hoisting semantics rather than function-declaration hoisting.
- Calling `run()` prior to initialization raises `ReferenceError` (`const`/`let` TDZ) or `TypeError` (`var` hoisted as `undefined`), reported by EdgeMind as `FunctionExpressionHoistingError`.

### 6. Class Hoisting & TDZ
- `class` declarations (`class User {}`) and class expressions (`const User = class {}`) are hoisted in binding name only and remain uninitialized inside the **Temporal Dead Zone** until the class definition is evaluated.
- Instantiating (`new User()`) or referencing `User` before its definition raises a `ReferenceError` (`ClassHoistingError`).

---

## Architecture & Pipeline Integration

- **Analyzer Module**: [`core/js_hoisting.py`](file:///C:/Users/DELL/Projects/EdgeMind/core/js_hoisting.py) implements a zero-dependency pure-Python JavaScript lexical tokenizer (`tokenize_javascript`) and two-pass scope/AST analyzer (`_JsHoistingAnalyzer` / `check_js_hoisting`), running completely statically with zero code execution.
- **Pipeline Routing**:
  - `analyze_code(...)` in [`core/service.py`](file:///C:/Users/DELL/Projects/EdgeMind/core/service.py) and `analyze_file(...)` in [`core/analyzer.py`](file:///C:/Users/DELL/Projects/EdgeMind/core/analyzer.py) detect `.js`, `.mjs`, `.cjs`, and `.jsx` filenames (or explicit `language="javascript"` in `AnalyzeCodeRequest` / `POST /api/v1/analyze`) and route directly to `check_js_hoisting` without invoking Python's `compile()`.
  - Standard findings serialize into `AnalysisReport` (`detailed_errors`, `detailed_warnings`, `score`, `summary`) cleanly.
- **Severity Mapping** (`core/analyzer.py`):
  - **Errors** (`ERROR_TYPES`): `TemporalDeadZoneError`, `FunctionExpressionHoistingError`, `ClassHoistingError`, `BlockScopeError`, `SyntaxError`.
  - **Warnings** (`WARNING_TYPES`): `VarHoistingWarning`.

---

## Known Limitations

- **Intra-file static analysis only**: ES module cross-file `import`/`export` execution ordering is not resolved across multiple files.
- **TypeScript syntax**: TypeScript-specific type annotations (`interface`, `type`, `as`, generics on expressions) are not supported by the JavaScript hoisting analyzer.
- **Dynamic call graphs inside functions**: Direct early calls (`helper()` before an outer `const x = 1`) are detected for top-level function declarations; deeply nested indirect/callback invocation chains (e.g. passing callbacks through event emitters) are intentionally excluded to avoid false positives.
- **Web Dashboard Workspace Language Selector**: The React Workspace language dropdown remains Python-only (`workspaceConfig.ts`) unless analyzing persisted or API-submitted `.js` reports directly through the backend `POST /api/v1/analyze` endpoint or viewing returned `AnalysisReport` findings.
