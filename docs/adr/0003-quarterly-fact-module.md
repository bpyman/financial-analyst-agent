# Quarterly fact module: one call, one fact

Lookup, compare, and rank-and-lookup all need the latest standalone 10-Q number for a name and one reported metric. Today that path returns a tuple and leaves related-CIK / 404 / cache wiring in `SecFactLookup` for callers to interpret. The deepened module’s interface is `get_financials(company: str, metric: str) -> FinancialFact`. Not required for the interview POC that shipped 20 August 2026; remaining deepening is unscheduled. Do not fold in ADR 0002 membership; that is a different seam in front of this module.

## Locked

- Membership (operating company / ineligible issuer / freeze presence) is out.
- One reported metric per call. No margins, no compare, no period alignment.
- `fact_selector` and `filing_selector` stay internal seams; keep their unit tests.
- Need algebra (`disclose(Who/What/When/How)`), PDF, multi-period, and extra currencies are out.

## Interface

```python
class FactsPort(Protocol):
    def get_financials(self, company: str, metric: str) -> FinancialFact: ...
```

- `company`: unresolved name, ticker, or 10-digit CIK. Callers never pass a resolved `Company`. Google → Alphabet stays inside identity (`providers/sec/aliases.py`).
- `metric`: one of `revenue`, `cost_of_revenue`, `gross_profit`, `operating_expenses`, `operating_income`, `net_income`, `research_and_development`, `selling_general_and_administrative`, `interest_expense`, `income_tax_expense`, `pretax_income`. Unknown string → `UnknownMetricError` (existing `parse_metric`).
- Result: one USD **quarterly fact** (`FinancialFact`): Decimal, `directly_reported=True`, duration 70–110 days, newest `report_date`, `10-Q/A` before `10-Q`, provenance on the object (`accession_number`, `concept`, `taxonomy`, `start_date`/`end_date`, `source_url`, `cik`, `ticker`, `company_name`).
- Construction: inject the SEC adapter only (`SECClient` live, `RecordedSECDataSource` cassette). No `close`, `resolve`, or `related_lookup_ciks` on this interface.

Errors that may leave the module: `CompanyNotFoundError`, `AmbiguousCompanyError`, `UnknownMetricError`, `AmbiguousFactError`, `UnsupportedQuarterlyFactError`, `ProviderError`.

`FilingNotFoundError` stays internal (selector/filing code may still raise it). At this seam it becomes `UnsupportedQuarterlyFactError`. `AmbiguousFactError` is never swallowed by related-CIK fallback.

```python
fact = facts.get_financials("Google", "net_income")
fact = facts.get_financials(member.cik, "net_income")
```

## Implementation (behind the seam)

Keep this behavior; stop exporting it:

1. Resolve identity from the ticker map (name / ticker / CIK).
2. Fetch submissions for the resolved CIK; parse filings.
3. Related CIKs: ticker-map CIK first, then a distinct accession-prefix filer if present.
4. For each related CIK: fetch companyfacts. HTTP 404 → skip to the next CIK. Any other `ProviderError` → raise.
5. Parse XBRL for the metric, USD; run filing + standalone-quarter selection (existing selectors).
6. Memoize tickers, submissions-by-CIK, and companyfacts-by-CIK on the lookup instance for the life of one `run_turn`.
7. If every CIK 404s companyfacts → `UnsupportedQuarterlyFactError`. If selection fails after a successful payload → re-raise that selector error (`AmbiguousFactError` or `UnsupportedQuarterlyFactError`).

Invariants unchanged: no YTD subtraction, no derived Q4, no float.

Adapters at the internal SEC seam (already two, keep both): `get_company_tickers`, `get_submissions(cik)`, `get_company_facts(cik)`. Cassette JSON stays source-shaped.

## Callers to change

- `FactsPort` and `SecFactLookup.get_financials` return `FinancialFact`, not `tuple`.
- `turn.py`: drop `_lookup_facts` unwrap / `len != 1` at this seam. Lookup uses the fact directly. Compare still calls once per reported component. Rank-and-lookup still passes ranking CIKs as strings.
- `mcp_server.get_financials`: dump one object. Delete the `{facts: [...]}` branch.
- Tests that fake `get_financials`: return one fact, not a 1-tuple. Fakes that raise `FilingNotFoundError` through the port should raise `UnsupportedQuarterlyFactError` instead. Successor/404 tests stay on `get_financials`. `related_lookup_ciks` may remain a private helper; do not add it to the port.

Do not implement ADR 0002 in this change. Do not add formula methods.

## Considered Options

- **Keep `tuple[FinancialFact, ...]`** — rejected: conflict is already `AmbiguousFactError`.
- **Need algebra** — rejected: speculative generality for callers that do not exist.
- **Expose `related_lookup_ciks`** — rejected: implementation. Orchestration tests go through `get_financials`.
- **Put membership inside `get_financials`** — rejected: ADR 0002 is a seam in front of this module.
