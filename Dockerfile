# Stage 1: build the virtual environment with uv (no dev dependencies, no editable install)
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.6.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock LICENSE README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

# Stage 2: minimal non-root runtime image
FROM python:3.12-slim AS runtime

RUN groupadd --gid 10001 appgroup && \
    useradd --uid 10001 --gid appgroup --shell /sbin/nologin --no-create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
# Read-only runtime data: county table, compliance/vertical configs, and static playground assets.
COPY --chown=appuser:appgroup data ./data
COPY --chown=appuser:appgroup config ./config
COPY --chown=appuser:appgroup web ./web

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROJECT_ROOT=/app \
    PORT=8080

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "uvicorn county_campaign_builder.api:create_app_from_env --factory --host 0.0.0.0 --port ${PORT:-8080}"]
