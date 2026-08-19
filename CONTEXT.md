# Financial analyst agent

A demo agent that looks up reported quarterly facts for operating companies, ranks snapshot members from a dated freeze, and answers qualitative questions without inventing numbers.

## Language

**Universe snapshot**:
A dated freeze of US exchange-listed common shares of operating companies. Ranking reads this freeze; it does not rescreen the market. Lookup does not require freeze presence. News does not use it.
_Avoid_: live screener, universe, catalog

**Snapshot member**:
An operating company whose common share is present in this universe snapshot.
_Avoid_: SEC filer, listed company, issuer

**Operating company**:
A company that runs a business, as opposed to a shell, SPAC, fund, BDC, or other financing vehicle.
_Avoid_: issuer (unqualified), name, entity

**Common share**:
The ordinary equity listing of an operating company, not a preferred, unit, warrant, right, or listed note.
_Avoid_: security, ticker, listing (unqualified)

**Ineligible issuer**:
An operating-company lookalike identified by CIK after security type and industry are not enough to tell it apart. It is not a snapshot member and cannot be looked up or compared.
_Avoid_: blocklist entry, banned ticker

**Quarterly fact**:
A directly reported standalone-quarter amount from a 10-Q, with provenance.
_Avoid_: TTM, derived quarter, restatement

**Ambiguous metric**:
A user metric phrase that matches more than one name in the closed catalog.
_Avoid_: metric collision, unknown metric

**Unknown metric**:
A user metric phrase that names nothing in the closed catalog.
_Avoid_: ambiguous metric
