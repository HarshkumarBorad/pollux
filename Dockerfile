# syntax=docker/dockerfile:1.6
#
# Pollux base image. One Dockerfile, one image — docker-compose overrides
# the CMD per service so api / ui / mcp / a2a all run from this same image.
#
FROM python:3.11-slim

WORKDIR /app

# Build tooling for native wheels + git (gitpython probes for the binary
# on import even when no git ops are performed — DocuMind lesson).
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
    GIT_PYTHON_REFRESH=quiet \
    PYTHONPATH=/app

# Default — runs the REST API (the surface most consumers want). docker-compose
# overrides this per service: streamlit for the UI, `python -m mcp_variant.server`
# for MCP, `python -m a2a_variant.server` for A2A.
EXPOSE 8001
CMD ["python", "-m", "api.server", "--host", "0.0.0.0", "--port", "8001"]
