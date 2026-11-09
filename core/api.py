"""
EdgeMind HTTP API.

Exposes a versioned HTTP API for static analysis of Python source code and adaptive test intelligence.
Guarantees static-only analysis, zero runtime execution, zero temporary files,
and sanitized error responses.

Includes:
- Centralized Pydantic settings configuration
- CORS middleware with support for web clients (Vite) and Chrome extensions
- Request tracing with X-Request-ID correlation headers
- Request logging and latency timing with X-Process-Time
- Typed Pydantic request and response schemas
- Consistent sanitized HTTP error responses
"""

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.auth.dependencies import get_optional_current_user
from core.auth.service import AuthService
from core.config import get_settings
from core.database.connection import close_db, get_db, get_session_factory
from core.database.models import User
from core.database.repositories import (
    AnalysisRepository,
    ProblemRepository,
    ProjectRepository,
)
from core.routes import (
    analyses_router,
    auth_router,
    problems_router,
    projects_router,
    users_router,
)
from core.schemas import (
    AnalyzeCodeRequest,
    EdgeMindAnalyzeRequest,
    ErrorResponse,
    HealthResponse,
)
from core.service import analyze_code, analyze_edgemind

# Configure logger
logger = logging.getLogger("edgemind.api")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [edgemind.api] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager handling resource startup and shutdown."""
    # Bootstrap initial admin account if database is active and credentials are provided
    factory = get_session_factory()
    if factory is not None:
        try:
            async with factory() as session:
                auth_service = AuthService(session)
                await auth_service.bootstrap_admin()
                await session.commit()
        except Exception as exc:
            logger.warning(
                f"Admin bootstrap check skipped or failed: {settings.sanitize_error(str(exc))}"
            )
    yield
    # Gracefully dispose database connection pools on shutdown
    await close_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
    expose_headers=[settings.request_id_header, settings.process_time_header],
)


# 2. Request Tracing, Logging & Timing Middleware
@app.middleware("http")
async def request_tracing_and_timing_middleware(request: Request, call_next):
    """
    Middleware that:
    1. Extracts or generates a unique correlation X-Request-ID header.
    2. Measures request execution duration with microsecond precision.
    3. Logs structured request receipt and completion metrics.
    4. Attaches X-Request-ID and X-Process-Time headers to the response.
    """
    client_request_id = request.headers.get(settings.request_id_header)
    request_id = client_request_id.strip() if client_request_id and client_request_id.strip() else str(uuid.uuid4())
    request.state.request_id = request_id

    start_time = time.perf_counter()
    logger.info(f"Incoming {request.method} {request.url.path} [Request-ID: {request_id}]")

    response = await call_next(request)

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    response.headers[settings.request_id_header] = request_id
    response.headers[settings.process_time_header] = f"{elapsed_ms:.2f}ms"

    logger.info(
        f"Completed {request.method} {request.url.path} -> {response.status_code} "
        f"in {elapsed_ms:.2f}ms [Request-ID: {request_id}]"
    )
    return response


# -----------------------------------------------------------------------------
# Mount REST API Routers
# -----------------------------------------------------------------------------
app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(problems_router, prefix="/api/v1")
app.include_router(analyses_router, prefix="/api/v1")


# -----------------------------------------------------------------------------
# Global Exception Handlers
# -----------------------------------------------------------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Consistent JSON handler for HTTP exceptions."""
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) and exc.status_code < 500 else "HTTP Error",
            "detail": str(exc.detail),
            "request_id": request_id,
        },
        headers={settings.request_id_header: request_id} if request_id else None,
    )


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint indicating service availability."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "EdgeMind",
        },
    )


