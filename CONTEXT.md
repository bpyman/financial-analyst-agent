# Financial analyst agent

A demo agent that looks up reported quarterly facts, ranks US exchange-listed operating companies from a dated freeze, and answers qualitative questions without inventing numbers.

## Language

**Universe snapshot**:
A dated freeze of US exchange-listed common shares of operating companies. Ranking reads this freeze; it does not rescreen the market on each question.
_Avoid_: live screener, universe, catalog

**Operating company**:
An issuer that runs a business, as opposed to a shell, SPAC, fund, BDC, or other financing vehicle.
_Avoid_: issuer (unqualified), name, entity

**Common share**:
The ordinary equity listing of an operating company, not a preferred, unit, warrant, right, or listed note.
_Avoid_: security, ticker, listing (unqualified)

**Ineligible issuer**:
An operating-company lookalike identified by CIK after security type and industry are not enough to tell it apart.
_Avoid_: blocklist entry, banned ticker
