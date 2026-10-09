# agent-skills

Agent skills authored by faviann. Each skill lives in `skills/<name>/` with a
`SKILL.md` whose frontmatter `name` matches the directory.

This repository only holds skill contents. Selection and installation are
handled by [faviann/skillset](https://github.com/faviann/skillset), which pins
this repository as a submodule source.

## Skills

- [`publish-artifact`](skills/publish-artifact/SKILL.md) — publish a finished
  file or directory through a host-configured filesystem-to-HTTP mapping.
  Extracted with history from the `faviann/skills` fork.
- [`herdr-playbook`](skills/herdr-playbook/SKILL.md) — makes Claude Code fluent in
  herdr inside a herdr pane. It catalogs every capability with its verified
  command so Claude uses it unprompted: visible panes, cheap helper agents,
  worktrees, herd checks, desktop and phone notifications, and settings worth
  suggesting. Its `hooks/session-start.sh` primes each session to load the
  skill; register it as a Claude Code `SessionStart` hook.

## Tests

```bash
bash skills/publish-artifact/scripts/test-publish-artifact.sh
bash skills/herdr-playbook/scripts/test-herdr-playbook.sh
```
