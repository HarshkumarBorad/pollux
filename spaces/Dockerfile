# syntax=docker/dockerfile:1.6
#
# Pollux HuggingFace Spaces deployment.
#
# Single container running:
#   - Embedded ChromaDB (PersistentClient → /home/user/app/data/chroma_data)
#   - REST API on internal port 8001 (entrypoint runs it in background)
#   - Streamlit UI on port 7860 — the only port HF Spaces exposes publicly
#
# MCP and A2A variants are intentionally NOT exposed here. HF Spaces gives
# you one public port; the docker-compose deploy in the main repo runs all
# four variants side-by-side for that use case.
#
# Run-time config:
#   - HF_TOKEN must be set as a Space secret (Settings → Variables and secrets)
#   - OPENAI_API_KEY is optional (Coordinator + OpsPlanner auto-upgrade if set)
#
FROM python:3.11-slim

# HF Spaces runs containers as a non-root user with UID 1000.
RUN useradd -m -u 1000 user

# Build tools + git (gitpython probes for it on import — DocuMind lesson).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# Install deps first for better layer caching across code-only pushes.
COPY --chown=user:user requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --user --upgrade pip \
    && pip install --no-cache-dir --user -r /tmp/requirements.txt

# Copy app code.
COPY --chown=user:user . .

# Single-container Pollux configuration.
#   POLLUX_API_URL — where the Streamlit UI looks for the REST API
#   CHROMA_MODE=persistent — embed ChromaDB, no separate Chroma service
#   DATABASE_URL — absolute SQLite path; 4 slashes intentional on Linux
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GIT_PYTHON_REFRESH=quiet \
    PYTHONPATH=/home/user/app \
    POLLUX_API_URL=http://127.0.0.1:8001 \
    POLLUX_DATA_DIR=/home/user/app/data \
    CHROMA_MODE=persistent \
    CHROMA_PERSIST_PATH=/home/user/app/data/chroma_data \
    DATABASE_URL=sqlite+aiosqlite:////home/user/app/data/pollux.db \
    APP_ENV=production \
    LOG_FORMAT=json

# HF Spaces standard public port.
EXPOSE 7860

RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
