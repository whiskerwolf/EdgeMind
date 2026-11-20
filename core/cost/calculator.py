"""
Cost calculation service and model pricing catalog for EdgeMind.

Implements exact Decimal arithmetic for token costs using configurable per-million pricing rates.
Preserves sub-micro-dollar costs without premature rounding.
"""

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Dict, List, Optional, Tuple, Union

from core.cost.models import CostBreakdown, ModelLifecycleStatus, ModelPrice

logger = logging.getLogger("edgemind.cost.calculator")

DEFAULT_PRICING_VERSION = "2026-11-01"
ONE_MILLION = Decimal("1000000")


class CostCalculator:
    """
    Calculates API costs from token usage using model-specific per-million rates
    and strict Decimal precision throughout.
    """

    def __init__(self, pricing_version: str = DEFAULT_PRICING_VERSION):
        self.pricing_version = pricing_version
        self._catalog: Dict[Tuple[str, str], ModelPrice] = {}
        self._load_default_rates()

    def _load_default_rates(self) -> None:
        """
        Register verified default rates (USD per 1,000,000 tokens)
        referenced against official provider documentation.
        Explicitly tracks model lifecycle: ACTIVE, DEPRECATED, or RETIRED,
        storing source URLs, lifecycle dates, and pricing effective dates.
        """
        verified_rates = [
            # OpenAI Models (Sources: https://developers.openai.com/api/docs/deprecations, https://openai.com/api/pricing/)
            (
                "openai",
                "gpt-3.5-turbo",
                Decimal("0.500"),
                Decimal("1.500"),
                "2024-01-25",
                "https://developers.openai.com/api/docs/deprecations",
                ModelLifecycleStatus.RETIRED,
                "October 23, 2026",
            ),
            (
                "openai",
                "gpt-4-turbo",
                Decimal("10.000"),
                Decimal("30.000"),
                "2024-04-09",
                "https://developers.openai.com/api/docs/deprecations",
                ModelLifecycleStatus.RETIRED,
                "October 23, 2026",
            ),
            (
                "openai",
                "gpt-4o-2024-05-13",
                Decimal("5.000"),
                Decimal("15.000"),
                "2024-05-13",
                "https://developers.openai.com/api/docs/deprecations",
                ModelLifecycleStatus.RETIRED,
                "October 23, 2026",
            ),
            (
                "openai",
                "gpt-4o-mini-2024-07-18",
                Decimal("0.150"),
                Decimal("0.600"),
                "2024-07-18",
                "https://developers.openai.com/api/docs/deprecations",
                ModelLifecycleStatus.DEPRECATED,
                "January 14, 2027",
            ),
            (
                "openai",
                "gpt-4o-2024-08-06",
                Decimal("2.500"),
                Decimal("10.000"),
                "2024-08-06",
                "https://developers.openai.com/api/docs/deprecations",
                ModelLifecycleStatus.DEPRECATED,
                "January 14, 2027",
            ),
            (
                "openai",
                "gpt-4o-mini",
                Decimal("0.150"),
                Decimal("0.600"),
                "2024-07-18",
                "https://developers.openai.com/api/docs/deprecations",
                ModelLifecycleStatus.DEPRECATED,
                "January 14, 2027",
            ),
            (
                "openai",
                "text-embedding-3-small",
                Decimal("0.020"),
                Decimal("0.000"),
                "2024-01-25",
                "https://openai.com/api/pricing/",
                ModelLifecycleStatus.ACTIVE,
                None,
            ),
            (
                "openai",
                "text-embedding-3-large",
                Decimal("0.130"),
                Decimal("0.000"),
                "2024-01-25",
                "https://openai.com/api/pricing/",
                ModelLifecycleStatus.ACTIVE,
                None,
            ),

            # Anthropic Exact Identifiers (Source: https://platform.claude.com/docs/en/about-claude/model-deprecations)
            (
                "anthropic",
                "claude-3-haiku-20240307",
                Decimal("0.250"),
                Decimal("1.250"),
                "2024-03-07",
                "https://platform.claude.com/docs/en/about-claude/model-deprecations",
                ModelLifecycleStatus.RETIRED,
                "April 20, 2026",
            ),
            (
                "anthropic",
                "claude-3-5-sonnet-20240620",
                Decimal("3.000"),
                Decimal("15.000"),
                "2024-06-20",
                "https://platform.claude.com/docs/en/about-claude/model-deprecations",
                ModelLifecycleStatus.RETIRED,
                "October 28, 2025",
            ),
            (
                "anthropic",
                "claude-3-5-sonnet-20241022",
                Decimal("3.000"),
                Decimal("15.000"),
                "2024-10-22",
                "https://platform.claude.com/docs/en/about-claude/model-deprecations",
                ModelLifecycleStatus.RETIRED,
                "October 28, 2025",
            ),
        ]
        for provider, model, inp, out, eff_date, url, status, life_date in verified_rates:
            self.register_price(
                model=model,
                input_price_per_million=inp,
                output_price_per_million=out,
                provider=provider,
                currency="USD",
                effective_date=eff_date,
                source_url=url,
                pricing_version=self.pricing_version,
                status=status,
                lifecycle_date=life_date,
            )

    def register_price(
        self,
        model: str,
        input_price_per_million: Decimal,
        output_price_per_million: Decimal,
        provider: str = "openai",
        currency: str = "USD",
        effective_date: str = "2024-07-18",
        source_url: str = "https://openai.com/api/pricing/",
        pricing_version: Optional[str] = None,
        status: Union[ModelLifecycleStatus, str] = ModelLifecycleStatus.ACTIVE,
        lifecycle_date: Optional[str] = None,
    ) -> None:
        """Register or override a model's exact pricing rates and lifecycle status."""
        ver = pricing_version or self.pricing_version
        normalized_model = model.strip().lower()
        model_status = (
            status if isinstance(status, ModelLifecycleStatus)
            else ModelLifecycleStatus(str(status).upper())
        )
        self._catalog[(normalized_model, ver)] = ModelPrice(
            provider=provider,
            model=normalized_model,
            input_price_per_million=Decimal(str(input_price_per_million)),
            output_price_per_million=Decimal(str(output_price_per_million)),
            currency=currency,
            effective_date=effective_date,
            source_url=source_url,
            pricing_version=ver,
            status=model_status,
            lifecycle_date=lifecycle_date,
        )

    def get_price(self, model: str, pricing_version: Optional[str] = None) -> Optional[ModelPrice]:
        """
        Fetch pricing rates for a model and pricing version via strict exact matching.
        Does not guess or silently apply incorrect model rates.
        """
        if not model:
            return None
        ver = pricing_version or self.pricing_version
        normalized_model = model.strip().lower()
        return self._catalog.get((normalized_model, ver))

    def list_models(self, pricing_version: Optional[str] = None) -> List[ModelPrice]:
        """List all verified models for a given pricing version."""
        ver = pricing_version or self.pricing_version
        return [price for (_, v), price in self._catalog.items() if v == ver]

    def get_active_models(self, pricing_version: Optional[str] = None) -> List[ModelPrice]:
        """List all currently active models for a given pricing version."""
        return [p for p in self.list_models(pricing_version) if p.status == ModelLifecycleStatus.ACTIVE]

    def get_deprecated_models(self, pricing_version: Optional[str] = None) -> List[ModelPrice]:
        """List all deprecated / snapshot-pinned models for a given pricing version."""
        return [p for p in self.list_models(pricing_version) if p.status == ModelLifecycleStatus.DEPRECATED]

    def get_retired_models(self, pricing_version: Optional[str] = None) -> List[ModelPrice]:
        """List all retired legacy models for a given pricing version."""
        return [p for p in self.list_models(pricing_version) if p.status == ModelLifecycleStatus.RETIRED]

    def is_model_active(self, model: str, pricing_version: Optional[str] = None) -> bool:
        """Check whether a model is currently active in the pricing catalog."""
        p = self.get_price(model, pricing_version)
        return p is not None and p.status == ModelLifecycleStatus.ACTIVE

    def is_model_deprecated(self, model: str, pricing_version: Optional[str] = None) -> bool:
        """Check whether a model is deprecated / snapshot-pinned in the pricing catalog."""
        p = self.get_price(model, pricing_version)
        return p is not None and p.status == ModelLifecycleStatus.DEPRECATED

    def is_model_retired(self, model: str, pricing_version: Optional[str] = None) -> bool:
        """Check whether a model is retired in the pricing catalog."""
        p = self.get_price(model, pricing_version)
        return p is not None and p.status == ModelLifecycleStatus.RETIRED

    def is_model_available_for_new_usage(self, model: str, pricing_version: Optional[str] = None) -> bool:
        """
        Check whether a model is available for new usage.
        Retired models preserve historical records but are NOT available for new API usage.
        """
        p = self.get_price(model, pricing_version)
        if p is None:
            return False
        return p.status != ModelLifecycleStatus.RETIRED

    def calculate_cost(
        self,
        prompt_tokens: Optional[int],
        completion_tokens: Optional[int],
        model: Optional[str],
        pricing_version: Optional[str] = None,
    ) -> CostBreakdown:
        """
        Calculate exact cost for a given token usage event using pure Decimal arithmetic.

        Formula:
            input_cost = (prompt_tokens / 1,000,000) * input_price_per_million
            output_cost = (completion_tokens / 1,000,000) * output_price_per_million
            total_cost = input_cost + output_cost

        Preserves sub-micro-dollar costs without rounding individual records.
        Returns CostBreakdown with is_pricing_known=False and None costs if model is unknown
        or token counts are missing.
        """
        ver = pricing_version or self.pricing_version

        if prompt_tokens is None or completion_tokens is None or not model:
            return CostBreakdown(
                input_cost=None,
                output_cost=None,
                total_cost=None,
                currency="USD",
                pricing_version=ver,
                is_pricing_known=False,
            )

        price = self.get_price(model, ver)
        if price is None:
            logger.debug(f"Unknown pricing for model '{model}' under version '{ver}'. Returning null cost.")
            return CostBreakdown(
                input_cost=None,
                output_cost=None,
                total_cost=None,
                currency="USD",
                pricing_version=ver,
                is_pricing_known=False,
            )

        p_tokens = Decimal(str(max(0, prompt_tokens)))
        c_tokens = Decimal(str(max(0, completion_tokens)))

        # Exact unrounded Decimal division and multiplication
        input_cost = (p_tokens / ONE_MILLION) * price.input_price_per_million
        output_cost = (c_tokens / ONE_MILLION) * price.output_price_per_million
        total_cost = input_cost + output_cost

        return CostBreakdown(
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            currency=price.currency,
            pricing_version=ver,
            is_pricing_known=True,
            model_status=price.status,
            lifecycle_date=price.lifecycle_date,
        )


# Global default cost calculator singleton
default_cost_calculator = CostCalculator()


def format_cost_usd(cost: Optional[Decimal], decimals: int = 6) -> str:
    """
    Format a Decimal monetary value strictly for UI or display output.
    Does not mutate the underlying exact Decimal value.
    """
    if cost is None:
        return "N/A"
    if cost == Decimal("0"):
        return "$0.00"
    if cost < Decimal("0.000001"):
        return f"${cost.normalize():f}"
    quantizer = Decimal("10") ** -decimals
    return f"${cost.quantize(quantizer, rounding=ROUND_HALF_UP):f}"


def estimate_local_tokens_from_text(text: Optional[str]) -> int:
    """
    Conservative local heuristic estimate (~4 chars per token)
    when actual provider usage metadata is unavailable.
    """
    if not text:
        return 0
    clean = text.strip()
    if not clean:
        return 0
    # Average ~4 characters per token for source code / English prose
    return max(1, (len(clean) + 3) // 4)
