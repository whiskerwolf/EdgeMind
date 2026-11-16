# EdgeMind — Low-Level Design (LLD)

**Product:** EdgeMind — Adaptive Test Intelligence  
**Release:** v1.0.0  
**Document status:** Project submission

---

## 1. Purpose

This document describes the main implementation units, their responsibilities, data flow, API interaction, candidate classifications, and safety rules in EdgeMind.

## 2. Repository Structure

```text
EdgeMind/
├── core/
│   ├── api.py
│   ├── config.py
│   ├── schemas.py
│   ├── auth/
│   │   ├── dependencies.py
│   │   ├── router.py
│   │   ├── schemas.py
│   │   ├── security.py
│   │   └── service.py
│   ├── database/
│   │   ├── base.py
│   │   ├── connection.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── problem.py
│   │   │   ├── analysis_session.py
│   │   │   └── analysis_report.py
│   │   └── repositories/
│   │       ├── user_repository.py
│   │       ├── project_repository.py
│   │       ├── problem_repository.py
│   │       ├── analysis_repository.py
│   │       └── report_repository.py
│   ├── reports/
│   │   └── builder.py
│   ├── routes/
│   │   ├── analyses.py
│   │   ├── reports.py
│   │   ├── projects.py
│   │   └── problems.py
│   └── test_intelligence/
│       ├── models.py
│       ├── constraint_parser.py
│       ├── gap_detector.py
│       ├── synthesizer.py
│       └── ranker.py
├── extension/
│   ├── edgemind/
│   │   ├── manifest.json
│   │   ├── popup/
│   │   └── scripts/
│   └── chrome/                 # Legacy extension; kept separate
├── migrations/
│   ├── env.py
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_auth_and_multi_tenancy.py
│       ├── 003_report_storage_status.py
│       └── 004_postgresql_jsonb_report_store.py
├── scripts/
│   ├── start_edgemind_api.ps1
│   ├── check_edgemind_api.ps1
│   ├── stop_edgemind_api.ps1
│   ├── edgemind_native_host.cs
│   ├── com.edgemind.native_host.json
│   ├── install_edgemind_native_messaging.ps1
│   └── uninstall_edgemind_native_messaging.ps1
├── tests/
├── README.md
└── requirements.txt
```

The exact set of files may evolve. The responsibilities below describe the logical implementation units.

## 3. Browser Extension Design

### 3.1 Manifest

`extension/edgemind/manifest.json` defines the Manifest V3 extension, popup, scripts, permissions, and local API access.

The configured extension uses the `nativeMessaging` permission for the local host integration. Host permissions are restricted to the local API origins used by the extension.

### 3.2 Content/Problem Detection

The page-facing extension logic reads supported programming-problem page information, such as:
- Problem title or slug.
- Selected programming language.
- Public example inputs.
- Visible problem statement and constraints where available.

Page extraction is dependent on the structure of the supported website. Missing or ambiguous content must not be silently invented.

### 3.3 Background Service Worker

`extension/edgemind/scripts/background.js` handles background lifecycle events and the Native Messaging request used to check/start the local backend.

It should:
1. Open a connection to the registered native host.
2. Send a structured startup/health request.
3. Receive a structured response.
4. Handle host errors or disconnects.
5. Avoid treating a request dispatch as proof that the API is healthy.

### 3.4 Popup

`extension/edgemind/popup/` contains the user-facing interface.

The popup presents:
- Backend connection state.
- Detected problem and language.
- Extracted examples and constraints.
- Analysis mode.
- Coverage gaps.
- Ranked candidate inputs.
- Candidate status and unverified-output notice.
- Static code-hygiene information.

Large candidate inputs are summarized; the user can inspect or copy the complete input.

## 4. Native Messaging Host

The native host source is located at `scripts/edgemind_native_host.cs`; the associated host manifest is `scripts/com.edgemind.native_host.json`.

### 4.1 Message Protocol

Chrome Native Messaging uses a four-byte little-endian length prefix followed by a UTF-8 JSON message.

Conceptual request:

```json
{
  "action": "ensure_backend"
}
```

Conceptual response:

```json
{
  "success": true,
  "status": "healthy",
  "url": "http://127.0.0.1:8000/health"
}
```

The exact supported request and response fields are determined by the installed native-host implementation.

### 4.2 Host Responsibilities

- Read the length-prefixed request from standard input.
- Parse the JSON message.
- Check the local health endpoint.
- Start the existing backend only when needed.
- Wait for health confirmation within a bounded timeout.
- Write one length-prefixed JSON response to standard output.
- Send logs and diagnostics to a file or standard error, never protocol standard output.

