"""Disk cache in front of a live SEC data source."""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any

from financial_analyst_agent.session import SessionBudget

_FILL_LOCKS: dict[str, Lock] = {}
_FILL_LOCKS_GUARD = Lock()


def _lock_for(path: Path) -> Lock:
    key = str(path.resolve())
    with _FILL_LOCKS_GUARD:
        lock = _FILL_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _FILL_LOCKS[key] = lock
        return lock


def _write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class CachingSECDataSource:
    """Cache SEC JSON for one hour and accession-pinned HTML indefinitely."""

    def __init__(
        self,
        inner: Any,
        cache_dir: Path,
        *,
        budget: SessionBudget | None = None,
    ) -> None:
        self._inner = inner
        self._dir = cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._budget = budget

    def close(self) -> None:
        close = getattr(self._inner, "close", None)
        if callable(close):
            close()

    def get_company_tickers(self) -> dict[str, Any]:
        payload = self._json("tickers.json", self._inner.get_company_tickers)
        if not isinstance(payload, dict):
            raise TypeError("cached company tickers must be an object")
        return payload

    def get_submissions(self, cik: str) -> dict[str, Any]:
        payload = self._json(f"submissions-{cik}.json", lambda: self._inner.get_submissions(cik))
        if not isinstance(payload, dict):
            raise TypeError("cached submissions must be an object")
        return payload

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        payload = self._json(f"facts-{cik}.json", lambda: self._inner.get_company_facts(cik))
        if not isinstance(payload, dict):
            raise TypeError("cached company facts must be an object")
        return payload

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        getter = getattr(self._inner, "get_filing_document", None)
        if not callable(getter):
            raise AttributeError("inner SEC source does not fetch filing documents")
        safe = "".join(ch if ch.isalnum() or ch in "-._" else "_" for ch in document)
        path = self._dir / f"html-{cik}-{accession}-{safe}"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        with _lock_for(path):
            if path.is_file():
                return path.read_text(encoding="utf-8")
            if self._budget is not None:
                self._budget.consume_live_sec()
            text = str(getter(cik, accession, document))
            _write_text_atomic(path, text)
            return text

    def _json(self, name: str, fetch: Any) -> object:
        path = self._dir / name
        if self._json_is_fresh(path):
            return json.loads(path.read_text(encoding="utf-8"))
        with _lock_for(path):
            if self._json_is_fresh(path):
                return json.loads(path.read_text(encoding="utf-8"))
            if self._budget is not None:
                self._budget.consume_live_sec()
            payload = fetch()
            _write_text_atomic(path, json.dumps(payload))
            return payload

    def _json_is_fresh(self, path: Path) -> bool:
        return path.is_file() and time.time() - path.stat().st_mtime < 3600
