Group the findings of several audits of Kraken into candidate breaches. You judge nothing: two verifiers judge each candidate after you. Your job is that each distinct breach becomes exactly one candidate.

## Where you work

- Read `{BLOCKS}` in full. It holds all {N} blocks the audits returned, each under a heading `## <label>: <title>`, where the label names the audit and the block (for example `G2-a#3`).
- You may read the tree at `{CHECKOUT}` to tell whether two blocks name the same code. Read-only there.
- Write no file anywhere, load no skill and start no other agent. Your answer is the text you return.

## What to do

- Blocks are one candidate when they name the same code (overlapping places, or the same function) and the same defect, even when they cite different entries.
- Every other block is a candidate on its own. Every label goes into exactly one candidate: drop nothing, judge nothing, add nothing.
- Give each candidate the highest severity its blocks give, and a short title of your own.

## What you return

Only a table, one line per candidate, ordered high severity first, then medium, then low:

```
| C01 | high | G2-a#3, G2-b#5, L-a#1 | <short title> |
| C02 | medium | G4-b#7 | <short title> |
```

Then one line: `blocks: <n> grouped into <m> candidates`. A script builds the candidates file from your table and the audits' own text, so return nothing else.