### 4.3 Registration

The installer registers the native host for the current Windows user and associates it with the EdgeMind extension origin. The uninstaller removes the integration registration created by the installer.

### 4.4 OS Security, Smart App Control & Code Signing

- **Smart App Control (SAC) Enforcement**: On modern Windows 11 installations with Smart App Control (SAC) enabled, unsigned binaries lacking Microsoft cloud reputation are blocked by Windows Defender Application Control policies before process execution (`WinError 4551`).
- **Production Authenticode Requirement**: For enterprise distribution, `edgemind_native_host.exe` must be signed with a trusted Authenticode code-signing certificate.
- **Graceful HTTP Fallback**: When the native messaging host is unavailable or blocked by OS security policies, the EdgeMind extension degrades gracefully by directly polling the local API endpoint (`http://127.0.0.1:8000/health`) and interacting over standard HTTP.

## 5. Backend API Design

### 5.1 Health Check

**Method:** `GET`  
**Path:** `/health`  
**Base URL:** `http://127.0.0.1:8000`

Expected healthy response:

```json
{
  "status": "healthy",
  "service": "EdgeMind"
}
```

The extension must only display `Connected` after a successful health response.

### 5.2 EdgeMind Analysis

**Method:** `POST`  
**Path:** `/api/v1/edgemind/analyze`

The endpoint receives problem context assembled by the extension and returns the analysis result. The precise request and response schemas are defined by the implementation and its API models.

The logical request information includes available problem metadata, language, examples, constraints, and relevant code context when supplied.

The logical response contains the detected context, analysis mode, parsed constraint information, coverage gaps, ranked candidates, candidate classifications, and static-analysis information where applicable.

When persistence is enabled, the analysis result is automatically stored in the PostgreSQL `analysis_sessions` table, and the full detailed report document is persisted to the `analysis_reports` JSONB table with `report_storage_status = "STORED"`.

### 5.3 Detailed Analysis Report Document

- **Method:** `GET`
- **Path:** `/api/v1/analyses/{analysis_id}/report`
- **Status Codes:** `200 OK`, `401 Unauthorized`, `404 Not Found`, `422 Unprocessable Entity`, `503 Service Unavailable`

Retrieves the complete analysis report document adhering to `schema_version: "1.0.0"`. Enforces tenant isolation: ordinary users can only access their own reports; administrators can view across all tenants. Returns HTTP 404 if the session ID is not found or owned by another tenant.

### 5.4 Test Candidates Subresource

- **Method:** `GET`
- **Path:** `/api/v1/analyses/{analysis_id}/candidates`
- **Status Codes:** `200 OK`, `401 Unauthorized`, `404 Not Found`, `422 Unprocessable Entity`, `503 Service Unavailable`

Retrieves the synthesized test candidate pool, total counts, classification breakdowns (`VALID`, `ROBUSTNESS_PROBE`, `CONSTRAINT_VALIDITY_UNKNOWN`), candidate provenance metadata, and solver limitation disclaimers.

### 5.5 Coverage Gaps Subresource

- **Method:** `GET`
- **Path:** `/api/v1/analyses/{analysis_id}/coverage-gaps`
- **Status Codes:** `200 OK`, `401 Unauthorized`, `404 Not Found`, `422 Unprocessable Entity`, `503 Service Unavailable`

Retrieves categorized boundary vulnerabilities, total detected gaps, formal parsed constraint specifications, and any unformalized semantic constraint strings.

### 5.6 Delete Detailed Analysis Report

- **Method:** `DELETE`
- **Path:** `/api/v1/analyses/{analysis_id}/report`
- **Status Codes:** `204 No Content`, `401 Unauthorized`, `404 Not Found`, `422 Unprocessable Entity`, `503 Service Unavailable`

Deletes the detailed JSONB report document from `analysis_reports` while preserving the relational `analysis_sessions` row for audit integrity. Updates the parent session's `report_storage_status` to `"DELETED"` within the same database transaction.

### 5.7 Paginated Analysis Reports

- **Method:** `GET`
- **Path:** `/api/v1/reports`
- **Query Parameters:** `skip` (default 0), `limit` (default 50, max 100), `project_id` (optional UUID), `problem_slug` (optional string)
- **Status Codes:** `200 OK`, `401 Unauthorized`, `503 Service Unavailable`

Lists paginated analysis report documents sorted newest first (`created_at DESC`). Enforces tenant query filtering: normal users only retrieve reports where `user_id == current_user.id`; administrators retrieve reports across all tenants.

## 6. Intelligence Pipeline

### 6.1 Models — `models.py`

Defines shared data structures and categories used by the intelligence pipeline.

