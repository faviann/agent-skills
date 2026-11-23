#!/usr/bin/env python3
"""Write the audit's report from a run folder: every candidate in one section, ranked for a tired reader.

usage: render.py <run-dir> --checkout DIR [--mode code|spec] [--previous REPORT] [--out FILE]
Reads <run-dir>/combined.json (written by combine.py), and when present agents.tsv, coverage/core-unreached.txt,
candidates.md's "## Vague" lines and notes.md (the session's own remarks, one per line).
--checkout  the audited tree: an entry's words are quoted from the guidance file itself when no auditor quoted
            the lines a verifier kept, and the report names the commit.
--previous  the last audit's report.md: open breaches are marked new or still open, matched by entry and place,
            and the ones that are gone are listed. Two runs on one tree differ, so "gone" is not "fixed".
Writes <run-dir>/report.md (or --out) and prints the counts.

The order: a summary of five lines; open breaches (binding entries, then design-level defaults, then other
defaults, then each tree-wide default pattern folded to one line); design concerns the verifiers did not confirm,
in full; contested; excused; vague rules; coverage; what the audit could not check; dropped.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

OK = ("confirmed", "narrowed")
SEVERITY = {"high": 0, "medium": 1, "low": 2}
MODEL = {"a": "opus", "b": "sonnet"}
FOLD_FILES = 8      # a default that its auditors placed in this many files or more is a tree-wide pattern
NEAR = 15           # two places in one file are the same place when their lines come this close
GUIDANCE = r"(?:COMMITMENTS|ENGINEERING|CONTRACTS|DEFAULTS|GUIDANCE|GLOSSARY)\.md|(?:docs/)?decision-log\.md"
PATH = r"[\w./-]+\.(?:ts|tsx|js|mjs|json|md|sh|toml|yml|yaml)"


def one_line(text):
    return re.sub(r"\s+", " ", text or "").strip()


def refs(text, pattern=PATH):
    """(file, first line, last line) for every `file:lines` in a text; lines are 0, 0 when the text gives none."""
    out = []
    for m in re.finditer(rf"({pattern})`?(?::\s?(\d[\d,\s–-]*))?", text or ""):
        spans = re.findall(r"(\d+)(?:\s*[–-]\s*(\d+))?", m.group(2) or "")
        if not spans:
            out.append((m.group(1), 0, 0))
        for a, b in spans:
            out.append((m.group(1), int(a), int(b or a)))
    return out


def same_place(a, b, near=NEAR):
    for fa, sa, ea in a:
        for fb, sb, eb in b:
            if os.path.basename(fa) != os.path.basename(fb) or not (fa.endswith(fb) or fb.endswith(fa)):
                continue
            if not sa or not sb or (sa <= eb + near and sb <= ea + near):
                return True
    return False


def quoted(block_entry):
    """[(file, start, end, words)] for each `FILE:lines "words"` in an auditor's entry line."""
    out = []
    for m in re.finditer(rf"({GUIDANCE})`?:\s?(\d+)(?:\s*[–-]\s*(\d+))?[^\"“]{{0,40}}[\"“]([^\"”]+)[\"”]", block_entry or ""):
        out.append((m.group(1), int(m.group(2)), int(m.group(3) or m.group(2)), m.group(4).strip()))
    return out


def entry_words(c, entry, checkout):
    """The words of the entry a verifier kept: the auditor's quotation when it is of those lines, else the file's."""
    want = refs(entry, GUIDANCE)
    if not want:
        return ""
    f, s, e = want[0]
    for b in c["blocks"]:
        for qf, qs, qe, words in quoted(b["fields"].get("entry", "")):
            if qf == f and (not s or (qs <= e + 3 and s <= qe + 3)):
                return words
    path = next((p for p in (os.path.join(checkout, f), os.path.join(checkout, "docs", f)) if os.path.exists(p)), "")
    if s and path:
        lines = open(path, encoding="utf-8").read().splitlines()[s - 1:e]
        text = one_line(" ".join(lines)).lstrip("-# ").strip()
        return text if len(text) <= 260 else text[:259] + "…"
    return ""


