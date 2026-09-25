# 08 — Containerize the analysis API

**What to build:** The Python API ships as a Docker image that runs anywhere a container runs:
- installs from the lockfile with uv;
- runs as a non-root user;
- listens on `$PORT` on all interfaces;
- starts in the recorded runtime unless configured otherwise;
- has a health check.

CI builds the image and smoke-tests the health check and one recorded-runtime turn inside the container, so a broken image never reaches a deploy.

Spec: ADR 0006 ("Hosting").

**Blocked by:** 07

**Status:** resolved

- [x] `docker build` succeeds and the running container answers the health check and the "Verify a quarterly fact" turn
- [x] The image excludes dev tooling, tests, `.git`, caches, and `web/`
- [x] CI builds and smoke-tests the image

## Answer

Shipped 2026-09-25.

- `Dockerfile` (repo root): two stages on `python:3.12-slim-bookworm` (overridable with `--build-arg PYTHON_IMAGE=`). The build stage installs uv 0.8.17 from PyPI, runs `uv sync --locked --no-dev --no-install-project` from `pyproject.toml` + `uv.lock`, then installs the package as a wheel (`--no-editable`) with precompiled bytecode. The runtime stage copies only `/app/.venv`, runs as `analyst` (uid 10001), and sets `HOST=0.0.0.0`, `PORT=8000` (the host may override it), and `APP_MODE=recorded`. The thread store lands in `/app/.cache/threads`, which the app user owns. `HEALTHCHECK` calls `/api/health` with Python's urllib (no curl in the image; start interval 2 s). `CMD ["serve-api"]`.
- `.dockerignore` is an allow-list: `pyproject.toml`, `uv.lock`, `src/financial_analyst_agent/`, minus `__pycache__`. Tests, `web/`, `.git`, caches, and `.env` never reach the build context.
- `scripts/smoke_api_image.py` (stdlib only). `--image` runs the image with `PORT=10000`, waits for Docker's health status to read healthy, then checks that a new thread with no runtime starts `recorded` and that the "Verify a quarterly fact" story (question taken from `/api/meta`) streams back a fact card. It also checks that the image is non-root, holds only `.venv` under `/app`, and cannot import pytest, ruff, or mypy. `--base-url` (with `--proxy-token`) runs the same HTTP checks against a running API. `tests/test_api_image_smoke.py` pins the HTTP check against an in-process uvicorn server on the recorded runtime, including its failures (401 without the token, no health).
- CI: a new `image` job runs `docker build` and then the smoke script.
- README: how to build, run, and smoke-test the image.