Important candidate classifications:

| Classification | Meaning |
|---|---|
| `VALID` | Satisfies the supported constraints checked by EdgeMind. |
| `ROBUSTNESS_PROBE` | Intentionally violates one or more known input constraints to probe defensive behavior. |
| `CONSTRAINT_VALIDITY_UNKNOWN` | The system cannot establish validity from the available constraints. |

Generated candidate provenance is recorded as generated test data. Generated expected outputs remain absent/unverified.

### 6.2 Constraint Parser — `constraint_parser.py`

Responsibilities:
- Normalize constraint text.
- Extract supported numerical bounds.
- Associate bounds with parameters.
- Interpret collection lengths and element-value bounds.
- Identify supported parameter relationships.
- Retain unresolved semantic statements when they cannot be fully formalized.

Examples of relationships include:
- A window size must not exceed the input array length.
- A matrix has row and column dimension limits.
- A problem may require exactly one valid pair, represented through dedicated semantic/cross-parameter logic where supported.

The parser must report partial parsing when relevant constraints remain unresolved.

### 6.3 Gap Detector — `gap_detector.py`

Responsibilities:
- Compare baseline examples with supported coverage dimensions.
- Identify missing lower/upper boundaries.
- Identify empty or singleton cases where permitted.
- Identify relevant value and structural patterns.
- Avoid applying irrelevant generic sequence gaps to domain-specific inputs such as trees or bracket strings.
- Deduplicate gaps without removing distinct value and length coverage.

### 6.4 Candidate Synthesizer — `synthesizer.py`

Responsibilities:
- Generate inputs for identified coverage gaps.
- Respect parameter-specific bounds.
- Preserve cross-parameter relationships.
- Generate domain-specific patterns when the problem type supports them.
- Keep valid candidates distinct from deliberate robustness probes.
- Avoid duplicate candidates that provide no additional coverage.

Examples of specialized patterns include:
- Sliding-window string patterns.
- Nested or repeated bracket patterns.
- Binary-tree structural variants.
- Boundary-sized arrays and matrices.

These are input candidates, not verified outputs.

### 6.5 Ranker — `ranker.py`

Responsibilities:
- Score candidates for relevance.
- Prioritize meaningful boundary and domain-specific coverage.
- Avoid penalizing distinct structures as if they were duplicates.
- Deduplicate only candidates that provide equivalent coverage.
- Return a ranked candidate collection for display.

Ranking is a heuristic prioritization, not a proof of correctness.

## 7. Static Code Hygiene

Static code hygiene is a separate analysis path from test-input generation. It provides static inspection information and must not be presented as a solution correctness verdict.

The safety invariant is that user-submitted code is not executed.

## 8. Candidate Lifecycle

```text
Problem Context
      |
      v
Constraint Parsing
      |
      v
Coverage Gap Detection
      |
      v
Candidate Synthesis
      |
      v
Constraint/Relationship Classification
      |
      v
Ranking and Deduplication
      |
      v
API Response
      |
      v
Popup Rendering
```

For every generated candidate:
- Preserve its generated-test provenance.
- Keep expected output unverified.
- Do not execute the candidate.
- Do not imply that `VALID` means algorithmic correctness.

## 9. Backend Lifecycle Scripts

The Windows scripts under `scripts/` manage the local API:
- `start_edgemind_api.ps1`: starts the backend.
- `check_edgemind_api.ps1`: checks backend availability.
- `stop_edgemind_api.ps1`: stops the EdgeMind-owned backend process.

The native messaging installer and uninstaller manage the Chrome-to-host registration. Paths and extension origin must match the active project location and installed extension ID.

## 10. Error Handling

| Condition | Expected handling |
|---|---|
| Unsupported page | Explain that problem context is unavailable. |
| Missing examples | Use Context-Based mode when sufficient context exists. |
| Partially parsed constraints | Show partial status and preserve unresolved constraints. |
| Backend unavailable | Show Offline/Connecting state and a useful error. |
| Native host unavailable | Show startup/host error and retain diagnostic information. |
| Candidate validity cannot be established | Use `CONSTRAINT_VALIDITY_UNKNOWN`. |
| Large candidate | Show a compact preview and preserve full input access. |

## 11. Testing Strategy

The repository includes automated tests for parser behavior, gap detection, synthesis, ranking, API integration, extension structure, and static-only safety.

The documented project benchmark includes representative programming problems such as Two Sum, Search Insert Position, Valid Parentheses, Maximum Depth of Binary Tree, Longest Substring Without Repeating Characters, Climbing Stairs, and Maximum Average Subarray I.

