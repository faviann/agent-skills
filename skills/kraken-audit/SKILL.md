---
name: kraken-audit
description: "Fan-out audit of a whole Kraken tree, or of a slice's spec before approval, against COMMITMENTS, ENGINEERING, CONTRACTS and DEFAULTS. Writes a temporary report outside the repo listing only verified breaches, plus excused breaches and vague rules."
disable-model-invocation: true
---

# Kraken audit

Find which entries of Kraken's guidance the tree does not respect, verify each, and write Fav a temporary report outside the repo to act on. Nothing goes into the repo: no register, no file left behind.

Two modes:

- **Code** (default): the whole tree at its current commit.
- **Spec**: a slice's spec before Fav approves it, at a commit or in the working tree. Design breaches start in the spec: once the code matches the spec, no code review sees them.

## Why it is shaped this way

- **Two auditors on different models per share of the guidance.** One reviewer holding all the rules finds a third of the breaches; splitting the rules among owners finds the most. Two models miss different things.
- **Symptom lenses.** Entry-by-entry passes have missed Kraken's costliest design breaches, every time, because each line looked fine. Only questions about symptoms found them: the costliest check, logic that exists twice, code only daemon tests reach, claims of "checked elsewhere".
- **Two independent verifiers per candidate.** A fan-out raises about 7 false alarms per review. Only breaches both verifiers confirm reach Fav as breaches.
- **A second look at the contested.** A verifier asked again gives the other answer for one candidate in eight, and every candidate that three of four verdicts kept was a true breach. So a second pair judges the candidates the first pair split on, and one that both keep is open. In two runs it opened 8 of 20 true contested candidates and none of 16 not-true ones. It needs both verifiers: Sonnet's vote decides most cases, and Opus's took out the one false candidate Sonnet kept.
- **Exceptions first.** A principle's exception is Fav's decision naming the code and what ends it (`GUIDANCE.md`, who departs from what). An excused breach is listed as excused and never counted as open.
- **Scripts write the report.** The same verdicts must give the same report. `combine.py` places every candidate, `render.py` ranks and writes, `check.py` proves each candidate sits in one section.

## Inputs

- **The checkout**: the path given as an argument, else the working directory. It must hold `GUIDANCE.md` at its root. The audit only reads it.
- **Mode**: `spec` with a commit or the spec's files, else code.
- **`--coverage`** (code mode, optional): run the coverage lens. It costs an `npm ci` and a module-test run, about 5 minutes.
- **`--previous <report.md>`** (optional): the last audit's report, wherever Fav kept it outside the repo. Open breaches are then marked new or still open, and the ones gone are listed.
- **`--tests N`** (code mode, optional): how many auditors own the tests. A group of Sonnet auditors, `G5`, owns the tests in every code run: each takes one region of `test/` and the entries that speak of tests. Left out, `briefs.py` starts one for every 6,500 lines of test code. `--tests 0` turns the group off. Without the group the auditors open `test/` only where an entry sends them, and three audits raised none of the key's five breaches of those entries. Measured in one full run with N=6: 43 candidates had a tests auditor among their sources, 28 came out open, and a blind judge scored 27 of those true, 2 of the five among them. The open breaches judged true went from 44 to 68. It adds about 45 candidates to verify, so one or two verifier batches.
- **`--known <file>`** (code mode, optional): findings the lenses must not repeat, one per line with its place, taken from an earlier report. The lenses spend their findings on one cluster: with the keeper's cluster listed as known, four lens texts gave 18 other findings, 10 of them real breaches by a blind judge.
- **`--regions N`** (code mode, optional): each group's auditors take one of N regions of `src/` instead of all of it, so 8×N auditors start, in waves of five Opus. Measured once, on one group with N=3: more breaches found, each auditor done in 9 to 17 minutes, 1.8 times the tokens, and twice the candidates to verify. Off unless Fav asks.

## The run folder and the report

Make one run folder outside the repo: `<scratchpad>/kraken-audit-<short sha>-<YYYYMMDD-HHMM>/` when your session names a scratchpad directory, else the same under `$TMPDIR` (or `/tmp`). Everything this skill writes goes there: briefs, the agents' texts, the candidates, the report. You, the session running this skill, write every file. The agents you start return text and write nothing: a harness can refuse a subagent's write, and the report must not depend on it.

## Agents

Each agent gets the prompt `Read <brief file> and do what it says.` and nothing else. The brief tells it to read only the tree (plus the one input file named in it), write no file, load no skill and start no other agent. Start every agent with the `Agent` tool in the background, with the model `briefs.py` prints for it. As each finishes, append a line to `<run>/agents.tsv`: label, model, the tokens and duration its completion notice reports, and whether it finished. The report's cost line sums it.

| Step | Code mode | Spec mode | Models |
|---|---|---|---|
| Auditors | 4 groups × 2: `G1` commitments, `G2` principles, `G3` contracts, `G4` defaults. And N on Sonnet alone: `G5.t<n>-b`, the tests | 2: `S` all entries against the spec | `-a` opus, `-b` sonnet |
| Lenses | 2: `L`, the four symptoms on the code | 2: `SL`, the four symptoms on the code the spec forces | `-a` opus, `-b` sonnet |
| Merger | 1 | 1 | sonnet |
| Verifiers | 2 per batch of ≤30 candidates | same | `-a` opus, `-b` sonnet |
| Second look | 2 on the contested candidates | same | `-a` opus, `-b` sonnet |

