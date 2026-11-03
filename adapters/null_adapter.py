from adapters.base import AIAdapter
from core.models import AIRequest, AIResponse


class NullAdapter(AIAdapter):
    """
    Null Object implementation of AIAdapter.
    Used when AI reasoning is disabled, offline, or consent is absent.
    Performs zero network operations and produces safe default responses.
    """

    def __init__(self, reason: str = "AI reasoning is disabled."):
        self.reason = reason

    @property
    def name(self) -> str:
        return "null"

    def is_available(self) -> bool:
        return True

    def analyze(self, request: AIRequest) -> AIResponse:
        if not request.user_consent:
            return AIResponse(
                status="skipped",
                provider=self.name,
                summary="Source-sharing consent not granted.",
                insights=[],
                error=None,
            )

        return AIResponse(
            status="disabled",
            provider=self.name,
            summary=self.reason,
            insights=[],
            error=None,
        )
