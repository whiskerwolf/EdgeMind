# EdgeMind — Low-Level Design (LLD)

**Product:** EdgeMind — Adaptive Test Intelligence
**Release:** v1.0.0 (Assessment Evaluation Candidate)
**Document Status:** Complete Architecture & Implementation Baseline
**Repository:** https://github.com/whiskerwolf/EdgeMind

---

## 1. Purpose

This document provides the definitive low-level engineering specification for EdgeMind, detailing the exact Python modules, class hierarchies, database schemas, API routes, tool dispatch mechanisms, vector search formulations, evaluation metrics, and security invariants implemented in the codebase.

---

## 2. Repository & Package Structure

```text
EdgeMind/
├── core/
│   ├── api.py                          # FastAPI application initialization & middleware
│   ├── config.py                       # Pydantic Settings singleton with secret sanitization
│   ├── schemas.py                      # Core API request and response data models
│   ├── agents/                         # Multi-step AI Agent & Function Calling Subsystem
│   │   ├── agent.py                    # Static analysis engine & agent fallback helpers
│   │   ├── orchestrator.py             # AgentOrchestrator: iterative multi-turn reasoning loop
│   │   ├── provider.py                 # BaseAgentProvider, MockAgentProvider, LiveAgentProvider
│   │   ├── schemas.py                  # AgentMessage, ToolCall, AgentStepResult, ToolExecutionRecord
│   │   └── tools.py                    # ToolRegistry & 8 deterministic analysis tool handlers
│   ├── auth/                           # Authentication, Passwords & JWT Security
│   │   ├── dependencies.py             # FastAPI Depends: get_current_user, get_current_admin
│   │   ├── router.py                   # /api/v1/auth routes: register, login, refresh, logout
│   │   ├── schemas.py                  # UserCreate, UserLogin, TokenResponse, UserResponse
│   │   ├── security.py                 # Argon2id hashing & HMAC-SHA256 JWT encoding/decoding
│   │   └── service.py                  # AuthService: registration, authentication, token rotation
│   ├── database/                       # Asynchronous SQLAlchemy 2.0 Persistence Layer
│   │   ├── base.py                     # DeclarativeBase, TimestampMixin, utc_now
│   │   ├── connection.py               # Engine singleton, sessionmaker, SQLite/PostgreSQL switcher
│   │   ├── models/                     # Relational, JSONB & pgvector Entities
│   │   │   ├── user.py                 # User model (Argon2id hashes, roles: user, admin)
│   │   │   ├── project.py              # Project container model (multi-tenant scoping)
│   │   │   ├── problem.py              # Problem catalog model (slug, platform, difficulty)
│   │   │   ├── analysis_session.py     # AnalysisSession audit model (status, duration, counts)
│   │   │   ├── analysis_report.py      # AnalysisReport model (PostgreSQL JSONB + GIN index)
│   │   │   ├── knowledge_document.py   # KnowledgeDocument model (metadata, content hash)
│   │   │   └── knowledge_chunk.py      # KnowledgeChunk model (Vector(1536) / HNSW / JSON)
│   │   └── repositories/               # Asynchronous Data Access Objects (DAOs)
│   │       ├── user_repository.py      # UserRepository: user queries and mutations
│   │       ├── project_repository.py   # ProjectRepository: project queries and ownership checks
│   │       ├── problem_repository.py   # ProblemRepository: catalog lookups by slug
│   │       ├── analysis_repository.py  # AnalysisRepository: session management
│   │       ├── report_repository.py    # ReportRepository: JSONB reports, upsert, pagination
│   │       └── knowledge_repository.py # KnowledgeRepository: pgvector <=> search, deduplication
│   ├── rag/                            # Retrieval-Augmented Generation (RAG) Subsystem
│   │   ├── embeddings/                 # Modular Vector Embedding Providers
│   │   │   ├── base.py                 # BaseEmbeddingProvider interface & exceptions
│   │   │   ├── mock.py                 # MockEmbeddingProvider: deterministic unit vectors (CI)
│   │   │   └── openai_provider.py      # OpenAIEmbeddingProvider: live text-embedding-3-small
│   │   ├── processing/                 # Document Ingestion & Chunking
│   │   │   └── document.py             # DocumentProcessor: sentence boundary lookback & SHA-256
│   │   └── retrieval/                  # Semantic Vector Retrieval Service
│   │       └── service.py              # VectorRetrievalService, RetrievedChunk, RetrievalResult
│   ├── reports/                        # JSONB Analysis Report Assembly
│   │   └── builder.py                  # Canonical report document builder (schema v1.0.0)
│   ├── routes/                         # FastAPI REST Endpoints
│   │   ├── agent.py                    # POST /api/v1/agent/analyze (Multi-step agent API)
│   │   ├── analyses.py                 # GET /api/v1/analyses (Sessions, /candidates, /gaps)
│   │   ├── reports.py                  # GET /api/v1/reports, GET/DELETE /api/v1/analyses/{id}/report
│   │   ├── projects.py                 # CRUD /api/v1/projects
│   │   └── problems.py                 # GET /api/v1/problems
│   └── test_intelligence/              # Deterministic Static Intelligence Engine
│       ├── models.py                   # TestCase, ConstraintSpec, CoverageGap models
│       ├── constraint_parser.py        # ConstraintParser: regex bounds & relational invariants
│       ├── gap_detector.py             # GapDetector: boundary & pattern coverage gaps
│       ├── synthesizer.py              # CandidateSynthesizer: edge-case input generator
│       └── ranker.py                   # CandidateRanker: heuristic scoring & deduplication
├── evaluation/                         # LLM Evaluation Framework
│   ├── schemas/                        # Evaluation Pydantic Data Models
│   │   ├── evaluation_example.py       # CodingProblemEvaluationExample schema
│   │   ├── dataset.py                  # EvaluationDataset schema & validation
│   │   └── evaluation_result.py        # EvaluationResult, BenchmarkSummary schemas
│   ├── datasets/                       # 20 Standard Coding Problem Benchmark Datasets
│   │   ├── dataset_loader.py           # Loader & filtering utilities
│   │   └── default_dataset.py          # 20 curated examples with ground-truth constraints/tools
│   ├── metrics/                        # Quantitative Scoring Metric Evaluators
│   │   ├── constraint_accuracy.py      # ConstraintAccuracyMetric: precision/recall of bounds
│   │   ├── tool_selection.py           # ToolSelectionMetric: precision/recall/F1 of tools
│   │   ├── edge_case_coverage.py       # EdgeCaseCoverageMetric: recall of critical edge cases
│   │   ├── response_validity.py        # ResponseValidityMetric: Pydantic schema validation
│   │   └── aggregate.py                # Aggregate evaluation calculator
│   └── runner.py                       # EvaluationRunner: executes mock/live benchmark passes
├── extension/edgemind/                 # Manifest V3 Chrome Extension
│   ├── manifest.json                   # Chrome extension manifest
│   ├── popup/                          # HTML, JavaScript & CSS user interface
│   └── scripts/                        # background.js (service worker) & content scripts
├── migrations/                         # Alembic Asynchronous Database Migrations
│   ├── env.py                          # Migration runner with asyncpg connection engine
│   └── versions/
│       ├── 001_initial_schema.py               # users, problems, projects, sessions
│       ├── 002_auth_and_multi_tenancy.py       # refresh_tokens, RBAC roles, tenant foreign keys
│       ├── 003_report_storage_status.py        # report_storage_status enum column
│       ├── 004_postgresql_jsonb_report_store.py# analysis_reports JSONB table + GIN index
│       └── 005_rag_vector_storage.py           # knowledge_documents, knowledge_chunks + HNSW
├── scripts/                            # Windows Native Messaging & Process Lifecycle Scripts
│   ├── edgemind_native_host.cs         # C# Native Messaging Host source code
│   ├── com.edgemind.native_host.json   # Chrome Native Messaging Manifest
│   ├── install_edgemind_native_messaging.ps1 # Dynamic HKCU registry installer
│   ├── uninstall_edgemind_native_messaging.ps1 # Clean uninstaller
│   ├── start_edgemind_api.ps1          # Background silent API launcher
│   └── stop_edgemind_api.ps1           # API process stopper
└── tests/                              # Automated Pytest Suite (602 Tests)
    ├── test_agent_orchestration.py     # 26 tests: Multi-step agent, tools, provider errors
    ├── test_rag_vector_retrieval.py    # 19 tests: Chunking, mock/live embeddings, RAG pipeline
    ├── test_rag_live_postgres.py       # 5 tests: SQL pgvector compilation, tenant order, HNSW
    ├── test_evaluation_framework.py    # 16 tests: Dataset validation, 4 metrics, runner passes
    └── test_postgresql_jsonb_report_store.py # 21 tests: JSONB persistence, GIN, isolation
```

