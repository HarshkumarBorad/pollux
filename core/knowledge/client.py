"""ChromaDB client setup.

Two modes, picked via `CHROMA_MODE`:
    persistent (default) — embedded on-disk client; no separate service.
                           Right for single-container deploys (HF Spaces, the
                           Phase 1 docker-compose).
    http                 — talks to a remote Chroma server. Pick this when
                           you split the vector store into its own service.

Telemetry is silenced both ways — both via env var (set before import) and
a Posthog monkey-patch, because chromadb-0.5.x's telemetry helper has a
PostHog version mismatch that prints "Failed to send telemetry event" on
every client init even when telemetry is supposedly disabled. Belt + braces.
"""
from __future__ import annotations

import os

# MUST be set before chromadb is imported — the telemetry singleton reads it
# once at import time and never again.
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from functools import lru_cache

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings

# Second layer of telemetry suppression — see module docstring.
try:
    from chromadb.telemetry.product.posthog import Posthog  # noqa: E402

    Posthog.capture = lambda *args, **kwargs: None
except (ImportError, AttributeError):
    pass

from core.config import PolluxConfig, get_config  # noqa: E402
from core.telemetry import get_logger  # noqa: E402

log = get_logger("pollux.knowledge.client")


def _build_client(config: PolluxConfig):
    settings = Settings(anonymized_telemetry=False)

    if config.chroma_mode == "persistent":
        try:
            return chromadb.PersistentClient(
                path=config.chroma_persist_path,
                settings=settings,
            )
        except AttributeError as exc:
            raise RuntimeError(
                "CHROMA_MODE=persistent requires the full `chromadb` package "
                "(not `chromadb-client`). Already pinned in requirements.txt."
            ) from exc

    if config.chroma_mode == "http":
        return chromadb.HttpClient(
            host=config.chroma_host,
            port=config.chroma_port,
            settings=settings,
        )

    raise ValueError(
        f"CHROMA_MODE must be 'persistent' or 'http'; got {config.chroma_mode!r}"
    )


@lru_cache(maxsize=1)
def get_client():
    """Process-wide singleton."""
    config = get_config()
    log.info(
        "knowledge.client_init",
        mode=config.chroma_mode,
        location=(
            config.chroma_persist_path
            if config.chroma_mode == "persistent"
            else f"{config.chroma_host}:{config.chroma_port}"
        ),
    )
    return _build_client(config)


@lru_cache(maxsize=1)
def get_collection() -> Collection:
    """The shared Pollux knowledge collection.

    Just one collection — domain isolation is enforced by per-chunk `domain`
    metadata, not separate collections. Keeps the retrieval API uniform
    across agents.
    """
    config = get_config()
    return get_client().get_or_create_collection(
        name=config.knowledge_collection,
        metadata={"hnsw:space": "cosine"},
    )
