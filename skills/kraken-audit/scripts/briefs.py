#!/usr/bin/env python3
"""Write the briefs of one audit run into <run-dir>/briefs/ and print who to start with which model.

usage:
  briefs.py fanout <checkout> <run-dir> --mode code|spec [--spec "<spec files>"] [--rules FILE] [--coverage FILE]
                                                        [--regions N]   # code mode: N regions of src/ per group
                                                        [--known FILE]  # code mode: findings the lenses must not repeat
                                                        [--tests N]     # code mode: N Sonnet auditors that own test/;
                                                                        # unset, one per 6,500 lines of it; 0, none
  briefs.py merge  <checkout> <run-dir>                 # after the auditors' texts are saved in <run-dir>/audits/
  briefs.py assemble <checkout> <run-dir>               # after the merger's table is saved as <run-dir>/grouping.txt
  briefs.py verify <checkout> <run-dir> --mode code|spec [--rules FILE] [--batch 30]
                                                        # after the merger's text is saved as <run-dir>/candidates.md
  briefs.py verify <checkout> <run-dir> --mode code|spec [--rules FILE] --second-look
                                                        # after combine.py: the contested candidates, labels W<n>
Each printed line is: <label> <model> <brief file>. Start one agent per line with the prompt
"Read <brief file> and do what it says." Every brief is self-contained.
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "references")
MODELS = {"a": "opus", "b": "sonnet"}
GROUPS = {
    "G1": ("commitments", "the commitments in `COMMITMENTS.md`, with their terms (the authorization policy, the threat model, the supported environments, the owner's configuration)"),
    "G2": ("engineering", "the engineering principles in `ENGINEERING.md`, each with every one of its points"),
    "G3": ("contracts", "the architectural contracts in `CONTRACTS.md`: Kraken's own, the Effect profile's E1 to E4, its Boundaries and its Import restrictions"),
    "G4": ("defaults", "the defaults in `DEFAULTS.md`, the Effect defaults included"),
}


def tpl(name):
    return open(os.path.join(REF, name), encoding="utf-8").read()


def checklist(checkout, *groups):
    got = subprocess.run([sys.executable, os.path.join(HERE, "checklist.py"), checkout, *groups],
                         capture_output=True, text=True)
    if got.returncode:
        sys.exit(got.stderr.strip() or f"checklist.py failed with status {got.returncode}")
    return got.stdout.rstrip()


def rules_text(path):
    if not path:
        return ""
    return ("\n## Standing rules for every agent on this repo (Fav's, verbatim)\n\nWhere they speak of pushing, a PR "
            "or tests, this task pushes nothing, opens nothing and runs nothing.\n\n"
            + open(path, encoding="utf-8").read().strip() + "\n")


def known_text(path):
    """The lens brief's part on what an earlier audit reported: FILE holds one finding per line, with its place."""
    if not path:
        return ""
    listed = open(path, encoding="utf-8").read().strip()
    if not listed:
        sys.exit(f"{path} is empty: leave --known out, or list one finding per line")
    return ("\n### Already reported\n\nAn earlier audit of this tree reported the findings below, and Fav has them. Write no "
            "block for any of them, and leave them out of Untied. Spend your findings on the rest of the tree. A symptom "
            "whose first answer is on this list has a next answer: the next costliest check, the next copy, the next "
            "choice made in effect code, the next claim of \"checked elsewhere\". Follow each symptom to that one.\n\n"
            + listed + "\n")


def where(checkout, extra=""):
    return (f"The tree is `{checkout}`. Read only inside it{extra}. Your shell may not start there: begin every shell "
            f"command with `cd {checkout} &&`, and give every search tool that folder as its path.")


READ_ALL = ("2. Read the code in full: every file under `src/`. Read `tools/` and `test/` wherever an entry of your group "
            "reaches them (tests and checks are code too, held to the same entries).")


TEST_REGION = 6500  # lines of test code one auditor takes: six regions of 4,400 to 6,800 lines were measured