---

## 3. Multi-Step AI Agent Architecture (`core/agents/`)

### 3.1 `AgentOrchestrator` (`core/agents/orchestrator.py`)
Coordinates the iterative reasoning loop between the user's problem context, the LLM provider, and the tool registry:
- **Initialization**:
  ```python
  class AgentOrchestrator:
      def __init__(
          self,
          provider: Optional[BaseAgentProvider] = None,
          registry: Optional[ToolRegistry] = None,
          embedding_provider: Optional[BaseEmbeddingProvider] = None,
          max_iterations: int = 10,
          max_tool_calls: int = 25,
      ):
  ```
- **Execution Loop (`run`)**:
  1. Assembles system instructions enforcing static-only invariants, unverified expected outputs, and untrusted RAG context separation.
  2. Enters reasoning cycles (up to `max_iterations`).
  3. Invokes `provider.generate_step(messages, tool_schemas)`.
  4. If tool calls are requested:
     - Enforces `max_tool_calls` upper bound.
     - Executes each tool via `ToolRegistry.execute()` inside an isolated timeout wrapper (`asyncio.wait_for`, default 5.0s).
     - Records duration, status (`SUCCESS`, `ERROR`, `TIMEOUT`), arguments, and results in `ToolExecutionRecord`.
     - Appends tool result message to conversation state.
     - Accumulates partial results in `state.accumulated_context` (`constraints`, `structure`, `gaps`, `candidates`, `retrieved_knowledge`).
  5. If final answer is returned (no tool calls): marks state as `AgentStatus.SUCCESS` and breaks loop.
  6. If provider fails or credentials missing: degrades gracefully to deterministic static analysis via `agent.py`, returning `execution_mode="DETERMINISTIC_STATIC_ONLY"`.
  7. Persists `AnalysisSession` and `AnalysisReport` (JSONB) when an authenticated user and database session are provided.

