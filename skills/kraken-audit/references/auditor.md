You are auditing Kraken, a codebase being rebuilt on Effect 4, for its owner, Fav. He wants to know which entries of his guidance the code does not respect, so he can act on each. Your share is one group of entries: {GROUP}. Other auditors hold the other groups.

## Where you work

- {WHERE}
- Read-only: change nothing, write no file anywhere, run no npm, test or build, and no git command that writes. Load no skill and start no other agent: do the work yourself. Your answer is the text you return.

## What to do

1. Read in full, first: `GUIDANCE.md`, `COMMITMENTS.md`, `ENGINEERING.md`, `CONTRACTS.md`, `DEFAULTS.md`, `GLOSSARY.md`, `docs/decision-log.md`. Note every exception in force in the decision log, with the code it names and what ends it. Code an exception covers is an **excused** breach: report it as excused, never as open.
2. Read the code in full: every file under `src/`. Read `tools/` and `test/` wherever an entry of your group reaches them (tests and checks are code too, held to the same entries).
3. For every entry of your group, listed below, decide whether code breaks it. Go entry by entry, down the whole list. An entry with sub-points is several entries: check each point.
4. Be strict about the text. A breach is code that does not do what the entry's words require; for a default, code that departs from the preferred way with no stated reason in the code, its docs or its commit message. A breach that the tree repeats everywhere, or that the specification prescribes, is still a breach: say that the spec prescribes it. Taste is not a breach.
5. Where an entry is too vague to decide at a place ("thin", "where that simplifies reasoning", "where practical"), say so, judge it by its plain reading and its stated "Why", and note the vague words.
6. You may read `docs/rebuild/` and `docs/enforcement.md` to see whether the spec prescribes a breach and whether the enforcement record already names it.

Your group, as an index generated from the files (the files are the authority):
{CHECKLIST}

## What you return

First, under `## Ledger`, one line per entry of your group, each point of an entry on its own line: the entry's `file:line`, then `meets`, `breaks` or `bears on nothing`, then the places you checked as `file:line`. An entry that bears on tests is checked in `test/` too. The ledger is how you make sure no entry went unchecked; keep each line short.

Then, under `## Breaches`, for each breach, one block:

```
### <short title>
- entry: <file>:<line> "<the exact words of the entry the code fails>"
- kind: commitment | principle | contract | default
- place: <file>:<line-range> (every place that applies)
- why: <two to four sentences: what the code does, and why that does not meet the words>
- severity: high | medium | low  (high: a guarantee to Fav or a binding entry fails in a way that can lose work, leak or mislead)
- level: design (the shape of a module or of a flow across functions) | local (a line or a function)
- spec: prescribes <file:line> | silent | forbids <file:line>
- status: open | excused by <decision-log heading>
- confidence: high | medium
```

Then `## Vague`: one line per place where an entry's words were too vague to decide, with the entry, the words and the place.

Report what you would defend line by line against the entry's text. Do not drop a real breach because it is small.
{RULES}
