FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    # Runtime `uv run` (including `make ingest-git` / smoke via `compose exec`)
    # must not re-resolve or re-sync: the image is built from uv.lock and the
    # runtime user cannot write to /app.
    UV_FROZEN=1 \
    UV_NO_SYNC=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 opencg

COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/shared-py /app/packages/shared-py
COPY services/pipeline /app/services/pipeline
COPY services/ingestion /app/services/ingestion

RUN uv sync --frozen --no-dev --package opencg-ingestion

ENV OPENCG_CONFIG=/app/opencg.yaml
COPY opencg.yaml /app/opencg.yaml

# Clones and smoke fixtures are written under /tmp, which stays writable.
USER opencg
EXPOSE 8100
HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD curl -fsS http://127.0.0.1:8100/healthz || exit 1
CMD ["uv", "run", "--package", "opencg-ingestion", "uvicorn", \
     "opencg_ingestion.server:app", "--host", "0.0.0.0", "--port", "8100"]
