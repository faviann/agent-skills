#!/usr/bin/env python3
"""Check a rendered report against its run folder: every candidate sits in exactly one section.

usage: check.py <run-dir> [report.md]
Each item of the report opens with its candidate's id in square brackets (`### 3. Title [C07]`, `- [C10] ...`).
Fails when a candidate of candidates.md has no item, has two, or when the report names an id that is no candidate;
when an open breach does not quote its entry's words; or when the summary is longer than five lines.
"""
import os
import re
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    run = os.path.abspath(sys.argv[1])
    report = sys.argv[2] if len(sys.argv) > 2 else os.path.join(run, "report.md")
    ids = re.findall(r"^### (C\d+):", open(os.path.join(run, "candidates.md"), encoding="utf-8").read(), re.M)
    text = open(report, encoding="utf-8").read()
    where, section = {}, "summary"
    for line in text.splitlines():
        h2 = re.match(r"^## (.*)", line)
        if h2:
            section = h2.group(1).strip()
        item = re.match(r"^(?:#{3,4} .*|- )\[(C\d+)\]", line) or re.match(r"^#{3,4} .*\[(C\d+)\]", line)
        if item:
            where.setdefault(item.group(1), []).append(section)
    bad = []
    for i in ids:
        if i not in where:
            bad.append(f"{i} is in no section")
        elif len(where[i]) > 1:
            bad.append(f"{i} is in {len(where[i])} places: {', '.join(where[i])}")
    bad += [f"{i} is in the report and is no candidate" for i in where if i not in ids]
    open_part = re.search(r"^## Open breaches\n(.*?)(?=^## )", text, re.S | re.M)
    for block in re.split(r"^(?=### \d+\. )", open_part.group(1) if open_part else "", flags=re.M):
        head = re.match(r"### \d+\. .*\[(C\d+)\]", block)
        entry = re.search(r"^- entry: (.*)$", block, re.M)
        if head and not (entry and re.search(r'"[^"]{8,}"', entry.group(1))):
            bad.append(f"{head.group(1)} is open and its entry line quotes no words of the entry")
    summary = [l for l in text.split("\n## ")[0].splitlines()[1:] if l.strip()]
    if len(summary) > 5:
        bad.append(f"the summary has {len(summary)} lines, more than five")
    sections = {}
    for i, s in where.items():
        sections[s[0]] = sections.get(s[0], 0) + 1
    print(f"{report}: {len(ids)} candidates, {len(where)} placed; " + ", ".join(f"{n} {s.lower()}" for s, n in sections.items()))
    for b in bad:
        print("FAIL:", b, file=sys.stderr)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
