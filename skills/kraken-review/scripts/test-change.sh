#!/usr/bin/env bash
# Five throwaway repositories, one per rule of change.py. usage: test-change.sh <empty-dir>
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); t=$(mkdir -p "$1" && cd "$1" && pwd); c="python3 $here/change.py"
g() { git -C "$1" -c user.name=t -c user.email=t@t "${@:2}"; }
mk() { rm -rf "$t/$1" "$t/$1.origin"; git init -q -b trunk "$t/$1.origin"; echo a > "$t/$1.origin/f"; g "$t/$1.origin" add f; g "$t/$1.origin" commit -q -m one
       git clone -q "$t/$1.origin" "$t/$1"; }
mk staged;   echo b >> "$t/staged/f"; g "$t/staged" add f
mk default;  g "$t/default" checkout -q -b unit; echo b >> "$t/default/f"; g "$t/default" commit -q -am two
mk upstream; g "$t/upstream" remote set-head origin -d; echo b >> "$t/upstream/f"; g "$t/upstream" commit -q -am two
mk none;     g "$t/none" remote set-head origin -d
mk base;     g "$t/base" remote set-head origin -d; g "$t/base" checkout -q -b unit; echo b >> "$t/base/f"; g "$t/base" commit -q -am two
fail=0
want() { out=$($c "${@:3}" 2>&1) && code=0 || code=$?; if [[ $code == "$1" && $out == *"$2"* ]]; then echo "ok   $3: $out"; else echo "FAIL $3 (exit $code): $out"; fail=1; fi; }
want 0 "git diff --cached" "$t/staged"
want 0 "the remote's default branch" "$t/default"
want 0 "not yet on its upstream" "$t/upstream"
want 2 "Pass --base" "$t/none"
want 0 "merge base with \`trunk\`" "$t/base" --base trunk
exit $fail