@app.post(
    "/api/v1/analyze",
    responses={
        200: {"description": "Static code analysis report"},
        400: {"model": ErrorResponse, "description": "Validation error or invalid request payload"},
        500: {"model": ErrorResponse, "description": "Unexpected internal error"},
    },
)
async def analyze_endpoint(request: Request):
    """
    Analyze submitted Python source code statically.

    Expects JSON body adhering to AnalyzeCodeRequest:
    {
        "code": "...",
        "filename": "optional_display_name.py"
    }

    Guarantees:
    - Pure static analysis only (runtime execution is permanently disabled)
    - Zero temporary files
    - Strict input bounds (64 KiB max source size)
    - Sanitized JSON errors without internal stack traces
    """
    request_id = getattr(request.state, "request_id", None)

    try:
        raw_body = await request.body()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Failed to read request body."},
        )

    if not raw_body or not raw_body.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Request body must not be empty."},
        )

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Malformed JSON payload in request body."},
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Request body must be a JSON object."},
        )

    if "code" not in body:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Missing required field 'code'."},
        )

    code = body.get("code")
    filename = body.get("filename", settings.default_filename)
    if filename is None:
        filename = settings.default_filename

    if not isinstance(code, str):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "detail": f"Source code must be a string, got {type(code).__name__}.",
            },
        )

    # Explicitly enforce static_only
    if body.get("static_only") is False:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "detail": "Runtime execution is disabled on the HTTP API; static_only must be True.",
            },
        )

    try:
        # Validate typed schema
        req_model = AnalyzeCodeRequest(
            code=code,
            filename=str(filename) if filename is not None else settings.default_filename,
            static_only=True,
        )
    except Exception as val_err:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": str(val_err)},
        )

    try:
        report = analyze_code(code=req_model.code, filename=req_model.filename, static_only=True)
        return JSONResponse(status_code=200, content=report)
    except (TypeError, ValueError) as err:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": str(err)},
        )
    except Exception:
        # Never leak internal stack traces or filesystem paths
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred during code analysis.",
            },
        )


