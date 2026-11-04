# EdgeMind — High-Level Design (HLD)

**Product:** EdgeMind — Adaptive Test Intelligence  
**Release:** v1.0.0  
**Document status:** Project submission

---

## 1. Introduction

This document describes the high-level architecture of EdgeMind, a Chrome Manifest V3 extension backed by a local FastAPI service. The system analyzes programming-problem context and proposes ranked edge-case input candidates using static, constraint-aware processing.

## 2. Architecture Goals

- Separate browser-page detection, user interface, API orchestration, and intelligence logic.
- Keep the backend local to the user's machine.
- Make constraint extraction and candidate generation modular and testable.
- Preserve the invariant that user code and generated candidate inputs are not executed.
- Communicate uncertainty and unverified expected outputs explicitly.

## 3. System Context

```text
+------------------------- Chrome --------------------------+
|                                                           |
|  Programming Problem Page                                 |
|       |                                                   |
|       v                                                   |
|  EdgeMind Content Scripts ---> Problem Context             |
|       |                                                   |
|       v                                                   |
|  EdgeMind Popup <------> Background Service Worker         |
|                               |                           |
|                               | Chrome Native Messaging   |
+-------------------------------|---------------------------+
                                v
                    EdgeMind Native Host
                                |
                                | starts/checks local service
                                v
                    FastAPI Backend
                    127.0.0.1:8000
                                |
             +------------------+-------------------+
             |                  |                   |
             v                  v                   v
       Context/Example     Test Intelligence    Static Code
         Processing           Pipeline          Hygiene
                                |
             +------------------+-------------------+
             |                  |                   |
             v                  v                   v
       Constraint Parser   Gap Detector       Candidate Models
                                |
                                v
                         Candidate Synthesizer
                                |
                                v
                           Candidate Ranker
                                |
                                v
                         Analysis Response
                                |
                                v
                         EdgeMind Popup
```

## 4. Major Components

### 4.1 Chrome Extension — `extension/edgemind/`

The Manifest V3 extension is the user-facing layer.

Responsibilities:
- Detect supported problem pages and read relevant page context.
- Identify the selected programming language where available.
- Present extracted examples, constraints, coverage gaps, and candidate inputs.
- Request analysis from the local API.
- Display connection state and analysis results.
- Summarize large inputs and provide access to their full representation.

The extension includes a background service worker and uses Chrome Native Messaging for the configured backend-startup integration.

### 4.2 Native Messaging Host — `scripts/`

The native host provides a controlled bridge between the Chrome extension and Windows startup scripts.

Responsibilities:
- Accept messages using Chrome's length-prefixed JSON Native Messaging protocol.
- Check whether the local API is healthy.
- Request startup of the existing backend when required.
- Return a structured success or failure response.
- Keep diagnostic output out of the protocol's standard-output stream.

The native host is not the analysis engine. It only assists with local service lifecycle management.

### 4.3 FastAPI Backend — `core/api.py`

The backend exposes the HTTP interface used by the extension.

Known service endpoints include:
- `GET /health`
- `POST /api/v1/edgemind/analyze`

The backend is configured to listen on `127.0.0.1:8000`. The health endpoint reports whether the EdgeMind API is available.

### 4.4 Test Intelligence — `core/test_intelligence/`

The intelligence pipeline is responsible for interpreting problem constraints and proposing additional inputs.

Logical responsibilities include:
- Constraint parsing and parameter association.
- Cross-parameter relationship representation.
- Coverage-gap identification.
- Candidate input synthesis.
- Candidate validity classification.
- Candidate ranking and deduplication.

### 4.5 Static Code Hygiene

Static code hygiene is presented separately from test-input intelligence. It provides static inspection information and must not be represented as a solution-correctness score.

## 5. Analysis Modes

### Baseline-Driven Intelligence

When public examples are available:
1. Extract the available examples.
2. Parse supported constraints.
3. Compare the baseline examples with relevant coverage dimensions.
4. Identify gaps.
5. Generate and rank additional candidates.

### Context-Based Intelligence

When public examples are unavailable or insufficient:
1. Use detected problem context and supported constraints.
2. Identify candidate coverage dimensions.
3. Generate inputs only where enough context exists.
4. Preserve unresolved constraints and uncertainty.
5. Avoid claiming that the generated inputs are guaranteed valid when the system cannot establish that.

## 6. High-Level Data Flow

1. The user opens a supported problem page.
2. The extension collects problem metadata, examples, constraints, and language context available from the page.
3. The user requests analysis.
4. The extension sends the analysis request to the local API.
5. The backend normalizes and interprets the supplied context.
6. The intelligence pipeline identifies gaps and synthesizes candidates.
7. The backend returns structured analysis data.
8. The extension renders the results and exposes full candidate input where requested.

## 7. Deployment View

- **Browser:** Google Chrome with the unpacked Manifest V3 extension.
- **Extension source:** `extension/edgemind/`.
- **Backend:** Local Python/FastAPI process.
- **API address:** `http://127.0.0.1:8000`.
- **Windows integration:** PowerShell lifecycle scripts and the configured Native Messaging host under `scripts/`.
- **Repository:** https://github.com/whiskerwolf/EdgeMind

The original `extension/chrome/` directory is retained separately for legacy compatibility and is not the active EdgeMind extension directory.

## 8. Security and Safety Design

- The API listens on loopback (`127.0.0.1`) rather than all network interfaces.
- Chrome Native Messaging registration is scoped to the configured extension origin.
- The native host is used for a narrow local startup/health-check purpose.
- User-submitted code is inspected statically; it is not executed.
- Synthesized candidate inputs are not executed.
- Generated candidates carry unverified expected-output status.
- `VALID` means that supported constraints are satisfied; it does not mean that a solution has been tested or proven correct.

## 9. Reliability and Failure Handling

- The extension displays connection state rather than assuming the backend is available.
- The health endpoint is used to establish actual backend availability.
- The native host should avoid starting duplicate backend processes.
- Startup failures should return a useful error and write diagnostics to logs.
- Large candidate inputs are summarized in the popup to keep the interface usable.

## 10. Key Architectural Constraints

1. Do not introduce runtime execution of user code or candidates.
2. Do not expose the backend publicly.
3. Keep the extension UI separate from backend intelligence.
4. Do not report unparsed semantic constraints as fully parsed.
5. Do not report generated expected outputs as verified.
