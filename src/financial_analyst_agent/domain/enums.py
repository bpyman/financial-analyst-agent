"""Domain enumerations."""

from enum import StrEnum


class Metric(StrEnum):
    """Closed set of directly reported quarterly metrics."""

    REVENUE = "revenue"
    COST_OF_REVENUE = "cost_of_revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_EXPENSES = "operating_expenses"
    OPERATING_INCOME = "operating_income"
    NET_INCOME = "net_income"


class FormType(StrEnum):
    """SEC form types relevant to quarterly reporting."""

    FORM_10_Q = "10-Q"
    FORM_10_Q_A = "10-Q/A"


class DataSourceKind(StrEnum):
    """Origin of a data value."""

    SEC_XBRL = "sec_xbrl"
