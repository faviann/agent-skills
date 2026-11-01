---
name: tailscale-policy
description: "Tailscale policy file of the user's work tailnet (ACLs, grants, groups, tag owners, SSH rules) through the API, with the user's review before every push. Use to read or change who can reach what on the tailnet."
---

# Tailscale policy

`scripts/tspolicy.py` (run it by full path from this skill's directory) moves the tailnet policy file between the live tailnet and a local working copy, `~/.cache/tailscale-policy/policy.hujson`. Every push carries the fingerprint of the version it was edited from, and Tailscale rejects it if the live policy has changed since. A push therefore lands on exactly the version the user reviewed.

## Change the policy

1. **Pull.** Run `tspolicy.py pull`. Exit 4 means a previous edit was never pushed. Show the user its diff with `tspolicy.py check` and ask whether to finish it or drop it (`pull --force` sets it aside in `policy.hujson.orig`).
2. **Edit** `policy.hujson` in place, keeping its comments and layout. When the change grants or removes access, add a `tests` entry that proves it, with `accept` for granted access and `deny` for removed access.
3. **Check.** Run `tspolicy.py check`. It prints the diff, then validates the policy and runs every policy test without applying anything. The step is done when it exits 0.
4. **Review.** Show the user the full diff and say in plain words who gains or loses access to what. Flag any change that could cut the user's own access. Wait for the user to approve this exact diff in their own message. Any later edit to the file needs a new check and a new approval.
5. **Push.** Run `tspolicy.py push`. The change is live when it exits 0.

| Exit | Meaning | Next move |
|---|---|---|
| 1 | Invalid policy or a failing policy test | Fix the edit and return to step 3 |
| 2 | Setup problem: no credential, auth failure, or no network | Relay the message to the user |
| 3 | The live policy changed since the pull. Nothing was written | Show the user the printed changes. Run `pull --force`, reapply the edit from `policy.hujson.orig`, and return to step 3 |
| 4 | Unpushed edits block a pull | Step 1 |

## Setup

The script reads an OAuth client from `~/.agents/tailscale-policy/oauth`, which the user's dotfiles render from the Bitwarden item `dotfiles/tailscale-policy-oauth`. The client holds only the `policy_file` scope. A missing file means the item doesn't exist yet. The user creates the OAuth client under Settings, then Trust credentials in the admin console, and saves its ID and secret in that item.

## Work data

The policy belongs to the user's employer. Keep it in `~/.cache/tailscale-policy` and this conversation, out of any repository and any published page.
