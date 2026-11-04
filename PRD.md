# EdgeMind — Product Requirements Document (PRD)

**Product:** EdgeMind — Adaptive Test Intelligence  
**Release:** v1.0.0  
**Document status:** Project submission  
**Repository:** https://github.com/whiskerwolf/EdgeMind

---

## 1. Product Overview

EdgeMind is a Chrome extension supported by a local FastAPI service. It analyzes programming-problem context, identifies potential test-coverage gaps, and proposes candidate edge-case inputs. Its purpose is to help developers think beyond the visible examples before submitting a solution.

EdgeMind uses static analysis and constraint-aware test-input synthesis. It does **not** execute user-submitted code or generated candidate inputs, and it does not claim that a candidate's expected output has been verified.

## 2. Problem Statement

Programming-problem pages commonly provide only a small number of examples. Those examples may not cover important boundaries, unusual but valid inputs, or relationships between parameters. Developers must identify these cases manually, which can lead to incomplete testing.

EdgeMind aims to make this reasoning more systematic by extracting available problem context and suggesting additional inputs that target likely coverage gaps.

## 3. Product Goals

1. Detect supported programming-problem pages and extract relevant problem context.
2. Identify public examples and supported input constraints.
3. Represent parameter bounds and relationships where they can be reliably extracted.
4. Identify potential coverage gaps relative to the examples already available.
5. Synthesize and rank useful candidate inputs.
6. Distinguish valid inputs from deliberate robustness probes and cases whose validity cannot be established.
7. Provide a clear Chrome popup experience and a local API connection.
8. Preserve a static-only safety model.

## 4. Intended Users

- Students learning data structures and algorithms.
- Programmers practicing on coding-challenge platforms.
- Developers who want a structured checklist of additional inputs to consider.

## 5. User Experience

### Primary workflow

1. The user opens a supported programming-problem page in Chrome.
2. The extension detects the problem context and programming language where available.
3. The extension extracts public examples and supported constraints.
4. The user opens EdgeMind and requests analysis.
5. EdgeMind presents the analysis mode, detected context, constraints, coverage gaps, and ranked candidate inputs.
6. The user can inspect candidate details and copy the full input for independent use.

### Operating modes

**Baseline-Driven Intelligence:** Used when public examples are available. The examples provide the baseline against which potential coverage gaps are assessed.

**Context-Based Intelligence:** Used when public examples are unavailable or insufficient. The system uses the detected problem context and supported constraints to propose candidate inputs. The system must communicate uncertainty when the available context is incomplete.

## 6. Functional Requirements

| ID | Requirement |
|---|---|
| FR-01 | Detect supported programming-problem pages. |
| FR-02 | Identify the problem title or slug and the selected language when available. |
| FR-03 | Extract public example inputs from supported page structures. |
| FR-04 | Extract supported constraints and associate them with relevant parameters. |
| FR-05 | Identify potential coverage gaps, including relevant boundary and pattern cases. |
| FR-06 | Generate candidate inputs that respect supported constraints and parameter relationships. |
| FR-07 | Rank candidate inputs by relevance. |
| FR-08 | Classify candidates as `VALID`, `ROBUSTNESS_PROBE`, or `CONSTRAINT_VALIDITY_UNKNOWN`. |
| FR-09 | Display candidate summaries and allow inspection/copying of full input data. |
| FR-10 | Display backend connection state and handle unavailable-service conditions. |
| FR-11 | Provide static code-hygiene analysis separately from test-input intelligence. |
| FR-12 | Support local backend startup through the configured Windows/Chrome integration. |

## 7. Non-Functional Requirements

- **Safety:** User-submitted code and generated candidate inputs must not be executed by EdgeMind.
- **Truthfulness:** Generated expected outputs remain unverified; the UI must not imply otherwise.
- **Locality:** The backend listens on `127.0.0.1:8000` rather than a public network interface.
- **Usability:** Large inputs should be summarized in the popup, with access to the complete input.
- **Reliability:** The extension should communicate backend connection failures clearly.
- **Maintainability:** Parsing, gap detection, synthesis, ranking, API, and extension responsibilities should remain separated.
- **Compatibility:** The Chrome extension uses Manifest V3.

## 8. Candidate Classification

- **VALID:** The candidate satisfies all supported input constraints checked by EdgeMind. This does not mean its expected output is known or that it proves a solution correct.
- **ROBUSTNESS_PROBE:** The candidate deliberately tests behavior outside one or more stated input constraints.
- **CONSTRAINT_VALIDITY_UNKNOWN:** Available information is insufficient to determine whether the candidate satisfies all relevant constraints.

## 9. Out of Scope

- Executing user-submitted solutions.
- Executing generated candidate inputs.
- Automatically asserting expected outputs for generated inputs.
- Guaranteeing solution correctness or completeness of test coverage.
- Replacing the programming platform's compiler, judge, or submission system.

## 10. Success Criteria

The product is considered to meet its intended scope when:
- The extension detects supported problem context.
- Extracted examples and constraints are displayed with appropriate uncertainty.
- Candidate generation respects supported parameter bounds and relationships.
- Candidate classifications are consistent with the constraints known to the system.
- The UI accurately states that expected outputs are unverified.
- The static-only execution invariant is preserved.

## 11. Known Limitations

- Page structure and constraint wording can change, which may affect extraction.
- Natural-language semantic guarantees may not always be fully formalized.
- Some constraints may remain partially parsed or unresolved.
- Candidate generation identifies useful inputs but does not prove that all important cases have been covered.
- Expected outputs for synthesized candidates are not verified by execution.

## 12. Release Information

The project release is identified as **EdgeMind v1.0.0**. The source repository is:

https://github.com/whiskerwolf/EdgeMind
