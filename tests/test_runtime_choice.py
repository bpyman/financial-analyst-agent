"""The recorded/live flag picks a runtime, and a built runtime says which one it is."""

import pytest

from financial_analyst_agent.config import AppMode, Settings
from financial_analyst_agent.contracts import RuntimeKind
from financial_analyst_agent.runtime import (
    build_runtime,
    live_runtime,
    recorded_runtime,
    runtime_for,
)
from financial_analyst_agent.turn import Intent, RendererKind, run_turn
from test_run_turn_lookup import ACCESSION, GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, NET_INCOME

_USER_AGENT = "FinancialAnalystAgent (dev@example.com)"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {"_env_file": None, "sec_user_agent": _USER_AGENT}
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_recorded_runtime_replays_recorded_google_net_income() -> None:
    result = run_turn(
        GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY,
        runtime_for(RuntimeKind.RECORDED),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.table_rows[0].value == NET_INCOME
    assert result.table_rows[0].accession_number == ACCESSION


def test_recorded_runtime_reports_recorded() -> None:
    assert recorded_runtime().kind is RuntimeKind.RECORDED


def test_live_runtime_reports_live() -> None:
    settings = _settings(public_demo=True, demo_live_sec=True)

    assert live_runtime(settings).kind is RuntimeKind.LIVE
    assert runtime_for(RuntimeKind.LIVE, settings=settings).kind is RuntimeKind.LIVE


def test_locked_public_demo_builds_recorded_when_live_is_asked_for() -> None:
    settings = _settings(public_demo=True, demo_live_sec=False)

    assert runtime_for(RuntimeKind.LIVE, settings=settings).kind is RuntimeKind.RECORDED


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("recorded", AppMode.RECORDED),
        ("live", AppMode.LIVE),
        ("fixture", AppMode.RECORDED),
        ("FIXTURE", AppMode.RECORDED),
    ],
)
def test_app_mode_accepts_recorded_live_and_the_fixture_alias(
    raw: str, expected: AppMode
) -> None:
    assert _settings(app_mode=raw).app_mode is expected


def test_app_mode_env_fixture_alias_still_builds_the_recorded_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_MODE", "fixture")

    assert build_runtime(Settings(_env_file=None)).kind is RuntimeKind.RECORDED


def test_app_mode_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="app_mode"):
        _settings(app_mode="cassette")


def test_recorded_banner_discloses_recorded_data() -> None:
    from financial_analyst_agent.storefront import RECORDED_BANNER

    # ADR 0006: the window's glossary words; "Guided demo data" is retired.
    assert RECORDED_BANNER.startswith(
        "Recorded runtime — captured SEC filings, not a live EDGAR pull."
    )
    assert "guided demo" not in RECORDED_BANNER.casefold()
