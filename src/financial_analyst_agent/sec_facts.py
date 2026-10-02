"""SEC fact lookup over an injectable live or recorded data source."""

import threading
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import date
from typing import Any, Protocol

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.enums import PERIODIC_FORMS, Metric
from financial_analyst_agent.domain.errors import (
    SOURCE_FAILURES,
    DataIntegrityError,
    FilingNotFoundError,
    IneligibleIssuerError,
    PerShareNotDerivableError,
    ProviderError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import Company, FactRecord, Filing, FinancialFact
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.company_facts import parse_company_facts
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.providers.sec.submissions import (
    files_quarterly_reports,
    parse_submissions,
    trim_submissions,
)
from financial_analyst_agent.providers.sec.tickers import parse_cik
from financial_analyst_agent.providers.sec.urls import build_filing_source_url
from financial_analyst_agent.services.fact_selector import (
    derive_quarter,
    derive_trailing_year,
    select_instant_fact,
    select_quarterly_fact_with_filing_fallback,
)
from financial_analyst_agent.services.filing_selector import (
    FISCAL_WEEK_TOLERANCE,
    get_annual_filings,
    get_candidate_filings,
    latest_period_end,
    list_quarterly_report_dates,
)
from financial_analyst_agent.services.fiscal_periods import (
    FiscalLabel,
    FiscalPeriod,
    fiscal_labels,
    gross_profit_from_components,
    periods_from_filings,
    revenue_from_components,
    sum_of_components,
)
from financial_analyst_agent.services.metric_catalog import (
    GROSS_PROFIT_EXCLUDING_CONCEPTS,
    INSTANT_METRICS,
    METRIC_CONCEPTS,
    TRAILING_YEAR_METRICS,
    metric_unit,
    parse_metric,
)
from financial_analyst_agent.universe import INELIGIBLE_ISSUER_CIKS, sec_identity_is_operating

# How many periods back "latest" may step when SEC has not yet added the
# newest filings' numbers to companyfacts. A year: Citigroup's companyfacts
# lagged two 10-Qs in September 2026.
_LATEST_FALLBACK = 4


class SECDataSource(Protocol):
    """Provider boundary shared by live EDGAR and offline recordings."""

    def get_company_tickers(self) -> dict[str, Any]: ...

    def get_submissions(self, cik: str) -> dict[str, Any]: ...

    def get_company_facts(self, cik: str) -> dict[str, Any]: ...

    def close(self) -> None: ...


# History the submissions list must span before company facts is asked for more.
_FULL_HISTORY_DAYS = 3 * 365
# Every concept a metric reads. A company's facts file holds a thousand concepts
# and parses to about 40 MB for a bank; once its whole-file summaries are taken,
# only these stay in memory (about 2 MB), so a ten-company ranking fits.
_READ_CONCEPTS = frozenset(
    concept for candidates in METRIC_CONCEPTS.values() for concept in candidates
) | frozenset(GROSS_PROFIT_EXCLUDING_CONCEPTS)
# Facts files parsed at once across the process: a spike of rankings would
# otherwise hold dozens of whole files in memory together. Only the parse holds
# a slot; the download happens before it, so a slow SEC holds none.
_FACTS_PARSE_SLOTS = threading.BoundedSemaphore(2)
# Fewer periodic reports than this marks a new registrant worth a predecessor check.
_THIN_HISTORY = 4


# A quarter whose filing SEC lists but whose facts its structured data lacks yet.
PENDING_IN_XBRL_MESSAGE = "SEC's structured data does not yet include this quarter's filing"
# Every entry SEC holds for the metric is malformed: not the same as not reported.
UNREADABLE_FACTS_MESSAGE = "SEC's structured data for this metric could not be read"


def _related_lookup_ciks(resolved_cik: str, predecessor: str | None) -> tuple[str, ...]:
    """The listed company's CIK, then its verified predecessor's (ExxonMobil's old CIK).

    An accession number's prefix alone is not enough: a subsidiary co-registrant
    (Georgia Power) files under its parent's prefix, and a filing agent
    (Workiva, Donnelley) under its own, so neither names the company asked for.
    """
    if predecessor is None or predecessor == resolved_cik:
        return (resolved_cik,)
    return (resolved_cik, predecessor)


def _select_or_derive(
    records: list[FactRecord],
    filings: list[Filing],
    metric: Metric,
    unit: str,
    company_name: str,
    ticker: str,
    cik: str,
    *,
    report_date: date | None,
    filer_ciks: Mapping[str, str] | None = None,
) -> FinancialFact:
    fact = _select_or_derive_in_unit(
        records,
        filings,
        metric,
        unit,
        company_name,
        ticker,
        cik,
        report_date=report_date,
        filer_ciks=filer_ciks,
    )
    # EPS is filtered by its "USD/shares" unit but is still an amount in dollars.
    return fact if fact.currency == "USD" else fact.model_copy(update={"currency": "USD"})


def _select_or_derive_in_unit(
    records: list[FactRecord],
    filings: list[Filing],
    metric: Metric,
    unit: str,
    company_name: str,
    ticker: str,
    cik: str,
    *,
    report_date: date | None,
    filer_ciks: Mapping[str, str] | None = None,
) -> FinancialFact:
    """A reported quarter when a filing has one, else a derived quarter (ADR 0007).

    ``filer_ciks`` names the registrant whose EDGAR folder holds a filing, when
    it is not ``cik`` (a predecessor's reports, see ``SecFactLookup._filings``).
    """
    by_accession = {filing.accession_number: filing for filing in filings}
    folders = filer_ciks or {}

    def source_url_for_filing(filing: Filing) -> str:
        return build_filing_source_url(folders.get(filing.accession_number, cik), filing)

    def source_url_for_accession(accession: str) -> str:
        filing = by_accession.get(accession)
        if filing is not None:
            return source_url_for_filing(filing)
        return build_filing_source_url(
            folders.get(accession, cik),
            Filing(
                form="",
                accession_number=accession,
                filed_date=date.min,
                report_date=date.min,
            ),
        )

    if report_date is None:
        raise FilingNotFoundError("No 10-Q or 10-K filing found")
    try:
        quarterly = get_candidate_filings(filings, report_date=report_date)
    except FilingNotFoundError:
        quarterly = []
    candidates = quarterly or get_annual_filings(filings, report_date=report_date)
    if not candidates:
        raise FilingNotFoundError(
            "No 10-Q or 10-K for reporting period",
            details={"report_date": report_date.isoformat()},
        )
    last: UnsupportedQuarterlyFactError | None = None
    if metric in INSTANT_METRICS or metric in TRAILING_YEAR_METRICS:
        for filing in candidates:
            try:
                if metric in INSTANT_METRICS:
                    return select_instant_fact(
                        records,
                        filing,
                        metric,
                        unit,
                        company_name,
                        ticker,
                        cik,
                        source_url_for_filing(filing),
                    )
                return derive_trailing_year(
                    records,
                    filing,
                    metric,
                    unit,
                    company_name,
                    ticker,
                    cik,
                    source_url_for_filing(filing),
                    source_url_for_accession,
                )
            except UnsupportedQuarterlyFactError as exc:
                last = last or exc
        assert last is not None
        raise last
    if quarterly:
        try:
            return select_quarterly_fact_with_filing_fallback(
                records,
                filings,
                metric,
                unit,
                company_name,
                ticker,
                cik,
                source_url_for_filing,
                report_date=report_date,
            )[0]
        except UnsupportedQuarterlyFactError as exc:
            last = exc
    for filing in candidates:
        try:
            return derive_quarter(
                records,
                filing,
                metric,
                unit,
                company_name,
                ticker,
                cik,
                source_url_for_filing(filing),
                source_url_for_accession,
            )
        except PerShareNotDerivableError:
            raise
        except UnsupportedQuarterlyFactError as exc:
            last = last or exc
    assert last is not None
    raise last


class SecFactLookup:
    """SEC XBRL lookup behind the application's get_financials port."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: SECDataSource | None = None,
        display_names: Mapping[str, str] | None = None,
        listed_tickers: Mapping[str, str] | None = None,
    ) -> None:
        # SEC's ticker file titles companies "AMAZON COM INC"; the snapshot
        # knows them as "Amazon.com, Inc.". Keyed by 10-digit CIK.
        self._display_names: Mapping[str, str] = display_names or {}
        # The snapshot's listing for a company with several (GOOG of GOOGL and
        # GOOG), so a table row and the ranking name it alike. Keyed by CIK.
        self._listed_tickers: Mapping[str, str] = listed_tickers or {}
        self._tickers: dict[str, Any] | None = None
        # A document that failed once this turn fails again without asking SEC:
        # a ranking's metrics and periods would otherwise ask six times each.
        self._failures: dict[str, BaseException] = {}
        self._resolved_by_query: dict[str, Company] = {}
        self._submissions_by_cik: dict[str, dict[str, Any]] = {}
        self._company_facts_by_cik: dict[str, dict[str, Any] | None] = {}
        self._facts_filings_by_cik: dict[str, list[Filing]] = {}
        self._fiscal_labels_by_cik: dict[str, dict[str, FiscalLabel]] = {}
        self._predecessor_ciks: dict[str, str | None] = {}
        if client is not None:
            self._client: SECDataSource = client
            self._owns_client = False
            return
        if settings is None:
            raise TypeError("settings are required when no SEC data source is provided")
        self._client = SECClient(settings)
        self._owns_client = True

    def display_name(self, cik: str, fallback: str) -> str:
        """The snapshot's name for a company, or ``fallback`` (SEC's title)."""
        return self._display_names.get(cik, fallback)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _remembering_failure[T](self, key: str, fetch: Callable[[], T]) -> T:
        failed = self._failures.get(key)
        if failed is not None:
            raise failed
        try:
            return fetch()
        except SOURCE_FAILURES as exc:
            if not (isinstance(exc, ProviderError) and exc.details.get("status_code") == 404):
                self._failures[key] = exc
            raise

    def _cached_company_tickers(self) -> dict[str, Any]:
        if self._tickers is None:
            self._tickers = self._remembering_failure("tickers", self._client.get_company_tickers)
        return self._tickers

    def _resolve(self, company: str) -> Company:
        # Resolution scans the whole ticker map; a turn repeats the same query per
        # metric, period, and formula component.
        resolved = self._resolved_by_query.get(company)
        if resolved is None:
            resolved = resolve_company(company, self._cached_company_tickers())
            self._resolved_by_query[company] = resolved
        return resolved

    def _cached_submissions(self, cik: str) -> dict[str, Any]:
        payload = self._submissions_by_cik.get(cik)
        if payload is None:
            payload = trim_submissions(
                self._remembering_failure(
                    f"submissions:{cik}", lambda: self._client.get_submissions(cik)
                )
            )
            self._submissions_by_cik[cik] = payload
        return payload

    def _filings(self, cik: str) -> list[Filing]:
        """The issuer's filings, with its predecessor's when it is a new registrant.

        A holding-company reorganisation (ExxonMobil in 2026) gives the listed
        company a new CIK whose history starts at the reorganisation. Its first
        reports are filed jointly with the old registrant, so the old CIK is found
        from them, and its filings supply the quarters before.
        """
        filings = self._with_facts_filings(cik, parse_submissions(self._cached_submissions(cik)))
        if cik not in self._predecessor_ciks:
            self._predecessor_ciks[cik] = self._find_predecessor(cik, filings)
        predecessor = self._predecessor_ciks[cik]
        if predecessor is None:
            return filings
        known = {filing.accession_number for filing in filings}
        older = [
            filing
            for filing in parse_submissions(self._cached_submissions(predecessor))
            if filing.accession_number not in known
        ]
        return sorted([*filings, *older], key=lambda filing: filing.filed_date, reverse=True)

    def _with_facts_filings(self, cik: str, filings: list[Filing]) -> list[Filing]:
        """``filings`` plus the 10-Qs and 10-Ks company facts names, for a short history.

        SEC's submissions list the last year or 1,000 filings; a bank filing
        thousands of prospectuses a year shows a year of reports there. Company
        facts carries every periodic report's accession, form, filing date and
        period, so the quarters before are found without paging through years
        of prospectuses.
        """
        if _periodic_history_days(filings) >= _FULL_HISTORY_DAYS:
            return filings
        try:
            self._cached_company_facts(cik)
        except ProviderError:
            return filings
        known = {filing.accession_number for filing in filings}
        extra = [
            filing
            for filing in self._facts_filings_by_cik.get(cik, [])
            if filing.accession_number not in known
        ]
        if not extra:
            return filings
        return sorted([*filings, *extra], key=lambda filing: filing.filed_date, reverse=True)

    def _with_predecessor_facts(
        self, records: list[FactRecord], predecessor: str, metric: Metric, unit: str
    ) -> tuple[list[FactRecord], dict[str, str]]:
        """``records`` plus the predecessor's, so a quarter can span the reorganisation."""
        try:
            payload = self._cached_company_facts(predecessor)
        except ProviderError as exc:
            if exc.details.get("status_code") != 404:
                raise
            return records, {}
        older, _rejections = parse_company_facts(payload, metric, unit)
        seen = {(record.accession_number, record.start_date, record.end_date) for record in records}
        extra = [
            record
            for record in older
            if (record.accession_number, record.start_date, record.end_date) not in seen
        ]
        own = {record.accession_number for record in records}
        folders = {
            record.accession_number: predecessor
            for record in extra
            if record.accession_number not in own
        }
        return [*records, *extra], folders

    def _find_predecessor(self, cik: str, filings: list[Filing]) -> str | None:
        periodic = [filing for filing in filings if filing.form in PERIODIC_FORMS]
        if len(periodic) >= _THIN_HISTORY:
            return None
        for filing in periodic:
            other = parse_cik(filing.accession_number.split("-", 1)[0])
            if other is None or other == cik:
                continue
            try:
                theirs = parse_submissions(self._cached_submissions(other))
            except ProviderError:
                continue
            # A filing agent's own submissions do not list its client's report;
            # a joint registrant's do.
            if any(item.accession_number == filing.accession_number for item in theirs):
                return other
        return None

    def _cached_company_facts(self, cik: str) -> dict[str, Any]:
        if cik in self._company_facts_by_cik:
            payload = self._company_facts_by_cik[cik]
            if payload is None:
                raise ProviderError(
                    "No SEC companyfacts response exists for the issuer",
                    details={"cik": cik, "status_code": 404},
                )
            return payload
        try:
            payload = self._remembering_failure(f"facts:{cik}", lambda: self._parsed_facts(cik))
        except ProviderError as exc:
            if exc.details.get("status_code") == 404:
                self._company_facts_by_cik[cik] = None
            raise
        self._company_facts_by_cik[cik] = payload
        return payload

    def _parsed_facts(self, cik: str) -> dict[str, Any]:
        prefetch = getattr(self._client, "prefetch_company_facts", None)
        if callable(prefetch):
            prefetch(cik)
        with _FACTS_PARSE_SLOTS:
            payload = self._client.get_company_facts(cik)
            # The summaries read every concept; the rest of the turn reads only the catalog's.
            self._fiscal_labels_by_cik.setdefault(cik, fiscal_labels(payload))
            self._facts_filings_by_cik[cik] = filings_from_company_facts(payload)
            return _read_concepts_only(payload)

    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> FinancialFact:
        parsed_metric = parse_metric(metric)
        unit = metric_unit(parsed_metric)
        resolved = self._resolve(company)
        # Lookup applies the ranking's membership rule (ADR 0002): a snapshot member
        # has been judged already, unless its CIK was listed ineligible since the
        # snapshot was built; any other name is judged by its SEC identity.
        if resolved.cik in INELIGIBLE_ISSUER_CIKS or (
            resolved.cik not in self._listed_tickers
            and not sec_identity_is_operating(resolved.cik, resolved.name)
        ):
            raise IneligibleIssuerError(
                f"{resolved.name} is not an operating company (it is a fund, business "
                "development company or similar listing), so its 10-Q figures are "
                "outside what this analyst covers.",
                details={"cik": resolved.cik},
            )
        listed = self._listed_tickers.get(resolved.cik)
        ticker = (
            listed
            if listed in resolved.tickers
            else resolved.tickers[0]
            if resolved.tickers
            else company.upper()
        )
        filings = self._filings(resolved.cik)
        # "Latest" is the newest period any 10-Q or 10-K covers (ADR 0007).
        target = report_date if report_date is not None else latest_period_end(filings)
        last_unsupported: UnsupportedQuarterlyFactError | FilingNotFoundError | None = None
        last_missing: ProviderError | None = None
        unreadable = False
        related = _related_lookup_ciks(resolved.cik, self._predecessor_ciks.get(resolved.cik))
        for cik in related:
            try:
                company_facts_payload = self._cached_company_facts(cik)
            except ProviderError as exc:
                if exc.details.get("status_code") != 404:
                    raise
                last_missing = exc
                continue
            records, rejections = parse_company_facts(company_facts_payload, parsed_metric, unit)
            unreadable = unreadable or (not records and bool(rejections))
            filer_ciks: dict[str, str] = {}
            predecessor = self._predecessor_ciks.get(resolved.cik)
            if cik == resolved.cik and predecessor is not None:
                records, filer_ciks = self._with_predecessor_facts(
                    records, predecessor, parsed_metric, unit
                )
            name = self._display_names.get(resolved.cik, resolved.name)
            targets: list[date | None] = [target]
            if report_date is None:
                targets = list(list_quarterly_report_dates(filings, limit=_LATEST_FALLBACK))
            for period in targets:
                try:
                    fact = self._select_with_fallbacks(
                        company_facts_payload,
                        records,
                        filings,
                        parsed_metric,
                        unit,
                        name,
                        ticker,
                        cik,
                        report_date=period,
                        filer_ciks=filer_ciks,
                    )
                except (UnsupportedQuarterlyFactError, FilingNotFoundError) as exc:
                    last_unsupported = exc
                    if (
                        report_date is not None
                        and period is not None
                        and not self._period_in_xbrl(cik, filings, period)
                        and any(
                            abs(filing.report_date - period) <= FISCAL_WEEK_TOLERANCE
                            for filing in filings
                        )
                    ):
                        # Filed, but SEC's company facts have not caught up with it.
                        last_unsupported = UnsupportedQuarterlyFactError(
                            PENDING_IN_XBRL_MESSAGE, details={"metric": parsed_metric.value}
                        )
                    if period is None or report_date is not None:
                        break
                    if self._period_in_xbrl(cik, filings, period):
                        break
                    # SEC has not yet added the newest filing to companyfacts;
                    # "latest" is then the newest quarter it has.
                    continue
                if period is not None and period != targets[0]:
                    fact = fact.model_copy(update={"newer_filing_end": targets[0]})
                return fact
        if unreadable:
            raise DataIntegrityError(
                UNREADABLE_FACTS_MESSAGE, details={"metric": parsed_metric.value}
            ) from last_unsupported
        if isinstance(last_unsupported, FilingNotFoundError):
            raise UnsupportedQuarterlyFactError(
                str(last_unsupported),
                details=last_unsupported.details,
            ) from last_unsupported
        if last_unsupported is not None:
            raise last_unsupported
        if last_missing is not None:
            raise UnsupportedQuarterlyFactError(
                "No SEC companyfacts response exists for the issuer",
                details={"metric": parsed_metric.value},
            ) from last_missing
        raise UnsupportedQuarterlyFactError(
            "No directly reported standalone-quarter fact exists for metric",
            details={"metric": parsed_metric.value},
        )

    def _select_with_fallbacks(
        self,
        payload: dict[str, Any],
        records: list[FactRecord],
        filings: list[Filing],
        metric: Metric,
        unit: str,
        company_name: str,
        ticker: str,
        cik: str,
        *,
        report_date: date | None,
        filer_ciks: Mapping[str, str] | None = None,
    ) -> FinancialFact:
        if metric is Metric.REVENUE:
            fact = _select_or_derive(
                records,
                filings,
                metric,
                unit,
                company_name,
                ticker,
                cik,
                report_date=report_date,
                filer_ciks=filer_ciks,
            )
            return self._plausible_revenue(
                fact, payload, filings, unit, company_name, ticker, cik, filer_ciks=filer_ciks
            )
        try:
            return _select_or_derive(
                records,
                filings,
                metric,
                unit,
                company_name,
                ticker,
                cik,
                report_date=report_date,
                filer_ciks=filer_ciks,
            )
        except UnsupportedQuarterlyFactError:
            if metric is Metric.DEPRECIATION_AMORTIZATION:
                return self._depreciation_plus_amortization(
                    payload,
                    filings,
                    unit,
                    company_name,
                    ticker,
                    cik,
                    report_date=report_date,
                    filer_ciks=filer_ciks,
                )
            if metric is not Metric.GROSS_PROFIT:
                raise
            # Retailers (Costco, Walmart) tag no gross profit line; revenue
            # minus cost of revenue is the same amount (ADR 0007).
            parts = []
            for component in (Metric.REVENUE, Metric.COST_OF_REVENUE):
                component_records, _ = parse_company_facts(payload, component, unit)
                parts.append(
                    _select_or_derive(
                        component_records,
                        filings,
                        component,
                        unit,
                        company_name,
                        ticker,
                        cik,
                        report_date=report_date,
                        filer_ciks=filer_ciks,
                    )
                )
            revenue, cost = parts
            if (revenue.start_date, revenue.end_date) != (cost.start_date, cost.end_date):
                raise
            if _reports_excluding_costs(payload, revenue.end_date):
                raise
            return gross_profit_from_components(revenue, cost)

    def _plausible_revenue(
        self,
        revenue: FinancialFact,
        payload: dict[str, Any],
        filings: list[Filing],
        unit: str,
        company_name: str,
        ticker: str,
        cik: str,
        *,
        filer_ciks: Mapping[str, str] | None,
    ) -> FinancialFact:
        """Revenue, unless the filing's own gross profit or cost of revenue exceeds it.

        Plexus tagged a quarter's revenue as $1,304,778, its thousands without
        their scale, beside $131 million of gross profit. Revenue is then gross
        profit plus cost of revenue, both as filed, when the two cover the
        quarter; otherwise the mis-scaled figure is refused, never shown.
        """
        parts: list[FinancialFact] = []
        for component in (Metric.GROSS_PROFIT, Metric.COST_OF_REVENUE):
            component_records, _ = parse_company_facts(payload, component, unit)
            try:
                parts.append(
                    _select_or_derive(
                        component_records,
                        filings,
                        component,
                        unit,
                        company_name,
                        ticker,
                        cik,
                        report_date=revenue.end_date,
                        filer_ciks=filer_ciks,
                    )
                )
            except (UnsupportedQuarterlyFactError, FilingNotFoundError):
                continue
        period = (revenue.start_date, revenue.end_date)
        same = {part.metric: part for part in parts if (part.start_date, part.end_date) == period}
        gross, cost = same.get(Metric.GROSS_PROFIT), same.get(Metric.COST_OF_REVENUE)
        if gross is not None and cost is not None:
            total = gross.value + cost.value
            # Cost above revenue is a negative gross margin, not an error, when
            # the three agree; only a revenue the parts do not add up to is.
            agrees = abs(total - revenue.value) <= abs(total) / 100
            if agrees or revenue.value >= max(gross.value, cost.value):
                return revenue
            return revenue_from_components(revenue, gross, cost)
        if gross is None or not gross.value > revenue.value > 0:
            return revenue
        raise UnsupportedQuarterlyFactError(
            "The filing's revenue is smaller than its own gross profit or cost of "
            "revenue, so the filed figure is mis-scaled",
            details={"metric": Metric.REVENUE.value, "concept": revenue.concept},
        )

    def _depreciation_plus_amortization(
        self,
        payload: dict[str, Any],
        filings: list[Filing],
        unit: str,
        company_name: str,
        ticker: str,
        cik: str,
        *,
        report_date: date | None,
        filer_ciks: Mapping[str, str] | None,
    ) -> FinancialFact:
        """D&A as depreciation plus amortization of intangibles (Microsoft, Alphabet).

        Both must cover the same period; depreciation alone would understate it.
        """
        parts = []
        for component in (Metric.DEPRECIATION, Metric.AMORTIZATION_OF_INTANGIBLES):
            component_records, _ = parse_company_facts(payload, component, unit)
            parts.append(
                _select_or_derive(
                    component_records,
                    filings,
                    component,
                    unit,
                    company_name,
                    ticker,
                    cik,
                    report_date=report_date,
                    filer_ciks=filer_ciks,
                )
            )
        return sum_of_components(Metric.DEPRECIATION_AMORTIZATION, parts)

    def _fiscal_labels(self, cik: str) -> dict[str, FiscalLabel]:
        if cik not in self._fiscal_labels_by_cik:
            # Reading the facts records their labels before trimming them.
            self._cached_company_facts(cik)
        return self._fiscal_labels_by_cik.get(cik, {})

    def _period_in_xbrl(self, cik: str, filings: list[Filing], period: date) -> bool:
        labels = self._fiscal_labels(cik)
        return any(
            filing.accession_number in labels
            for filing in filings
            if abs(filing.report_date - period) <= FISCAL_WEEK_TOLERANCE
        )

    def fiscal_periods(self, company: str) -> tuple[FiscalPeriod, ...]:
        """Every 10-Q and 10-K period end with the fiscal year and quarter it declares.

        Newest first. A 10-K's period is the fiscal fourth quarter.
        """
        resolved = self._resolve(company)
        filings = self._filings(resolved.cik)
        labels: dict[str, FiscalLabel] = {}
        predecessor = self._predecessor_ciks.get(resolved.cik)
        for cik in (predecessor, resolved.cik):
            if cik is None:
                continue
            try:
                labels.update(self._fiscal_labels(cik))
            except ProviderError as exc:
                if exc.details.get("status_code") != 404:
                    raise
        return periods_from_filings(filings, labels)

    def files_quarterly(self, company: str) -> tuple[bool, str]:
        """(Whether the company files 10-Qs, its name). False for 20-F/40-F filers."""
        resolved = self._resolve(company)
        name = self._display_names.get(resolved.cik, resolved.name)
        return files_quarterly_reports(self._cached_submissions(resolved.cik)), name

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        """Newest-first distinct quarterly report dates for a company."""
        resolved = self._resolve(company)
        return tuple(list_quarterly_report_dates(self._filings(resolved.cik), limit=limit))


