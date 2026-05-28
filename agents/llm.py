"""Async HF Inference chat client shared by every agent.

Lazy-init: the underlying `AsyncInferenceClient` is built on first `chat()`
call, not at instantiation. That lets tests instantiate agents (and verify
their metadata / capabilities) without requiring `HF_TOKEN`.
"""
from __future__ import annotations

from typing import List, Optional

from huggingface_hub import AsyncInferenceClient

from core.config import PolluxConfig, get_config


class HFChatLLM:
    """Thin async wrapper around HF Inference Provider chat-completion."""

    def __init__(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> None:
        self.config: PolluxConfig = get_config()
        self.model = model or self.config.hf_default_model
        self.provider = provider or self.config.hf_inference_provider
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client: Optional[AsyncInferenceClient] = None

    def _ensure_client(self) -> AsyncInferenceClient:
        if self._client is not None:
            return self._client
        if not self.config.hf_token:
            raise RuntimeError(
                "HF_TOKEN is not set. Add it to .env or your environment.\n"
                "Get a free token at https://huggingface.co/settings/tokens"
            )
        self._client = AsyncInferenceClient(
            model=self.model,
            token=self.config.hf_token,
            provider=self.provider,
        )
        return self._client

    async def chat(
        self,
        messages: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Send a chat-completion request, return the assistant's text reply."""
        client = self._ensure_client()
        response = await client.chat_completion(
            messages=messages,
            max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
        )
        return response.choices[0].message.content
