# syntax=docker/dockerfile:1
# The analysis API (ADR 0006): FastAPI on the recorded runtime unless configured otherwise.
#
#   docker build -t financial-analyst-api .
#   docker run --rm -p 8000:8000 financial-analyst-api

ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${PYTHON_IMAGE} AS build
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /src

# Dependencies first, from the lockfile only, so a code change reuses this layer.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    pip install --no-cache-dir uv==0.8.17 \
    && uv sync --locked --no-dev --no-install-project

# Then the package itself, installed as a wheel (not editable): the runtime
# stage copies only /app/.venv, never the source tree.
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE}
RUN useradd --create-home --uid 10001 --user-group analyst \
    && mkdir -p /app \
    && chown analyst:analyst /app
COPY --from=build /app/.venv /app/.venv

# HOST: listen on all interfaces. PORT: the host platform may override it.
# APP_MODE: the recorded runtime unless the deployment sets APP_MODE=live.
# The thread store is ./.cache/threads under /app, writable by the app user only.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    APP_MODE=recorded
WORKDIR /app
USER analyst
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/health\", timeout=4)"]

CMD ["serve-api"]
