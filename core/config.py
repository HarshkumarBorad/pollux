"""Pollux global configuration.

A single Pydantic Settings model that pulls from env / .env. Both orchestration
variants (MCP and A2A) and every service (api / ui / agents) read from this
same source — no two configurations to keep in sync.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class PolluxConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM ---
    hf_token: Optional[str] = None
    hf_default_model: str = "Qwen/Qwen2.5-7B-Instruct"
    hf_inference_provider: str = "auto"

    # Optional OpenAI fallback used only by Coordinator + Ops Planner agents
    # where reasoning quality matters most. Blank → HF for everything.
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # --- Storage ---
    # async-friendly SQLite default; swap to postgres+asyncpg for production.
    database_url: str = "sqlite+aiosqlite:///pollux.db"

    # --- Telemetry ---
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "text"
    otel_service_name: str = "pollux"
    # Blank → console exporter only (dev). Set to OTLP HTTP endpoint for prod.
    otel_exporter_endpoint: Optional[str] = None

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- App ---
    app_env: Literal["dev", "staging", "production"] = "dev"

    # --- Orchestration variant (Phases 6 + 7) ---
    # Chosen at startup; same agent business logic either way.
    pollux_orchestration: Literal["mcp", "a2a"] = "mcp"

    # --- Knowledge layer (Phase 2) ---
    # persistent — embedded ChromaDB, on-disk persistence (single-container demo).
    # http       — talks to a separate Chroma service (for split deploys).
    chroma_mode: Literal["persistent", "http"] = "persistent"
    chroma_persist_path: str = "./chroma_data"
    chroma_host: str = "localhost"
    chroma_port: int = 8000
    knowledge_collection: str = "pollux_knowledge"

    # HF embedding model + provider routing. BGE-M3 is multilingual.
    hf_embed_model: str = "BAAI/bge-m3"
    hf_embed_batch_size: int = 32
    hf_embed_provider: str = "auto"

    @property
    def openai_enabled(self) -> bool:
        """True when OpenAI is configured as the Coordinator/Planner fallback."""
        return bool(self.openai_api_key and self.openai_api_key.strip())


@lru_cache(maxsize=1)
def get_config() -> PolluxConfig:
    """Process-wide singleton. Cheap; readers can call it freely."""
    return PolluxConfig()
