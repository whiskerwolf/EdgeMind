"""
EdgeMind HTTP API.

Exposes a versioned HTTP API for static analysis of Python source code and adaptive test intelligence.
Guarantees static-only analysis, zero runtime execution, zero temporary files,
and sanitized error responses.
"""

import json
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.service import analyze_code, analyze_edgemind

app = FastAPI(
    title="EdgeMind API",
    version="1.0.0",
    description=(
        "EdgeMind is an adaptive test intelligence tool that analyzes programming problems, "
        "identifies potential test coverage gaps and generates relevant edge-case inputs using static analysis."
    ),
    docs_url="/docs",
    redoc_url=None,
)


@app.get("/health")
async def health_check():
    """Health check endpoint indicating service availability."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "EdgeMind",
        },
    )


@app.post("/api/v1/analyze")
async def analyze_endpoint(request: Request):
    """
    Analyze submitted Python source code statically.

    Expects JSON body:
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
    filename = body.get("filename", "snippet.py")
    if filename is None:
        filename = "snippet.py"

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
        report = analyze_code(code=code, filename=filename, static_only=True)
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


@app.post("/api/v1/edgemind/analyze")
async def edgemind_analyze_endpoint(request: Request):
    """
    EdgeMind Adaptive Code Analysis and Test Intelligence endpoint.

    Expects JSON body:
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
        report = analyze_edgemind(
            code=code,
            problem_context=problem_context,
            test_cases=test_cases,
            filename=filename,
            max_candidates=max_candidates,
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


def run_server(host: str = "127.0.0.1", port: int = 8000, reload: bool = False):
    """Start development uvicorn server."""
    import uvicorn
    uvicorn.run("core.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    run_server()