### 3.2 Provider Adapters (`core/agents/provider.py`)
- **`BaseAgentProvider`**: Abstract interface defining `generate_step(messages, tools, settings) -> AgentStepResult` and `is_available() -> bool`.
- **`MockAgentProvider`**: Scriptable queue of `AgentStepResult` objects for deterministic, reproducible CI testing.
- **`LiveAgentProvider`**: Production adapter communicating with standard OpenAI-compatible `/v1/chat/completions` endpoints:
  - Formats messages with role (`system`, `user`, `assistant`, `tool`).
  - Serializes tool definitions into OpenAI function format.
  - Parses assistant tool calls and arguments.
  - Classifies errors: HTTP 401 (authentication), HTTP 429 (rate limit), HTTP 500 (upstream error), timeouts, and network failures.
  - Redacts sensitive keys from error messages using `Settings.sanitize_error`.

### 3.3 Function/Tool Calling Registry (`core/agents/tools.py`)
- **`ToolRegistry`**: Manages registration, discovery, schema generation, and execution of deterministic tools.
- **Registered Tools**:
  1. `parse_problem_constraints`: Extracts parameter bounds, array length limits, and character set invariants.
  2. `analyze_problem_structure`: Analyzes AST structures, signatures, and input parameter mappings.
  3. `detect_coverage_gaps`: Discovers omitted lower/upper bounds, zero/negative cases, and empty sets.
  4. `generate_candidate_inputs`: Synthesizes candidate inputs for identified coverage gaps.
  5. `rank_candidate_inputs`: Heuristically prioritizes candidates and prunes redundant test inputs.
  6. `validate_candidate_inputs`: Classifies inputs into `VALID`, `ROBUSTNESS_PROBE`, or `CONSTRAINT_VALIDITY_UNKNOWN`.
  7. `synthesize_edge_cases`: Executes combined boundary analysis and edge-case candidate generation.
  8. `retrieve_knowledge_context`: Searches domain knowledge for algorithmic patterns and invariants via RAG.
- **Zero Code Execution**: None of the registered tools use `eval()`, `exec()`, file writes, or shell execution. They perform pure mathematical, string, and AST inspection.

### 3.4 Data Schemas (`core/agents/schemas.py`)
- `AgentMessage`: `role` (`system`, `user`, `assistant`, `tool`), `content`, `tool_call_id`, `tool_calls`, `name`.
- `ToolCall`: `id`, `name`, `arguments` (JSON string or dictionary).
- `AgentStepResult`: `content`, `thought`, `tool_calls`, `finish_reason` (`stop`, `tool_calls`, `error`).
- `ToolExecutionRecord`: `tool_call_id`, `tool_name`, `arguments`, `status` (`success`, `error`, `timeout`), `duration_ms`, `result`, `error`.
- `AgentAnalyzeRequest`: `code`, `filename`, `problem_context`, `test_cases`, `max_iterations`, `max_candidates`, `project_id`, `problem_id`.
- `AgentAnalyzeResponse`: `analysis_session_id`, `execution_mode`, `status`, `summary`, `test_intelligence`, `code_analysis`, `tool_executions`, `duration_ms`.

