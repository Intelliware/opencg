FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# uv binary for fast installs
COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /usr/local/bin/uv

WORKDIR /app

# Workspace files. uv.lock covers every workspace member, so each member's
# pyproject must be present for --locked to verify against it — hence
# services/ingestion, even though this image never runs it.
COPY pyproject.toml uv.lock ./
COPY packages/shared-py /app/packages/shared-py
COPY services/pipeline /app/services/pipeline
COPY services/ingestion /app/services/ingestion

# --locked, not a bare sync: without the lockfile the image resolved
# dependencies afresh on every build, so it could silently run different
# versions than the ones pinned for local development.
RUN uv sync --locked --no-dev --all-packages

ENV OPENCG_CONFIG=/app/opencg.yaml
COPY opencg.yaml /app/opencg.yaml

EXPOSE 8000
CMD ["uv", "run", "--package", "opencg-pipeline", "uvicorn", \
     "opencg_pipeline.app:app", "--host", "0.0.0.0", "--port", "8000"]
