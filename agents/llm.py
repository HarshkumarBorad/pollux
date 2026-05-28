"""Chat LLM clients used by the agents.

Two backends, same `async def chat(messages, ...) -> str` interface:

- `HFChatLLM`      — HuggingFace Inference Providers. The default for every
                     specialist agent (HR / IT / Customer-Facing).
- `OpenAIChatLLM`  — OpenAI Chat Completions. Used only by the Coordinator
                     and Ops Planner when `OPENAI_API_KEY` is set, where
                     stronger reasoning materially affects routing / planning
                     quality.

Lazy init throughout: instantiating an LLM never touches the network or
imports optional packages. The actual client (`AsyncInferenceClient` or
`AsyncOpenAI`) is built on the first `chat()` call. That lets tests
exercise agent metadata without needing any API keys.
"""
from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from core.config import PolluxConfig, get_config


@runtime_checkable
class ChatLLM(Protocol):
    """Duck-typed interface every agent's `self.llm` satisfies."""

    async def chat(
        self,
        messages: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str: ...


# ----- HF Inference -------------------------------------------------------

class HFChatLLM:
    """Async HF Inference chat client. Default LLM for specialists."""

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
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.config.hf_token:
            raise RuntimeError(
                "HF_TOKEN is not set. Add it to .env or your environment.\n"
                "Get a free token at https://huggingface.co/settings/tokens"
            )
        from huggingface_hub import AsyncInferenceClient  # lazy
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
        client = self._ensure_client()
        response = await client.chat_completion(
            messages=messages,
            max_tokens=max_tokens if max_tokens is not None else self.max_tokens,
            temperature=temperature if temperature is not None else self.temperature,
        )
        return response.choices[0].message.content


# ----- OpenAI -------------------------------------------------------------

class OpenAIChatLLM:
    """Async OpenAI chat client. Coordinator + OpsPlanner fallback when
    `OPENAI_API_KEY` is set. Specialists deliberately stay on HF."""

    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> None:
        self.config: PolluxConfig = get_config()
        self.model = model or self.config.openai_model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.config.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Coordinator falls back to HF when "
                "OpenAI is unavailable — this path should not be reached."
            )
        try:
            from openai import AsyncOpenAI  # lazy
        except ImportError as exc:
            raise RuntimeError(
                "openai package not installed but OPENAI_API_KEY is set. "
                "Run: pip install -r requirements.txt"
            ) from exc
        self._client = AsyncOpenAI(api_key=self.config.openai_api_key)
        return self._client

    async def chat(
        self,
        messages: List[dict],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        client = self._ensure_client()
        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=max_tokens
            if max_tokens is not None
            else self.max_tokens,
            temperature=temperature
            if temperature is not None
            else self.temperature,
        )
        return response.choices[0].message.content


# ----- Backend selection --------------------------------------------------

def make_coordinator_llm(
    max_tokens: int = 512,
    temperature: float = 0.0,
) -> ChatLLM:
    """LLM for agents that benefit from stronger reasoning — Coordinator and
    OpsPlanner. Prefers OpenAI when configured; otherwise falls back to HF.
    """
    config = get_config()
    if config.openai_enabled:
        return OpenAIChatLLM(max_tokens=max_tokens, temperature=temperature)
    return HFChatLLM(max_tokens=max_tokens, temperature=temperature)
