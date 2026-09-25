"""The container smoke check (``scripts/smoke_api_image.py``) against a real HTTP server.

CI runs the same check inside the built image (ticket 08). Here it runs against
an in-process uvicorn server on the recorded runtime, so the check's own logic
is pinned offline: it must pass on a healthy API and fail loudly otherwise.
"""

from __future__ import annotations

import importlib.util
import socket
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import uvicorn
from fastapi import FastAPI

from financial_analyst_agent.api import create_app
from financial_analyst_agent.config import AppMode, Settings

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_api_image.py"


def _load_smoke() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_api_image", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke()


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _serve(app: FastAPI) -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    runner = threading.Thread(target=server.run, daemon=True)
    runner.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        runner.join(timeout=10)


@pytest.fixture
def recorded_api(tmp_path: Path) -> Iterator[str]:
    settings = Settings(app_mode=AppMode.RECORDED, _env_file=None)  # type: ignore[call-arg]
    yield from _serve(create_app(settings, store_root=tmp_path / "threads"))


@pytest.fixture
def guarded_api(tmp_path: Path) -> Iterator[str]:
    settings = Settings(
        app_mode=AppMode.RECORDED,
        api_proxy_token="s3cret",  # type: ignore[arg-type]
        _env_file=None,  # type: ignore[call-arg]
    )
    yield from _serve(create_app(settings, store_root=tmp_path / "threads"))


def test_smoke_check_passes_on_the_recorded_runtime(recorded_api: str) -> None:
    report = smoke.check_api(recorded_api, timeout=30)

    assert report.runtime == "recorded"
    assert report.story == "Verify a quarterly fact"
    assert "Microsoft" in report.fact_card_company
    assert report.fact_card_value


def test_smoke_check_sends_the_proxy_token(guarded_api: str) -> None:
    report = smoke.check_api(guarded_api, timeout=30, proxy_token="s3cret")

    assert report.runtime == "recorded"


def test_smoke_check_fails_when_the_api_refuses_the_turn(guarded_api: str) -> None:
    with pytest.raises(smoke.SmokeFailure, match="401"):
        smoke.check_api(guarded_api, timeout=30)


def test_smoke_check_fails_when_nothing_answers_health() -> None:
    with pytest.raises(smoke.SmokeFailure, match="health"):
        smoke.check_api(f"http://127.0.0.1:{_free_port()}", timeout=1)
