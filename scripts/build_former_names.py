"""Build data/former_names.json: names the snapshot's larger companies used to file under.

People keep using a company's old name: "Square" for Block, "Raytheon
Technologies" for RTX. SEC submissions list each filer's former names; the
issuer index takes them as phrases a current name does not already hold.

Usage: uv run python scripts/build_former_names.py [--top N]
Reads the top N operating companies of the universe snapshot by market cap
(SEC_USER_AGENT needed). Submissions are cached in .cache/sec-corpus/.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from financial_analyst_agent.config import get_settings
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.universe import is_common_operating_listing, load_universe_snapshot

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src/financial_analyst_agent/data/former_names.json"
CACHE = ROOT / ".cache/sec-corpus"
# Names dropped before this year are rarely what anyone types now.
SINCE_YEAR = 2005


def _submissions(client: SECClient, cik: str) -> dict[str, Any]:
    path = CACHE / f"submissions-{cik}.json"
    if path.exists():
        return dict(json.loads(path.read_text(encoding="utf-8")))
    payload = client.get_submissions(cik, with_history=False)
    CACHE.mkdir(parents=True, exist_ok=True)
    slim = {"formerNames": payload.get("formerNames", [])}
    path.write_text(json.dumps(slim), encoding="utf-8")
    return slim


def main(top: int) -> None:
    snapshot = load_universe_snapshot(None)
    ranked = sorted(
        (company for company in snapshot.companies if is_common_operating_listing(company)),
        key=lambda company: company.market_cap,
        reverse=True,
    )
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    client = SECClient(get_settings())
    try:
        for company in ranked:
            if company.cik in seen:
                continue
            seen.add(company.cik)
            if len(seen) > top:
                break
            try:
                former = _submissions(client, company.cik).get("formerNames", [])
            except Exception as error:  # noqa: BLE001 - one filer's failure skips it
                print(f"skip {company.ticker}: {error}")
                continue
            for entry in former:
                until = str(entry.get("to") or "")[:10]
                if until and date.fromisoformat(until).year >= SINCE_YEAR:
                    rows.append({"ticker": company.ticker, "name": str(entry["name"])})
    finally:
        client.close()
    OUT.write_text(json.dumps({"names": rows}, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} former names of {len(seen)} companies -> {OUT}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=1500)
    main(parser.parse_args().top)
