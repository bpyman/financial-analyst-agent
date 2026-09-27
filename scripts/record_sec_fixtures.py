"""Refresh the recorded runtime's data: its ranking snapshot and SEC cassette.

Run it after ``build-universe-snapshot`` so the public demo, which is locked to
the recorded runtime, shows the same freeze as the live runtime.

First, ``fixture_universe_snapshot.json`` takes the freeze's ``as_of`` and each
of its companies' market caps, industries, and ``files_quarterly`` flags from
``universe_snapshot.json`` (membership and sectors stay as they are).

Then ``sec_fixture_recordings.json`` is re-recorded from live EDGAR. The
recorded runtime replays it through the same selection code the live runtime
uses, so the cassette holds real EDGAR payloads, trimmed to what the demo reads:

- ``company_tickers``: the SEC ticker rows for every recorded issuer.
- ``submissions``: each issuer's 10-Q and 10-Q/A filings from the last
  ``--quarters`` report dates.
- ``company_facts``: the concepts in ``METRIC_CONCEPTS``, only as reported in
  those filings.
- ``filing_documents``: the Management's Discussion and Analysis and Risk
  Factors sections of the two Microsoft 10-Qs the "What changed" story
  compares, the newest and the one a year before it, as extracted by
  ``filing_change.extract_section``.

Issuers are every company in ``fixture_universe_snapshot.json`` plus the
compare story's extras.

    SEC_USER_AGENT="app-name you@example.com" uv run python scripts/record_sec_fixtures.py
"""

from __future__ import annotations

import argparse
import html
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from financial_analyst_agent.filing_change import REVIEWED_SECTIONS, extract_section
from financial_analyst_agent.services.metric_catalog import METRIC_CONCEPTS

DATA = Path(__file__).resolve().parents[1] / "src" / "financial_analyst_agent" / "data"
CASSETTE = DATA / "sec_fixture_recordings.json"
LIVE_SNAPSHOT = DATA / "universe_snapshot.json"
FIXTURE_SNAPSHOT = DATA / "fixture_universe_snapshot.json"
# Issuers the guided stories and gold prompts name outside the ranking snapshot.
EXTRA_CIKS = ("0001318605", "0001467858")  # Tesla, General Motors
MICROSOFT = "0000789019"
QUARTERLY_FORMS = frozenset({"10-Q", "10-Q/A"})
FACT_FIELDS = ("start", "end", "val", "accn", "fy", "fp", "form", "filed", "frame")
SEC_INTERVAL_SECONDS = 0.15
DISPLAY_NAMES: dict[int, str] = {
    **{
        int(company["cik"]): company["name"]
        for company in json.loads(FIXTURE_SNAPSHOT.read_text())["companies"]
    },
    1318605: "Tesla, Inc.",
    1467858: "General Motors Company",
}


def _sync_fixture_snapshot() -> str:
    """Carry the live freeze's date, caps, industries, and filer flags into the recorded one."""
    raw = FIXTURE_SNAPSHOT.read_text()
    fixture = json.loads(raw)
    live = json.loads(LIVE_SNAPSHOT.read_text())
    caps = {company["cik"]: company["market_cap"] for company in live["companies"]}
    industries = {company["cik"]: company.get("industry", "") for company in live["companies"]}
    # Like write_universe_snapshot, only a False flag is written.
    foreign = {c["cik"] for c in live["companies"] if c.get("files_quarterly", True) is False}
    missing = [c["ticker"] for c in fixture["companies"] if c["cik"] not in caps]
    if missing:
        raise SystemExit(f"The live snapshot has no row for {missing}; update the fixture")
    fixture["as_of"] = live["as_of"]
    for company in fixture["companies"]:
        company["market_cap"] = caps[company["cik"]]
        company["industry"] = industries[company["cik"]]
        if company["cik"] in foreign:
            company["files_quarterly"] = False
        else:
            company.pop("files_quarterly", None)
    trailer = "\n" if raw.endswith("\n") else ""
    FIXTURE_SNAPSHOT.write_text(json.dumps(fixture, indent=2) + trailer)
    return str(live["as_of"])


def _get(url: str, user_agent: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=60) as response:
        body: bytes = response.read()
    time.sleep(SEC_INTERVAL_SECONDS)
    return body


def _get_json(url: str, user_agent: str) -> Any:
    return json.loads(_get(url, user_agent))


def _recorded_ciks() -> list[str]:
    return list(dict.fromkeys([*(f"{cik:010d}" for cik in DISPLAY_NAMES), *EXTRA_CIKS]))


def _quarterly_filings(submissions: dict[str, Any], quarters: int) -> dict[str, list[Any]]:
    recent = submissions["filings"]["recent"]
    keys = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument")
    rows = [
        dict(zip(keys, values, strict=True))
        for values in zip(*(recent[key] for key in keys), strict=True)
        if values[0] in QUARTERLY_FORMS
    ]
    report_dates = sorted({row["reportDate"] for row in rows}, reverse=True)[:quarters]
    kept = [row for row in rows if row["reportDate"] in report_dates]
    return {key: [row[key] for row in kept] for key in keys}


def _trim_submissions(payload: dict[str, Any], quarters: int) -> dict[str, Any]:
    return {
        "cik": payload["cik"],
        "name": payload["name"],
        "tickers": payload.get("tickers", []),
        "filings": {"recent": _quarterly_filings(payload, quarters)},
    }


