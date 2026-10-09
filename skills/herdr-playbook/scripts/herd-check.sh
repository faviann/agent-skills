#!/usr/bin/env bash
# List the other herdr agents working in this repository, so a destructive Git operation
# doesn't pull the tree out from under one. Read-only: runs `git` and `herdr agent list`.
#
# Usage: herd-check.sh [path]        (default: current directory)
# Output: one TSV row per agent: scope, pane_id, agent, status, cwd
#   same-checkout   the agent works inside the checkout at <path>
#   other-worktree  the agent works in another worktree of the same repository
# Prints "no other agents in this repository" when there are none.
# Exit: 0 on success, 2 outside herdr or outside a Git checkout, 1 if herdr fails.
set -euo pipefail

target=${1:-$PWD}
if [[ "${HERDR_ENV:-}" != 1 ]]; then
  printf 'herd-check: not inside herdr (HERDR_ENV is not 1)\n' >&2
  exit 2
fi
if ! top=$(git -C "$target" rev-parse --show-toplevel 2>/dev/null); then
  printf 'herd-check: %s is not inside a Git checkout\n' "$target" >&2
  exit 2
fi
roots=$(git -C "$target" worktree list --porcelain | sed -n 's/^worktree //p' | jq -R . | jq -sc .)
agents=$(herdr agent list)

jq -r --arg top "$top" --argjson roots "$roots" --arg me "${HERDR_PANE_ID:-}" '
  [ .result.agents[]
    | select(.pane_id != $me)
    | (.foreground_cwd // .cwd // "") as $cwd
    | ([ $roots[] | . as $root | select(($cwd + "/") | startswith($root + "/")) ]
       | max_by(length)) as $checkout
    | select($checkout != null)
    | [ (if $checkout == $top then "same-checkout" else "other-worktree" end),
        .pane_id, (.agent // "-"), .agent_status, $cwd ] ]
  | if length == 0 then "no other agents in this repository"
    else (["scope", "pane_id", "agent", "status", "cwd"], .[]) | @tsv end
' <<<"$agents"
