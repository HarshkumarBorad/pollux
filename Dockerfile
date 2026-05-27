# syntax=docker/dockerfile:1.6
#
# Pollux base image. Single Dockerfile, multiple commands — docker-compose
# overrides CMD per service (api / ui / mcp / a2a) in later phases.
#
FROM python:3.11-slim

WORKDIR /app

# Build tooling for native wheels + git for ragas/gitpython once it's added.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install deps first so they layer-cache independently of source changes.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GIT_PYTHON_REFRESH=quiet

# Phase 1 default — verifies the core module imports cleanly. Replaced by
# uvicorn / streamlit / MCP server / A2A endpoints in later phases.
CMD ["python", "-m", "core.smoketest"]
