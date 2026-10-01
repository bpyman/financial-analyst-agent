"""Build data/sec_filer_names.json: operating SEC filers outside the ranking snapshot.

The rules planner finds companies by the names in the snapshot, so a filer the
snapshot leaves out is not found by name: "Southern California Edison" read as
California Resources and Edison International, "Entergy Texas" as its parent
Entergy, and "Consumers Energy" as nothing. These are listed SEC filers (often
subsidiaries whose only listed shares are preferreds) that file their own 10-Qs.
This file names them so the planner can, without a network call per question.

Every CIK in SEC's company_tickers.json that is not in the snapshot, not on the
ineligible list, not an instrument by its SEC title (ADR 0002) and not named as a
fund is written
once, with its first listed ticker. Rebuild it when the snapshot is rebuilt.

Usage: uv run python scripts/build_sec_filer_names.py
Needs SEC_USER_AGENT (or the default in config) and network access to sec.gov.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from financial_analyst_agent.config import get_settings
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.tickers import extract_usable_ticker_entries
from financial_analyst_agent.universe import (
    DEFAULT_SNAPSHOT_PATH,
    INELIGIBLE_ISSUER_CIKS,
    load_universe_snapshot,
    sec_identity_is_operating,
)

OUT = (
    Path(__file__).resolve().parent.parent / "src/financial_analyst_agent/data/sec_filer_names.json"
)
# Closed-end funds, ETFs and blank-check companies (SPACs) list on exchanges too;
# they are not operating companies (ADR 0001).
FUND_NAME = re.compile(
    r"\b(?:funds?|etf|portfolio|municipal|bonds?|acquisitions?)\b", re.IGNORECASE
)
SOURCE = "https://www.sec.gov/files/company_tickers.json"


def main() -> None:
    entries = extract_usable_ticker_entries(SECClient(get_settings()).get_company_tickers())
    snapshot = load_universe_snapshot(DEFAULT_SNAPSHOT_PATH)
    in_snapshot = {company.cik for company in snapshot.companies}
    filers: dict[str, dict[str, str]] = {}
    for entry in entries:
        cik = entry["cik"]
        if cik in filers or cik in in_snapshot or cik in INELIGIBLE_ISSUER_CIKS:
            continue
        if not sec_identity_is_operating(cik, entry["title"]) or FUND_NAME.search(entry["title"]):
            continue
        # SEC lists a filer's main listing first.
        filers[cik] = {"cik": cik, "ticker": entry["ticker"], "name": entry["title"]}
    rows = sorted(filers.values(), key=lambda filer: filer["cik"])
    # One filer per line keeps a rebuild's diff readable.
    lines = ",\n".join(f"    {json.dumps(row)}" for row in rows)
    OUT.write_text(
        "{\n"
        f'  "source": {json.dumps(SOURCE)},\n'
        f'  "built": "{datetime.now(UTC).date().isoformat()}",\n'
        f'  "snapshot": {json.dumps(DEFAULT_SNAPSHOT_PATH.name)},\n'
        f'  "filers": [\n{lines}\n  ]\n'
        "}\n",
        encoding="utf-8",
    )
    print(f"{len(filers)} filers outside the snapshot -> {OUT}")


if __name__ == "__main__":
    main()
