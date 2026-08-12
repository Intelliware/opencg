FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/shared-py /app/packages/shared-py
COPY services/pipeline /app/services/pipeline
COPY services/ingestion /app/services/ingestion

# --locked, not a bare sync: without the lockfile the image resolved
# dependencies afresh on every build, so it silently ran a different graphifyy
# than the one pinned for local development. --locked also fails the build if
# pyproject and uv.lock have drifted apart.
RUN uv sync --locked --no-dev --all-packages

ENV OPENCG_CONFIG=/app/opencg.yaml
COPY opencg.yaml /app/opencg.yaml

EXPOSE 8100
CMD ["uv", "run", "--package", "opencg-ingestion", "uvicorn", \
     "opencg_ingestion.server:app", "--host", "0.0.0.0", "--port", "8100"]
