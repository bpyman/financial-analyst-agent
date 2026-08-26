"""Evidence addressed by identifier so thread checkpoints stay small.

Fetched facts, news hits, and turn results live here. Thread state holds only
references. Reuse across turns is the caller's responsibility to label.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, Protocol
from urllib.parse import quote

from pydantic import BaseModel, Field

from financial_analyst_agent.contracts import Intent, NewsHit, TurnResult

EvidenceKind = Literal["fact", "news", "result"]

THREAD_EVIDENCE_BANNER = "Reused thread evidence"


class EvidenceRecord(BaseModel):
    evidence_id: str
    kind: EvidenceKind
    payload: dict[str, Any] = Field(default_factory=dict)


def fact_evidence_id(
    company: str, metric: str, report_date: date | None = None
) -> str:
    """Stable id so the same cell reuses across turns without refetching."""
    period = report_date.isoformat() if report_date is not None else "latest"
    raw = f"fact|{company.casefold()}|{metric}|{period}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"fact-{digest}"


def news_evidence_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return f"news-{digest}"


def _fact_to_payload(fact: Any) -> dict[str, Any]:
    if hasattr(fact, "model_dump"):
        dumped = fact.model_dump(mode="json")
        return dict(dumped)
    return {
        key: getattr(fact, key)
        for key in (
            "company_name",
            "ticker",
            "cik",
            "metric",
            "value",
            "currency",
            "start_date",
            "end_date",
            "form",
            "accession_number",
            "taxonomy",
            "concept",
            "source_url",
            "source",
        )
        if hasattr(fact, key)
    }


def _payload_to_fact(payload: dict[str, Any]) -> Any:
    data = dict(payload)
    for key in ("start_date", "end_date", "filed_date"):
        raw = data.get(key)
        if isinstance(raw, str):
            data[key] = date.fromisoformat(raw)
    if "value" in data and data["value"] is not None:
        from decimal import Decimal

        data["value"] = Decimal(str(data["value"]))
    return SimpleNamespace(**data)


class EvidenceStore(Protocol):
    def has(self, evidence_id: str) -> bool: ...

    def put_fact(
        self,
        company: str,
        metric: str,
        fact: Any,
        *,
        report_date: date | None = None,
    ) -> str: ...

    def get_fact(self, evidence_id: str) -> Any: ...

    def put_news(self, hit: NewsHit) -> str: ...

    def get_news(self, evidence_id: str) -> NewsHit: ...

    def put_result(self, result: TurnResult) -> str: ...

    def get_result(self, evidence_id: str) -> TurnResult: ...

    def known_ids(self) -> frozenset[str]: ...


class InMemoryEvidenceStore:
    """Process-local evidence for ephemeral conversation threads."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    def has(self, evidence_id: str) -> bool:
        return evidence_id in self._records

    def known_ids(self) -> frozenset[str]:
        return frozenset(self._records)

    def put_fact(
        self,
        company: str,
        metric: str,
        fact: Any,
        *,
        report_date: date | None = None,
    ) -> str:
        evidence_id = fact_evidence_id(company, metric, report_date)
        self._records[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            kind="fact",
            payload=_fact_to_payload(fact),
        )
        return evidence_id

    def get_fact(self, evidence_id: str) -> Any:
        record = self._records[evidence_id]
        if record.kind != "fact":
            raise KeyError(evidence_id)
        return _payload_to_fact(record.payload)

    def put_news(self, hit: NewsHit) -> str:
        evidence_id = news_evidence_id(hit.url)
        self._records[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            kind="news",
            payload=hit.model_dump(mode="json"),
        )
        return evidence_id

    def get_news(self, evidence_id: str) -> NewsHit:
        record = self._records[evidence_id]
        if record.kind != "news":
            raise KeyError(evidence_id)
        return NewsHit.model_validate(record.payload)

    def put_result(self, result: TurnResult) -> str:
        evidence_id = f"result-{uuid.uuid4().hex[:16]}"
        self._records[evidence_id] = EvidenceRecord(
            evidence_id=evidence_id,
            kind="result",
            payload=result.model_dump(mode="json"),
        )
        return evidence_id

    def get_result(self, evidence_id: str) -> TurnResult:
        record = self._records[evidence_id]
        if record.kind != "result":
            raise KeyError(evidence_id)
        return TurnResult.model_validate(record.payload)


