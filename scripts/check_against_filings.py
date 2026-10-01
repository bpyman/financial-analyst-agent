"""Check figures the app shows against the filings they cite.

For each (company, metric) below, the live runtime looks up the latest reported
quarter as the window would, then this opens the 10-Q the figure cites and
looks for the number in the filing's own text, at the scale filings print
("$ 109,417" in millions, "109,417,000" in thousands or units, "1.57" per
share). It is an independent check that what the window shows is what the
filing says, outside the XBRL path the app reads from.

Writes docs/evaluation/filing-check.md and filing-check.json.

Usage: uv run python scripts/check_against_filings.py
Needs network access to sec.gov; reads about 25 filings.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from financial_analyst_agent.filing_change import html_to_text
from financial_analyst_agent.runtime import live_runtime

ROOT = Path(__file__).resolve().parent.parent
OUT_MD = ROOT / "docs/evaluation/filing-check.md"
OUT_JSON = ROOT / "docs/evaluation/filing-check.json"

# Reported (not derived) quarterly figures across sectors and metrics.
FIGURES: tuple[tuple[str, str], ...] = (
    ("AAPL", "revenue"),
    ("AAPL", "eps_diluted"),
    ("NVDA", "revenue"),
    ("NVDA", "net_income"),
    ("AMZN", "net_income"),
    ("GOOGL", "research_and_development"),
    ("META", "operating_income"),
    ("JPM", "net_income"),
    ("BAC", "revenue"),
    ("XOM", "revenue"),
    ("CVX", "net_income"),
    ("WMT", "revenue"),
    ("LLY", "revenue"),
    ("PFE", "research_and_development"),
    ("KO", "net_income"),
    ("TSLA", "revenue"),
    ("NFLX", "revenue"),
    ("INTC", "revenue"),
    ("HD", "net_income"),
    ("V", "net_income"),
    ("UNH", "revenue"),
    ("CAT", "revenue"),
    ("BA", "revenue"),
    ("DIS", "revenue"),
    ("JNJ", "eps_diluted"),
)


def _printed_forms(value: Decimal, metric: str) -> list[str]:
    """How a filing may print ``value``: per share to the cent, or in millions,
    thousands or units with thousands separators."""
    amount = abs(value)
    if metric.startswith("eps"):
        return [f"{amount:.2f}"]
    forms = []
    for scale in (Decimal(1_000_000), Decimal(1_000), Decimal(1)):
        scaled = amount / scale
        if scaled == scaled.to_integral_value():
            forms.append(f"{int(scaled):,}")
    if not forms:
        forms.append(f"{amount / Decimal(1_000_000):,.1f}")
    return forms


def _found(text: str, form: str) -> bool:
    # The number on its own: not inside a longer number ("109,4170" or "1,109,417").
    return re.search(rf"(?<![\d,.]){re.escape(form)}(?![\d]|,\d|\.\d)", text) is not None


def main() -> None:
    runtime = live_runtime()
    filings = runtime.filings
    assert filings is not None, "the live runtime reads filing documents"
    rows = []
    for ticker, metric in FIGURES:
        row: dict[str, object] = {"ticker": ticker, "metric": metric}
        try:
            fact = runtime.facts.get_financials(ticker, metric)
        except Exception as exc:  # noqa: BLE001 - reported per figure
            rows.append({**row, "result": "lookup failed", "detail": type(exc).__name__})
            continue
        row.update(
            company=fact.company_name,
            value=str(fact.value),
            period_end=fact.end_date.isoformat(),
            form=fact.form,
            accession=fact.accession_number,
            concept=fact.concept,
            source_url=fact.source_url,
        )
        document = fact.source_url.rsplit("/", 1)[-1]
        if fact.derivation is not None or not fact.form.startswith("10-Q"):
            rows.append({**row, "result": "skipped", "detail": "derived or not a 10-Q"})
            continue
        if document.endswith("-index.htm"):
            rows.append({**row, "result": "skipped", "detail": "no primary document"})
            continue
        text = html_to_text(filings.get_filing_document(fact.cik, fact.accession_number, document))
        forms = _printed_forms(Decimal(fact.value), metric)
        match = next((form for form in forms if _found(text, form)), None)
        rows.append(
            {
                **row,
                "result": "found" if match else "not found",
                "detail": f"printed as {match}" if match else f"looked for {', '.join(forms)}",
            }
        )
    checked = [row for row in rows if row["result"] in ("found", "not found")]
    found = [row for row in checked if row["result"] == "found"]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "runtime": "live (SEC EDGAR)",
        "checked": len(checked),
        "found": len(found),
        "figures": rows,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Figures checked against their filings",
        "",
        f"Generated `{payload['generated_at']}` on the live runtime.",
        "",
        "Each figure is the latest reported quarter the window shows for the company. "
        "The check opens the 10-Q the figure cites and looks for the number in the "
        "filing's own text, at the scale the filing prints it: an independent check, "
        "outside the XBRL data the app reads.",
        "",
        f"**{len(found)} of {len(checked)}** figures appear in their filing's text.",
        "",
        "| Company | Metric | Value | Quarter ended | Filing | Result |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        filing = (
            f"[{row['form']} {row['accession']}]({row['source_url']})" if "accession" in row else ""
        )
        lines.append(
            f"| {row.get('company', row['ticker'])} | {row['metric']} | {row.get('value', '')} "
            f"| {row.get('period_end', '')} | {filing} | {row['result']}: {row['detail']} |"
        )
    lines.append("")
    lines.append("Regenerate with `uv run python scripts/check_against_filings.py`.")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"{len(found)}/{len(checked)} found -> {OUT_MD}")


if __name__ == "__main__":
    main()
