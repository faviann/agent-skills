#!/usr/bin/env python3
"""Put every candidate of one audit run into exactly one section, from its two verifiers' verdicts.

usage: combine.py <run-dir>
Reads <run-dir>/candidates.md and <run-dir>/verdicts/V<n>-<a|b>.tsv, and the second look's W<n>-<a|b>.tsv when
they are there. Writes <run-dir>/combined.json and prints the counts. Exits 1 when a verdict file holds no verdict,
or names a candidate that does not exist, or a second look names a candidate that was not contested.

The sections, by the two verdicts of a candidate:
  open       both `confirmed` or `narrowed`
  excused    either `excused`, and the other not `rejected`
  contested  one `confirmed` or `narrowed`, the other `rejected`
  dropped    both `rejected`, or one `excused` and the other `rejected` (neither verifier leaves it open)
  unverified a verdict is missing or unreadable: the report lists it under what the audit could not check
The second look: a second pair of verifiers judges the contested candidates alone. A contested candidate that
both of them keep is open: `verdicts` then holds the second pair's and `first` the first pair's. Any other answer
leaves it contested, with the second pair's verdicts in `second`. Why: a verifier asked again gives the other answer
for about one candidate in eight, and every candidate that three of four verdicts kept was a true breach.
A contested or dropped candidate that a lens raised (a source label `L-*` or `SL-*`) goes to the section
`design` instead: the report shows it in full under "Design concerns the verifiers did not confirm".
"""
import glob
import html
import json
import os
import re
import sys

OK = {"confirmed", "narrowed"}
VERDICTS = OK | {"excused", "rejected"}
BINDING = ("COMMITMENTS.md", "ENGINEERING.md", "CONTRACTS.md")
SEVERITY = {"high": 0, "medium": 1, "low": 2}
LABEL = r"\b(?:G\d+|S|SL|L)(?:\.[A-Za-z0-9]+)?-[ab](?:#\d+)?"


def fields(text):
    """`- name: value` lines of a block, each with the lines that continue it."""
    out, name = {}, None
    for line in text.splitlines():
        m = re.match(r"^- ([a-z][a-z ]*?):\s?(.*)$", line)
        if m:
            name = m.group(1)
            out[name] = (out[name] + "\n" if name in out else "") + m.group(2)
        elif name and line.strip() and not line.startswith(("From ", "#")):
            out[name] += "\n" + line.rstrip()
        elif not line.strip():
            name = None
    return {k: v.strip() for k, v in out.items()}


def candidates(path):
    text = open(path, encoding="utf-8").read()
    out = []
    parts = re.split(r"^(?=#{2,3} )", text, flags=re.M)
    for part in parts:
        head = re.match(r"^### (C\d+): (.*)\n", part)
        if not head:
            continue
        body = part[head.end():]
        top = fields(re.split(r"^From \S+:\s*$", body, flags=re.M)[0])
        blocks = [{"label": lab, "fields": fields(txt)}
                  for lab, txt in re.findall(r"^From (\S+):\s*\n(.*?)(?=^From \S+:\s*$|\Z)", body, flags=re.M | re.S)]
        if not blocks:  # a merger-written candidate: its fields sit on the candidate itself
            blocks = [{"label": "merged", "fields": top}]
        sources = re.findall(LABEL, top.get("source", ""))
        words = re.findall(r"high|medium|low", top.get("severity", "").lower())
        out.append({
            "id": head.group(1), "title": head.group(2).strip(), "sources": sources,
            "severity": min(words, key=SEVERITY.get) if words else "low",
            "lens": any(s.startswith(("L-", "SL-")) for s in sources),
            "design": any("design" in b["fields"].get("level", "").lower() for b in blocks),
            "blocks": blocks,
        })
    return out