A code run starts 10 + N + 1 + 2×batches + 2 agents. Measured once with N=6: 27 (10 on Opus, 17 on Sonnet), 58 minutes, 1.3M output tokens and 280M cache reads. Without the tests group and the second look it was 17 (8 on Opus, 9 on Sonnet), about 50 minutes, 0.85M output tokens and 170M cache reads, roughly $55 at list prices. A spec run starts 4 + 1 + 2×batches + 2, measured without the second look 7 (3 on Opus), about 20 minutes. The second look adds 6 to 9 minutes. At most five Opus agents run at once. Stop any agent still running after 30 minutes with `TaskStop`, and record it in the report as not finished.

When this skill runs headless (`claude -p`), set `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0`. Without it the harness kills background agents 10 minutes after the session's last turn, and the auditors run 20 to 28.

## Steps

1. **Prepare.** Resolve the checkout and its commit (`git -C <checkout> rev-parse --short HEAD`). Make the run folder. Write the operator's standing rules for this repo, verbatim as your session holds them, to `<run>/rules.md`; skip it when your session holds none. In spec mode at a commit, make a throwaway copy in the run folder (`git clone -q --no-hardlinks <checkout> <run>/tree && git -C <run>/tree checkout -q <commit>`) and use `<run>/tree` as the checkout from here on. Done when the run folder exists and you know the checkout and commit.
2. **Coverage lens** (code mode, only with `--coverage`). Run `scripts/coverage-lens.sh <checkout> <run>/coverage` in the background. Wait for it before step 3 so the lenses can read its output; if it fails, note why for the report and go on without it.
3. **Fan out.** Run `python3 <this skill>/scripts/briefs.py fanout <checkout> <run> --mode <mode> [--spec "<spec files>"] [--rules <run>/rules.md] [--coverage <run>/coverage/core-unreached.txt] [--regions N] [--tests N] [--known <file>]`. In spec mode, `--spec` names the files, for example "its core, `docs/rebuild/s1-spec.md`, and the unit files under `docs/rebuild/s1/`". Start one agent per printed line, all at once. As each returns, save its text verbatim to `<run>/audits/<label>.md`. A completion notice can cut a long text short: when a text ends mid-block or lacks its last section, copy the full text from the agent's output file instead. Done when every agent has returned or been stopped.
4. **Merge.** Run `briefs.py merge <checkout> <run>`: it splits the audits into labelled blocks in `<run>/blocks.md` and writes the merger's brief. Start the merger and save its table verbatim as `<run>/grouping.txt`. Then run `briefs.py assemble <checkout> <run>`: it builds `<run>/candidates.md` from the table and the audits' own text, keeps any block the table left out as its own candidate, and prints the counts. If it reports unknown labels, send the merger its error once with `SendMessage`.
5. **Verify.** Run `briefs.py verify <checkout> <run> --mode <mode> [--rules <run>/rules.md]`. Start every printed verifier at once. Save each text as `<run>/verdicts/<label>.tsv`.
6. **Combine.** Run `combine.py <run>`. It puts each candidate in one section by its two verdicts (the rules are in its header) and writes `<run>/combined.json`. It exits 1 and names the file when a verdict file holds no verdict or names a candidate that does not exist: save that text again from the agent's output file and rerun. Done when it prints the counts and exits 0.
7. **Look again at the contested.** Run `briefs.py verify <checkout> <run> --mode <mode> [--rules <run>/rules.md] --second-look`. It prints two more verifiers, `W1-a` and `W1-b`, over the candidates that one verifier kept and the other rejected, or says there is none. Start them, save each text as `<run>/verdicts/<label>.tsv`, and run `combine.py <run>` again. Done when it prints how many the second look opened and exits 0.
8. **Write the report.** Write to `<run>/notes.md`, one per line, what no saved file shows: a lens or check that failed, a text you had to recover, a choice you made where this skill left one. Then run `render.py <run> --checkout <checkout> --mode <mode> [--previous <report.md>]` and `check.py <run>`. To change the report, change `notes.md` or a saved text and render again. Done when `check.py` exits 0. Give Fav the report's path and its five summary lines.

## The report

`render.py` writes `<run>/report.md`, in this order:

- **Five summary lines**: the counts, the three breaches to start with, the design concerns the verifiers did not confirm, what was not checked, the cost.
- **Open breaches**: both verifiers kept them, or both verifiers of the second look did, and then the item says so and gives the first rejection. Breaches of binding entries first (commitments, principles, contracts), then design-level defaults, then other defaults, most severe first. Each gives the entry and its words, the place, the verifiers' evidence, the verdict and what the spec says. Where one verifier narrowed a candidate, the breach is the narrower reading, and the wider one follows it, marked as one verifier's. A default that its auditors placed in eight files or more is a tree-wide pattern: one line, with its count.
- **Design concerns the verifiers did not confirm**: every candidate a lens raised that was contested or dropped, whole: its symptom, the entry, the place, the shape it blames, and both verifiers' reasons. Then the design problems the lenses could tie to no entry. None counts as a breach. A breach of design shows here first, while the guidance still lacks the words for it.
- **Contested**, **Excused**, **Vague rules**, **Coverage by test tier**, **What this audit could not check**, **Dropped**.

In spec mode the place is the spec's `file:line`, and each open breach adds the smallest change to the spec.

With `--previous`, read "gone" as "look again", not as "fixed". Two audits of one unchanged tree differ: about one open breach in five was new and one in six gone between saved runs, and a rerun of the verifiers alone moved one candidate in five to another section.

The report is temporary: it lives in the run folder and goes with it. Fav acts on it; nothing tracks it in the repo.
