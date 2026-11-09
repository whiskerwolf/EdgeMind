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
from typing import Any, Dict, Optional
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import get_settings
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

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    docs_url="/docs",
    redoc_url=None,
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
        500: {"model": ErrorResponse, "description": "Unexpected internal error"},
    },
)
async def edgemind_analyze_endpoint(request: Request):
    """
    EdgeMind Adaptive Code Analysis and Test Intelligence endpoint.

    Expects JSON body adhering to EdgeMindAnalyzeRequest:
    {
        "code": "...",
        "filename": "optional_name.py",
        "problem_context": { ... },   # Optional ProblemContext dict
        "test_cases": [ ... ],        # Optional list of test cases (TestCase dicts or raw inputs)
        "max_candidates": 10          # Optional integer limit (defaults to 10)
    }

    Guarantees:
    - Pure static analysis and candidate synthesis (runtime execution permanently disabled)
    - Zero temporary files
    - Strict input bounds (64 KiB max source size)
    - Strict provenance tracking: candidates labeled GENERATED_TEST with null expected outputs
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
        req_model = EdgeMindAnalyzeRequest(
            code=code,
            filename=str(filename) if filename is not None else "solution.py",
            problem_context=problem_context,
            test_cases=test_cases,
            max_candidates=max_candidates,
            static_only=True,
        )
    except Exception as val_err:
        return JSONResponse(
            status_code=400,
            content={"error": "Bad Request", "detail": str(val_err)},
        )

    try:
        report = analyze_edgemind(
            code=req_model.code,
            problem_context=req_model.problem_context,
            test_cases=req_model.test_cases,
            filename=req_model.filename,
            max_candidates=req_model.max_candidates or 10,
            static_only=True,
        )
        return JSONResponse(status_code=200, content=report)
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


def run_server(host: Optional[str] = None, port: Optional[int] = None, reload: bool = False):
    """Start development uvicorn server using centralized settings."""
    import uvicorn
    cfg = get_settings()
    server_host = host or cfg.host
    server_port = port or cfg.port
    uvicorn.run("core.api:app", host=server_host, port=server_port, reload=reload)


if __name__ == "__main__":
    run_server()