---

## 4. RAG & Vector Retrieval Implementation (`core/rag/`)

### 4.1 Document Ingestion & Chunking (`core/rag/processing/document.py`)
- **`DocumentProcessor`**:
  - `chunk_size`: 500 characters (configurable).
  - `chunk_overlap`: 100 characters (enforcing $0 \le \text{overlap} < \text{chunk\_size}$).
  - **Sentence Boundary Lookback**: Scans the last 20% of the window for paragraph (`\n\n`), sentence (`. `, `! `, `? `), or word boundaries (` `) to prevent mid-token truncation.
  - **SHA-256 Fingerprints**: Computes cryptographic content hashes for the root document and every chunk.
  - **Provenance Metadata**: Attaches `source_uri`, `title`, `chunk_index`, and tenant ownership IDs to every chunk.

### 4.2 Embedding Layer (`core/rag/embeddings/`)
- **`BaseEmbeddingProvider` (`base.py`)**: Defines `embed_text(str) -> List[float]`, `embed_batch(List[str]) -> List[List[float]]`, `dimensions: int`, `provider_name: str`, `is_mock: bool`.
- **`MockEmbeddingProvider` (`mock.py`)**:
  - Fully deterministic, offline unit vector generator.
  - Uses **token-level Gaussian hash blending**: word tokens are hashed via SHA-256 to seed pseudo-random Gaussian distributions. Texts with overlapping vocabulary yield positive dot products ($> 0.5$); identical texts yield $\text{similarity} = 1.0$.
  - Enforces unit length via $L_2$ normalization ($\|v\|_2 = 1.0$).
  - Explicitly reports `provider_name = "mock"`, `is_mock = True`.
- **`OpenAIEmbeddingProvider` (`openai_provider.py`)**:
  - Targets OpenAI's `/v1/embeddings` endpoint using model `text-embedding-3-small` (1536 dimensions).
  - Batches input texts in chunks of 100 strings.
  - Classifies HTTP 401, 429, 500, and timeout errors, redacting secrets via `Settings.sanitize_error`.
  - Explicitly reports `provider_name = "openai"`, `is_mock = False`.
  - When API key is missing: raises `EmbeddingProviderUnavailableError`; **never** silently falls back to synthetic mock vectors.

### 4.3 Database Models & Schema (`core/database/models/`)
- **`KnowledgeDocument` (`knowledge_document.py`)**:
  - `id`: UUID (Primary Key).
  - `title`: String(255).
  - `source_uri`: String(1024), nullable.
  - `content_hash`: String(64), SHA-256 indexed.
  - `doc_metadata`: `JSON().with_variant(JSONB, "postgresql")`.
  - `user_id`: UUID, Foreign Key (`users.id`, `ON DELETE CASCADE`), nullable.
  - `project_id`: UUID, Foreign Key (`projects.id`, `ON DELETE CASCADE`), nullable.
  - `is_global`: Boolean, default `False`, indexed.
  - `created_at`, `updated_at`: DateTime(timezone=True).
- **`KnowledgeChunk` (`knowledge_chunk.py`)**:
  - `id`: UUID (Primary Key).
  - `document_id`: UUID, Foreign Key (`knowledge_documents.id`, `ON DELETE CASCADE`).
  - `chunk_index`: Integer.
  - `content`: Text.
  - `content_hash`: String(64), SHA-256 indexed.
  - `embedding_model`: String(128).
  - `vector_dim`: Integer.
  - `embedding`: Configured via `get_embedding_column_type(1536)`:
    ```python
    def get_embedding_column_type(dimensions: int = 1536):
        if PGVECTOR_AVAILABLE and Vector is not None:
            return Vector(dimensions).with_variant(JSON(), "sqlite")
        return JSON()
    ```
    Compiles to `vector(1536)` on PostgreSQL and `JSON` on SQLite.
  - `chunk_metadata`: `JSON().with_variant(JSONB, "postgresql")`.
  - `user_id`: UUID, Foreign Key (`users.id`, `ON DELETE CASCADE`), nullable.
  - `project_id`: UUID, Foreign Key (`projects.id`, `ON DELETE CASCADE`), nullable.
  - `is_global`: Boolean, default `False`.
  - Indexes: `ix_knowledge_chunks_tenant_scope` (`user_id`, `project_id`, `is_global`), `ix_knowledge_chunks_doc_chunk` (`document_id`, `chunk_index`).

