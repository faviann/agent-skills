#!/usr/bin/env bash
# Create a herdr worktree workspace at the user's worktree location:
#   ~/worktrees/<repo-name>/<branch-with-slashes-as-dashes>
# <repo-name> is the repository's directory under ~/repos, or the main checkout's directory name
# elsewhere. The branch forks from the current checkout's HEAD unless a base ref is given. herdr
# refuses a linked worktree as the source, so the command runs against the main worktree.
#
# Usage: new-worktree.sh <branch> [base-ref]
# Prints the herdr command to stderr and herdr's JSON response to stdout; read
# .result.workspace.workspace_id and .result.root_pane.pane_id from it.
# Exit: herdr's status; 2 for bad usage, outside herdr or Git, or an existing path.
set -euo pipefail

fail() { printf 'new-worktree: %s\n' "$1" >&2; exit 2; }
[[ $# -ge 1 && $# -le 2 && -n "$1" ]] || fail 'usage: new-worktree.sh <branch> [base-ref]'
branch=$1
[[ "${HERDR_ENV:-}" == 1 ]] || fail 'not inside herdr (HERDR_ENV is not 1)'
common=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || fail 'not inside a Git checkout'
base=$(git rev-parse --verify --quiet "${2:-HEAD}^{commit}") || fail "unknown base ref: ${2:-HEAD}"
source=$(git worktree list --porcelain | sed -n '1s/^worktree //p')
case $common in
  "$HOME"/repos/*) rel=${common#"$HOME/repos/"}; repo=${rel%%/*} ;;
  *) repo=$(basename "$(dirname "$common")") ;;
esac
path="$HOME/worktrees/$repo/${branch//\//-}"
[[ ! -e "$path" ]] || fail "$path already exists"

printf '+ herdr worktree create --cwd %q --branch %q --base %s --path %q --label %q --no-focus\n' \
  "$source" "$branch" "$base" "$path" "$repo $branch" >&2
exec herdr worktree create --cwd "$source" --branch "$branch" --base "$base" --path "$path" \
  --label "$repo $branch" --no-focus
