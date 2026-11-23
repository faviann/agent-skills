#!/usr/bin/env python3
"""The review's verification step: tag the reviewer's claims, brief one verifier, apply its verdicts.

usage:
  verify.py tag   <review.md> <tagged.md>
      Copies the reviewer's text with a tag on every claim of a breach: [L1].. on ledger lines that say "breaks",
      [F1].. on findings, [O1].. on the list of other breaches. Exits 2 when the text lacks one of the three parts.
  verify.py brief <kraken-checkout> <tagged.md> --change "<as given to brief.py>" [--rules FILE]
      Prints the verifier's brief.
  verify.py apply <tagged.md> <verdicts.tsv>
      Prints the review as Fav gets it: the reviewer's text without the claims the verifier rejected or found
      excused, then a section "Verification" that lists what was narrowed and what was taken out, with the reasons.
      Exits 2 when the verdicts name a tag that does not exist or leave a tag without a verdict.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARTS = (("L", r"ledger"), ("F", r"findings"), ("O", r"(other|every other)\b.*breach|breach.*\bother"))
KEEP = ("confirmed", "narrowed", "defect")
DROP = ("rejected", "excused")
TAG = r"\[([LFO]\d+)\]"


def parts(lines):
    """[(letter, first line, one past the last line)] of the three parts, by their headings."""
    heads = [(i, re.sub(r"[#*\d.\s]+", " ", l).strip().lower()) for i, l in enumerate(lines) if re.match(r"^#{1,4} ", l)]
    found = []
    for letter, pattern in PARTS:
        hit = next((i for i, text in heads if re.search(pattern, text)), None)
        if hit is None:
            sys.stderr.write(f"the review has no part whose heading says {pattern!r}: ask the reviewer for that part\n")
            sys.exit(2)
        after = [i for i, _ in heads if i > hit]
        found.append((letter, hit + 1, after[0] if after else len(lines)))
    return found


def tag(src, dest):
    lines = open(src, encoding="utf-8").read().splitlines()
    count = {"L": 0, "F": 0, "O": 0}
    for letter, start, end in parts(lines):
        for i in range(start, end):
            line = lines[i]
            if letter == "L":
                claim = re.match(r"^\s*- ", line) and re.search(r"\bbreaks?\b|\bbroken\b", line, re.I)
            elif letter == "F":
                claim = re.match(r"^(\*\*(F|Finding )?\d+[.:]|\d+\.\s+\*\*|#{3,5} )", line)
            else:
                claim = re.match(r"^- ", line)
            if claim:
                count[letter] += 1
                mark = f"[{letter}{count[letter]}] "
                bullet = re.match(r"^(\s*- |\d+\.\s+)", line)
                lines[i] = (bullet.group(0) + mark + line[bullet.end():]) if bullet else mark + line
    open(dest, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{dest}: {count['L']} ledger lines that say breaks, {count['F']} findings, {count['O']} other breaches")
    if not all(count.values()):
        sys.stderr.write("a part holds no claim the tagger knows: check the review's form before you verify it\n")
        sys.exit(2)


def brief(checkout, tagged, change, rules):
    text = open(os.path.join(HERE, "..", "references", "verifier-brief.md"), encoding="utf-8").read()
    extra = ""
    if rules:
        extra = ("\nThe standing rules for every agent on this repo follow, verbatim. Where they speak of pushing, "
                 "a PR or tests, this task pushes nothing, opens nothing and runs nothing.\n\n"
                 + open(rules, encoding="utf-8").read().strip() + "\n")
    for k, v in (("CHECKOUT", os.path.abspath(checkout)), ("REVIEW", os.path.abspath(tagged)),
                 ("CHANGE", change.strip()), ("RULES", extra)):
        text = text.replace("{" + k + "}", v)
    print(text)


def blocks(lines):
    """tag -> the lines it covers: a ledger line, a finding to the next finding, a bullet with what hangs under it."""
    spans, order = {}, []
    span = parts([re.sub(TAG + " ", "", l) for l in lines])
    for letter, start, end in span:
        open_tag = None
        for i in range(start, end):
            m = re.search(TAG, lines[i])
            if m and m.group(1)[0] == letter:
                open_tag = m.group(1)
                spans[open_tag] = [i]
                order.append(open_tag)
            elif open_tag and letter != "L" and (letter == "F" or not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                if lines[i].strip() or letter == "F":
                    spans[open_tag].append(i)
            else:
                open_tag = None
    return spans, order


def apply(tagged, tsv):
    lines = open(tagged, encoding="utf-8").read().splitlines()
    spans, order = blocks(lines)
    by_tag, rows, bad = {}, [], []
    for raw in open(tsv, encoding="utf-8"):
        cells = [c.strip().strip("`") for c in raw.rstrip("\n").split("\t")]
        tags = re.findall(r"\b[LFO]\d+", cells[0]) if cells else []
        if not tags or len(cells) < 2 or cells[0].lower().startswith("tags"):
            continue
        word = re.match(r"[a-z]+", cells[1].lower())
        verdict = word.group(0) if word and word.group(0) in KEEP + DROP else None
        if not verdict:
            bad.append(f"{cells[0]}: no verdict the script knows in {cells[1]!r}")
            continue
        cells += [""] * (5 - len(cells))
        rows.append((verdict, cells[2], cells[3], " ".join(cells[4:]).strip()))
        for t in tags:
            if t not in spans:
                bad.append(f"{t}: the verdicts name it, and the review has no such tag")
            by_tag.setdefault(t, []).append(verdict)
    bad += [f"{t}: no verdict" for t in order if t not in by_tag]
    if bad:
        sys.stderr.write("the verdicts do not cover the review:\n" + "".join(f"  {b}\n" for b in bad))
        sys.exit(2)
    gone = set()
    for t in order:  # a claim the verifier split by place stays unless every part of it was taken out
        if all(v in DROP for v in by_tag[t]):
            gone.update(spans[t])
    out = [re.sub(TAG + " ", "", l) for i, l in enumerate(lines) if i not in gone]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).rstrip()
    n = {v: sum(r[0] == v for r in rows) for v in KEEP + DROP}
    said = ["## Verification", "",
            f"One verifier judged the {len(rows)} breaches this review listed against the entries' words and the code: "
            f"{n['confirmed']} confirmed, {n['narrowed']} narrowed, {n['defect']} real defects that no entry reaches, "
            f"{n['rejected']} rejected, {n['excused']} excused. The rejected and excused ones are taken out of the "
            f"text above and listed here."]
    for verdict, title in (("narrowed", "Narrowed: the breach is real, and narrower than the reviewer said"),
                           ("defect", "A real defect, and no breach of an entry"),
                           ("rejected", "Taken out: rejected"), ("excused", "Taken out: excused by an exception in force")):
        if n[verdict]:
            said += ["", f"**{title}**"] + [f"- {r[2] or 'no place given'} — {r[1] or 'no entry'}: {r[3]}"
                                            for r in rows if r[0] == verdict]
    print(text + "\n\n" + "\n".join(said))
    sys.stderr.write(f"{len(rows)} breaches: " + ", ".join(f"{n[v]} {v}" for v in KEEP + DROP) + "\n")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="step", required=True)
    t = sub.add_parser("tag"); t.add_argument("review"); t.add_argument("tagged")
    b = sub.add_parser("brief"); b.add_argument("checkout"); b.add_argument("tagged")
    b.add_argument("--change", required=True); b.add_argument("--rules")
    a = sub.add_parser("apply"); a.add_argument("tagged"); a.add_argument("verdicts")
    args = ap.parse_args()
    if args.step == "tag":
        tag(args.review, args.tagged)
    elif args.step == "brief":
        brief(args.checkout, args.tagged, args.change, args.rules)
    else:
        apply(args.tagged, args.verdicts)


if __name__ == "__main__":
    main()
