You are reviewing a change to Kraken, a codebase being rebuilt on Effect 4, for its owner, Fav, before he merges it.

The checkout is `{CHECKOUT}`. Work only in that folder: open, list and search nothing outside it, load no skill, and start no other agent: do the work yourself. Your shell may not start there, so begin every shell command with `cd {CHECKOUT} &&`, and give every search tool that folder as its path. The change: {CHANGE} This is a read-only review. Change nothing, commit nothing, write no file anywhere, and run only commands that read: no git command that writes, no npm, no tests, no build.

Hold the change to the guidance at the repo's root, which you read in full first: `GUIDANCE.md`, `COMMITMENTS.md`, `ENGINEERING.md`, `CONTRACTS.md`, `DEFAULTS.md`, `GLOSSARY.md` and `docs/decision-log.md`. The guidance is the measure. A breach that the tree already repeats elsewhere, or that the specification asks for, is still a breach: report it, and say that the spec asks for it. An exception in force in `docs/decision-log.md` that names the code excuses it; nothing else does. Then read the specification for context: {SPEC}

Review the code the change adds or alters, and what that code now relies on. Breaches that sit wholly in code the change leaves alone are out of scope here.

What I want back, in three parts. The first two together take at most 1,500 words. First, a ledger: for each binding entry of the guidance (each commitment and its terms, each engineering principle and each of its points, each contract) and each default that bears on what you review, one line with the entry and its `file:line`, then "meets" or "breaks", with the place in the code as `file:line`. Close the ledger with one line naming the entries that bear on nothing here. Then your findings, most serious first. For each, its place as `file:line`, why it matters to me, and the smallest fix. Last, with no word limit, a list of every other breach of an entry that you saw, however small, one line each: the place as `file:line`, the entry it breaks, and the words of that entry the code fails, quoted. Leave out anything you cannot tie to such words: an entry whose words do not plainly reach that code is no breach of it.

Beside the full files, here is the guidance as a checklist, one line per entry, generated from the files just now. It replaces nothing in the files, and where a line and its file differ, the file is right. Go down it for what you review, and do not stop at the first entries.
{CHECKLIST}
{RULES}
