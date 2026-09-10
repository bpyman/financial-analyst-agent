"""Structured turn logs: thread, turn, and provider timing."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

_LOGGER = logging.getLogger("financial_analyst_agent")


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    _LOGGER.info(json.dumps(payload, default=str))


def timed(event: str, **fields: Any) -> Callable[..., None]:
    started = time.perf_counter()

    def done(**extra: Any) -> None:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log_event(event, elapsed_ms=elapsed_ms, **fields, **extra)

    return done
