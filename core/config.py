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
from pydantic import AliasChoices, Field, model_validator
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
    edgemind_chrome_extension_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "edgemind_chrome_extension_id",
            "chrome_extension_id",
            "EDGEMIND_CHROME_EXTENSION_ID",
            "CHROME_EXTENSION_ID",
        ),
        description="Exact 32-character lowercase [a-p] Chrome extension ID permitted in production",
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow HTTP credentials in CORS")
    cors_allow_methods: List[str] = Field(default_factory=lambda: ["*"], description="Allowed HTTP methods")
    cors_allow_headers: List[str] = Field(default_factory=lambda: ["*"], description="Allowed HTTP request headers")

    # Request Tracing & Middleware
    request_id_header: str = Field(default="X-Request-ID", description="HTTP header name for request correlation ID")
    process_time_header: str = Field(default="X-Process-Time", description="HTTP header name for latency in milliseconds")

    # AI Reasoning Provider Selection & Local Ollama
    agent_provider: str = Field(
        default="ollama",
        validation_alias=AliasChoices("edgemind_agent_provider", "agent_provider", "EDGEMIND_AGENT_PROVIDER", "AGENT_PROVIDER"),
        description="Active AI agent reasoning provider ('ollama' or 'openai')",
    )
    ollama_base_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("ollama_base_url", "edgemind_ollama_base_url", "OLLAMA_BASE_URL", "EDGEMIND_OLLAMA_BASE_URL"),
        description="Base URL for local Ollama server",
    )
    ollama_model: str = Field(
        default="qwen3:4b",
        validation_alias=AliasChoices("ollama_model", "edgemind_ollama_model", "OLLAMA_MODEL", "EDGEMIND_OLLAMA_MODEL"),
        description="Default model for local Ollama reasoning",
    )
    ollama_timeout: float = Field(
        default=75.0,
        validation_alias=AliasChoices("ollama_timeout", "edgemind_ollama_timeout", "OLLAMA_TIMEOUT", "EDGEMIND_OLLAMA_TIMEOUT"),
        description="Request timeout in seconds for local Ollama inference",
    )
    ollama_num_predict: int = Field(
        default=512,
        validation_alias=AliasChoices("ollama_num_predict", "edgemind_ollama_num_predict", "OLLAMA_NUM_PREDICT", "EDGEMIND_OLLAMA_NUM_PREDICT"),
        description="Maximum completion tokens generated per Ollama inference turn",
    )

    # External AI Reasoning & Secrets
    edgemind_ai_key: Optional[str] = Field(default=None, description="Primary EdgeMind AI reasoning API key")
    gemini_api_key: Optional[str] = Field(default=None, description="Google Gemini API key")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o-mini", description="Default OpenAI model for AI reasoning")
    openai_base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL endpoint")

    # Multi-Step AI Agent & Tool Calling
    agent_max_iterations: int = Field(default=5, description="Maximum iterative reasoning cycles for the multi-step agent")
    agent_max_tool_calls: int = Field(default=15, description="Maximum total tool executions allowed per agent session")
    agent_tool_timeout: float = Field(default=10.0, description="Per-tool execution timeout in seconds")
    agent_session_timeout: float = Field(default=90.0, description="Maximum total wall-clock timeout for an agent session in seconds")
    agent_pricing_version: str = Field(default="2026-11-01", description="Default pricing catalog version for API cost calculation")
    agent_enable_local_token_estimates: bool = Field(default=False, description="Whether to compute clearly labeled local token estimates when provider metadata is absent")

    # Retrieval-Augmented Generation (RAG) & Vector Storage
    rag_embedding_provider: str = Field(
        default="ollama",
        validation_alias=AliasChoices("rag_embedding_provider", "edgemind_rag_embedding_provider", "RAG_EMBEDDING_PROVIDER", "EDGEMIND_RAG_EMBEDDING_PROVIDER"),
        description="Active embedding provider for RAG ('ollama', 'openai', 'mock')",
    )
    ollama_embedding_model: str = Field(
        default="all-minilm:latest",
        validation_alias=AliasChoices("ollama_embedding_model", "edgemind_ollama_embedding_model", "OLLAMA_EMBEDDING_MODEL", "EDGEMIND_OLLAMA_EMBEDDING_MODEL"),
        description="Local Ollama embedding model identifier",
    )
    ollama_embedding_dimensions: int = Field(
        default=384,
        validation_alias=AliasChoices("ollama_embedding_dimensions", "edgemind_ollama_embedding_dimensions", "OLLAMA_EMBEDDING_DIMENSIONS", "EDGEMIND_OLLAMA_EMBEDDING_DIMENSIONS"),
        description="Vector dimension size for local Ollama embeddings",
    )
    rag_embedding_model: str = Field(default="text-embedding-3-small", description="Default RAG embedding model identifier")
    rag_embedding_dimensions: int = Field(default=1536, description="Vector dimension size for embeddings")
    rag_chunk_size: int = Field(default=500, description="Default character chunk size for document processing")
    rag_chunk_overlap: int = Field(default=50, description="Default character overlap size between consecutive chunks")
    rag_top_k: int = Field(default=3, description="Default top-k retrieved chunks")
    rag_similarity_threshold: float = Field(default=0.4, description="Default cosine similarity threshold for vector retrieval")

    # Database Settings (PostgreSQL / SQLAlchemy 2.0 Async)
    database_url: Optional[str] = Field(
        default=None,
        description="Async database URL (e.g. postgresql+asyncpg://postgres:postgres@localhost:5433/edgemind [host port 5433 mapped to container 5432] or sqlite+aiosqlite:///./edgemind.db)",
    )
    db_pool_size: int = Field(default=10, description="SQLAlchemy connection pool size")
    db_max_overflow: int = Field(default=20, description="Maximum overflow connections beyond pool_size")
    db_pool_timeout: float = Field(default=30.0, description="Connection pool checkout timeout in seconds")
    db_pool_recycle: int = Field(default=1800, description="Recycle connections older than this many seconds")
    db_pool_pre_ping: bool = Field(default=True, description="Enable connection health pre-ping before checkout")
    db_echo: bool = Field(default=False, description="Echo SQL statements to logs/stdout")

    # JWT Authentication & Multi-Tenancy (Phase 3)
    jwt_secret_key: Optional[str] = Field(default=None, description="Cryptographic secret key for signing JWT tokens")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_minutes: int = Field(default=15, description="Access token expiration in minutes (~15 min)")
    jwt_refresh_token_expire_days: int = Field(default=7, description="Refresh token expiration in days (~7 days)")
    jwt_issuer: str = Field(default="edgemind-api", description="Expected JWT issuer claim (iss)")
    jwt_audience: str = Field(default="edgemind-client", description="Expected JWT audience claim (aud)")

    # Administrator Bootstrap (Phase 3)
    admin_bootstrap_email: Optional[str] = Field(default=None, description="Optional environment-provided bootstrap admin email")
    admin_bootstrap_password: Optional[str] = Field(default=None, description="Optional environment-provided bootstrap admin password")

    # Redis & Distributed Caching (Phase 4)
    redis_url: Optional[str] = Field(
        default=None,
        description="Redis connection URL for caching (e.g. redis://127.0.0.1:6379/0)",
    )
    redis_password: Optional[str] = Field(
        default=None,
        description="Optional Redis password for authenticated cache instances",
    )
    redis_rate_limit_url: Optional[str] = Field(
        default=None,
        description="Optional dedicated Redis connection URL for rate limiting (e.g. redis://127.0.0.1:6380/0)",
    )
    redis_rate_limit_password: Optional[str] = Field(
        default=None,
        description="Optional Redis password for authenticated rate-limit instances",
    )
    redis_pool_size: int = Field(default=20, description="Redis connection pool size")
    redis_connect_timeout: float = Field(default=3.0, description="Redis connection timeout in seconds")
    redis_socket_timeout: float = Field(default=3.0, description="Redis socket read/write timeout in seconds")
    cache_enabled: bool = Field(default=True, description="Enable application-level Redis caching")
    cache_default_ttl: int = Field(default=3600, description="Default cache TTL in seconds")
    cache_key_prefix: str = Field(default="edgemind:cache:v1", description="Global prefix/version namespace for cache keys")

    # Distributed Rate Limiting (Phase 4)
    rate_limit_enabled: bool = Field(default=True, description="Enable distributed rate limiting via Redis")
    rate_limit_fallback_allow: bool = Field(
        default=False,
        description="Fallback policy when Redis is unavailable: False = fail-closed (reject request), True = fail-open (allow request)",
    )
    rate_limit_default_limit: int = Field(default=60, description="Default allowed requests per window")
    rate_limit_default_window: int = Field(default=60, description="Default rate limit window in seconds")
    rate_limit_agent_limit: int = Field(default=10, description="Rate limit for expensive agent reasoning endpoints per window")
    rate_limit_agent_window: int = Field(default=60, description="Window size in seconds for agent reasoning endpoints")
    trusted_proxy_ips: List[str] = Field(
        default_factory=lambda: ["127.0.0.1", "::1"],
        description="Trusted reverse proxy IP addresses allowed to provide X-Forwarded-For client IP",
    )

    @property
    def is_database_enabled(self) -> bool:
        """Check if a database URL is configured and non-empty."""
        return bool(self.database_url and self.database_url.strip())

    @property
    def is_redis_enabled(self) -> bool:
        """Check if any Redis URL is configured and non-empty."""
        return bool(
            (self.redis_url and self.redis_url.strip())
            or (self.redis_rate_limit_url and self.redis_rate_limit_url.strip())
        )

    @property
    def is_rate_limit_redis_dedicated(self) -> bool:
        """Return True if a dedicated rate-limit Redis instance is configured."""
        return bool(
            self.redis_rate_limit_url
            and self.redis_rate_limit_url.strip()
            and self.redis_rate_limit_url.strip() != (self.redis_url or "").strip()
        )

    @model_validator(mode="after")
    def validate_production_invariants(self) -> "Settings":
        """
        Enforce production safety invariants:
        - static_only is permanently True (arbitrary code execution prohibited).
        - debug must be False when environment == 'production'.
        - edgemind_chrome_extension_id validation and CORS restriction in production.
        """
        if not self.static_only:
            raise ValueError("static_only must remain True. Arbitrary code execution is permanently disabled.")
        if self.environment.lower() == "production" and self.debug:
            raise ValueError("DEBUG must be False in production environment.")

        # Exact Chrome Extension ID enforcement
        if self.edgemind_chrome_extension_id and self.edgemind_chrome_extension_id.strip():
            ext_id = self.edgemind_chrome_extension_id.strip()
            if not re.match(r"^[a-p]{32}$", ext_id):
                raise ValueError(
                    f"Invalid EDGEMIND_CHROME_EXTENSION_ID '{ext_id}': must be exactly 32 lowercase chars [a-p]"
                )
            self.cors_origin_regex = rf"^chrome-extension://{re.escape(ext_id)}$"
        elif self.environment.lower() == "production":
            # In production without an explicit extension ID, eliminate the unrestricted wildcard regex
            self.cors_origin_regex = None

        return self

    def validate_redis_security(self) -> None:
        """
        Enforce Redis security constraints.
        In production environment, explicitly configured REDIS_PASSWORD is required for all active Redis instances.
        Fails fast if password is missing or blank in production.
        """
        from urllib.parse import urlparse

        if self.environment.lower() == "production" and self.is_redis_enabled:
            # Check cache redis password
            if self.redis_url and self.redis_url.strip():
                has_pass = bool(
                    (self.redis_password and self.redis_password.strip())
                    or ("@" in self.redis_url and urlparse(self.redis_url).password)
                )
                if not has_pass:
                    raise RuntimeError(
                        "REDIS_PASSWORD must be explicitly configured in production environment."
                    )
            # Check dedicated rate limit redis password
            if self.is_rate_limit_redis_dedicated:
                has_rl_pass = bool(
                    (self.redis_rate_limit_password and self.redis_rate_limit_password.strip())
                    or (self.redis_password and self.redis_password.strip())
                    or ("@" in self.redis_rate_limit_url and urlparse(self.redis_rate_limit_url).password)
                )
                if not has_rl_pass:
                    raise RuntimeError(
                        "REDIS_RATE_LIMIT_PASSWORD or REDIS_PASSWORD must be explicitly configured in production environment."
                    )

    def get_jwt_secret_key(self) -> str:
        """
        Retrieve configured JWT secret key.
        Raises RuntimeError if the secret key is missing or blank.
        Never silently falls back to an insecure default.
        """
        if not self.jwt_secret_key or not self.jwt_secret_key.strip():
            raise RuntimeError(
                "JWT secret key is not configured. Set the JWT_SECRET_KEY environment variable."
            )
        return self.jwt_secret_key.strip()

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
        Redact sensitive API keys, database credentials, JWT tokens, or Redis passwords from error or log messages.
        """
        if not message:
            return ""
        from core.sanitization import redact_secrets
        custom = [
            self.jwt_secret_key,
            self.edgemind_ai_key,
            self.gemini_api_key,
            self.openai_api_key,
            self.admin_bootstrap_password,
            self.redis_password,
            self.redis_rate_limit_password,
        ]
        from urllib.parse import urlparse
        for url_val in [self.redis_url, self.redis_rate_limit_url]:
            if url_val and "@" in url_val:
                try:
                    parsed = urlparse(url_val)
                    if parsed.password:
                        custom.append(parsed.password)
                except Exception:
                    pass
        return redact_secrets(str(message), custom_secrets=[c for c in custom if c and len(c) >= 6])


@lru_cache()
def get_settings() -> Settings:
    """
    Return cached singleton Settings instance.
    Cached with @lru_cache for fast, zero-overhead dependency injection in FastAPI.
    """
    return Settings()

