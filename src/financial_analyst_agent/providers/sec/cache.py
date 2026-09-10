"""Disk cache in front of a live SEC data source."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from financial_analyst_agent.session import SessionBudget


class CachingSECDataSource:
    """Replay SEC JSON from disk; charge live quota only on a miss."""

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
        if self._budget is not None:
            self._budget.consume_live_sec()
        text = str(getter(cik, accession, document))
        path.write_text(text, encoding="utf-8")
        return text

    def _json(self, name: str, fetch: Any) -> object:
        path = self._dir / name
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if self._budget is not None:
            self._budget.consume_live_sec()
        payload = fetch()
        path.write_text(json.dumps(payload), encoding="utf-8")
        return payload