def line_counts(checkout, root):
    """{file: lines} for the files under root: the tracked ones, or every file when the tree is no git checkout.
    Under "test" only code files count: fixtures and other data are left out."""
    got = subprocess.run(["git", "-C", checkout, "ls-files", root], capture_output=True, text=True)
    files = got.stdout.split() if got.returncode == 0 and got.stdout.strip() else [
        os.path.relpath(os.path.join(d, f), checkout) for d, _, fs in os.walk(os.path.join(checkout, root)) for f in fs]
    if root == "test":
        files = [f for f in files if f.endswith((".ts", ".tsx", ".js", ".mjs"))]
    counts = {}
    for f in sorted(files):
        try:
            counts[f] = sum(1 for _ in open(os.path.join(checkout, f), encoding="utf-8", errors="replace"))
        except OSError:  # tracked and gone from the working tree
            pass
    return counts


def regions(checkout, n, root="src"):
    """Split src/ into n runs of neighbouring folders with about the same number of lines: [[folder, ...], ...].
    With root "test", the units are the code files themselves."""
    size = {}
    for f, lines in line_counts(checkout, root).items():
        parts = f.split("/")
        unit = f if root == "test" else "/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:-1])
        size[unit] = size.get(unit, 0) + lines
    units = sorted(size)
    if len(units) < n:
        sys.exit(f"{root}/ holds {len(units)} {'files' if root == 'test' else 'folders'}, fewer than {n} regions")
    # contiguous split that keeps the largest region smallest
    best = {(0, 0): (0, [])}
    for k in range(1, n + 1):
        for j in range(k, len(units) + 1):
            for i in range(k - 1, j):
                if (i, k - 1) in best:
                    cost = max(best[(i, k - 1)][0], sum(size[u] for u in units[i:j]))
                    if (j, k) not in best or cost < best[(j, k)][0]:
                        best[(j, k)] = (cost, best[(i, k - 1)][1] + [units[i:j]])
    return [(chunk, sum(size[u] for u in chunk)) for chunk in best[(len(units), n)][1]]


def read_region(folders, every):
    listed = ", ".join(f"`{f}/`" + (" (the files directly in it)" if any(o.startswith(f + "/") for o in every) else "")
                       for f in folders)
    return (f"2. Read your region of the code in full: {listed}. Other auditors hold the rest of `src/`: open a file "
            "outside your region only to follow a call, a type or a table that a file of your region uses. Read `tools/` "
            "and `test/` wherever an entry of your group reaches them for your region (tests and checks are code too, "
            "held to the same entries). Report breaches in your region only.")


TESTS = ("the entries that speak of tests and checks, wherever they sit in `ENGINEERING.md` and `DEFAULTS.md`. You own "
         "the tests: the other auditors read `test/` only where one of their entries sends them")


def tests_checklist(checkout):
    """The entries of the engineering and defaults indexes whose words speak of a test or a check, with their points."""
    out, keep, parent = [], False, None
    speaks = lambda line: bool(re.search(r"\btests?\b|\ba check\b|TestClock|vitest|\bfakes?\b", line, re.I))
    for line in checklist(checkout, "engineering", "defaults").splitlines():
        if re.match(r"^  \S", line):  # an entry, or a heading inside the file
            keep, parent = speaks(line), line
        elif not keep and speaks(line) and parent:  # a point that speaks of tests under an entry that does not
            out.append(parent)
            parent = None
            out.append(line)
            continue
        if keep or re.match(r"^\S", line):
            out.append(line)
    if not any(l.startswith("  ") for l in out):
        sys.exit("no entry of ENGINEERING.md or DEFAULTS.md speaks of tests: --tests has nothing to hold the tests to")
    return "\n".join(out)


def read_tests(files):
    listed = ", ".join(f"`{f}`" for f in files)
    return (f"2. Read your region of the tests in full: {listed}. For each test file, read the code under `src/` or "
            "`tools/` that it is there for, and the helpers under `test/` that it uses. Other auditors hold the rest of "
            "`test/`. Report breaches in your region only: in the tests themselves, and in what they leave unchecked of "
            "the code they are there for (a branch of a consequential decision that no test runs, a promise checked on "
            "one side only).")


def fill(t, **kv):
    for k, v in kv.items():
        t = t.replace("{" + k + "}", v)
    left = re.findall(r"\{[A-Z]+\}", t)
    assert not left, left
    return t


