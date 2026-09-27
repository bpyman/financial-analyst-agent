"""The recorded runtime and the live runtime, and the builders that choose between them."""

import json
import threading
from functools import lru_cache
from pathlib import Path

from financial_analyst_agent.config import AppMode, Settings, get_settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.essay import OpenAIEssayCompleter
from financial_analyst_agent.facts import RecordedSECDataSource
from financial_analyst_agent.news import (
    FIXTURE_NEWS_QUERY,
    FIXTURE_RESEARCH_QUERY,
    RecordedNewsSearch,
    TavilyNewsSearch,
)
from financial_analyst_agent.planner import OpenAIStructuredCompleter
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.rules_planner import (
    _ISSUER_PHRASES as _ISSUER_PHRASES,
)
from financial_analyst_agent.rules_planner import (
    FIXTURE_UNIVERSE_SNAPSHOT_PATH as FIXTURE_UNIVERSE_SNAPSHOT_PATH,
)
from financial_analyst_agent.rules_planner import (
    RECORDED_FILING_NEWER as RECORDED_FILING_NEWER,
)
from financial_analyst_agent.rules_planner import (
    RECORDED_FILING_OLDER as RECORDED_FILING_OLDER,
)
from financial_analyst_agent.rules_planner import (
    DemoCompleter as DemoCompleter,
)
from financial_analyst_agent.rules_planner import (
    _companies_from_query as _companies_from_query,
)
from financial_analyst_agent.rules_planner import issuer_index, recorded_issuer_index
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.session import SessionBudget
from financial_analyst_agent.turn import Runtime, RuntimeKind

FIXTURE_EXPLAIN_ESSAY = (
    "AI can disrupt healthcare by automating imaging review, triage, and documentation. "
    "Common use cases include clinical decision support, administrative coding, "
    "and patient outreach."
)
FIXTURE_EXPLAIN_QUERY = "How can AI disrupt healthcare?"
# Written from the recorded Microsoft 10-Q pair's changes, one per reviewed
# section, and replayed only for that evidence. No numerals, so the numeral lock
# has nothing to check against the grounding.
RECORDED_DISCLOSURE_SUMMARIES = {
    (RECORDED_FILING_OLDER, RECORDED_FILING_NEWER, "mda"): (
        "Management's highlights now report faster Microsoft Cloud and Azure growth "
        "and add the commercial remaining performance obligation, while Windows OEM "
        "and Devices and Xbox content and services revenue now fell where a year "
        "earlier they grew."
    ),
    (RECORDED_FILING_OLDER, RECORDED_FILING_NEWER, "risk_factors"): (
        "The Risk Factors edits are small: competition now “could” rather than "
        "“may” affect results, and the platform risk adds that scale is needed to "
        "meet consumer demand."
    ),
}
RECORDED_SUMMARY_MISSING = (
    "No summary is shown: the recorded demo holds one only for the Microsoft 10-Qs "
    "it recorded. The live runtime can summarize any filing pair."
)