def _trim_company_facts(payload: dict[str, Any], accessions: set[str]) -> dict[str, Any]:
    facts: dict[str, dict[str, Any]] = {}
    for concepts in METRIC_CONCEPTS.values():
        for taxonomy, concept in concepts:
            body = payload.get("facts", {}).get(taxonomy, {}).get(concept)
            if body is None:
                continue
            units: dict[str, list[dict[str, Any]]] = {}
            for unit, records in body.get("units", {}).items():
                kept = [
                    {field: record[field] for field in FACT_FIELDS if field in record}
                    for record in records
                    if record.get("accn") in accessions
                ]
                if kept:
                    units[unit] = kept
            if units:
                facts.setdefault(taxonomy, {})[concept] = {"units": units}
    return {"cik": payload["cik"], "entityName": payload["entityName"], "facts": facts}


def _section_excerpt(document: str) -> str:
    """Rebuild a filing from just its reviewed sections, one line per paragraph."""
    parts = ["<html><body>"]
    for section in REVIEWED_SECTIONS:
        text = extract_section(document, section)
        if not text:
            raise SystemExit(f"Section {section} not found in the Microsoft filing")
        parts.extend(f"<p>{html.escape(line)}</p>" for line in text.splitlines())
    # A closing item heading ends the last section the way the full filing does.
    parts.append("<p>Item 6. Exhibits</p>")
    parts.append("</body></html>")
    excerpt = "\n".join(parts)
    for section in REVIEWED_SECTIONS:
        if extract_section(excerpt, section) != extract_section(document, section):
            raise SystemExit(f"Excerpt changed the {section} section; refusing to record it")
    return excerpt


def _microsoft_documents(
    submissions: dict[str, Any], user_agent: str
) -> tuple[dict[str, str], tuple[str, str]]:
    recent = submissions["filings"]["recent"]
    rows = sorted(
        (
            (report, accession, document)
            for form, accession, report, document in zip(
                recent["form"],
                recent["accessionNumber"],
                recent["reportDate"],
                recent["primaryDocument"],
                strict=True,
            )
            if form == "10-Q"
        ),
        reverse=True,
    )
    newest = rows[0]
    year_before = str(int(newest[0][:4]) - 1) + newest[0][4:]
    older = next(row for row in rows if row[0] == year_before)
    documents: dict[str, str] = {}
    for _report, accession, document in (older, newest):
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(MICROSOFT)}/"
            f"{accession.replace('-', '')}/{document}"
        )
        raw = _get(url, user_agent).decode("utf-8", errors="replace")
        documents[f"{MICROSOFT}:{accession}:{document}"] = _section_excerpt(raw)
    return documents, (older[1], newest[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quarters", type=int, default=6, help="10-Q report dates per issuer")
    args = parser.parse_args()
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if not user_agent:
        raise SystemExit("Set SEC_USER_AGENT to 'app-name contact@example.com' (SEC policy).")

    print(f"Recorded snapshot now as of {_sync_fixture_snapshot()}")
    ciks = _recorded_ciks()
    tickers = _get_json("https://www.sec.gov/files/company_tickers.json", user_agent)
    wanted = {int(cik) for cik in ciks}
    ticker_rows = [row for row in tickers.values() if row["cik_str"] in wanted]
    # SEC titles are upper-case conformed names ("MICROSOFT CORP"); show the same
    # display names the ranking table uses so a company reads alike across stories.
    for row in ticker_rows:
        row["title"] = DISPLAY_NAMES.get(row["cik_str"], row["title"])
    missing = wanted - {row["cik_str"] for row in ticker_rows}
    if missing:
        raise SystemExit(f"SEC ticker index has no row for CIKs {sorted(missing)}")

    submissions: dict[str, Any] = {}
    company_facts: dict[str, Any] = {}
    full_microsoft: dict[str, Any] = {}
    for cik in ciks:
        raw_submissions = _get_json(
            f"https://data.sec.gov/submissions/CIK{cik}.json", user_agent
        )
        trimmed = _trim_submissions(raw_submissions, args.quarters)
        submissions[cik] = trimmed
        accessions = set(trimmed["filings"]["recent"]["accessionNumber"])
        raw_facts = _get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", user_agent
        )
        company_facts[cik] = _trim_company_facts(raw_facts, accessions)
        if cik == MICROSOFT:
            full_microsoft = raw_submissions
        print(f"{cik} {raw_submissions['name']}: {len(accessions)} filings")

    # The filing-change story needs the year-ago 10-Q, which may predate --quarters.
    documents, (older, newer) = _microsoft_documents(
        {"filings": {"recent": _quarterly_filings(full_microsoft, 8)}}, user_agent
    )
    kept = submissions[MICROSOFT]["filings"]["recent"]
    if older not in kept["accessionNumber"]:
        all_rows = _quarterly_filings(full_microsoft, 8)
        index = all_rows["accessionNumber"].index(older)
        for key, values in kept.items():
            values.append(all_rows[key][index])

    cassette = {
        "company_tickers": {str(index): row for index, row in enumerate(ticker_rows)},
        "submissions": submissions,
        "company_facts": company_facts,
        "filing_documents": documents,
    }
    CASSETTE.write_text(json.dumps(cassette, indent=2) + "\n")
    print(f"Wrote {CASSETTE.name}: filing-change story compares {older} with {newer}")


if __name__ == "__main__":
    main()
