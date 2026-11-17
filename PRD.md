# EdgeMind — Product Requirements Document (PRD)

**Product:** EdgeMind — Adaptive Test Intelligence
**Release:** v1.0.0 (Assessment Evaluation Candidate)
**Document Status:** Complete Architecture & Implementation Baseline
**Repository:** https://github.com/whiskerwolf/EdgeMind

---

## 1. Product Overview

EdgeMind is an adaptive test intelligence system delivered as a Google Chrome (Manifest V3) extension backed by a local asynchronous FastAPI backend (`127.0.0.1:8000`). It analyzes programming problems, detects hidden edge-case coverage gaps, and synthesizes structured boundary test inputs to help software engineers and students test their solutions thoroughly before submission.

Beyond traditional static heuristics, EdgeMind incorporates:
1. **Multi-Step AI Agent**: An autonomous reasoning engine with native tool/function calling that iteratively decomposes problem statements, analyzes algorithm structures, detects edge cases, and synthesizes candidate test inputs.
2. **Retrieval-Augmented Generation (RAG)**: A semantic vector retrieval pipeline backed by PostgreSQL 16 with `pgvector` (`Vector(1536)`), providing grounded algorithmic domain knowledge, boundary invariants, and canonical patterns.
3. **Automated LLM Evaluation Framework**: A rigorous offline evaluation system featuring 20 curated coding problem benchmarks, Pydantic dataset validation, and quantitative metrics (constraint accuracy, tool selection precision/recall/F1, edge-case coverage recall, and schema validity).
4. **PostgreSQL Relational & JSONB Storage**: Unified persistence combining relational multi-tenant models (`users`, `projects`, `problems`, `analysis_sessions`) with native PostgreSQL JSONB document storage (`analysis_reports`) and pgvector vector storage (`knowledge_documents`, `knowledge_chunks`).
5. **Strict Static-Only Safety Invariant**: User-submitted code and synthesized test inputs are **never executed** at runtime (`eval()`, `exec()`, or subshell execution are strictly disabled). Expected outputs are honestly marked unverified (`expected_output = None`, `is_expected_output_verified = False`).

---

## 2. Problem Statement

Competitive programming and technical interview platforms (e.g., LeetCode, HackerRank, Codeforces) typically present users with 2 to 3 trivial example test cases. These public examples frequently fail to expose:
- Extreme boundary conditions (e.g., minimum/maximum parameter limits, zero/negative values).
- Off-by-one errors and empty/singleton collections.
- Structural edge cases (e.g., skewed binary trees, cyclic graphs, identical duplicate values).
- Cross-parameter dependencies (e.g., window size exceeding array length).

Consequently, developers suffer from blind submissions, failed hidden test cases, and inadequate testing habits. EdgeMind bridges this gap by systematically extracting problem context, comparing visible examples against theoretical boundaries, retrieving relevant algorithmic invariants via RAG, and synthesizing prioritized edge-case candidates.

---

## 3. Target Users

- **Computer Science Students**: Learning data structures, algorithm design, and boundary analysis.
- **Software Engineers**: Practicing for technical interviews and competitive programming challenges.
- **Instructors & Mentors**: Demonstrating comprehensive testing strategies beyond visible problem examples.
- **Quality Assurance Engineers**: Analyzing code snippets for boundary vulnerabilities without runtime execution.

---

## 4. User Stories

1. **Autonomous Agent Analysis**:
   - *As a developer practicing dynamic programming*, I want an autonomous AI agent to iteratively analyze my problem constraints, search for boundary patterns, and synthesize edge cases so that I can discover hidden edge cases before submitting.
2. **Knowledge-Grounded Insights (RAG)**:
   - *As a developer tackling graph problems*, I want the agent to retrieve canonical algorithmic invariants (such as disconnected components and cycle traps) from an indexed knowledge store so that suggested edge cases reflect established computer science principles.
3. **Chrome Extension One-Click Inspection**:
   - *As a competitive programmer on a coding platform*, I want the browser extension to automatically extract problem statements, visible examples, and constraints from the active DOM and display prioritized test inputs in a clean popup.
4. **Persistent Multi-Tenant History**:
   - *As an authenticated user*, I want my analysis sessions, generated edge cases, and detailed reports securely saved to my account so that I can review past problem analyses while preventing other users from accessing my data.
5. **Quantitative Framework Confidence**:
   - *As an engineering evaluator*, I want a quantitative evaluation harness measuring tool selection precision, constraint extraction accuracy, and edge-case recall across standard benchmarks so that system performance is empirically verifiable.

---

## 5. Functional Requirements

### 5.1 Browser Extension & Client Integration
- **FR-01: Problem Page Detection**: Automatically detect supported coding problem URLs and extract title, slug, description, and visible examples from DOM structures.
- **FR-02: Programming Language Identification**: Extract the active language context (e.g., Python, C++, Java) from the web editor.
- **FR-03: Native Messaging Lifecycle**: Communicate with `edgemind_native_host.exe` via Chrome Native Messaging to check status and launch the local backend silently.
- **FR-04: Graceful Loopback Fallback**: Automatically fall back to direct HTTP polling (`http://127.0.0.1:8000/health`) if Native Messaging is blocked or unavailable.
- **FR-05: Input Preview & Clipboard Access**: Render compact previews of large test inputs in the popup with single-click clipboard copying.