def _read_concepts_only(payload: dict[str, Any]) -> dict[str, Any]:
    """Company facts with only the concepts a metric reads; other keys kept as they are."""
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return payload
    kept = {
        taxonomy: {
            name: body for name, body in concepts.items() if (taxonomy, name) in _READ_CONCEPTS
        }
        if isinstance(concepts, dict)
        else concepts
        for taxonomy, concepts in facts.items()
    }
    return {**payload, "facts": kept}


def _reports_excluding_costs(payload: dict[str, Any], end: date) -> bool:
    """Whether the company reports costs that "cost of revenue" leaves out, for ``end``."""
    facts = payload.get("facts", {})
    for taxonomy, concept in GROSS_PROFIT_EXCLUDING_CONCEPTS:
        body = facts.get(taxonomy, {}).get(concept)
        if body is None:
            continue
        for records in body.get("units", {}).values():
            if any(record.get("end") == end.isoformat() for record in records):
                return True
    return False


def _periodic_history_days(filings: list[Filing]) -> int:
    ends = [filing.report_date for filing in filings if filing.form in PERIODIC_FORMS]
    return (max(ends) - min(ends)).days if ends else 0


def filings_from_company_facts(payload: dict[str, Any]) -> list[Filing]:
    """The 10-Qs and 10-Ks company facts cites: accession, form, filing date and period.

    A report's period is the latest end date that many of its financial facts
    share: a 10-K can carry as many prior-year comparatives as current facts,
    and a few subsequent-event facts are dated after the period. Cover-page
    (dei) facts such as shares outstanding are dated later and are left out.
    Its primary document is not in company facts, so its source link is the
    filing's index page.
    """
    seen: dict[str, tuple[str, date, Counter[date]]] = {}
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return []
    for taxonomy, concepts in facts.items():
        if taxonomy == "dei" or not isinstance(concepts, dict):
            continue
        for concept in concepts.values():
            units = concept.get("units") if isinstance(concept, dict) else None
            if not isinstance(units, dict):
                continue
            for entries in units.values():
                for entry in entries if isinstance(entries, list) else []:
                    _note_filing(seen, entry)
    return [
        Filing(
            form=form,
            accession_number=accession,
            filed_date=filed,
            report_date=_report_period(ends),
        )
        for accession, (form, filed, ends) in seen.items()
    ]


def _report_period(ends: Counter[date]) -> date:
    """The latest end date with at least half as many facts as the commonest one."""
    most = max(ends.values())
    return max(end for end, count in ends.items() if count * 2 >= most)


def _note_filing(seen: dict[str, tuple[str, date, Counter[date]]], entry: Any) -> None:
    if not isinstance(entry, dict) or entry.get("form") not in ("10-Q", "10-K"):
        return
    accession, filed, end = entry.get("accn"), entry.get("filed"), entry.get("end")
    if not (isinstance(accession, str) and isinstance(filed, str) and isinstance(end, str)):
        return
    try:
        filed_date, end_date = date.fromisoformat(filed), date.fromisoformat(end)
    except ValueError:
        return
    if accession not in seen:
        seen[accession] = (str(entry["form"]), filed_date, Counter())
    seen[accession][2][end_date] += 1
