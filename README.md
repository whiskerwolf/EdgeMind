# EdgeMind — Adaptive Test Intelligence

EdgeMind is an adaptive test intelligence tool that analyzes programming problems, identifies potential test coverage gaps and generates relevant edge-case inputs using static analysis.

Originally engineered from advanced static analysis foundations, EdgeMind pairs deterministic AST code inspection with constraint-aware test case synthesis. It directly empowers developers and competitive programmers solving algorithmic challenges (e.g. on LeetCode) to identify subtle edge-case vulnerabilities, boundary condition omissions, and logic flaws before submitting code.

---

## Key Features

- **AST-Based Static Analysis**: Evaluates Python code using deterministic abstract syntax tree (AST) inspections without arbitrary code execution.
- **Adaptive Test Intelligence Engine**: Discovers edge cases and synthesizes targeted test inputs from problem constraints, extracted parameters, and existing baseline samples.
- **Dual Operating Modes**:
  - **Baseline-Driven Intelligence (Mode A)**: Activated when public baseline examples are extracted or provided. Analyzes observed baseline input coverage against deterministic problem constraints, pinpoints coverage gaps (e.g., missing boundaries, extreme scales, empty collections), and synthesizes targeted candidates to close those gaps.
  - **Context-Based Intelligence (Mode B)**: Automatically activated when zero public baseline examples are available. Synthesizes valid, compliant edge-case candidates and structural robustness probes directly from parsed problem constraints, parameter types, and solution signatures without fabricating false coverage claims.
- **Constraint-Aware Coverage-Gap Detector**: Identifies boundary conditions (e.g., minimum/maximum lengths, zero values, empty collections, negative values, and extreme scale inputs).
- **Candidate Ranking & Deduplication**: Ranks synthesized test candidates by severity, risk, and uniqueness while removing semantic duplicates.
- **EdgeMind Chrome Extension**: Seamless browser extension (`extension/edgemind`) with a custom geometric E brand identity, floating quick-launch, and dark-theme dashboard.
- **Persistent Backend Management**: Dedicated Windows PowerShell lifecycle scripts (`start_edgemind_api.ps1`, `check_edgemind_api.ps1`, `stop_edgemind_api.ps1`) for reliable detached background service execution.

---

## Installation & Setup

### Prerequisites

- Python 3.10+ (tested on Python 3.13)
- PowerShell (Windows) or bash
- Google Chrome (for the EdgeMind browser extension)

### 1. Clone & Setup Virtual Environment

```powershell
# Navigate to the project directory
cd c:\Users\HP\Downloads\Codedoctor

# Activate existing virtual environment or create a new one
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

---

## Backend Startup & Lifecycle Management

EdgeMind provides automated PowerShell lifecycle scripts in `scripts/` to reliably manage the background FastAPI service.

### Start the EdgeMind Backend

Launches the FastAPI server as a detached, persistent background process on `127.0.0.1:8000`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_edgemind_api.ps1
```

The script verifies:
1. Virtual environment interpreter availability.
2. Port availability.
3. Detached execution via WMI (`Win32_Process.Create`) writing stdout/stderr to `logs/edgemind-api.log` and `logs/edgemind-api-error.log`.
4. Successful `/health` socket connection before returning.

### Check Backend Health

Verifies socket connectivity and queries the `/health` endpoint:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_edgemind_api.ps1
```

Expected output:
```text
====================================================
 EdgeMind Backend Health Status Check
====================================================
[STATUS] Connected
  Service  : EdgeMind
  Status   : healthy
  Endpoint : http://127.0.0.1:8000/health
  PID      : <process_id>
```

### Stop the Backend

Safely terminates only the EdgeMind server process and frees port 8000:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop_edgemind_api.ps1
```

### Manual Development Startup

Alternatively, run the development server directly with Uvicorn:

```powershell
.\.venv\Scripts\python.exe -m uvicorn core.api:app --host 127.0.0.1 --port 8000 --reload
```

