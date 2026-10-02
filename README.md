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

## Tests

```bash
bash skills/publish-artifact/scripts/test-publish-artifact.sh
```
