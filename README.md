# agent-skills

Agent skills authored by faviann. Each skill lives in `skills/<name>/` with a
`SKILL.md` whose frontmatter `name` matches the directory.

This repository only holds skill contents. Selection and installation are
handled by [faviann/skillset](https://github.com/faviann/skillset), which pins
this repository as a submodule source.

## Skills

- [`publish-artifact`](skills/publish-artifact/SKILL.md) — publish a finished
  file or directory through the artifact-server CLI and return a private review
  link. It checks the render in headless Chromium, reads comments over MCP, and
  makes an artifact public only when asked. Extracted with history from the
  `faviann/skills` fork.
- [`herdr-playbook`](skills/herdr-playbook/SKILL.md) — makes Claude Code fluent in
  herdr inside a herdr pane. It catalogs every capability with its verified
  command so Claude uses it unprompted: visible panes, cheap helper agents,
  worktrees, herd checks, desktop and phone notifications, and settings worth
  suggesting. Its `hooks/session-start.sh` primes each session to load the
  skill; register it as a Claude Code `SessionStart` hook.
- [`quest-3s`](skills/quest-3s/SKILL.md) — connects adb to faviann's Meta Quest
  3S over Tailscale, including from hosts whose tailscaled runs in userspace
  networking mode, and records the headset's quirks. `scripts/quest-connect.sh`
  diagnoses each failure and names the fix a person must make.

## Tests

```bash
bash skills/publish-artifact/scripts/test-publish.sh
bash skills/herdr-playbook/scripts/test-herdr-playbook.sh
```
