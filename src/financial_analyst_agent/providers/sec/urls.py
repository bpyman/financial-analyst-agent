"""Build SEC EDGAR provenance URLs for filings."""

from financial_analyst_agent.domain.models import Filing

_SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"


def _cik_path_segment(cik: str) -> str:
    return str(int(cik))


def _accession_path_segment(accession_number: str) -> str:
    return accession_number.replace("-", "")


def build_filing_document_url(cik: str, accession_number: str, document: str) -> str:
    cik_segment = _cik_path_segment(cik)
    accession_segment = _accession_path_segment(accession_number)
    return f"{_SEC_ARCHIVES_BASE}/{cik_segment}/{accession_segment}/{document}"


def build_filing_source_url(cik: str, filing: Filing) -> str:
    """
    Build a continuous URL to the filing's primary HTML document.

    Falls back to the SEC filing index URL when primary_document is missing.
    """
    cik_segment = _cik_path_segment(cik)
    accession_segment = _accession_path_segment(filing.accession_number)
    if filing.primary_document:
        return f"{_SEC_ARCHIVES_BASE}/{cik_segment}/{accession_segment}/{filing.primary_document}"
    return (
        f"{_SEC_ARCHIVES_BASE}/{cik_segment}/{accession_segment}/"
        f"{filing.accession_number}-index.htm"
    )
