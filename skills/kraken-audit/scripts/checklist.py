#!/usr/bin/env python3
"""Print Kraken's guidance as a checklist, one line per entry, read from the files at run time.

usage: checklist.py <kraken-checkout> [group ...]
  groups: commitments engineering contracts defaults (default: all four)

Each line is `FILE:start-end  <heading or first sentence>`. Line numbers are those of the checkout,
so a reviewer can open the entry's full words. The files are the authority; this is only an index.

It exits 2 and prints nothing to stdout when a file's shape is not the one it knows how to index: a file is
missing, holds no entries, reads as a few very long entries, or holds lines it would index wrongly (see `odd`).
A checklist that silently lost entries would make every audit and review built on it look complete.
"""
import os
import re
import sys

FILES = {
    "commitments": ("COMMITMENTS.md", "binding"),
    "engineering": ("ENGINEERING.md", "binding"),
    "contracts": ("CONTRACTS.md", "binding"),
    "defaults": ("DEFAULTS.md", "a departure needs a stated reason"),
}


def first_sentence(text, limit=200):
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.findall(r".+?(?:[.:;](?=\s|$)|$)", text)
    s = parts[0].strip() if parts else text
    if len(s.split()) <= 4 and len(parts) > 1:  # a label such as "Ownership." carries no rule
        s += " " + parts[1].strip()
    return s if len(s) <= limit else s[: limit - 1] + "…"


def entries(lines):
    """Yield (start, end, label, depth) for headings and top-level bullets or paragraphs under them."""
    out = []
    cur = None  # [start, end, text, kind]
    in_code = False

    def close(end):
        nonlocal cur
        if cur:
            cur[1] = end
            out.append(cur)
            cur = None

    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        h = re.match(r"^(#{2,4})\s+(.*)", line)
        if h:
            close(i - 1)
            out.append([i, i, h.group(2).strip(), "h" + str(len(h.group(1)))])
            continue
        if line.startswith("|"):
            close(i - 1)
            continue
        if re.match(r"^(- |\d+\. )", line):
            close(i - 1)
            cur = [i, i, re.sub(r"^(- |\d+\. )", "", line), "item"]
            continue
        if not line.strip():
            if cur and cur[3] == "para":
                close(i - 1)
            continue
        if re.match(r"^\s+- ", line):
            close(i - 1)
            cur = [i, i, re.sub(r"^\s+- ", "", line), "sub"]
            continue
        if line.startswith(" ") and cur:
            cur[2] += " " + line.strip()
            cur[1] = i
            continue
        if cur and cur[3] == "para":
            cur[2] += " " + line.strip()
            cur[1] = i
            continue
        close(i - 1)
        cur = [i, i, line, "para"]
    close(len(lines))
    return out


def odd(lines):
    """Lines the index would get wrong: [(line number, why)]."""
    out, in_code, last = [], False, "blank"
    for i, raw in enumerate(lines, 1):
        line = raw.rstrip("\n")
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if re.match(r"^[*+] ", line):
            out.append((i, "a `*` or `+` bullet: entries are `- ` bullets, and this one would join its neighbours"))
        elif re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", line):
            out.append((i, "a rule line: it would be listed as an entry"))
        elif re.match(r"^#{5,}\s", line) or (re.match(r"^#\s", line) and i > 1):
            out.append((i, "a heading of a level the index does not know (it knows ## to ####, and # on line 1)"))
        elif line.startswith("<!--"):
            out.append((i, "an HTML comment: it would be listed as an entry"))
        elif line.startswith("|") and last in ("blank-after-heading", "heading"):
            out.append((i, "a table right under a heading: its rows would be left out with no entry to introduce them"))
        if not line.strip():
            last = "blank-after-heading" if last in ("heading", "blank-after-heading") else "blank"
        else:
            last = "heading" if re.match(r"^#{1,6}\s", line) else "text"
    if in_code:
        out.append((len(lines), "a code fence that never closes: everything after it is left out"))
    return out


def index(root, group):
    """The checklist lines of one group, or the reasons its file cannot be indexed."""
    name, status = FILES[group]
    path = os.path.join(root, name)
    if not os.path.isfile(path):
        return [], [f"{name}: no such file in {root}"]
    lines = open(path, encoding="utf-8").readlines()
    problems = [f"{name}:{n}: {why}: {lines[n - 1].strip()[:80]}" for n, why in odd(lines)]
    out, count = [f"\n{name} ({status})"], 0
    for start, end, text, kind in entries(lines):
        if kind == "h1" or start == 1:
            continue
        # trailing blank lines are not part of an entry
        while end > start and not lines[end - 1].strip():
            end -= 1
        span = f"{start}" if start == end else f"{start}-{end}"
        if kind != "sub" and re.match(r"^(Why|Checked by)\b", text):
            continue
        if kind.startswith("h"):
            out.append(f"  {name}:{span}  ## {text}")
        else:
            count += 1
            indent = "      " if kind == "sub" else "  "
            out.append(f"{indent}- {name}:{span}  {first_sentence(text)}")
    full = sum(1 for l in lines if l.strip())
    if count == 0:
        problems.append(f"{name}: no entries found in {full} lines")
    elif full / count > 30:
        problems.append(f"{name}: {full} lines read as only {count} entries; the file's shape changed")
    return out, problems


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = sys.argv[1]
    groups = sys.argv[2:] or list(FILES)
    unknown = [g for g in groups if g not in FILES]
    if unknown:
        sys.exit(f"unknown group {', '.join(unknown)}: the groups are {', '.join(FILES)}")
    out, problems = [], []
    for g in groups:
        lines, bad = index(root, g)
        out += lines
        problems += bad
    if problems:
        print("checklist.py cannot index the guidance as it stands. Fix the file, or teach checklist.py its new shape:",
              file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        sys.exit(2)
    print("\n".join(out))


if __name__ == "__main__":
    main()
