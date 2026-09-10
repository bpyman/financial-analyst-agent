"""Structured turn logs: thread, turn, and provider timing."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_LOGGER = logging.getLogger("financial_analyst_agent")
_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar(
    "observability_context", default=None
)


def configure_logging() -> None:
    """Emit INFO structured events in Streamlit and CLI runs."""
    _LOGGER.setLevel(logging.INFO)
    if _LOGGER.handlers:
        return
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    token = bind_log_context(**fields)
    try:
        yield
    finally:
        reset_log_context(token)


def bind_log_context(**fields: Any) -> Any:
    current = dict(_CONTEXT.get() or {})
    current.update({key: value for key, value in fields.items() if value is not None})
    return _CONTEXT.set(current)


def reset_log_context(token: Any) -> None:
    _CONTEXT.reset(token)


def log_event(event: str, **fields: Any) -> None:
    payload = {**(_CONTEXT.get() or {}), "event": event, **fields}
    _LOGGER.info(json.dumps(payload, default=str))


def timed(event: str, **fields: Any) -> Callable[..., None]:
    started = time.perf_counter()

    def done(**extra: Any) -> None:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        log_event(event, elapsed_ms=elapsed_ms, **fields, **extra)

    return done


def call_provider[T](name: str, fn: Callable[[], T], **fields: Any) -> T:
    """Time a planner, SEC, news, or LLM call and emit a provider log event."""
    finish = timed("provider", provider=name, **fields)
    try:
        result = fn()
    except Exception as exc:
        finish(ok=False, error=type(exc).__name__)
        raise
    finish(ok=True)
    return result