Automated tests and manual browser checks should be reported separately. A passing unit test does not by itself prove that the installed Chrome extension and native host work on every machine.

## 12. Security Invariants

1. Bind the backend to `127.0.0.1:8000`.
2. Do not expose the API on `0.0.0.0`.
3. Do not execute user code.
4. Do not execute synthesized candidate inputs.
5. Do not fabricate expected outputs.
6. Scope Native Messaging registration to the intended extension origin.
7. Keep native-host protocol output separate from diagnostic logging.

## 13. Database Architecture & PostgreSQL JSONB Report Store

### 13.1 PostgreSQL 16 Relational Schema

The relational layer is managed asynchronously via SQLAlchemy 2.0 with `asyncpg` connection pooling:
- `users`: User identity, Argon2id password hashes, RBAC roles (`user`, `admin`), activation status.
- `refresh_tokens`: Cryptographic refresh token families, rotation tracking, revocation timestamps, client metadata.
- `projects`: Multi-tenant project containers, programming language, technology stack metadata, user ownership foreign keys.
- `problems`: Normalized LeetCode problem catalog indexed by unique `problem_slug`, title, platform, and difficulty.
- `analysis_sessions`: High-level session execution logs, gap and candidate counts, execution duration, project/problem/user links, and `report_storage_status` (`PENDING`, `STORED`, `FAILED`, `DELETED`, `NOT_CONFIGURED`).

### 13.2 AnalysisReport Model — `core/database/models/analysis_report.py`

Stores detailed analysis reports, candidate edge-case pools, constraints, and coverage gaps:

```python
class AnalysisReport(Base, TimestampMixin):
    __tablename__ = "analysis_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    problem_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("problems.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    problem_slug: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    report_data: Mapped[Dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
```

- **Relationships**: 1-to-1 relationship with `AnalysisSession` (`session.report`) with `cascade="all, delete-orphan"`.
- **Serialization**: `to_dict()` canonicalizes top-level foreign keys, timestamps, and the nested `report_data` payload.

### 13.3 Report Repository — `core/database/repositories/report_repository.py`

Encapsulates all asynchronous SQLAlchemy 2.0 operations for `analysis_reports`:
- `create_report`: Inserts a new report; raises `DuplicateReportError` on conflict.
- `upsert_report`: Idempotently inserts or updates an existing report by `analysis_session_id`.
- `get_report_by_session_id`: Fetches a report document by session UUID.
- `list_reports`: Paginated query sorted newest first (`created_at DESC`) with multi-tenant filtering (`user_id`, `project_id`, `problem_slug`).
- `update_report`: Safe partial field updates.
- `delete_report`: Deletes report row and returns boolean deletion status.
- **Safe UUID Normalization**: Converts strings, UUID objects, or malformed inputs into optional valid UUIDs without raising 500 exceptions.
- **Exception Sanitization**: Database errors are wrapped in `ReportRepositoryError` with password and secret scrubbing.

### 13.4 Alembic Migration 004 & GIN Indexing

Migration `migrations/versions/004_postgresql_jsonb_report_store.py`:
- **Chaining**: Downstream revision linked to parent `003_report_storage_status`.
- **Table Definition**: Creates `analysis_reports` with foreign keys and unique constraint on `analysis_session_id`.
- **PostgreSQL GIN Index**: Attaches a native Generalized Inverted Index on `report_data`:
  ```sql
  CREATE INDEX ix_analysis_reports_report_data_gin ON analysis_reports USING gin (report_data jsonb_path_ops);
  ```
  Accelerates JSON path expression queries (`@>`, `?`, `?&`) across complex candidate arrays and gap structures.
- **Dialect Guard**: Skips GIN creation on SQLite to allow seamless in-memory test execution.
- **Bidirectional Downgrade**: Drops GIN index, foreign keys, and table cleanly during downgrade operations.

### 13.5 Authentication & Multi-Tenancy Isolation

- **Password Security**: Argon2id hashing with randomized salts and parameter verification.
- **Token Security**: HMAC-SHA256 JWT access tokens (~15m expiration) and single-use refresh token rotation (~7d expiration) with reuse detection and automated token family revocation.
- **Tenant Scoping**: All report and session queries strictly enforce user ownership. Non-admin cross-tenant lookups return HTTP 404 to eliminate enumeration risks.
- **Anonymous Extension Compatibility**: Analysis runs from unauthenticated browser sessions store reports with `user_id = None`, preserving local developer workflows.
- **Static-Only Safety Invariant**: User source code, cookies, and tokens are scrubbed prior to document storage; candidate tests persistently enforce `expected_output = null` and `is_expected_output_verified = false`.