def kept(c):
    """The verdicts that keep the breach, the confirming ones first."""
    v = [(side, c["verdicts"][side]) for side in "ab" if c["verdicts"][side]["verdict"] in OK + ("excused",)]
    return sorted(v, key=lambda x: x[1]["verdict"] != "confirmed")


def first(c, name, prefer=""):
    values = [b["fields"][name] for b in c["blocks"] if b["fields"].get(name)]
    for v in values:
        if prefer and v.lower().startswith(prefer):
            return v
    return values[0] if values else ""


def files_named(c):
    return {f for b in c["blocks"] for f, _, _ in refs(b["fields"].get("place", "") or b["fields"].get("spec", ""))}


def tier(c):
    if c["kind"] == "binding":
        return "binding"
    blocks = [b["fields"].get("level", "") for b in c["blocks"] if b["fields"].get("level")]
    design = c["lens"] or (blocks and sum("design" in x.lower() for x in blocks) * 2 > len(blocks))
    if not c["lens"] and len(files_named(c)) >= FOLD_FILES:
        return "pattern"
    return "design" if design else "rest"


def rank(c):
    return (SEVERITY.get(c["severity"], 3), -len(c["sources"]), int(c["id"][1:]))


def verdict_line(c):
    a, b = c["verdicts"]["a"]["verdict"], c["verdicts"]["b"]["verdict"]
    if a == b == "confirmed":
        return "confirmed by both"
    if a == b == "narrowed":
        return "narrowed by both: each verifier's reading is in its evidence line; act on the part both keep"
    return "confirmed, narrowed: the entry, place and evidence above are the narrower reading"


def agree(c):
    return c["verdicts"]["a"]["verdict"] == c["verdicts"]["b"]["verdict"] == "confirmed"


def place_of(c, sides):
    places = [one_line(c["verdicts"][s]["place"]) for s in sides if c["verdicts"][s]["place"]]
    if len(places) == 2 and places[0] != places[1] and not agree(c):
        return f"{places[0]} (verifier b: {places[1]})"
    return places[0] if places else one_line(first(c, "place") or first(c, "spec"))


def entry_of(c, sides, checkout):
    entries = [one_line(c["verdicts"][s]["entry"]) for s in sides if c["verdicts"][s]["entry"]]
    if not entries:
        return one_line(first(c, "entry"))
    words = entry_words(c, entries[0], checkout)
    text = entries[0] + (f' — "{words}"' if words else "")
    if len(entries) == 2 and {f for f, _, _ in refs(entries[1], GUIDANCE)} != {f for f, _, _ in refs(entries[0], GUIDANCE)}:
        text += f" (verifier b: {entries[1]})"
    return text


def narrower(c):
    """The verifier whose reading both keep, when one confirmed the whole candidate and the other narrowed it."""
    a, b = c["verdicts"]["a"]["verdict"], c["verdicts"]["b"]["verdict"]
    return ("a" if a == "narrowed" else "b") if {a, b} == {"confirmed", "narrowed"} else None


def open_block(n, c, mode, checkout, mark):
    sides = sorted(s for s, _ in kept(c)) or ["a", "b"]
    one = narrower(c)
    out = [f"### {n}. {c['title']} [{c['id']}]{mark}",
           f"- entry: {entry_of(c, [one] if one else sides, checkout)}",
           f"- place: {place_of(c, [one] if one else sides)}"]
    if agree(c):
        out.append(f"- evidence: {one_line(c['verdicts']['a']['reason'])}")
    elif one:
        other = "b" if one == "a" else "a"
        out.append(f"- evidence (the narrower reading, which both verifiers keep): {one_line(c['verdicts'][one]['reason'])}")
        out.append(f"- wider reading (one verifier alone, not counted): {one_line(c['verdicts'][other]['place'])}. "
                   f"{one_line(c['verdicts'][other]['reason'])}")
    else:
        for s in "ab":
            v = c["verdicts"][s]
            out.append(f"- evidence (verifier {s}, {v['verdict']}): {one_line(v['reason'])}")
    out.append(f"- verdict: {verdict_line(c)}{second_look(c)}")
    if mode == "spec":
        change = first(c, "smallest change to the spec")
        if change:
            out.append(f"- smallest change to the spec: {one_line(change)}")
    else:
        out.append(f"- spec: {one_line(first(c, 'spec', 'prescribes')) or 'not stated'}")
    notes = [f"severity {c['severity']}", "raised by " + ", ".join(c["sources"])]
    if c["lens"] or c["design"]:
        notes.insert(0, "design-level")
    out.append(f"- {'; '.join(notes + c['flags'])}")
    return "\n".join(out)