### 5.2 Multi-Step AI Agent & Function Calling
- **FR-06: Autonomous Multi-Step Reasoning**: Execute an iterative agent loop (`AgentOrchestrator`) coordinating multi-turn tool calling, intermediate reasoning, and response synthesis up to a bounded maximum iterations limit (default 10).
- **FR-07: Tool Registry & Dispatch**: Register and execute 8 deterministic tools:
  1. `parse_problem_constraints`: Extracts parameter bounds and invariants.
  2. `analyze_problem_structure`: Identifies inputs, outputs, collections, and structural types.
  3. `detect_coverage_gaps`: Discovers boundary and pattern omissions.
  4. `generate_candidate_inputs`: Synthesizes candidate inputs for identified gaps.
  5. `rank_candidate_inputs`: Heuristically scores and prioritizes candidates.
  6. `validate_candidate_inputs`: Classifies candidates against known constraints.
  7. `synthesize_edge_cases`: Executes combined boundary synthesis.
  8. `retrieve_knowledge_context`: Performs semantic vector search on domain references.
- **FR-08: Dual-Provider Operation**:
  - **Live Mode (`LiveAgentProvider`)**: Communicates with external LLM endpoints using OpenAI-compatible tool-calling protocols.
  - **Mock Mode (`MockAgentProvider`)**: Provides deterministic scripted tool calls and responses for offline testing and CI.
- **FR-09: Degraded Static Fallback**: If LLM credentials are unavailable or the provider fails (401, 429, 500, timeout), degrade gracefully to deterministic static analysis rather than failing completely.
- **FR-10: Cancellation & Timeout Isolation**: Enforce isolated timeouts per tool call (default 5.0s) and honor `asyncio.CancelledError` tokens during agent execution.

### 5.3 Retrieval-Augmented Generation (RAG) & Vector Storage
- **FR-11: Boundary-Aware Document Processing**: Segment reference documents into overlapping chunks with configurable size (default 500 chars) and overlap (default 100 chars), snapping breaks to natural sentence and paragraph boundaries.
- **FR-12: Cryptographic Content Fingerprinting**: Calculate SHA-256 fingerprints for documents and chunks to ensure idempotent upserts and deduplication.
- **FR-13: Modular Embedding Generation**:
  - `OpenAIEmbeddingProvider`: Generates live embeddings via `text-embedding-3-small` (1536 dimensions) with batching and error classification.
  - `MockEmbeddingProvider`: Generates deterministic, unit-normalized ($L_2 = 1.0$) vectors using token-level Gaussian hash blending for offline CI testing.
  - Transparent disclosure: Explicitly tag results with `provider_name` and `is_mock` so mock embeddings are never masqueraded as live completions.
- **FR-14: Database-Side Vector Retrieval**: Execute genuine PostgreSQL vector similarity queries using the pgvector `<=>` cosine distance operator and HNSW indexing (`Vector(1536)`).
- **FR-15: Multi-Tenant Retrieval Scoping**: Enforce 3-tier tenant isolation in SQL `WHERE` clauses prior to `ORDER BY` and `LIMIT` (`(is_global IS true OR user_id = :user_id)`).

### 5.4 LLM Evaluation Framework
- **FR-16: Curated Benchmark Dataset**: Maintain a standardized dataset of at least 20 diverse algorithm evaluation examples with unique IDs, coding problems, expected constraints, expected edge cases, relevant tools, and structural schemas.
- **FR-17: Schema Validation**: Validate dataset examples and runner results using strict Pydantic models.
- **FR-18: Quantitative Evaluation Metrics**: Compute:
  - Constraint Extraction Accuracy
  - Tool Selection Precision, Recall, and F1-Score
  - Edge-Case Coverage Recall
  - Structured Response Validity Score
  - Aggregate Benchmark Summary
- **FR-19: Evaluation Runner**: Support deterministic offline evaluation (mock provider) and optional live LLM evaluation, outputting JSON reports to disk.

### 5.5 Authentication, Multi-Tenancy & Persistence
- **FR-20: Cryptographic User Authentication**: User registration and login utilizing Argon2id password hashing and RFC 7519 JWT tokens (access + single-use rotating refresh tokens).
- **FR-21: Multi-Tenant Workspace Scoping**: Strict user and project ownership isolation; non-admin cross-tenant accesses return HTTP 404 to eliminate resource enumeration.
- **FR-22: PostgreSQL JSONB Analysis Report Store**: Persist complete analysis reports, candidate edge-case pools, constraints, and coverage gaps into PostgreSQL `JSONB` columns indexed by a GIN index (`jsonb_path_ops`).
- **FR-23: Anonymous Run Support**: Allow unauthenticated browser sessions to analyze code without authentication (`user_id = None`), preserving frictionless local development.