@app.post(
    "/api/v1/edgemind/analyze",
    responses={
        200: {"description": "EdgeMind Adaptive Test Intelligence report"},
        400: {"model": ErrorResponse, "description": "Validation error or invalid request payload"},
        404: {"model": ErrorResponse, "description": "Referenced project not found"},
        422: {"model": ErrorResponse, "description": "Malformed UUID or unprocessable entity"},
        500: {"model": ErrorResponse, "description": "Unexpected internal error"},
    },
)
async def edgemind_analyze_endpoint(
    request: Request,
    db: Optional[AsyncSession] = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    """
    EdgeMind Adaptive Code Analysis and Test Intelligence endpoint.

    Expects JSON body adhering to EdgeMindAnalyzeRequest:
    {
        "code": "...",
        "filename": "optional_name.py",
        "problem_context": { ... },   # Optional ProblemContext dict
        "test_cases": [ ... ],        # Optional list of test cases (TestCase dicts or raw inputs)
        "max_candidates": 10,         # Optional integer limit (defaults to 10)
        "project_id": "optional-uuid" # Optional project UUID
    }

    Guarantees:
    - Pure static analysis and candidate synthesis (runtime execution permanently disabled)
    - Zero temporary files
    - Strict input bounds (64 KiB max source size)
    - Strict provenance tracking: candidates labeled GENERATED_TEST with null expected outputs
    - Sanitized JSON errors without internal stack traces
    - Graceful degradation: If PostgreSQL is unconfigured or unreachable, analysis succeeds
      and returns analysis_session_id: null.
    """
    request_id = getattr(request.state, "request_id", None)

    try:
        raw_body = await request.body()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Failed to read request body."},
        )

    if not raw_body or not raw_body.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Request body must not be empty."},
        )

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Malformed JSON payload in request body."},
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Request body must be a JSON object."},
        )

    if "code" not in body:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": "Missing required field 'code'."},
        )

    code = body.get("code")
    filename = body.get("filename", "solution.py")
    if filename is None:
        filename = "solution.py"

    if not isinstance(code, str):
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "detail": f"Source code must be a string, got {type(code).__name__}.",
            },
        )

    problem_context = body.get("problem_context")
    test_cases = body.get("test_cases")
    max_candidates = body.get("max_candidates", 10)
    project_id_raw = body.get("project_id")

    # Explicitly enforce static_only
    if body.get("static_only") is False:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Bad Request",
                "detail": "Runtime execution is disabled on the HTTP API; static_only must be True.",
            },
        )

    # Validate project_id format and existence if supplied
    project_uuid: Optional[uuid.UUID] = None
    if project_id_raw is not None:
        try:
            project_uuid = uuid.UUID(str(project_id_raw))
        except (ValueError, TypeError):
            return JSONResponse(
                status_code=422,
                content={
                    "error": "Unprocessable Entity",
                    "detail": f"Invalid project_id UUID format: '{project_id_raw}'",
                    "request_id": request_id,
                },
            )

        if db is not None:
            try:
                project_repo = ProjectRepository(db)
                existing_proj = await project_repo.get_by_id(project_uuid)
                if not existing_proj:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": "Not Found",
                            "detail": f"Referenced project with ID '{project_uuid}' not found.",
                            "request_id": request_id,
                        },
                    )

                # Ownership isolation check: cannot attach to another user's project or unowned project anonymously
                if not current_user or (
                    current_user.role != "admin"
                    and existing_proj.owner_user_id != current_user.id
                ):
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": "Not Found",
                            "detail": f"Referenced project with ID '{project_uuid}' not found.",
                            "request_id": request_id,
                        },
                    )
            except HTTPException:
                raise
            except Exception as db_check_err:
                sanitized = settings.sanitize_error(str(db_check_err))
                logger.warning(f"Database error checking project existence (graceful degradation): {sanitized}")

    try:
        # Validate typed schema
        req_model = EdgeMindAnalyzeRequest(
            code=code,
            filename=str(filename) if filename is not None else "solution.py",
            problem_context=problem_context,
            test_cases=test_cases,
            max_candidates=max_candidates,
            static_only=True,
            project_id=str(project_uuid) if project_uuid else None,
        )
    except Exception as val_err:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": str(val_err)},
        )

    start_analyze_time = time.perf_counter()
    try:
        report = analyze_edgemind(
            code=req_model.code,
            problem_context=req_model.problem_context,
            test_cases=req_model.test_cases,
            filename=req_model.filename,
            max_candidates=req_model.max_candidates or 10,
            static_only=True,
        )
    except (TypeError, ValueError) as err:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": str(err)},
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred during EdgeMind analysis.",
            },
        )
    duration_ms = (time.perf_counter() - start_analyze_time) * 1000.0

    # Auto-link problem and persist analysis session metadata if database is available
    analysis_session_id: Optional[str] = None
    if db is not None:
        try:
            problem_id: Optional[uuid.UUID] = None
            if isinstance(problem_context, dict):
                prob_slug = (
                    problem_context.get("slug")
                    or problem_context.get("problem_slug")
                    or ""
                ).strip().lower()
                prob_title = (problem_context.get("title") or "").strip()
                prob_platform = (problem_context.get("platform") or "leetcode").strip().lower()
                prob_difficulty = problem_context.get("difficulty")

                if prob_title and not prob_slug:
                    prob_slug = prob_title.lower().replace(" ", "-")
                elif prob_slug and not prob_title:
                    prob_title = prob_slug.replace("-", " ").title()

                if prob_slug and prob_title:
                    problem_repo = ProblemRepository(db)
                    problem_rec, _ = await problem_repo.get_or_create(
                        title=prob_title,
                        problem_slug=prob_slug,
                        platform=prob_platform,
                        difficulty=prob_difficulty,
                    )
                    problem_id = problem_rec.id

            analysis_repo = AnalysisRepository(db)
            analysis_mode = report.get("analysis_mode", "BASELINE_DRIVEN")
            analysis_status = report.get("status", "SUCCESS")
            ti_section = (
                report.get("test_intelligence", {})
                if isinstance(report.get("test_intelligence"), dict)
                else {}
            )
            gaps_count = ti_section.get(
                "total_gaps",
                len(ti_section.get("coverage_gaps", ti_section.get("identified_gaps", []))),
            )
            candidates_list = ti_section.get(
                "generated_candidates",
                ti_section.get("candidate_tests", []),
            )
            candidates_count = len(candidates_list)

            user_id = current_user.id if current_user else None
            session_record = await analysis_repo.create(
                analysis_mode=analysis_mode,
                language="python",
                analysis_status=analysis_status,
                gaps_detected=gaps_count,
                candidates_generated=candidates_count,
                duration_ms=duration_ms,
                project_id=project_uuid,
                problem_id=problem_id,
                user_id=user_id,
            )
            analysis_session_id = str(session_record.id)
        except Exception as db_save_err:
            sanitized = settings.sanitize_error(str(db_save_err))
            logger.warning(
                f"Failed to persist analysis session to database (graceful degradation): {sanitized}"
            )
            analysis_session_id = None

    report["analysis_session_id"] = analysis_session_id
    return JSONResponse(status_code=200, content=report)


def run_server(host: Optional[str] = None, port: Optional[int] = None, reload: bool = False):
    """Start development uvicorn server using centralized settings."""
    import uvicorn
    cfg = get_settings()
    server_host = host or cfg.host
    server_port = port or cfg.port
    uvicorn.run("core.api:app", host=server_host, port=server_port, reload=reload)


if __name__ == "__main__":
    run_server()
