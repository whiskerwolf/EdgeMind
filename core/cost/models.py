"""
Token usage and API cost monitoring data models.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UsageSource(str, Enum):
    """Origin of the token accounting data."""
    ACTUAL_PROVIDER = "ACTUAL_PROVIDER"
    LOCAL_ESTIMATE = "LOCAL_ESTIMATE"
    LOCAL_INFERENCE = "LOCAL_INFERENCE"
    MIXED = "MIXED"
    UNAVAILABLE = "UNAVAILABLE"


class ModelLifecycleStatus(str, Enum):
    """Lifecycle status for a model in the pricing catalog."""
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ModelPrice(BaseModel):
    """Pricing rates per 1,000,000 tokens for a specific model."""
    model_config = ConfigDict(frozen=True)

    provider: str = Field(default="openai", description="Model provider (openai, anthropic, etc.)")
    model: str
    input_price_per_million: Decimal = Field(..., description="Cost in USD per 1M prompt/input tokens")
    output_price_per_million: Decimal = Field(..., description="Cost in USD per 1M completion/output tokens")
    currency: str = Field(default="USD", description="Billing currency")
    effective_date: str = Field(default="2024-07-18", description="Date price became officially effective")
    source_url: str = Field(default="https://openai.com/api/pricing/", description="Official documentation source URL")
    pricing_version: str = Field(default="2026-11-01", description="Pricing catalog version identifier")
    status: ModelLifecycleStatus = Field(
        default=ModelLifecycleStatus.ACTIVE,
        description="Lifecycle status: ACTIVE, DEPRECATED, or RETIRED",
    )
    lifecycle_date: Optional[str] = Field(
        default=None,
        description="Official retirement or deprecation date (e.g. 'October 23, 2026' or '2026-10-23')",
    )


class CostBreakdown(BaseModel):
    """Calculated cost outcome for a token usage event."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    input_cost: Optional[Decimal] = None
    output_cost: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    currency: str = "USD"
    pricing_version: Optional[str] = None
    is_pricing_known: bool = False
    model_status: Optional[ModelLifecycleStatus] = None
    lifecycle_date: Optional[str] = None


class TokenUsage(BaseModel):
    """Atomic token accounting record for a single LLM request."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    prompt_tokens: Optional[int] = Field(default=None, description="Number of prompt/input tokens")
    completion_tokens: Optional[int] = Field(default=None, description="Number of completion/output tokens")
    total_tokens: Optional[int] = Field(default=None, description="Sum of prompt and completion tokens")
    model: Optional[str] = Field(default=None, description="Model identifier used for this call")
    provider: str = Field(default="openai", description="AI provider name")
    request_id: Optional[str] = Field(default=None, description="Provider-returned unique request/completion ID")
    analysis_session_id: Optional[uuid.UUID] = Field(default=None, description="Associated analysis session ID")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Attributed authenticated user ID")
    project_id: Optional[uuid.UUID] = Field(default=None, description="Attributed project ID")
    timestamp: datetime = Field(default_factory=utc_now, description="UTC timestamp of the usage event")
    usage_source: UsageSource = Field(default=UsageSource.ACTUAL_PROVIDER, description="Source/validity of usage data")
    estimated_cost_usd: Optional[Decimal] = Field(default=None, description="Estimated USD cost as exact Decimal")
    pricing_version: Optional[str] = Field(default=None, description="Pricing catalog version used for cost")
    is_estimated_cost_known: bool = Field(default=False, description="True if pricing was available and applied")


class ModelUsageSummary(BaseModel):
    """Aggregated token and cost metrics for a single model."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests_count: int = 0
    estimated_cost_usd: Optional[Decimal] = None
    is_estimated_cost_known: bool = False


class AgentUsageSummary(BaseModel):
    """Complete aggregated token usage and cost accounting for an agent session."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests_count: int = 0
    estimated_cost_usd: Optional[Decimal] = None
    is_estimated_cost_known: bool = False
    pricing_version: Optional[str] = None
    usage_source: UsageSource = UsageSource.ACTUAL_PROVIDER
    by_model: Dict[str, ModelUsageSummary] = Field(default_factory=dict)
    records: List[TokenUsage] = Field(default_factory=list)


class UsageSummaryResponse(BaseModel):
    """Aggregated token usage and cost accounting query response."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: Optional[Decimal] = None
    requests_count: int = 0
    period: str = "month"
    by_model: Dict[str, Any] = Field(default_factory=dict)
    by_source: Dict[str, int] = Field(default_factory=dict)
    is_estimated_cost_known: bool = False


class ProviderUsageSummary(BaseModel):
    """Aggregated token and cost metrics for a single AI provider."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests_count: int = 0
    estimated_cost_usd: Optional[Decimal] = None
    is_estimated_cost_known: bool = False


class TenantUsageSummary(BaseModel):
    """Pseudonymized per-tenant usage aggregate (exposes only user UUID, never PII or secrets)."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests_count: int = 0
    estimated_cost_usd: Optional[Decimal] = None
    is_estimated_cost_known: bool = False


class AdminUsageFilters(BaseModel):
    """Active query filter scope echoed in admin usage analytics responses."""

    user_id: Optional[str] = None
    project_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None


class AdminUsageAnalyticsResponse(BaseModel):
    """Administrator-only cross-tenant AI token usage and cost analytics response."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    period: str = "month"
    filters: AdminUsageFilters = Field(default_factory=AdminUsageFilters)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_estimated_cost_usd: Optional[Decimal] = None
    is_estimated_cost_known: bool = False
    requests_count: int = 0
    distinct_users_count: int = 0
    distinct_projects_count: int = 0
    anonymous_requests_count: int = 0
    by_provider: Dict[str, ProviderUsageSummary] = Field(default_factory=dict)
    by_model: Dict[str, ModelUsageSummary] = Field(default_factory=dict)
    by_source: Dict[str, int] = Field(default_factory=dict)
    by_user: List[TenantUsageSummary] = Field(default_factory=list)