---

## 6. Non-Functional Requirements

- **NFR-01: Runtime Safety (Zero Code Execution)**: User code and synthesized inputs must never be executed via `eval()`, `exec()`, or subshells.
- **NFR-02: Truthfulness & Transparency**: Generated expected outputs are unverified (`expected_output = None`). The UI and API must explicitly state this invariant.
- **NFR-03: Security & Network Locality**: The backend binds exclusively to loopback (`127.0.0.1:8000`). No inbound public internet connections are permitted.
- **NFR-04: Dialect Portability**: Core persistence must support full PostgreSQL 16 + pgvector operations in production while maintaining an in-memory SQLite (`aiosqlite`) fallback for zero-dependency CI unit testing.
- **NFR-05: Performance & Timeouts**: Static analysis completes in $< 200\text{ ms}$; agent tool iterations complete within bounded per-step timeouts ($5.0\text{ s}$ per tool); total agent reasoning capped at 10 cycles.
- **NFR-06: Memory & Input Clamping**: User source code capped at 64 KiB; RAG queries capped at 2,000 characters; RAG chunk storage capped at 4,000 characters.
- **NFR-07: Error Sanitization**: API keys, database credentials, and JWT secrets are scrubbed from all log messages, error responses, and persisted reports via `Settings.sanitize_error`.

---

## 7. Acceptance Criteria

| Requirement | Acceptance Test | Success Criterion |
| :--- | :--- | :--- |
| **Multi-Step Agent** | `test_multistep_sequential_tool_calling` | Agent executes sequential tools, tracks context, and terminates with final answer. |
| **Tool Bounds** | `test_maximum_iterations_bound` | Agent halts cleanly with `MAX_ITERATIONS_REACHED` when cycles exceed limit. |
| **Zero Code Execution** | `test_zero_code_execution_security` | Code containing `os.system` or file deletions is parsed statically without execution. |
| **RAG Cosine Ordering** | `test_postgres_vector_query_operator_compilation` | Query compiles to `ORDER BY (knowledge_chunks.embedding <=> ...) ASC LIMIT ...`. |
| **Tenant Isolation** | `test_tenant_isolation_cross_user_rejection` | User 2 cannot retrieve User 1's private knowledge chunks (0 results returned). |
| **Evaluation Framework** | `test_default_dataset_validity` | 20 benchmark examples pass all Pydantic validation checks with unique IDs. |
| **Database Migrations** | `test_alembic_upgrade_and_downgrade` | Migrations 001–005 apply and revert cleanly in reverse order. |

---

## 8. Implementation Status: Completed vs. Planned

| Feature Area | Implemented & Verified in v1.0.0 | Planned Future Scope (Not Implemented) |
| :--- | :--- | :--- |
| **AI Agent** | Autonomous multi-step orchestrator, 8 function calling tools, schema validation, mock/live adapters. | Asynchronous human-in-the-loop approvals, multi-agent debate swarms. |
| **RAG Pipeline** | Boundary-aware chunking, SHA-256 deduplication, mock/live embeddings, pgvector `<=>` ordering, HNSW indexing. | Hybrid BM25 + dense reciprocal rank fusion (RRF), contextual re-ranking models. |
| **Evaluation** | 20-problem benchmark set, 4 core metric evaluators, Pydantic validation, deterministic CI runner. | Continuous online eval telemetry, automated prompt optimization loops. |
| **Persistence** | PostgreSQL 16 relational tables, JSONB report documents with GIN indexing, pgvector vector storage. | Distributed Redis caching, MongoDB cluster, horizontal read replicas. |
| **API & Client** | FastAPI REST endpoints, Chrome Manifest V3 popup, C# Native Messaging host. | Streaming Server-Sent Events (SSE) / WebSockets, paid billing/Stripe integration, public cloud deployment. |

---

## 9. Known Limitations

1. **Local Host Dependency**: The backend is intended for local single-node execution on `127.0.0.1:8000`. Cloud-native clustering, distributed load balancing, and multi-region deployment are not implemented.
2. **Offline Docker Daemon**: When the host Docker engine is offline, live pgvector operations are gracefully skipped in favor of the verified SQLite JSON fallback and AST SQL compilation verification.
3. **Unverified Expected Outputs**: Synthesized edge cases provide input parameters only; determining ground-truth expected outputs requires an authoritative reference oracle or formal verification engine.
4. **Heuristic Boundary Extraction**: Highly ambiguous or idiosyncratic problem descriptions on non-standard coding websites may result in partial constraint parsing.

---

## 10. Release & Repository Information

- **Product**: EdgeMind
- **Version**: 1.0.0
- **License**: Educational / Assessment Submission
- **Source Repository**: https://github.com/whiskerwolf/EdgeMind
- **Active Assessment Branch**: `feature/assessment-score-6`