Interactive OpenAPI documentation is accessible at `http://127.0.0.1:8000/docs`.

---

## Windows Invisible Autostart & One-Click Launch

EdgeMind provides zero-configuration Windows integration so you never need to keep a terminal window open.

### 1. Automatic Invisible Startup on Windows Login

Registers a standard user Windows Task Scheduler task that launches the EdgeMind FastAPI backend silently in the background whenever you log into Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_edgemind_autostart.ps1
```

- **Silent & Invisible**: Uses `scripts/start_edgemind_silent.vbs` (`SW_HIDE (0)`) — no flashing terminal windows or console popups.
- **Normal Permissions**: Runs under current user credentials (`TASK_LOGON_INTERACTIVE_TOKEN`); does not require administrator privileges.
- **Reusable Lifecycle**: Reuses `scripts/start_edgemind_api.ps1` to prevent duplicate processes and redirect logs cleanly.

To remove the startup task at any time:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_edgemind_autostart.ps1
```

### 2. One-Click Desktop Chrome Launcher

Creates an `EdgeMind Chrome` shortcut on your Desktop:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\create_edgemind_desktop_shortcut.ps1
```

Clicking the desktop shortcut:
1. Silently verifies if the EdgeMind backend is running; if offline, starts it in the background automatically.
2. Polls `http://127.0.0.1:8000/health` until ready.
3. Automatically opens Google Chrome with the active EdgeMind extension profile.

### 3. Automatic Startup Triggered by Opening Chrome Profile 7

Whenever you open Chrome Profile 7 normally, the EdgeMind extension triggers an automatic background startup using Chrome Native Messaging:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_edgemind_native_messaging.ps1
```

- **Zero Manual Effort**: Opening Chrome Profile 7 automatically starts the FastAPI backend silently in the background.
- **Length-Prefixed Protocol**: Uses a compiled native C# executable (`scripts/edgemind_native_host.exe`) registered in `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.edgemind.native_host`.
- **Duplicate Prevention**: If the backend is already online and healthy, it connects immediately without starting extra processes.
- **Non-blocking UI**: The popup dynamically displays `Connecting` during startup and automatically transitions to `Connected` upon health check success.

To uninstall native messaging registration:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_edgemind_native_messaging.ps1
```

---

## HTTP API Documentation

### 1. Health Check

Verifies backend service availability and status.

- **Method**: `GET`
- **Path**: `/health`
- **Response**: `200 OK`
  ```json
  {
    "status": "healthy",
    "service": "EdgeMind"
  }
  ```

---

### 2. Static Code Analysis

Analyzes a submitted Python code snippet statically for syntax errors, logic flaws, code smells, and cyclomatic complexity.

- **Method**: `POST`
- **Path**: `/api/v1/analyze`
- **Headers**: `Content-Type: application/json`

#### Request Body Schema

```json
{
  "code": "string (required, max 64 KiB)",
  "filename": "string (optional, display label only, defaults to 'snippet.py')"
}
```

#### Example Request

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "code": "def calculate_average(a, b):\n    return a + b / 2\n\nprint(calculate_average(10, 20))\n",
    "filename": "solution.py"
  }'
