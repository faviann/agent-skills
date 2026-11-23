#!/usr/bin/env python3
"""Say what the change under review is, as the git command that shows it. Read-only.

usage: change.py <kraken-checkout> [--base REF]
Prints one sentence for brief.py's --change. The first of these that holds decides:
  1. --base REF: the current branch against its merge base with REF.
  2. Something is staged: the staged change against the last commit.
  3. The remote names a default branch (origin/HEAD) and this branch is ahead of it: against that merge base.
  4. The branch has an upstream and is ahead of it: the commits not yet pushed.
Exits 2 when none holds: name the base, do not guess one. No branch name is built into this script.
"""
import argparse
import subprocess
import sys


def git(checkout, *args):
    got = subprocess.run(["git", "-C", checkout, *args], capture_output=True, text=True)
    return got.returncode, got.stdout.strip()


def ahead(checkout, base):
    code, mb = git(checkout, "merge-base", "HEAD", base)
    if code:
        return None, 0
    _, n = git(checkout, "rev-list", "--count", f"{mb}..HEAD")
    return mb, int(n or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("--base")
    a = ap.parse_args()
    co = a.checkout
    code, head = git(co, "rev-parse", "--short", "HEAD")
    if code:
        sys.exit(f"{co} is not a git checkout with a commit")
    _, branch = git(co, "rev-parse", "--abbrev-ref", "HEAD")

    if a.base:
        mb, n = ahead(co, a.base)
        if mb is None:
            sys.exit(f"no merge base between HEAD and {a.base}")
        print(f"the branch `{branch}`, {n} commits past its merge base with `{a.base}`: `git diff {mb[:7]}..HEAD` shows it.")
        return
    staged, _ = git(co, "diff", "--cached", "--quiet")
    if staged == 1:
        print(f"staged and not committed: `git diff --cached` shows it against the last commit, `{head}`.")
        return
    code, default = git(co, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if code == 0 and default:
        mb, n = ahead(co, default)
        if mb and n:
            print(f"the branch `{branch}`, {n} commits past its merge base with `{default}`, the remote's default "
                  f"branch: `git diff {mb[:7]}..HEAD` shows it.")
            return
    code, upstream = git(co, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    if code == 0 and upstream:
        mb, n = ahead(co, upstream)
        if mb and n:
            print(f"the {n} commits of `{branch}` that are not yet on its upstream `{upstream}`: "
                  f"`git diff {mb[:7]}..HEAD` shows them.")
            return
    sys.stderr.write("cannot tell what the change is: nothing is staged, and the branch is not ahead of a remote default "
                     "branch or of an upstream. Pass --base <the branch or commit this change will merge into>.\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