class LocalEvidenceStore:
    """JSON files under a directory, one record per evidence id."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, evidence_id: str) -> Path:
        return self._root / f"{quote(evidence_id, safe='')}.json"

    def has(self, evidence_id: str) -> bool:
        return self._path(evidence_id).is_file()

    def known_ids(self) -> frozenset[str]:
        ids: set[str] = set()
        for path in self._root.glob("*.json"):
            try:
                record = EvidenceRecord.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                continue
            ids.add(record.evidence_id)
        return frozenset(ids)

    def _write(self, record: EvidenceRecord) -> None:
        self._path(record.evidence_id).write_text(
            record.model_dump_json(), encoding="utf-8"
        )

    def _read(self, evidence_id: str) -> EvidenceRecord:
        path = self._path(evidence_id)
        if not path.is_file():
            raise KeyError(evidence_id)
        return EvidenceRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def put_fact(
        self,
        company: str,
        metric: str,
        fact: Any,
        *,
        report_date: date | None = None,
    ) -> str:
        evidence_id = fact_evidence_id(company, metric, report_date)
        self._write(
            EvidenceRecord(
                evidence_id=evidence_id,
                kind="fact",
                payload=_fact_to_payload(fact),
            )
        )
        return evidence_id

    def get_fact(self, evidence_id: str) -> Any:
        record = self._read(evidence_id)
        if record.kind != "fact":
            raise KeyError(evidence_id)
        return _payload_to_fact(record.payload)

    def put_news(self, hit: NewsHit) -> str:
        evidence_id = news_evidence_id(hit.url)
        self._write(
            EvidenceRecord(
                evidence_id=evidence_id,
                kind="news",
                payload=hit.model_dump(mode="json"),
            )
        )
        return evidence_id

    def get_news(self, evidence_id: str) -> NewsHit:
        record = self._read(evidence_id)
        if record.kind != "news":
            raise KeyError(evidence_id)
        return NewsHit.model_validate(record.payload)

    def put_result(self, result: TurnResult) -> str:
        evidence_id = f"result-{uuid.uuid4().hex[:16]}"
        self._write(
            EvidenceRecord(
                evidence_id=evidence_id,
                kind="result",
                payload=result.model_dump(mode="json"),
            )
        )
        return evidence_id

    def get_result(self, evidence_id: str) -> TurnResult:
        record = self._read(evidence_id)
        if record.kind != "result":
            raise KeyError(evidence_id)
        return TurnResult.model_validate(record.payload)


class EvidenceCachedFacts:
    """FactsPort wrapper: retain fetched facts and serve them by identifier.

    Ids present before this turn are thread evidence (label reuse). Ids written
    during this turn are run-state cache (no cross-turn label).
    """

    def __init__(
        self,
        inner: Any,
        store: EvidenceStore,
        *,
        prior_ids: frozenset[str],
    ) -> None:
        self._inner = inner
        self._store = store
        self._prior_ids = prior_ids
        self._lock = threading.Lock()
        self.reused_ids: set[str] = set()

    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> Any:
        evidence_id = fact_evidence_id(company, metric, report_date)
        with self._lock:
            cached = self._store.has(evidence_id)
            if cached:
                if evidence_id in self._prior_ids:
                    self.reused_ids.add(evidence_id)
                return self._store.get_fact(evidence_id)
        kwargs: dict[str, Any] = {}
        if report_date is not None:
            kwargs["report_date"] = report_date
        try:
            fact = self._inner.get_financials(company, metric, **kwargs)
        except TypeError:
            # Fixture ports that omit report_date.
            fact = self._inner.get_financials(company, metric)
        with self._lock:
            if not self._store.has(evidence_id):
                self._store.put_fact(company, metric, fact, report_date=report_date)
            elif evidence_id in self._prior_ids:
                self.reused_ids.add(evidence_id)
                return self._store.get_fact(evidence_id)
        return fact

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        listing = getattr(self._inner, "list_quarterly_report_dates", None)
        if listing is None:
            return ()
        dates = listing(company, limit=limit)
        return tuple(dates)


def label_reused_evidence(result: TurnResult, *, reused: bool) -> TurnResult:
    if not reused:
        return result
    banners = list(result.banners)
    if THREAD_EVIDENCE_BANNER not in banners:
        banners.append(THREAD_EVIDENCE_BANNER)
    return result.model_copy(update={"banners": banners})


def retain_result_evidence(store: EvidenceStore, result: TurnResult) -> str:
    """Persist news hits (by url) and the turn result; return the result id."""
    for hit in result.citations:
        store.put_news(hit)
    return store.put_result(result)


def grounding_json_from_result(result: TurnResult | None) -> str:
    """Deterministic analysis payload for a later qualitative numeral lock.

    News and model-analysis essays are not analysis numbers; passing them as
    essay tool JSON makes a later explain treat them as the news set.
    """
    if result is None:
        return ""
    if result.intent in {
        Intent.EXPLAIN,
        Intent.NEWS_AND_EXPLAIN,
        Intent.EXPLORATORY_RESEARCH,
    }:
        return ""
    if not result.table_rows:
        return ""
    return json.dumps(
        [row.model_dump(mode="json") for row in result.table_rows],
        default=str,
    )
