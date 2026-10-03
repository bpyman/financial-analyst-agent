# One reading of company names, windows and edits, whichever planner proposed them

> **Extends [ADR 0002](0002-lookup-membership.md) and [ADR 0004](0004-ambiguous-metric-clarify.md).** The planner still only proposes; resolution still decides.

The planner comparison found three cases that both planners failed, and three more that only the LLM planner failed. None was a planning error. Each was in the deterministic code that runs after either planner:

- **Two resolvers.** The rules planner read names with the issuer index, but spec resolution read a planner's company field with a narrower SEC-style resolver. So "Goldman Sachs", "Lilly" and "Merck and Co" from the LLM planner were not found. Facts were then fetched by the raw text, and resolved a third time from SEC titles: GS was shown as "company not found", and "Coca-Cola" came back ambiguous between three bottlers.
- **A narrow period reader.** It knew "last N quarters" for six number words. "Past six quarters" and "previous nine quarters" fell back to the latest quarter.
- **Edits read from raw text.** "include Oracle too" became a company called "Oracle too", and "what about Goldman?" meant a swap only to the rules planner.

## Decision

**One resolver.** Spec resolution reads a company field with the planner's issuer index, and the facts lookup is given the snapshot's reading of a name before SEC titles. A ticker typed as one ("TEAM", "$COKE") is that listing even where it is also a name. The index also takes the names the 1,500 largest companies used to file under (SEC submissions), and a listing's security description ("Class A Common Stock", "S.A.B. de C.V.") is not part of the name.

**A name that is also a word.** Whether a word is everyday English comes from case in 10-Q text: filings write "target", "block" and "match" in lower case mid-sentence, and "Nvidia" and "Oracle" with a capital (`scripts/build_everyday_words.py`). An everyday-word name counts only where the question uses it as a company: capitalised mid-sentence, possessive, listed with another company, followed by a figure, a company's verb or a legal form. A capitalised-in-filings name counts unless the question plainly uses the word ("ask the oracle").

**A name several companies share is asked about.** "Lincoln" is Lincoln Electric or Lincoln National. The answer offers the snapshot's largest matches, and the analyst's reply (a number, a ticker or a name) resumes the held question. Guessing the larger company would answer a different question with confidence.

**One period grammar.** A window is a recency word or preposition, a count and a unit. Counts run to ninety-nine in digits or words; "a couple" is 2 and "a dozen" 12. "A few" and "several" read as 4, and the answer says so. Years are four quarters; months are a third of one, rounded up, and said. A model planner may propose a window too (`recent_quarters`). The grammar's reading wins, and the model's stands only where the grammar reads none and the message has a period word at all. So "what about AMD?" cannot pick up a window nobody asked for.

**Edits by their own words.** For both planners, "add", "include", "too" and "as well" add companies, and adding never removes. "What about", "how about" and "same for" put the named companies in place of those on screen, keeping metrics and window. "Swap X for Y" swaps. "Switch the metric to X" and "show X instead" replace the metric. An edit's companies are read with the index, so filler never becomes a company.

**Evaluation discipline.** Cases a planner change was diagnosed on are development cases. A held-out set is written by a separate session after the change, labelled with the product's behaviour, and not read by whoever changed the planner until it has run. A window is scored by the quarters asked for, since the recording holds about nine quarters a company and the answer already says when it shows fewer.

## Considered options

- **Teach the LLM planner more aliases in its prompt.** Rejected: the failures were after planning, and the rules planner, the public demo's default, would not benefit.
- **Resolve every name to the largest matching company.** Rejected: it answers "Lincoln revenue" for a company the analyst may not mean, with no sign that it chose.
- **A hand-written list of everyday-word company names.** Rejected: it goes stale as the snapshot changes. Case in filings is measured, and rebuilt by a script.
- **Let the model's window win when it disagrees with the wording.** Rejected: the wording is what the analyst typed, and the grammar's reading is deterministic and tested.