def verdicts(run):
    """({candidate: {side: verdict}} of the first look, the same of the second look, problems)."""
    looks, problems = {"V": {}, "W": {}}, []
    files = sorted(glob.glob(os.path.join(run, "verdicts", "*.tsv")))
    if not files:
        sys.exit(f"no verdict files in {run}/verdicts")
    for f in files:
        m = re.match(r"([VW])\d+-([ab])\.tsv$", os.path.basename(f))
        if not m:
            problems.append(f"{os.path.basename(f)}: not named V<n>-<a|b>.tsv, or W<n>-<a|b>.tsv for the second look")
            continue
        out, side = looks[m.group(1)], m.group(2)
        n = 0
        for line in open(f, encoding="utf-8"):
            line = line.rstrip("\n")
            cells = line.split("\t") if "\t" in line else [c for c in line.strip().strip("|").split("|")]
            cells = [html.unescape(c).strip().strip("`*").strip() for c in cells]
            if not re.fullmatch(r"C\d+", cells[0] if cells else ""):
                continue
            word = re.match(r"[a-z]+", cells[1].lower()) if len(cells) > 1 else None
            verdict = word.group(0) if word and word.group(0) in VERDICTS else "unreadable"
            cells += [""] * (5 - len(cells))
            out.setdefault(cells[0], {})[side] = {
                "verdict": verdict, "entry": cells[2], "place": cells[3], "reason": " ".join(cells[4:]).strip()}
            n += 1
        if n == 0:
            problems.append(f"{os.path.basename(f)}: no verdict line (id<TAB>verdict<TAB>entry<TAB>place<TAB>reason)")
    return looks["V"], looks["W"], problems


def section(a, b):
    pair = {a, b}
    if not pair <= VERDICTS:
        return "unverified"
    if pair <= OK:
        return "open"
    if "excused" in pair:
        return "dropped" if "rejected" in pair else "excused"
    return "dropped" if pair == {"rejected"} else "contested"


def binding(entry):
    return any(f in entry for f in BINDING)


def kind(c):
    """binding when each verifier that keeps the breach ties it to a binding file; a split says so in `flags`."""
    kept = [v["entry"] for v in c["verdicts"].values() if v["verdict"] in OK | {"excused"}]
    if not kept:
        kept = [b["fields"].get("entry", "") for b in c["blocks"]]
    votes = [binding(e) for e in kept if e]
    if votes and all(votes):
        return "binding"
    if any(votes):
        c["flags"].append("the readings differ on whether the entry binds")
        return "binding"
    return "default"


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    run = os.path.abspath(sys.argv[1])
    cands = candidates(os.path.join(run, "candidates.md"))
    if not cands:
        sys.exit(f"no candidate headings (### C01: ...) in {run}/candidates.md")
    ids = [c["id"] for c in cands]
    if len(set(ids)) != len(ids):
        sys.exit(f"candidate ids repeat in candidates.md: {sorted(i for i in set(ids) if ids.count(i) > 1)}")
    judged, again, problems = verdicts(run)
    problems += [f"verdict for {i}, which is no candidate" for i in sorted((set(judged) | set(again)) - set(ids))]
    missing = {"verdict": "missing", "entry": "", "place": "", "reason": ""}
    for c in cands:
        v = judged.get(c["id"], {})
        c["verdicts"] = {"a": v.get("a", missing), "b": v.get("b", missing)}
        a, b = c["verdicts"]["a"]["verdict"], c["verdicts"]["b"]["verdict"]
        c["flags"] = []
        c["section"] = section(a, b)
        c["split"] = c["section"] == "contested"
        if c["id"] in again and not c["split"]:
            problems.append(f"second-look verdict for {c['id']}, which the first two verifiers did not contest")
        elif c["id"] in again:
            w = again[c["id"]]
            second = {"a": w.get("a", missing), "b": w.get("b", missing)}
            if section(second["a"]["verdict"], second["b"]["verdict"]) == "open":
                no = next(s for s in "ab" if c["verdicts"][s]["verdict"] == "rejected")
                c["first"], c["verdicts"], c["section"] = c["verdicts"], second, "open"
                c["first_no"] = no
                a, b = second["a"]["verdict"], second["b"]["verdict"]
            else:
                c["second"] = second
        if c["lens"] and c["section"] in ("contested", "dropped"):
            c["was"], c["section"] = c["section"], "design"
        reasons = " ".join(x["reason"] for x in c["verdicts"].values())
        c["vague"] = c["split"] or bool(re.search(r"\bvague\b", reasons, re.I))
        c["kind"] = kind(c)
        if a == b == "narrowed":
            c["flags"].append("both verifiers narrowed it: read both readings")
    json.dump({"run": run, "candidates": cands, "problems": problems},
              open(os.path.join(run, "combined.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    count = {}
    for c in cands:
        count[c["section"]] = count.get(c["section"], 0) + 1
    order = ["open", "design", "contested", "excused", "dropped", "unverified"]
    looked = sum(1 for c in cands if "first" in c or "second" in c)
    print(f"{len(cands)} candidates: " + ", ".join(f"{count.get(s, 0)} {s}" for s in order)
          + (f"; second look at {looked}, {sum(1 for c in cands if 'first' in c)} of them now open" if again else ""))
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
