"""
EdgeMind Centralized Configuration & Settings Module.

Provides Pydantic Settings-driven configuration management with:
- Automatic environment variable reading (.env file support)
- Secrets management and credential redaction
- CORS, middleware, and server operational settings
- Immutable safety invariants (static-only analysis)
"""

from functools import lru_cache
import os
import re
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central application settings for EdgeMind API and intelligence engine.
    Values can be overridden via environment variables or a .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application Metadata
    app_name: str = Field(default="EdgeMind API", description="Public display name of the API service")
    app_version: str = Field(default="1.0.0", description="Semantic release version of EdgeMind")
    app_description: str = Field(
        default=(
            "EdgeMind is an adaptive test intelligence tool that analyzes programming problems, "
            "identifies potential test coverage gaps and generates relevant edge-case inputs using static analysis."
        ),
        description="Public OpenAPI description",
    )
    environment: str = Field(default="development", description="Runtime environment (development, testing, production)")

    # Server Bindings
    host: str = Field(default="127.0.0.1", description="Loopback host address for local security")
    port: int = Field(default=8000, description="Listening TCP port")
    debug: bool = Field(default=False, description="Debug logging flag")

    # Static-Only Safety Invariants (Permanent)
    static_only: bool = Field(default=True, description="Strictly disable arbitrary code execution")
    max_source_size: int = Field(default=64 * 1024, description="Maximum allowed source code size in bytes (64 KiB)")
    default_filename: str = Field(default="snippet.py", description="Default filename display label")

    # CORS Settings
    cors_origins: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        description="Allowed web origins (Vite/React dev servers)",
    )
    cors_origin_regex: Optional[str] = Field(
        default=r"^chrome-extension://[a-p]{32}$",
        description="Allowed origin regex matching unpacked and packaged Chrome extensions",
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow HTTP credentials in CORS")
    cors_allow_methods: List[str] = Field(default_factory=lambda: ["*"], description="Allowed HTTP methods")
    cors_allow_headers: List[str] = Field(default_factory=lambda: ["*"], description="Allowed HTTP request headers")

    # Request Tracing & Middleware
    request_id_header: str = Field(default="X-Request-ID", description="HTTP header name for request correlation ID")
    process_time_header: str = Field(default="X-Process-Time", description="HTTP header name for latency in milliseconds")

    # External AI Reasoning & Secrets
    edgemind_ai_key: Optional[str] = Field(default=None, description="Primary EdgeMind AI reasoning API key")
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")

    def get_ai_api_key(self) -> Optional[str]:
        """
        Retrieve active AI key with precedence:
        1. Explicit settings (EDGEMIND_AI_KEY, GEMINI_API_KEY, OPENAI_API_KEY)
        2. Legacy OS environment variables (CODEDOCTOR_AI_KEY)
        """
        return (
            self.edgemind_ai_key
            or self.gemini_api_key
            or self.openai_api_key
            or os.environ.get("EDGEMIND_AI_KEY")
            or os.environ.get("CODEDOCTOR_AI_KEY")
            or os.environ.get("GEMINI_API_KEY")
        )

    def sanitize_error(self, message: str) -> str:
        """
        Redact sensitive API keys or credentials from error or log messages.
        """
        if not message:
            return ""
        sanitized = str(message)
        active_key = self.get_ai_api_key()
        if active_key and active_key in sanitized:
            sanitized = sanitized.replace(active_key, "[REDACTED]")
        for key in (self.edgemind_ai_key, self.gemini_api_key, self.openai_api_key):
            if key and key in sanitized:
                sanitized = sanitized.replace(key, "[REDACTED]")
        return sanitized


@lru_cache()
def get_settings() -> Settings:
    """
    Return cached singleton Settings instance.
    Cached with @lru_cache for fast, zero-overhead dependency injection in FastAPI.
    """
    return Settings()