```

---

### 3. EdgeMind Adaptive Test Intelligence

Analyzes code against problem context and baseline test cases to discover test coverage gaps and synthesize edge-case candidates.

- **Method**: `POST`
- **Path**: `/api/v1/edgemind/analyze`
- **Headers**: `Content-Type: application/json`

#### Request Body Schema

```json
{
  "code": "string (required, max 64 KiB)",
  "filename": "string (optional, defaults to 'solution.py')",
  "problem_context": {
    "title": "Two Sum",
    "slug": "two-sum",
    "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"],
    "parameters": [
      {"name": "nums", "type": "List[int]"},
      {"name": "target", "type": "int"}
    ]
  },
  "test_cases": [
    {
      "input_data": {"nums": [2, 7, 11, 15], "target": 9},
      "expected_output": [0, 1]
    }
  ],
  "max_candidates": 10
}
```

#### Response Properties

- `status`: `"SUCCESS"`
- `product`: `"EdgeMind"`
- `version`: `"1.0.0"`
- `analysis_mode`: `"BASELINE_DRIVEN"` (Mode A) or `"CONTEXT_BASED"` (Mode B).
- `baseline_available`: Boolean indicating whether baseline test samples were provided/extracted (`true` for Mode A, `false` for Mode B).
- `identified_parameters`: List of extracted parameters with inferred types and domain structures.
- `parsed_constraints`: Summary of parsed constraints and boundary extraction status.
- `test_intelligence`: Test intelligence results containing:
  - `coverage_gaps`: Detected input vulnerabilities with severity, category, and explanation.
  - `generated_candidates`: Ranked, synthesized test cases tagged `GENERATED_TEST` with structured inputs.
- `code_analysis`: Comprehensive static analysis report (syntax, logic errors, code quality, and cyclomatic complexity score).
- `provenance`: Strict provenance metadata and execution safety guarantees.

---

## Persistence Architecture (PostgreSQL & MongoDB)

EdgeMind employs a dual-database persistence design separating relational metadata and authorization from detailed analysis documents:

| Concern | Primary Store | Storage Scope |
|---|---|---|
| **Users & Authentication** | PostgreSQL (`asyncpg` + SQLAlchemy 2.0) | User accounts, Argon2id password hashes, JWT refresh token families, RBAC roles (`user`, `admin`). |
| **Projects & Tenancy** | PostgreSQL | Multi-tenant projects, user ownership links, creation/update timestamps. |
| **Problem Catalog** | PostgreSQL | LeetCode problem slugs, titles, and difficulty metadata. |
| **Analysis Metadata** | PostgreSQL | `analysis_sessions` table tracking timestamps, status, project/problem/user links, and `report_storage_status` (`PENDING`, `STORED`, `FAILED`, `NOT_CONFIGURED`). |
| **Analysis Reports & Artifacts** | MongoDB (`pymongo.AsyncMongoClient`) | `analysis_reports` collection storing full test intelligence reports, synthesized edge-case candidates, coverage gaps, parsed constraints, and code metrics. |

### MongoDB Document Schema (`analysis_reports`)

Documents in the `analysis_reports` collection adhere to `schema_version: "1.0.0"`:

```json
{
  "_id": "ObjectId(...)",
  "schema_version": "1.0.0",
  "analysis_session_id": "UUID (matches PostgreSQL analysis_sessions.id)",
  "project_id": "UUID (optional, tenant isolation)",
  "user_id": "UUID (optional, tenant isolation)",
  "problem_slug": "string",
  "created_at": "ISODate(...)",
  "storage_metadata": {
    "engine_version": "1.0.0",
    "analysis_mode": "BASELINE_DRIVEN | CONTEXT_BASED",
    "static_only": true,
    "stored_at": "ISODate(...)"
  },
  "identified_parameters": [...],
  "parsed_constraints": [...],
  "coverage_gaps": [...],
  "generated_candidates": [
    {
      "candidate_id": "string",
      "tag": "GENERATED_TEST",
      "input_data": {...},
      "expected_output": null,
      "is_expected_output_verified": false,
      "target_gaps": [...],
      "rationale": "string",
      "severity": "CRITICAL | HIGH | MEDIUM | LOW"
    }
  ],
  "code_analysis": {
    "syntax_valid": true,
    "complexity_score": 1,
    "code_smells": []
  },
  "provenance": {...}
}
```

> [!IMPORTANT]
> **Safety Invariants**:
> - Generated candidates strictly enforce `expected_output = null` and `is_expected_output_verified = false`. EdgeMind never executes code and never fabricates verified outputs.
> - Source code, LeetCode DOM trees, cookies, and bearer tokens are strictly scrubbed prior to MongoDB persistence.

---

### Detailed Analysis & Report Endpoints

#### 1. Retrieve Complete Analysis Report
- **Method**: `GET`
- **Path**: `/api/v1/analyses/{analysis_id}/report`
- **Auth**: Bearer Token required for private sessions. Returns the full MongoDB report document.

#### 2. Retrieve Synthesized Test Candidates
- **Method**: `GET`
- **Path**: `/api/v1/analyses/{analysis_id}/candidates`
- **Auth**: Bearer Token required for private sessions. Returns the candidate array, count, and safety warnings.

#### 3. Retrieve Coverage Gaps
- **Method**: `GET`
- **Path**: `/api/v1/analyses/{analysis_id}/coverage-gaps`
- **Auth**: Bearer Token required for private sessions. Returns categorized boundary vulnerabilities.

#### 4. List Paginated Reports
- **Method**: `GET`
- **Path**: `/api/v1/reports?skip=0&limit=20`
- **Auth**: Bearer Token required. Normal users only view reports they own; admin users can inspect reports across tenants.

#### 5. Delete Analysis Document
- **Method**: `DELETE`
- **Path**: `/api/v1/analyses/{analysis_id}/report`
- **Auth**: Bearer Token required. Safely removes the MongoDB document and updates the PostgreSQL session's `report_storage_status` to `"FAILED"`, preserving audit history.

---

## Docker Compose Infrastructure

A production-aligned local development environment is configured via `docker-compose.yml`:

```powershell
# Start PostgreSQL 16 and MongoDB 7 in detached mode
docker compose up -d