def audit_blocks(run):
    """Split each saved audit text into its blocks (### headings) and its Vague / Untied lines."""
    d = os.path.join(run, "audits")
    files = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    if not files:
        sys.exit(f"no audit texts in {d}")
    blocks, vague = [], []
    for f in files:
        src = f[:-3]
        n, cur, section = 0, None, None
        for line in open(os.path.join(d, f), encoding="utf-8").read().splitlines():
            h3 = re.match(r"^###\s+(.*)", line)
            h2 = re.match(r"^##\s+(.*)", line)
            if h3 and section is None:
                n += 1
                cur = [f"{src}#{n}", h3.group(1).strip(), ""]
                blocks.append(cur)
            elif h2:
                cur = None
                section = h2.group(1).strip() if re.match(r"(Vague|Untied)", h2.group(1).strip()) else None
            elif section and line.strip():
                vague.append(f"{line.rstrip()} ({src})")
            elif cur is not None:
                cur[2] += line + "\n"
    return [tuple(b) for b in blocks], vague


def write(run, label, text, model):
    d = os.path.join(run, "briefs")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, label + ".md")
    open(p, "w", encoding="utf-8").write(text)
    print(f"{label}\t{model}\t{p}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["fanout", "merge", "assemble", "verify"])
    ap.add_argument("checkout")
    ap.add_argument("run")
    ap.add_argument("--mode", choices=["code", "spec"], default="code")
    ap.add_argument("--spec", default="")
    ap.add_argument("--rules")
    ap.add_argument("--coverage")
    ap.add_argument("--batch", type=int, default=30)
    ap.add_argument("--regions", type=int, default=1)
    ap.add_argument("--known")
    ap.add_argument("--tests", type=int, default=None)
    ap.add_argument("--second-look", action="store_true")
    a = ap.parse_args()
    co, run = os.path.abspath(a.checkout), os.path.abspath(a.run)
    if not os.path.exists(os.path.join(co, "GUIDANCE.md")):
        sys.exit(f"{co} holds no GUIDANCE.md: not a Kraken checkout")
    rules = rules_text(a.rules)

    if a.step == "fanout":
        checklist(co)  # every guidance file must index before any brief is written
        if a.known and a.mode != "code":
            sys.exit("--known is for code mode: the spec lens has no part for it")
        known = known_text(a.known)
        if a.mode == "code":
            shards = regions(co, a.regions) if a.regions > 1 else [None]
            for g, (group, desc) in GROUPS.items():
                for n, shard in enumerate(shards, 1):
                    for side, model in MODELS.items():
                        text = fill(tpl("auditor.md"), GROUP=desc, WHERE=where(co), CHECKLIST=checklist(co, group), RULES=rules)
                        label = f"{g}-{side}"
                        if shard:
                            assert READ_ALL in text, "auditor.md no longer holds the sentence that --regions replaces"
                            every = [f for folders, _ in shards for f in folders]
                            text, label = text.replace(READ_ALL, read_region(shard[0], every)), f"{g}.r{n}-{side}"
                        write(run, label, text, model)
            if shards[0]:
                for n, (folders, lines) in enumerate(shards, 1):
                    print(f"# region r{n}: {lines} lines: {' '.join(folders)}")
            if a.tests is None:  # the tests group is on unless --tests 0 turns it off
                a.tests = -(-sum(line_counts(co, "test").values()) // TEST_REGION)
            if a.tests:
                text = fill(tpl("auditor.md"), GROUP=TESTS, WHERE=where(co), CHECKLIST=tests_checklist(co), RULES=rules)
                assert READ_ALL in text, "auditor.md no longer holds the sentence that --tests replaces"
                parts = regions(co, a.tests, "test")
                for n, (files, lines) in enumerate(parts, 1):  # on Sonnet alone: the one way it was measured
                    write(run, f"G5.t{n}-b", text.replace(READ_ALL, read_tests(files)), MODELS["b"])
                for n, (files, lines) in enumerate(parts, 1):
                    print(f"# tests t{n}: {lines} lines: {' '.join(files)}")
            cov = ""
            if a.coverage:
                cov = (f"\nA coverage run of the module tests (no daemon, kill-sweep or real-agent test) left these lines of "
                       f"`src/core` unreached; read the file `{os.path.abspath(a.coverage)}` for symptom 3. Unreached lines "
                       f"are reached only by the expensive tests, or by none.\n")
            for side, model in MODELS.items():
                write(run, f"L-{side}", fill(tpl("lens.md"), WHERE=where(co, " (and the coverage file named below)" if cov else ""),
                                             COVERAGE=cov, KNOWN=known, RULES=rules), model)
        else:
            if not a.spec:
                sys.exit("--spec is required in spec mode")
            for side, model in MODELS.items():
                write(run, f"S-{side}", fill(tpl("spec-auditor.md"), WHERE=where(co), SPEC=a.spec,
                                             CHECKLIST=checklist(co), RULES=rules), model)
                write(run, f"SL-{side}", fill(tpl("spec-lens.md"), WHERE=where(co), SPEC=a.spec, RULES=rules), model)

    elif a.step == "merge":
        blocks, _ = audit_blocks(run)
        out = os.path.join(run, "blocks.md")
        with open(out, "w", encoding="utf-8") as f:
            for label, title, body in blocks:
                f.write(f"## {label}: {title}\n{body.strip()}\n\n")
        write(run, "merge", fill(tpl("merger.md"), BLOCKS=out, N=str(len(blocks)), CHECKOUT=co), "sonnet")

    elif a.step == "assemble":
        blocks, vague = audit_blocks(run)
        by = {label: (title, body) for label, title, body in blocks}
        rows = []
        for line in open(os.path.join(run, "grouping.txt"), encoding="utf-8"):
            m = re.match(r"^\s*\|?\s*(C\d+)\s*\|\s*(\w+)\s*\|\s*([^|]+)\|\s*(.*?)\s*\|?\s*$", line)
            if m:
                rows.append((m.group(1), m.group(2), [x.strip() for x in m.group(3).split(",") if x.strip()], m.group(4)))
        used = [x for r in rows for x in r[2]]
        unknown = [x for x in used if x not in by]
        missing = [x for x in by if x not in used]
        order = {"high": 0, "medium": 1, "low": 2}
        for x in missing:  # nothing is dropped: an unassigned block becomes its own candidate
            sev = re.search(r"severity:\s*(high|medium|low)", by[x][1])
            rows.append(("C", sev.group(1) if sev else "low", [x], by[x][0]))
        rows.sort(key=lambda r: order.get(r[1].lower(), 3))
        with open(os.path.join(run, "candidates.md"), "w", encoding="utf-8") as f:
            for n, (_, sev, members, title) in enumerate(rows, 1):
                members = [x for x in members if x in by]
                f.write(f"### C{n:02d}: {title}\n- severity: {sev}\n- source: {', '.join(members)}"
                        f"{' (single-source)' if len(members) == 1 else ''}\n\n")
                for x in members:
                    f.write(f"From {x}:\n{by[x][1].strip()}\n\n")
            f.write("## Vague\n\n" + "\n".join(vague) + "\n")
        print(f"# {len(rows)} candidates from {len(by)} blocks; unassigned blocks kept alone: {len(missing)}; "
              f"unknown labels in the table: {', '.join(unknown) or 'none'}")

    else:
        cand = os.path.join(run, "candidates.md")
        ids = sorted(set(re.findall(r"^#+\s*(C\d+)\b", open(cand, encoding="utf-8").read(), re.M)), key=lambda i: int(i[1:]))
        if not ids:
            sys.exit(f"no candidate headings (### C01 ...) in {cand}")
        letter = "V"
        if a.second_look:
            combined = os.path.join(run, "combined.json")
            if not os.path.exists(combined):
                sys.exit(f"no {combined}: run combine.py before the second look")
            split = {c["id"] for c in json.load(open(combined, encoding="utf-8"))["candidates"] if c["split"]}
            ids, letter = [i for i in ids if i in split], "W"
            if not ids:
                print("# no contested candidate: there is nothing to look at again")
                return
        target, subject = ("the code", "code") if a.mode == "code" else ("the spec's text", "spec")
        batches = [ids[i:i + a.batch] for i in range(0, len(ids), a.batch)]
        for n, b in enumerate(batches, 1):
            for side, model in MODELS.items():
                write(run, f"{letter}{n}-{side}", fill(tpl("verifier.md"), WHERE=where(co, " and the candidates file"), CAND=cand,
                                                IDS=", ".join(b), TARGET=target, SUBJECT=subject, RULES=rules), model)
        print(f"# {len(ids)} candidates in {len(batches)} batch(es)")


if __name__ == "__main__":
    main()
