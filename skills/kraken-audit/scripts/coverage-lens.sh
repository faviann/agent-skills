#!/usr/bin/env bash
# Coverage by test tier: which lines of src/core no module test reaches.
# Those lines are reached, if at all, only by daemon, kill-sweep or real-agent tests: the expensive tier.
#
# usage: coverage-lens.sh <kraken-checkout> <out-dir>
# Works in a throwaway clone under <out-dir>; never touches the checkout. Runs npm ci, adds the coverage
# provider without saving it, and runs only module tests, with at most four workers. It runs no daemon test,
# no kill sweep and no real-agent test, and no test that calls sudo.
# Writes <out-dir>/module-tests.txt, <out-dir>/excluded-tests.txt and <out-dir>/core-unreached.txt.
set -euo pipefail
src=$(cd "$1" && pwd); out=$(mkdir -p "$2" && cd "$2" && pwd)
copy="$out/cov-copy"
rm -rf "$copy"
git clone -q --no-hardlinks "$src" "$copy"
git -C "$copy" remote remove origin 2>/dev/null || true
cd "$copy"

# Module tests: every test file that starts no daemon, no kill sweep, no real agent and calls no sudo.
: > "$out/module-tests.txt"; : > "$out/excluded-tests.txt"
for f in test/*.test.ts; do
  if [[ $f == *kill-sweep* || $f == *real-agent* || $f == *-users.test.ts || $f == test/daemon* ]] \
     || grep -qE 'from "\./(daemons|ends|owner-socket|sudo-rules|kill-sweep-invariants)(\.ts)?"' "$f" \
     || grep -qE '"sudo"|`sudo |sudo -u|sudoRules' "$f"; then
    echo "$f" >> "$out/excluded-tests.txt"
  else
    echo "$f" >> "$out/module-tests.txt"
  fi
done

npm ci --no-audit --no-fund --loglevel=error > "$out/npm-ci.log" 2>&1
vitest_version=$(node -p 'require("vitest/package.json").version')
npm install --no-save --no-audit --no-fund --loglevel=error "@vitest/coverage-v8@$vitest_version" >> "$out/npm-ci.log" 2>&1

# shellcheck disable=SC2046
npx vitest run --testTimeout=60000 --maxWorkers=4 \
  --coverage.enabled --coverage.provider=v8 --coverage.reporter=json --coverage.reportOnFailure=true \
  --coverage.include='src/core/**' --coverage.reportsDirectory="$out/coverage" \
  $(cat "$out/module-tests.txt") > "$out/vitest.log" 2>&1 || echo "some module tests failed; see $out/vitest.log" >&2

python3 - "$out/coverage/coverage-final.json" "$copy" > "$out/core-unreached.txt" <<'PY'
import json, sys, os
cov, root = json.load(open(sys.argv[1])), sys.argv[2]
def ranges(nums):
    nums = sorted(nums); out = []
    for n in nums:
        if out and n == out[-1][1] + 1: out[-1][1] = n
        else: out.append([n, n])
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in out)
rows = []
for path, f in cov.items():
    rel = os.path.relpath(path, root)
    if not rel.startswith("src/core/"): continue
    lines = {}
    for k, loc in f["statementMap"].items():
        for ln in range(loc["start"]["line"], loc["end"]["line"] + 1):
            lines[ln] = lines.get(ln, 0) or f["s"][k]
    miss = [ln for ln, hit in lines.items() if not hit]
    br = [b["loc"]["start"]["line"] for k, b in f["branchMap"].items() if any(c == 0 for c in f["b"][k])]
    if miss or br: rows.append((len(miss) + len(br), rel, len(lines), ranges(miss), len(br), ranges(br)))
print("# src/core code no module test reaches: file, unreached statement lines, lines with a branch never taken")
for _, rel, total, r, nb, rb in sorted(rows, key=lambda r: -r[0]):
    print(f"{rel}\tstatements {r or '-'} (of {total} lines)\tbranches never taken at {rb or '-'} ({nb})")
PY
echo "wrote $out/core-unreached.txt"