### 4.4 Similarity Search & Repository (`core/database/repositories/knowledge_repository.py`)
- **PostgreSQL Database-Side Vector Ordering**:
  ```python
  def build_postgres_search_query(self, query_embedding, user_id, project_id, top_k, similarity_threshold):
      distance_expr = KnowledgeChunk.embedding.cosine_distance(query_embedding)
      max_distance = 1.0 - similarity_threshold
      stmt = (
          select(KnowledgeChunk, distance_expr.label("distance"))
          .options(selectinload(KnowledgeChunk.document))
          .where(tenant_condition)
          .where(KnowledgeChunk.embedding.isnot(None))
          .where(distance_expr <= max_distance)
          .order_by(distance_expr.asc())
          .limit(top_k)
      )
      return stmt
  ```
- **Compiled SQL Verification**:
  ```sql
  SELECT knowledge_chunks.id, ..., knowledge_chunks.embedding <=> %(embedding_1)s AS distance
  FROM knowledge_chunks
  WHERE (knowledge_chunks.is_global IS true OR knowledge_chunks.user_id = %(user_id_1)s::UUID)
    AND knowledge_chunks.embedding IS NOT NULL
    AND (knowledge_chunks.embedding <=> %(embedding_1)s) <= %(param_1)s
  ORDER BY (knowledge_chunks.embedding <=> %(embedding_1)s) ASC
  LIMIT %(param_2)s;
  ```
- **Tenant Isolation Invariant**: Tenant conditions are evaluated in SQL `WHERE` clauses **before** `ORDER BY` and `LIMIT`, ensuring candidate chunks from other users are completely excluded prior to top-$k$ truncation.
- **SQLite In-Memory Fallback**: When running on SQLite, candidate chunks are fetched under tenant filters, and cosine similarity is computed in Python memory via `compute_cosine_similarity`.

### 4.5 Vector Retrieval Service (`core/rag/retrieval/service.py`)
- Coordinates embedding generation, repository queries, threshold filtering, and structured provenance packaging.
- **`RetrievedChunk`**: `chunk_id`, `document_id`, `title`, `content`, `similarity_score`, `source_uri`, `metadata`, `is_global`.
- **`RetrievalResult`**: `query`, `top_k`, `similarity_threshold`, `chunks`, `total_retrieved`, `execution_duration_ms`, `embedding_model`, `embedding_provider`, `is_mock`.

---

## 5. Persistence Architecture & Alembic Migrations

### 5.1 Alembic Migration Lineage
The database schema is managed via sequential, reversible migrations:
1. `001_initial_schema.py`: Establishes `users`, `projects`, `problems`, `analysis_sessions`.
2. `002_auth_and_multi_tenancy.py`: Adds `refresh_tokens`, role column (`user`, `admin`), and tenant foreign keys.
3. `003_report_storage_status.py`: Adds `report_storage_status` enum column (`PENDING`, `STORED`, `FAILED`, `DELETED`, `NOT_CONFIGURED`).
4. `004_postgresql_jsonb_report_store.py`: Creates `analysis_reports` table with native `JSONB` column `report_data` and GIN index `USING gin (report_data jsonb_path_ops)`.
5. `005_rag_vector_storage.py`: Executes `CREATE EXTENSION IF NOT EXISTS vector;`, creates `knowledge_documents` and `knowledge_chunks` tables, and attaches HNSW cosine index `USING hnsw (embedding vector_cosine_ops)`.

### 5.2 AnalysisReport Model & GIN Indexing (`core/database/models/analysis_report.py`)
- Stores complete EdgeMind analysis reports, synthesized edge-case candidates, coverage gaps, parsed constraints, and code metrics within native PostgreSQL `JSONB` columns (`report_data`).
- Accelerated via a PostgreSQL GIN index (`USING gin (report_data jsonb_path_ops)`).
- 1-to-1 relationship with `AnalysisSession` (`session.report`) with `cascade="all, delete-orphan"`.

---

## 6. LLM Evaluation Framework (`evaluation/`)

