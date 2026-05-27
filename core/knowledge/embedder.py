"""Async-first HF Inference embedder.

Pollux is asyncio-throughout, so this defaults to `AsyncInferenceClient`. A
sync client is also kept around for the rare path that hasn't been awaited
into async yet (e.g. ad-hoc CLI introspection).
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from huggingface_hub import AsyncInferenceClient, InferenceClient

from core.config import PolluxConfig, get_config
from core.telemetry import get_logger

log = get_logger("pollux.knowledge.embedder")


class HFInferenceEmbedder:
    """Wraps the HF Inference Provider routing for embedding only.

    Reads HF_TOKEN, HF_EMBED_MODEL, HF_EMBED_BATCH_SIZE, HF_EMBED_PROVIDER
    from PolluxConfig. Same provider routing pattern as the chat LLM, so a
    misbehaving provider for BGE-M3 can be sidestepped by setting
    HF_EMBED_PROVIDER=together (or whichever).
    """

    def __init__(self, config: PolluxConfig | None = None) -> None:
        self.config = config or get_config()
        if not self.config.hf_token:
            raise RuntimeError(
                "HF_TOKEN is not set. Add it to .env or your environment.\n"
                "Get a free token at https://huggingface.co/settings/tokens"
            )
        self._async_client = AsyncInferenceClient(
            model=self.config.hf_embed_model,
            token=self.config.hf_token,
            provider=self.config.hf_embed_provider,
        )
        self._sync_client = InferenceClient(
            model=self.config.hf_embed_model,
            token=self.config.hf_token,
            provider=self.config.hf_embed_provider,
        )

    @staticmethod
    def _to_list(raw) -> List[List[float]]:
        """Normalize HF's varying return shapes to list[list[float]]."""
        if hasattr(raw, "tolist"):
            raw = raw.tolist()
        if raw and isinstance(raw[0], (int, float)):
            return [list(map(float, raw))]
        return [list(map(float, row)) for row in raw]

    # ----- async (the primary path) -----

    async def aembed(self, texts: List[str]) -> List[List[float]]:
        """Batched async embedding. Splits long input lists to keep payloads
        under the provider's request-size limit."""
        results: List[List[float]] = []
        bs = self.config.hf_embed_batch_size
        for i in range(0, len(texts), bs):
            batch = texts[i : i + bs]
            raw = await self._async_client.feature_extraction(batch)
            results.extend(self._to_list(raw))
        return results

    async def aembed_query(self, text: str) -> List[float]:
        raw = await self._async_client.feature_extraction(text)
        return self._to_list(raw)[0]

    # ----- sync (convenience) -----

    def embed(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        bs = self.config.hf_embed_batch_size
        for i in range(0, len(texts), bs):
            batch = texts[i : i + bs]
            raw = self._sync_client.feature_extraction(batch)
            results.extend(self._to_list(raw))
        return results

    def embed_query(self, text: str) -> List[float]:
        raw = self._sync_client.feature_extraction(text)
        return self._to_list(raw)[0]


@lru_cache(maxsize=1)
def get_embedder() -> HFInferenceEmbedder:
    """Process-wide singleton. The underlying HF clients are stateless +
    thread-safe enough for this use."""
    return HFInferenceEmbedder()
