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

**Operating System Security & Code Signing:**
- On Windows systems with Smart App Control (SAC) enabled, custom compiled binaries like `edgemind_native_host.exe` require an Authenticode code-signing certificate for production distribution to avoid execution blocks (`WinError 4551`).
- The EdgeMind extension architecture is resilient and designed with graceful degradation: if Native Messaging is blocked or unavailable, the extension automatically falls back to direct loopback HTTP polling (`http://127.0.0.1:8000/health`).

### 4.3 FastAPI Backend — `core/api.py`

The backend exposes the HTTP interface used by the extension.

Service endpoints include:
- **Health & Core Intelligence**:
  - `GET /health` — Service availability check.
  - `POST /api/v1/edgemind/analyze` — Static analysis, constraint parsing, and candidate generation with automated report persistence.
- **Authentication & Multi-Tenancy**:
  - `POST /api/v1/auth/register` — User registration with password complexity enforcement.
  - `POST /api/v1/auth/login` — Authentication returning access and refresh token pair.
  - `POST /api/v1/auth/refresh` — Single-use refresh token rotation with reuse detection.
  - `POST /api/v1/auth/logout` — Token revocation.
  - `GET /api/v1/users/me`, `PATCH /api/v1/users/me` — Profile retrieval and update.
- **Projects & Analysis History**:
  - `GET /api/v1/projects`, `POST /api/v1/projects` — Multi-tenant project workspace management.
  - `GET /api/v1/analyses`, `GET /api/v1/analyses/{analysis_id}`, `POST /api/v1/analyses` — Session audit history.
- **PostgreSQL JSONB Report Documents**:
  - `GET /api/v1/analyses/{analysis_id}/report` — Full detailed test intelligence report document.
  - `GET /api/v1/analyses/{analysis_id}/candidates` — Synthesized candidate pool and classification summaries.
  - `GET /api/v1/analyses/{analysis_id}/coverage-gaps` — Boundary gaps and constraint breakdowns.
  - `DELETE /api/v1/analyses/{analysis_id}/report` — Report deletion while preserving session audit metadata.
  - `GET /api/v1/reports` — Paginated multi-tenant report history with user ownership isolation.

The backend is configured to listen on `127.0.0.1:8000`.

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

### 4.6 Database & Persistence Architecture — PostgreSQL 16 & JSONB Document Store

EdgeMind implements a unified PostgreSQL 16 persistence architecture combining relational tables and native JSONB document storage:
- **Relational Entities (`core/database/models/`)**: Manages structured accounts (`users`), tenant scopes (`projects`), catalog items (`problems`), and execution sessions (`analysis_sessions`).
- **JSONB Document Store (`analysis_reports`)**: Stores full test intelligence reports, synthesized edge-case candidates, coverage gaps, parsed constraints, and code metrics within native PostgreSQL `JSONB` columns (`report_data`), accelerated via a PostgreSQL GIN index (`USING gin (report_data jsonb_path_ops)`).
- **Alembic Database Migrations (`migrations/versions/`)**: Sequential, reversible schema migrations (001 initial tables, 002 auth/multi-tenancy, 003 storage status, 004 PostgreSQL JSONB report store).
- **Graceful Portability**: Employs SQLAlchemy 2.0 async engine with SQLite fallback (`aiosqlite` with SQLite JSON and PRAGMA foreign keys) for fast, zero-dependency local unit testing.

### 4.7 Authentication, Authorization & Multi-Tenancy

- **Password Security**: Uses Argon2id password hashing via `pwdlib`.
- **Stateless Tokens**: RFC 7519 compliant JSON Web Tokens (HMAC-SHA256) with short-lived access tokens (~15m) and cryptographically tracked refresh token rotation (~7d) with automatic reuse detection and family revocation.
- **Role-Based Access Control (RBAC)**: Supports `user` and `admin` roles.
- **Tenant Isolation**: Analysis sessions, projects, and report documents are strictly scoped to the owning user. Non-admin cross-tenant accesses return HTTP 404 to prevent resource enumeration.
- **Anonymous Extension Compatibility**: Supports unauthenticated Chrome extension analysis runs with null `user_id`, ensuring developer usability is never blocked.

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
- **Backend:** Local Python/FastAPI process (`core/api.py`).
- **Database:** Local or containerized PostgreSQL 16 (`docker-compose.yml`) with in-memory SQLite (`aiosqlite`) fallback for isolated test execution.
- **API address:** `http://127.0.0.1:8000`.
- **Windows integration:** PowerShell lifecycle scripts and the configured Native Messaging host under `scripts/`.
- **Repository:** https://github.com/whiskerwolf/EdgeMind

The original `extension/chrome/` directory is retained separately for legacy compatibility and is not the active EdgeMind extension directory.

## 8. Security and Safety Design

- The API listens on loopback (`127.0.0.1`) rather than all network interfaces.
- Chrome Native Messaging registration is scoped to the configured extension origin.
- The native host is used for a narrow local startup/health-check purpose.
- User-submitted code is inspected statically; it is never executed.
- Synthesized candidate inputs are never executed.
- Generated candidates carry unverified expected-output status (`expected_output = None`, `is_expected_output_verified = False`).
- User passwords are protected using Argon2id cryptographic hashing; tokens are validated via HMAC-SHA256 with single-use refresh token rotation.
- Multi-tenant data isolation: all projects, sessions, and report documents require authorization and return HTTP 404 for unauthorized tenant lookups.
- Privacy & data sanitization: raw user source code, passwords, JWTs, and authentication secrets are strictly scrubbed prior to report document persistence.
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
