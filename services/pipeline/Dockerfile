FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    # Runtime `uv run` must not re-resolve or re-sync: the image is built from
    # uv.lock and the runtime user cannot write to /app.
    UV_FROZEN=1 \
    UV_NO_SYNC=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 opencg

# uv binary for fast installs
COPY --from=ghcr.io/astral-sh/uv:0.5.10 /uv /usr/local/bin/uv

WORKDIR /app

# Workspace files. uv.lock pins every version; the ingestion pyproject is
# copied only so the locked workspace is complete (its code is not installed).
COPY pyproject.toml uv.lock ./
COPY packages/shared-py /app/packages/shared-py
COPY services/pipeline /app/services/pipeline
COPY services/ingestion/pyproject.toml /app/services/ingestion/pyproject.toml

RUN uv sync --frozen --no-dev --package opencg-pipeline

ENV OPENCG_CONFIG=/app/opencg.yaml
COPY opencg.yaml /app/opencg.yaml

USER opencg
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=6 \
  CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1
CMD ["uv", "run", "--package", "opencg-pipeline", "uvicorn", \
     "opencg_pipeline.app:app", "--host", "0.0.0.0", "--port", "8000"]
