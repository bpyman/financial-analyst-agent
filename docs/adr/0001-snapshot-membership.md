# Universe snapshot membership is structural, plus a CIK blocklist

Ranking membership is the common share of an operating company: vendor `isEtf`/`isFund`, NYSE/NASDAQ product-suffix tickers, instrument tokens in the listing title, and the FMP industries `Shell Companies` and `Financial - Conglomerates`. Asset Management stays eligible because it mixes operators (BlackRock) with BDCs. Residual non-operators that share an industry with operators are listed by CIK in `src/financial_analyst_agent/data/ineligible_issuers.json`. Future ranking or lookup leaks append a CIK there; they do not change these rules. Lookup and compare apply these same rules without requiring freeze presence; see ADR 0002.

## Considered Options

- **Issuer-name catalogs** (`Fund`, `BDC`, `Acquisition`, `Capital Corp`) — miss ordinary-named shells and the next brand; already false-dropped operating companies.
- **Drop all of Asset Management** — would remove BlackRock, Blackstone, and KKR with the BDCs.
- **Universe-wide companion tickers** (drop `MU` if `M` exists) — treats a letter suffix as a warrant/unit and false-dropped Micron because Macy’s is `M`.
