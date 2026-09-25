"""The container smoke check (``scripts/smoke_api_image.py``) against a real HTTP server.

CI runs the same check inside the built image (ticket 08). Here it runs against
an in-process uvicorn server on the recorded runtime, so the check's own logic
is pinned offline: it must pass on a healthy API and fail loudly otherwise.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from api_server import free_port, serve, smoke
from financial_analyst_agent.api import create_app
from financial_analyst_agent.config import AppMode, Settings


@pytest.fixture
def recorded_api(tmp_path: Path) -> Iterator[str]:
    settings = Settings(app_mode=AppMode.RECORDED, _env_file=None)  # type: ignore[call-arg]
    yield from serve(create_app(settings, store_root=tmp_path / "threads"))


@pytest.fixture
def guarded_api(tmp_path: Path) -> Iterator[str]:
    settings = Settings(
        app_mode=AppMode.RECORDED,
        api_proxy_token="s3cret",  # type: ignore[arg-type]
        _env_file=None,  # type: ignore[call-arg]
    )
    yield from serve(create_app(settings, store_root=tmp_path / "threads"))


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
        smoke.check_api(f"http://127.0.0.1:{free_port()}", timeout=1)
