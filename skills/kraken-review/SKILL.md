---
name: kraken-review
description: "Review a Kraken change or PR against Kraken's guidance (COMMITMENTS, ENGINEERING, CONTRACTS, DEFAULTS), entry by entry, with a fresh reviewer and one verifier. For a Kraken PR, branch, staged change or unit's work before merge."
disable-model-invocation: true
---

# Kraken review

A review of one change against Kraken's guidance. The guidance is the measure, not the code around the change and not the spec: reviewers that hold a change to its surroundings catch only what stands out, and miss every breach the tree already repeats or the spec prescribes.

What this review returns is a **ledger** (every entry that bears on the change, meets or breaks, with the place), the findings most serious first, and an **uncapped list** of every other breach, each quoting the words of the entry it breaks. On a blind benchmark that form found almost twice the breaches of a plain "findings, most serious first" review at the same precision.

It reviews new code only. Breaches in code the change leaves alone belong to the guidance audit (`kraken-audit`).

## Inputs

- **The checkout**: the path given as an argument, else the working directory. It must hold `GUIDANCE.md` and the four entry files at its root.
- **The change**: a PR branch, a commit range, or staged work. `scripts/change.py <checkout> [--base <ref>]` names it as the git command that shows it: `--base` when Fav or the PR names what the change merges into, else staged work, else the branch against the remote's default branch, else its unpushed commits. No branch name is built in.
- **The spec**: the core `docs/rebuild/s1-spec.md` plus the unit file(s) under `docs/rebuild/s1/` the change implements. Find the unit from the branch name, the PR body or the commit messages.

## Steps

Keep the working files (rules, brief, the reviewer's text, the verdicts) in your scratchpad or `$TMPDIR`, outside the repo.

1. Resolve the three inputs. Run `python3 <this skill>/scripts/change.py <checkout> [--base <ref>]` and keep its sentence. When it exits 2 it could not tell the change: pass `--base` with what Fav named, and when nobody can be asked, review the last commit (`--base HEAD~1`) and say so in your first line. Done when you can name the checkout path, the git command that shows the change, and the spec files.
2. Write the operator's standing rules for this repo, verbatim as your session holds them, to a file. Skip this when your session holds none.
3. Build the brief:
   ```
   python3 <this skill>/scripts/brief.py <checkout> --change "<the sentence from change.py>" --spec "<spec files>" [--rules <rules file>]
   ```
   The script reads the guidance files at run time and embeds one checklist line per entry with the checkout's line numbers, so the checklist cannot drift from the files. It exits with the reason when a guidance file's shape changed and the checklist would lose entries: fix that first. Keep its output whole.
4. Start one reviewer with the `Agent` tool: model `opus`, the brief as its whole prompt, in the background. A fresh reviewer matters: the session that built the change measures it against what it meant to write. If the `Agent` tool is unavailable, do the review yourself from the brief and say so.
5. When it returns, save its text and check its form: three parts, the ledger with a `file:line` per line, each listed breach quoting an entry's words. If a part is missing, send it back once through `SendMessage` asking for that part only.
6. Verify. One verifier judges each listed breach against the entry's words and the code, as the audit's verifiers do:
   ```
   python3 <this skill>/scripts/verify.py tag <review.md> <tagged.md>
   python3 <this skill>/scripts/verify.py brief <checkout> <tagged.md> --change "<the same sentence>" [--rules <rules file>] > <verifier-brief.md>
   ```
   Start one agent, model `sonnet`, with the prompt `Read <verifier-brief.md> and do what it says.` Save its text as `<verdicts.tsv>`, then run `verify.py apply <tagged.md> <verdicts.tsv> > <verified.md>`. It takes the rejected and excused claims out of the reviewer's text and lists them, with the verifier's reasons, under "Verification". When `apply` exits 2, a claim has no verdict: send the verifier that message once. When `tag` exits 2, or the verifier fails twice, hand Fav the reviewer's text as it is and say it is unverified.
7. Hand Fav the verified text unchanged, preceded by two lines of your own: how many breaches the verifier kept, and the most serious finding. Write it to a file in the repo only if Fav asks.

## Cost

Two Opus agents (this session and the reviewer) and one Sonnet verifier: about 15 minutes. The reviewer takes 7 to 10 minutes, 55k output tokens and 3 to 5M cache reads on a unit-sized change; the verifier 2 to 9 minutes and 120k to 160k tokens.