def second_look(c):
    """What the report says of an open breach that the first two verifiers contested."""
    if "first" not in c:
        return ""
    no = c["first_no"]
    return (f". Open on a second look: of the first two verifiers, verifier {no} ({MODEL[no]}) rejected it "
            f"({one_line(c['first'][no]['reason'])}), and a second pair both kept it")


def looked_again(c):
    """What the report says of a candidate that a second pair of verifiers did not both keep."""
    if "second" not in c:
        return ""
    return " Second look: " + ", ".join(f"verifier {s} ({MODEL[s]}) {c['second'][s]['verdict']}" for s in "ab") + "."


def folded(c, checkout, mark):
    sides = [narrower(c)] if narrower(c) else sorted(s for s, _ in kept(c))
    files = files_named(c)
    places = sum(len(refs(b["fields"].get("place", ""))) for b in c["blocks"])
    return (f"- [{c['id']}]{mark} **{c['title']}** — {entry_of(c, sides, checkout)} — raised at {places} places in "
            f"{len(files)} files; {verdict_line(c).split(':')[0]}{', on a second look' if 'first' in c else ''}, at {place_of(c, sides)}. "
            f"Every place: candidates.md, {c['id']}.")


def design_block(n, c, mode):
    a, b = c["verdicts"]["a"], c["verdicts"]["b"]
    state = "dropped: both verifiers rejected it" if c.get("was") == "dropped" else "contested: one verifier kept it"
    out = [f"### D{n}. {c['title']} [{c['id']}]", f"{state}. Raised by {', '.join(c['sources'])}; severity {c['severity']}.", ""]
    shown = [x for x in c["blocks"] if x["label"].startswith(("L-", "SL-"))] or c["blocks"]
    names = (["symptom", "entry", "spec", "forced code", "why", "smallest change to the spec"] if mode == "spec"
             else ["symptom", "entry", "place", "why", "shape that would meet it", "spec"])
    for x in shown:
        out.append(f"From {x['label']}:")
        for name in names:
            if x["fields"].get(name):
                out.append(f"- {name}: {x['fields'][name]}")
        out.append("")
    for s, v in (("a", a), ("b", b)):
        out.append(f"Verifier {s} ({MODEL[s]}): {v['verdict']}. {one_line(v['reason'])}")
    if looked_again(c):
        out.append(looked_again(c).strip())
    return "\n".join(out)


def previous_findings(path):
    """Open breaches of an earlier report: [(title, entry refs, place refs)], from its trailer or its headings."""
    text = open(path, encoding="utf-8").read()
    m = re.search(r"<!-- kraken-audit open breaches: (\[.*?\]) -->", text, re.S)
    if m:
        return [(x["title"], [tuple(r) for r in x["entry"]], [tuple(r) for r in x["place"]]) for x in json.loads(m.group(1))]
    body = re.split(r"^## ", text, flags=re.M)
    section = next((s for s in body if s.lower().startswith("open breaches")), "")
    out = []
    for part in re.split(r"^(?=#{3,4} \d+\. )", section, flags=re.M):
        head = re.match(r"#{3,4} \d+\. (.*)", part)
        if not head:
            continue
        entry = re.search(r"^- entry: (.*)$", part, re.M)
        place = re.search(r"^- place: (.*)$", part, re.M)
        out.append((head.group(1).strip(), refs(entry.group(1) if entry else "", GUIDANCE), refs(place.group(1) if place else "")))
    return out


def same_finding(entry_a, place_a, entry_b, place_b):
    """Matched by entry and place: one guidance file in common, and one place in common."""
    return bool({f for f, _, _ in entry_a} & {f for f, _, _ in entry_b}) and same_place(place_a, place_b)


