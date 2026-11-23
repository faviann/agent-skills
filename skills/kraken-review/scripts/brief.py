#!/usr/bin/env python3
"""Assemble the reviewer's brief: the template, the change, the spec pointers, a fresh checklist, the rules.

usage: brief.py <kraken-checkout> --change "<one or two sentences: what the change is and the git command that shows it>"
                --spec "<the spec files to read, e.g. its core, `docs/rebuild/s1-spec.md`, and `docs/rebuild/s1/u5.md`>"
                [--rules <file holding the operator's standing rules, appended verbatim>]
Prints the brief on stdout.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

p = argparse.ArgumentParser()
p.add_argument("checkout")
p.add_argument("--change", required=True)
p.add_argument("--spec", required=True)
p.add_argument("--rules")
a = p.parse_args()

checkout = os.path.abspath(a.checkout)
for f in ("GUIDANCE.md", "COMMITMENTS.md", "ENGINEERING.md", "CONTRACTS.md", "DEFAULTS.md"):
    if not os.path.exists(os.path.join(checkout, f)):
        sys.exit(f"{checkout} holds no {f}: not a Kraken checkout")

got = subprocess.run([sys.executable, os.path.join(HERE, "checklist.py"), checkout], capture_output=True, text=True)
if got.returncode:
    sys.exit(got.stderr.strip() or f"checklist.py failed with status {got.returncode}")
checklist = got.stdout
rules = ""
if a.rules:
    rules = ("\nThe standing rules for every agent on this repo follow, verbatim. Where they speak of pushing, "
             "a PR or tests, this review pushes nothing, opens nothing and runs nothing.\n\n"
             + open(a.rules, encoding="utf-8").read().strip() + "\n")

brief = open(os.path.join(HERE, "..", "references", "reviewer-brief.md"), encoding="utf-8").read()
brief = (brief.replace("{CHECKOUT}", checkout).replace("{CHANGE}", a.change.strip())
         .replace("{SPEC}", a.spec.strip()).replace("{CHECKLIST}", checklist.rstrip())
         .replace("{RULES}", rules))
assert "{" + "CHECKOUT}" not in brief
print(brief)
