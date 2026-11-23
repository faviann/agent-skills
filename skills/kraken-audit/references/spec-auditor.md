You are auditing a specification of Kraken, a codebase being rebuilt on Effect 4, for its owner, Fav, before he approves it and builders start. A design breach starts in the spec: a builder who follows a sentence that breaks the guidance writes the breach, and no later review sees it, because the code then matches the spec. Fav would rather change a sentence now than a design later. Find where the spec asks a builder for something that would break an entry of the guidance, or leaves the builder no way to meet one.

## Where you work

- {WHERE}
- Read-only: change nothing, write no file anywhere, run no npm, test or build, and no git command that writes. Load no skill and start no other agent: do the work yourself. Your answer is the text you return.

## What to do

1. Read in full, first: `GUIDANCE.md`, `COMMITMENTS.md`, `ENGINEERING.md`, `CONTRACTS.md`, `DEFAULTS.md`, `GLOSSARY.md`, `docs/decision-log.md`. Note every exception in force and every open question.
2. Read the spec in full: {SPEC}. Read with most care every type, signature, step, loop, check and test plan it prescribes. Those are the sentences builders copy.
3. Go down every entry of the guidance, listed below. For each, find the spec's sentences that bear on it and decide whether code built exactly as they say would meet the entry's words. An entry with sub-points is several entries.
4. Be strict about the text both ways. A spec sentence breaks an entry when the code it prescribes would not do what the entry's words require; for a default, when it prescribes a departure and gives no reason. Silence is no breach unless it leaves the builder no way to meet the entry. Where an entry is too vague to decide, say so and name the vague words.

The guidance, as an index generated from the files (the files are the authority):
{CHECKLIST}

## What you return

For each breach, one block:

```
### <short title>
- entry: <file>:<line> "<the exact words of the entry the prescribed code would fail>"
- kind: commitment | principle | contract | default
- spec: <spec file>:<line-range> "<the spec's words that prescribe it>"
- why: <two to five sentences: what a builder following the spec writes, and why that fails the entry's words>
- smallest change to the spec: <one or two sentences>
- severity: high | medium | low
- level: design | local
- confidence: high | medium
```

Then `## Vague`: one line per place where an entry's words were too vague to judge the spec, with the entry, the words and the spec's place.
{RULES}