def cost(run):
    path = os.path.join(run, "agents.tsv")
    if not os.path.exists(path):
        return "", []
    rows = [l.rstrip("\n").split("\t") for l in open(path, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if len(r) >= 5 and r[0] != "label"]
    tokens = sum(int(re.sub(r"\D", "", r[2]) or 0) for r in rows)
    longest = [int(re.sub(r"\D", "", r[3]) or 0) for r in rows]
    stopped = [f"{r[0]} ({r[1]}) did not finish: {r[4]}" for r in rows if not re.match(r"(yes|finished)", r[4].strip().lower())]
    opus = sum(r[1] == "opus" for r in rows)
    text = f"{len(rows)} agents ({opus} Opus, {len(rows) - opus} Sonnet), {tokens:,} tokens"
    if longest and max(longest) > 5000:
        text += f", longest agent {max(longest) / 60000:.0f} minutes"
    return text, stopped


def vague_lines(run, cands):
    """(what the verifiers called vague, entries two or more auditors called vague, how many more places one
    auditor named, the design problems the lenses could tie to no entry)."""
    said = []
    for c in cands:
        words = [m.group(0).strip() for v in c["verdicts"].values()
                 for m in re.finditer(r"[^.]*\bvague\b[^.]*\.?", v["reason"], re.I)]
        entry = one_line(c["verdicts"]["a"]["entry"] or c["verdicts"]["b"]["entry"])
        if words:
            said.append(f"- {entry}, at {c['id']} ({c['title']}): {one_line(words[0])}")
        elif c["split"] or c.get("was") == "contested":
            said.append(f"- {entry}, at {c['id']} ({c['title']}): the verifiers split; see it under "
                        f"{'Design concerns' if c['section'] == 'design' else 'Contested'}.")
    path = os.path.join(run, "candidates.md")
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    m = re.search(r"^## Vague\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    untied, by_entry, alone = [], {}, 0
    for line in (m.group(1) if m else "").splitlines():
        line = line.strip()
        label = re.search(r"\(((?:G\d+|SL|S|L)[\w.]*-[ab])\)\s*$", line)
        if not line.startswith("- ") or not label:
            continue
        if label.group(1).startswith(("L-", "SL-")):
            untied.append(line)
            continue
        ref = refs(line[:60], GUIDANCE)
        key = f"{ref[0][0]}:{ref[0][1]}" if ref and ref[0][1] else None
        by_entry.setdefault(key or line, []).append((label.group(1), line))
    agreed = []
    for key, rows in by_entry.items():
        who = sorted({lab for lab, _ in rows})
        if len(who) < 2:
            alone += len(rows)
            continue
        quote = re.search(r'["“]([^"”]+)["”]', rows[0][1])
        agreed.append(f"- {key}{': \"' + quote.group(1) + '\"' if quote else ''}, called vague by {', '.join(who)}")
    return said, agreed, alone, untied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--checkout", required=True)
    ap.add_argument("--mode", choices=["code", "spec"], default="code")
    ap.add_argument("--previous")
    ap.add_argument("--out")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()
    run = os.path.abspath(a.run)
    data = json.load(open(os.path.join(run, "combined.json"), encoding="utf-8"))
    cands = data["candidates"]
    by = {s: sorted((c for c in cands if c["section"] == s), key=rank)
          for s in ("open", "design", "contested", "excused", "dropped", "unverified")}
    tiers = {t: [c for c in by["open"] if tier(c) == t] for t in ("binding", "design", "rest", "pattern")}
    ordered = tiers["binding"] + tiers["design"] + tiers["rest"] + tiers["pattern"]

    sha = ""
    if a.checkout:
        got = subprocess.run(["git", "-C", a.checkout, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        sha = got.stdout.strip()

    marks, gone, prev = {}, [], None
    if a.previous:
        prev = previous_findings(a.previous)
        seen = set()
        for c in ordered:
            sides = sorted(s for s, _ in kept(c))
            entry = [r for s in sides for r in refs(c["verdicts"][s]["entry"], GUIDANCE)]
            place = [r for s in sides for r in refs(c["verdicts"][s]["place"])]
            hit = [i for i, (_, pe, pp) in enumerate(prev) if same_finding(entry, place, pe, pp)]
            seen.update(hit)
            marks[c["id"]] = " — still open" if hit else " — new"
        gone = [prev[i][0] for i in range(len(prev)) if i not in seen]

    agents, stopped = cost(run)
    vague, vague_agreed, vague_alone, untied = vague_lines(run, cands)
    notes = []
    if os.path.exists(os.path.join(run, "notes.md")):
        notes = [l.strip() for l in open(os.path.join(run, "notes.md"), encoding="utf-8") if l.strip()]
    unchecked = stopped + data.get("problems", []) + [
        f"{c['id']} ({c['title']}) has no verdict from "
        f"{' and '.join('verifier ' + s for s in 'ab' if c['verdicts'][s]['verdict'] not in OK + ('excused', 'rejected'))}"
        for c in by["unverified"]]

    out = [f"# Kraken audit, {a.mode} mode{', ' + sha if sha else ''}, {a.date}", ""]
    n_open = len(by["open"])
    out.append(f"**{n_open} open breaches:** {len(tiers['binding'])} of binding entries, {len(tiers['design'])} design-level "
               f"defaults, {len(tiers['rest']) + len(tiers['pattern'])} other defaults ({len(tiers['pattern'])} of them "
               f"tree-wide patterns, one line each)."
               + (f" Against the last report: {sum(m.endswith('new') for m in marks.values())} new, "
                  f"{sum(m.endswith('open') for m in marks.values())} still open, {len(gone)} gone." if prev is not None else ""))
    if ordered:
        out.append("**Start with:** " + "; ".join(f"{i}. {c['title']}" for i, c in enumerate(ordered[:3], 1)) + ".")
    if by["design"]:
        out.append(f"**Design concerns the verifiers did not confirm: {len(by['design'])}.** "
                   + "; ".join(f"{c['title']} ({c.get('was')})" for c in by["design"][:3])
                   + (f"; and {len(by['design']) - 3} more" if len(by["design"]) > 3 else "")
                   + ". They are not counted as breaches; read them after the open ones.")
    else:
        out.append("**Design concerns the verifiers did not confirm:** none.")
    out.append(f"{len(by['contested'])} contested, {len(by['excused'])} excused, {len(vague) + len(vague_agreed)} vague places, "
               f"{len(by['dropped'])} dropped. Not checked: {len(unchecked)} thing{'s' if len(unchecked) != 1 else ''}"
               f"{' (see the section)' if unchecked else ''}.")
    out.append(f"Tree: `{os.path.abspath(a.checkout)}`." + (f" Cost: {agents}." if agents else ""))

    out += ["", "## Open breaches", "",
            "Both verifiers kept each of these" + (", or, where an item says so, both verifiers of a second look after the "
            "first two disagreed" if any("first" in c for c in by["open"]) else "") + ". Breaches of binding entries (commitments, principles, contracts) come first, "
            "then design-level defaults, then the other defaults, most severe first in each."]
    n = 0
    for name, title in (("binding", "Binding entries"), ("design", "Design-level defaults"), ("rest", "Other defaults")):
        if tiers[name]:
            out += ["", f"<!-- {title} -->", f"**{title}**", ""]
        for c in tiers[name]:
            n += 1
            out += [open_block(n, c, a.mode, a.checkout, marks.get(c["id"], "")), ""]
    if tiers["pattern"]:
        out += ["**Tree-wide default patterns**, one line each: the same departure in many files.", ""]
        out += [folded(c, a.checkout, marks.get(c["id"], "")) for c in tiers["pattern"]] + [""]
    if not by["open"]:
        out += ["", "None.", ""]
    if gone:
        out += ["**Gone since the last report** (open there, not found open here; an audit run varies, so check before "
                "you call one fixed):", ""] + [f"- {t}" for t in gone] + [""]

    out += ["## Design concerns the verifiers did not confirm", "",
            "A lens raised each of these from a symptom, and the verifiers contested or rejected it. They are not counted "
            "as breaches. Each is shown whole, because this is where a breach of design shows first, and where the "
            "guidance may lack the words for it."]
    for i, c in enumerate(by["design"], 1):
        out += ["", design_block(i, c, a.mode)]
    if not by["design"]:
        out += ["", "None."]
    if untied:
        out += ["", "**Design problems no entry's words reach**, as the lenses wrote them. This is where the guidance is silent:", ""] + untied

    out += ["", "## Contested", "", "One verifier kept it and one rejected it."]
    for c in by["contested"]:
        yes = next(s for s in "ab" if c["verdicts"][s]["verdict"] in OK)
        no = "b" if yes == "a" else "a"
        out.append(f"- [{c['id']}] **{c['title']}** — {one_line(c['verdicts'][yes]['entry'])}; {one_line(c['verdicts'][yes]['place'])}. "
                   f"For (verifier {yes}): {one_line(c['verdicts'][yes]['reason'])} Against (verifier {no}): {one_line(c['verdicts'][no]['reason'])}{looked_again(c)}")
    if not by["contested"]:
        out.append("None.")

    out += ["", "## Excused", "", "A breach that an exception in force in the decision log covers. Not counted as open."]
    for c in by["excused"]:
        s, v = kept(c)[-1] if kept(c)[-1][1]["verdict"] == "excused" else kept(c)[0]
        v = next(c["verdicts"][x] for x in "ab" if c["verdicts"][x]["verdict"] == "excused")
        out.append(f"- [{c['id']}] **{c['title']}** — {one_line(v['entry'])}; {one_line(v['place'])}. {one_line(v['reason'])}")
    if not by["excused"]:
        out.append("None.")

    out += ["", "## Vague rules", "", "Where an entry's words were too vague to decide. First what the verifiers said, "
            "then the entries that two or more auditors called vague."]
    out += vague or ["- The verifiers named none."]
    if vague_agreed:
        out += [""] + vague_agreed
    if vague_alone:
        out += ["", f"One auditor alone named {vague_alone} more places: candidates.md, under \"## Vague\"."]

    cov = os.path.join(run, "coverage", "core-unreached.txt")
    out += ["", "## Coverage by test tier", ""]
    if os.path.exists(cov):
        rows = [l.rstrip("\n") for l in open(cov, encoding="utf-8") if l.strip() and not l.startswith("#")]
        out.append(f"`src/core` code that no module test reaches, the {min(10, len(rows))} files with the most of it "
                   f"(of {len(rows)}); the whole list is `{cov}`.")
        out += [f"- {r.replace(chr(9), '; ')}" for r in rows[:10]]
    else:
        out.append("Not run (`--coverage` was not given, or the lens failed: see below).")

    out += ["", "## What this audit could not check", ""]
    out += [f"- {x}" for x in unchecked + notes] or ["Nothing was skipped: every agent finished and every candidate has two verdicts."]

    out += ["", "## Dropped", "", "Neither verifier left it open."]
    for c in by["dropped"]:
        v = c["verdicts"]["a"]
        out.append(f"- [{c['id']}] {c['title']} — {re.split(r'(?<=[.!?])\s', one_line(v['reason']), maxsplit=1)[0]}")
    if not by["dropped"]:
        out.append("None.")

    trailer = []
    for c in ordered:
        sides = sorted(s for s, _ in kept(c))
        trailer.append({"id": c["id"], "title": c["title"],
                        "entry": sorted({r for s in sides for r in refs(c["verdicts"][s]["entry"], GUIDANCE)}),
                        "place": sorted({r for s in sides for r in refs(c["verdicts"][s]["place"])})})
    out += ["", "<!-- kraken-audit open breaches: " + json.dumps(trailer, ensure_ascii=False) + " -->"]

    dest = a.out or os.path.join(run, "report.md")
    open(dest, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print(f"{dest}: {n_open} open ({len(tiers['binding'])} binding, {len(tiers['design'])} design-level, "
          f"{len(tiers['rest'])} other, {len(tiers['pattern'])} folded), {len(by['design'])} design concerns, "
          f"{len(by['contested'])} contested, {len(by['excused'])} excused, {len(by['dropped'])} dropped, "
          f"{len(by['unverified'])} unverified"
          + (f"; against the last report {sum(m.endswith('new') for m in marks.values())} new, "
             f"{sum(m.endswith('open') for m in marks.values())} still open, {len(gone)} gone" if prev is not None else ""))


if __name__ == "__main__":
    main()