# Check service health
docker compose ps
```

- **PostgreSQL**: Accessible at `localhost:5432` (`edgemind` database).
- **MongoDB**: Accessible at `localhost:27017` (`edgemind` database).

When Docker is unavailable, EdgeMind gracefully operates with local SQLite and falls back safely if MongoDB is offline (`report_storage_status = "FAILED"` or `"NOT_CONFIGURED"`), ensuring the Chrome extension and core intelligence engine are never blocked.


The unpacked extension is located in `extension/edgemind/`.

### Installation in Google Chrome

1. Open Google Chrome and go to `chrome://extensions/`.
2. Enable **Developer mode** via the toggle switch in the top right.
3. Click **Load unpacked**.
4. Select the directory:
   ```text
   C:\Users\HP\Downloads\Codedoctor\extension\edgemind
   ```
5. Pin **EdgeMind** to the Chrome extensions toolbar.

### Using EdgeMind on LeetCode

1. Open any LeetCode problem (e.g., `https://leetcode.com/problems/two-sum/`).
2. Set the code editor language to **Python3**.
3. Click the EdgeMind icon in the toolbar or click the floating quick-action pill on the page.
4. Click **Analyze & Discover Edge Cases** to receive instant coverage gaps, risk assessments, and synthesized boundary test inputs.

---

## Security Model & Static-Only Guarantees

- **Permanently Enforced Static Analysis**: The API strictly enforces `static_only = True`. User-submitted code is never executed, preventing arbitrary code execution.
- **Runtime Status Skipped**: `runtime_status` is consistently returned as `"SKIPPED"`.
- **Zero Temporary Files**: In-memory parsing ensures no untrusted files are written to the host filesystem.
- **Strict Payload Bounds**: Source code payloads are strictly capped at 64 KiB (65,536 bytes).

---

## Running the Test Suite

Run the full automated test suite using `pytest`:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Run specific test modules:

```powershell
# API tests
.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_edgemind_api.py -v

# EdgeMind extension and isolation tests
.\.venv\Scripts\python.exe -m pytest tests/test_edgemind_extension.py tests/test_chrome_extension.py -v

# Adaptive test intelligence engine tests
.\.venv\Scripts\python.exe -m pytest tests/test_gap_detector.py tests/test_synthesizer.py tests/test_ranker.py -v

# Database persistence & multi-tenancy tests
.\.venv\Scripts\python.exe -m pytest tests/test_database_persistence.py tests/test_auth_multi_tenancy.py -v

# MongoDB document store integration tests
.\.venv\Scripts\python.exe -m pytest tests/test_mongodb_integration.py -v

```
