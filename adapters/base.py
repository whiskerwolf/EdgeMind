from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.models import AIRequest, AIResponse


class AIAdapter(ABC):
    """
    Abstract Base Class for all EdgeMind AI reasoning adapters.
    All providers (Null, HTTP, etc.) must implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider / adapter (e.g. 'null', 'gemini')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if credentials and configuration are valid, False otherwise."""
        pass

    @abstractmethod
    def analyze(self, request: AIRequest) -> AIResponse:
        """
        Analyze code and diagnostic findings to produce explanatory insights.
        Must never raise unhandled exceptions; return AIResponse(status='failed', ...) on error.
        """
        pass