### 6.1 Benchmark Datasets (`evaluation/datasets/`)
- Contains 20 curated problem benchmarks covering diverse algorithmic paradigms:
  1. `eval_01_two_sum`: Array boundary indices, duplicate elements, negative targets.
  2. `eval_02_binary_search`: Empty array, single element, target not found, boundaries.
  3. `eval_03_valid_parentheses`: Unmatched brackets, odd lengths, deep nesting.
  4. `eval_04_max_depth_tree`: Empty tree (null root), single node, skewed degenerate tree.
  5. `eval_05_longest_substring`: All identical characters, alternating sequences, empty string.
  ... (20 total benchmark problems spanning arrays, strings, trees, dynamic programming, and graphs).
- Every example defines `id`, `problem_statement`, `expected_constraints`, `expected_edge_cases`, `relevant_tools`, and `expected_response_structure`.

### 6.2 Quantitative Metrics (`evaluation/metrics/`)
1. **Constraint Accuracy (`constraint_accuracy.py`)**: Computes precision, recall, and F1 between parsed parameter constraints and ground-truth bounds.
2. **Tool Selection (`tool_selection.py`)**: Computes precision, recall, and F1 comparing agent tool executions against expected relevant tools.
3. **Edge-Case Coverage (`edge_case_coverage.py`)**: Computes recall comparing synthesized candidate categories against required edge-case conditions.
4. **Structured Response Validity (`response_validity.py`)**: Verifies response schema adherence, non-null status, and unverified expected-output notices.

### 6.3 Evaluation Runner (`evaluation/runner.py`)
- `EvaluationRunner`: Executes benchmark suites deterministically using `MockAgentProvider` or live LLM providers.
- Supports tag filtering (`--tags boundary,arrays`), isolated timeouts, and generates structured JSON reports under `evaluation/reports/`.

---

## 7. REST API Endpoints

### 7.1 Multi-Step Agent Analysis
- **Route**: `POST /api/v1/agent/analyze`
- **Authentication**: JWT Bearer token optional for analysis, required for persistent report attachment.
- **Request Body (`AgentAnalyzeRequest`)**:
  ```json
  {
    "code": "def two_sum(nums, target): return []",
    "filename": "two_sum.py",
    "problem_context": {
      "title": "Two Sum",
      "slug": "two-sum",
      "description": "Given an array of integers nums and an integer target...",
      "constraints": ["2 <= nums.length <= 10^4", "-10^9 <= nums[i] <= 10^9"]
    },
    "test_cases": [{"nums": [2, 7, 11, 15], "target": 9}],
    "max_iterations": 10,
    "max_candidates": 10
  }
  ```
- **Response Body (`AgentAnalyzeResponse`)**:
  ```json
  {
    "analysis_session_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "execution_mode": "AI_AGENT",
    "status": "SUCCESS",
    "summary": "Agent completed reasoning: analyzed constraints, identified 4 boundary gaps, and synthesized 6 candidate inputs.",
    "test_intelligence": {
      "coverage_gaps": [...],
      "generated_candidates": [...],
      "ranked_candidates": [...],
      "retrieved_knowledge": [...]
    },
    "code_analysis": {...},
    "tool_executions": [
      {
        "tool_name": "parse_problem_constraints",
        "status": "success",
        "duration_ms": 1.25,
        "result": {...}
      },
      {
        "tool_name": "retrieve_knowledge_context",
        "status": "success",
        "duration_ms": 2.45,
        "result": {...}
      }
    ],
    "duration_ms": 45.8
  }
  ```

---

## 8. Security & Safety Invariants

1. **Static-Only Execution Model**: `static_only = True` is permanently hardcoded. No dynamic code interpretation (`exec()`, `eval()`, `subprocess.Popen`) is permitted.
2. **Unverified Expected Output Contract**: All synthesized candidates enforce `expected_output = None` and `is_expected_output_verified = False`.
3. **Secret Redaction**: `Settings.sanitize_error` scrubs database connection URLs, JWT tokens, and API keys before logging or persistence.
4. **Argon2id & JWT Token Rotation**: Passwords hashed with Argon2id; access tokens expire in ~15 minutes; single-use refresh tokens rotate on every invocation with automated reuse detection and token family revocation.
5. **Tenant Isolation**: All database queries enforce user ownership (`user_id == current_user.id`). Unauthorized tenant lookups return HTTP 404.
6. **Prompt Injection Hardening**: All external content and retrieved RAG chunks are enclosed in XML-escaped `<retrieved_context>` tags with explicit system prompt delimiters instructing the model that context can never override core safety instructions.
