"""
Abstract AI Provider Interface
"""

from __future__ import annotations

import abc
from typing import Any, Dict, Optional

from app.ai.schemas import AIResponse


class AIProvider(abc.ABC):
    """Abstract base class for AI provider adapters."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abc.abstractmethod
    def model_id(self) -> str: ...

    @abc.abstractmethod
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        timeout: float = 45.0,
        max_tokens: int = 1024,
    ) -> AIResponse:
        """
        Send a generation request to the provider.

        Args:
            prompt: User-facing prompt text.
            system: Optional system instruction.
            schema: Optional JSON schema for structured output.
            timeout: Hard request timeout in seconds.
            max_tokens: Maximum output tokens.

        Returns:
            AIResponse with success, content, tokens, latency.
        """
        ...

    def is_available(self) -> bool:
        """Returns True if the provider is configured and eligible for use."""
        return True