def _recorded_disclosure_summary(tool_json: str) -> str:
    """The recorded summary for exactly this evidence, one sentence per section."""
    try:
        payload = json.loads(tool_json)
    except json.JSONDecodeError as exc:
        raise ProviderError("Recorded disclosure changes were invalid") from exc
    if not isinstance(payload, list) or not payload:
        raise ProviderError(RECORDED_SUMMARY_MISSING)
    keys: list[tuple[str, str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ProviderError(RECORDED_SUMMARY_MISSING)
        key = (
            str(item.get("older_accession") or ""),
            str(item.get("newer_accession") or ""),
            str(item.get("section") or ""),
        )
        if key not in RECORDED_DISCLOSURE_SUMMARIES:
            raise ProviderError(RECORDED_SUMMARY_MISSING)
        if key not in keys:
            keys.append(key)
    return " ".join(RECORDED_DISCLOSURE_SUMMARIES[key] for key in keys)


class RecordedEssayCompleter:
    """Recorded essay so explain and news_and_explain turns stay offline."""

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if not tool_json:
            if query.strip().casefold() != FIXTURE_EXPLAIN_QUERY.casefold():
                raise ProviderError(
                    "The recorded demo only replays one captured essay, for "
                    f"“{FIXTURE_EXPLAIN_QUERY}”. Other qualitative questions need "
                    "the live runtime."
                )
            return FIXTURE_EXPLAIN_ESSAY
        if query.strip().casefold() not in {
            FIXTURE_NEWS_QUERY.casefold(),
            FIXTURE_RESEARCH_QUERY.casefold(),
        } and "disclosure changes" not in query.casefold():
            raise ProviderError("No recorded fixture news essay for this prompt")
        if "disclosure changes" in query.casefold():
            return _recorded_disclosure_summary(tool_json)
        try:
            payload = json.loads(tool_json)
        except json.JSONDecodeError as exc:
            raise ProviderError("Recorded fixture news input was invalid") from exc
        if not isinstance(payload, list):
            raise ProviderError("Recorded fixture news input was not a list")
        sentences: list[str] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            published = str(item.get("published") or "").strip()
            if not title:
                continue
            sentence = f"{title}: {snippet}" if snippet else title
            if published:
                sentence = f"{sentence} ({published})"
            sentences.append(sentence)
        if not sentences:
            raise ProviderError("Recorded fixture news input contained no usable hits")
        return " ".join(sentences)


@lru_cache(maxsize=4)
def _cached_ranking(path: Path | None, _mtime_ns: int) -> SnapshotRanking:
    return SnapshotRanking.from_path(path)


def _display_names(path: Path | None) -> dict[str, str]:
    """Snapshot company names by CIK, for tables that read like the landing page."""
    return {
        company.cik: company.name for company in _snapshot_ranking(path).snapshot_companies()
    }


def _snapshot_ranking(path: Path | None) -> SnapshotRanking:
    """The snapshot is immutable per file version; parse it once, not on every turn."""
    from financial_analyst_agent.universe import DEFAULT_SNAPSHOT_PATH

    resolved = path or DEFAULT_SNAPSHOT_PATH
    return _cached_ranking(path, resolved.stat().st_mtime_ns)


_SEC_CLIENTS: dict[tuple[object, ...], SECClient] = {}
_SEC_CLIENTS_LOCK = threading.Lock()


def _shared_sec_client(settings: Settings) -> SECClient:
    """One SEC client (and connection pool) per configuration for the process.

    A client per turn left an unclosed httpx pool behind on every live turn.
    """
    key = (
        settings.sec_user_agent,
        settings.sec_base_url,
        settings.sec_max_requests_per_second,
        settings.sec_timeout_seconds,
    )
    with _SEC_CLIENTS_LOCK:
        client = _SEC_CLIENTS.get(key)
        if client is None:
            client = SECClient(settings)
            _SEC_CLIENTS[key] = client
        return client


def recorded_runtime() -> Runtime:
    """Replay captured SEC, news, and model responses; never touches the network."""
    return Runtime(
        completer=DemoCompleter(recorded_issuer_index(), recorded=True),
        facts=SecFactLookup(
            client=RecordedSECDataSource(),
            display_names=_display_names(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        ),
        ranking=_snapshot_ranking(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        news=RecordedNewsSearch(),
        essay=RecordedEssayCompleter(),
        kind=RuntimeKind.RECORDED,
    )


def live_runtime(
    settings: Settings | None = None,
    *,
    budget: SessionBudget | None = None,
) -> Runtime:
    resolved = settings or get_settings()
    # Without a key the rules planner plans the question, as on the public demo.
    use_openai = bool(resolved.openai_api_key.strip()) and (
        not resolved.public_demo or resolved.allow_public_openai
    )
    use_tavily = bool(resolved.tavily_api_key.strip()) and (
        not resolved.public_demo or resolved.allow_public_tavily
    )
    completer = (
        OpenAIStructuredCompleter.from_settings(resolved)
        if use_openai
        else DemoCompleter(issuer_index())
    )
    essay = OpenAIEssayCompleter.from_settings(resolved) if use_openai else RecordedEssayCompleter()
    news = TavilyNewsSearch(resolved) if use_tavily else RecordedNewsSearch()
    cache_dir = resolved.sec_cache_dir or Path(".cache") / "sec"
    client = CachingSECDataSource(_shared_sec_client(resolved), Path(cache_dir), budget=budget)
    return Runtime(
        completer=completer,
        facts=SecFactLookup(client=client, display_names=_display_names(None)),
        ranking=_snapshot_ranking(None),
        news=news,
        essay=essay,
        kind=RuntimeKind.LIVE,
    )


def runtime_locked(settings: Settings | None = None) -> bool:
    """Whether this deployment serves only the recorded runtime.

    A public demo (``PUBLIC_DEMO`` on) with ``DEMO_LIVE_SEC`` off is locked.
    """
    resolved = settings or get_settings()
    return bool(resolved.public_demo) and not resolved.demo_live_sec


def resolve_runtime_kind(kind: RuntimeKind, settings: Settings | None = None) -> RuntimeKind:
    """The runtime this deployment serves when ``kind`` is asked for.

    A locked deployment (see ``runtime_locked``) serves recorded for every request.
    """
    if runtime_locked(settings):
        return RuntimeKind.RECORDED
    return kind


def default_runtime_kind(settings: Settings | None = None) -> RuntimeKind:
    """The runtime ``APP_MODE`` selects, after the public-demo lock."""
    resolved = settings or get_settings()
    kind = RuntimeKind.RECORDED if resolved.app_mode is AppMode.RECORDED else RuntimeKind.LIVE
    return resolve_runtime_kind(kind, resolved)


def runtime_for(
    kind: RuntimeKind,
    *,
    settings: Settings | None = None,
    budget: SessionBudget | None = None,
) -> Runtime:
    """Build the runtime asked for.

    A locked public demo builds the recorded runtime even when the live one is asked
    for (see ``resolve_runtime_kind``); read ``Runtime.kind`` for the answer.
    """
    resolved = settings or get_settings()
    if resolve_runtime_kind(kind, resolved) is RuntimeKind.RECORDED:
        return recorded_runtime()
    return live_runtime(resolved, budget=budget)


def build_runtime(settings: Settings | None = None) -> Runtime:
    """Build the runtime ``APP_MODE`` selects."""
    resolved = settings or get_settings()
    return runtime_for(default_runtime_kind(resolved), settings=resolved)
