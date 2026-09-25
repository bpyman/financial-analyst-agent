"""Smoke-test the analysis API image, or any running API, before a deploy (ticket 08).

Checks that the API answers its health check, that a new thread starts on the
recorded runtime, and that the "Verify a quarterly fact" guided story streams
back a quarterly fact card.

    python3 scripts/smoke_api_image.py --image financial-analyst-api:ci
    python3 scripts/smoke_api_image.py --base-url http://127.0.0.1:8000
    SMOKE_PROXY_TOKEN=... python3 scripts/smoke_api_image.py --base-url https://<api host>

``--image`` runs the image the way a host would (``$PORT`` set, no ``APP_MODE``),
waits for Docker's own health check, runs the HTTP checks, and confirms the
image runs as a non-root user and holds no source tree or dev tooling. It uses
the standard library only, so CI can run it without installing the project.

The proxy token for an API behind the web proxy comes from ``--proxy-token`` or,
when that is absent, from ``$SMOKE_PROXY_TOKEN``. Scripts pass it in the
environment, since a command-line argument is visible to anyone who can list
processes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

STORY = "Verify a quarterly fact"
PROXY_TOKEN_HEADER = "X-Proxy-Token"
PROXY_TOKEN_ENV = "SMOKE_PROXY_TOKEN"
# The host sets $PORT; Render's default is 10000. Not 8000, so the check proves
# the image listens on $PORT rather than on a hard-coded port.
CONTAINER_PORT = 10000
# What the runtime image may hold under /app: the installed environment only.
IMAGE_APP_ENTRIES = [".venv"]
DEV_MODULES = ("pytest", "ruff", "mypy")


class SmokeFailure(Exception):
    """The API or image failed a smoke check; the message says which."""


@dataclass(frozen=True)
class SmokeReport:
    runtime: str
    story: str
    question: str
    fact_card_company: str
    fact_card_value: str


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    proxy_token: str | None,
    timeout: float,
) -> bytes:
    headers = {"Accept": "application/json, text/event-stream"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if proxy_token:
        headers[PROXY_TOKEN_HEADER] = proxy_token
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload: bytes = response.read()
            return payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        raise SmokeFailure(f"{method} {path} answered {exc.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise SmokeFailure(f"{method} {path} failed: {exc}") from None


def wait_for_health(base_url: str, *, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last = "no answer"
    while True:
        try:
            body = _request(base_url, "GET", "/api/health", proxy_token=None, timeout=5)
            if json.loads(body) == {"status": "ok"}:
                return
            last = body.decode(errors="replace")[:200]
        except SmokeFailure as exc:
            last = str(exc)
        if time.monotonic() >= deadline:
            raise SmokeFailure(f"health check did not pass within {timeout:g}s: {last}")
        time.sleep(0.5)


def _sse_events(stream: bytes) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in stream.decode().strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            events.append((fields["event"], json.loads(fields.get("data", "{}"))))
    return events


def check_api(
    base_url: str,
    *,
    timeout: float = 120,
    proxy_token: str | None = None,
    expected_runtime: str = "recorded",
) -> SmokeReport:
    """Health, a new thread on the deployment's default runtime, and one guided turn."""
    wait_for_health(base_url, timeout=timeout)

    def call(method: str, path: str, body: dict[str, Any] | None = None) -> bytes:
        return _request(
            base_url, method, path, body=body, proxy_token=proxy_token, timeout=timeout
        )

    meta = json.loads(call("GET", "/api/meta"))
    stories = {story["label"]: story["question"] for story in meta["guided_stories"]}
    if STORY not in stories:
        raise SmokeFailure(f"/api/meta has no guided story {STORY!r}: {sorted(stories)}")
    question = stories[STORY]

    thread = json.loads(call("POST", "/api/threads"))
    runtime = thread.get("runtime")
    if runtime != expected_runtime:
        raise SmokeFailure(f"a new thread started on {runtime!r}, not {expected_runtime!r}")

    turn_path = f"/api/threads/{thread['thread_id']}/turns"
    events = _sse_events(call("POST", turn_path, {"message": question}))
    if not events:
        raise SmokeFailure("the turn stream sent no events")
    kind, data = events[-1]
    if kind != "thread":
        raise SmokeFailure(f"the turn ended with {kind!r}: {data}")
    turns = data.get("turns") or []
    card = turns[-1]["presentation"].get("fact_card") if turns else None
    if not card:
        raise SmokeFailure(f"{STORY!r} returned no fact card")
    return SmokeReport(
        runtime=runtime,
        story=STORY,
        question=question,
        fact_card_company=str(card["company_name"]),
        fact_card_value=str(card["amount"]),
    )


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SmokeFailure(f"docker {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def _in_image(image: str, *command: str) -> subprocess.CompletedProcess[str]:
    return _docker("run", "--rm", "--entrypoint", command[0], image, *command[1:], check=False)


def check_image_contents(image: str) -> None:
    """Non-root user, only the installed environment under /app, no dev tooling."""
    user = _in_image(image, "id", "-u").stdout.strip()
    if not user or user == "0":
        raise SmokeFailure(f"the image runs as uid {user or '?'}; it must not run as root")
    entries = sorted(_in_image(image, "ls", "-A", "/app").stdout.split())
    if entries != IMAGE_APP_ENTRIES:
        raise SmokeFailure(f"/app holds {entries}; expected only {IMAGE_APP_ENTRIES}")
    probe = "import importlib.util as u, sys; print(*(m for m in sys.argv[1:] if u.find_spec(m)))"
    shipped = _in_image(image, "python", "-c", probe, *DEV_MODULES)
    if shipped.returncode != 0 or shipped.stdout.strip():
        raise SmokeFailure(f"the image ships dev tooling: {shipped.stdout}{shipped.stderr}")


def _health_status(container: str) -> str:
    return _docker(
        "inspect", "--format", "{{.State.Status}} {{.State.Health.Status}}", container
    ).stdout.strip()


def check_image(image: str, *, timeout: float) -> SmokeReport:
    check_image_contents(image)
    container = _docker(
        "run", "--detach", "--env", f"PORT={CONTAINER_PORT}",
        "--publish", f"127.0.0.1::{CONTAINER_PORT}", image,
    ).stdout.strip()
    try:
        deadline = time.monotonic() + timeout
        while (status := _health_status(container)) != "running healthy":
            if not status.startswith("running") or time.monotonic() >= deadline:
                logs = _docker("logs", container, check=False)
                raise SmokeFailure(
                    f"container is {status!r}, not healthy\n{logs.stdout}{logs.stderr}"
                )
            time.sleep(1)
        published = _docker("port", container, f"{CONTAINER_PORT}/tcp").stdout.split()[0]
        return check_api(f"http://{published}", timeout=timeout)
    finally:
        _docker("rm", "--force", container, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--image", help="run this image and check it")
    target.add_argument("--base-url", help="check an API that is already running")
    parser.add_argument(
        "--proxy-token",
        help=f"X-Proxy-Token for an API behind the web proxy (default: ${PROXY_TOKEN_ENV})",
    )
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args(argv)
    proxy_token = args.proxy_token
    if proxy_token is None:
        proxy_token = os.environ.get(PROXY_TOKEN_ENV) or None
    try:
        if args.image:
            report = check_image(args.image, timeout=args.timeout)
        else:
            report = check_api(args.base_url, timeout=args.timeout, proxy_token=proxy_token)
    except SmokeFailure as exc:
        print(f"smoke check failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"ok: {report.runtime} runtime, {report.story!r} -> "
        f"{report.fact_card_company} {report.fact_card_value}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
