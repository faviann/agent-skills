---
name: publish-artifact
description: Publish a completed one-file artifact through an optional host-configured filesystem-to-HTTP mapping. Use when a browser-viewable file must be reachable from another machine, especially from remote or SSH-based agent sessions.
---

# Publish Artifact

Publish only a completed regular file. This skill is a thin adapter over [scripts/publish-artifact.sh](scripts/publish-artifact.sh); the script owns configuration, repository grouping, generation allocation, copying, cleanup, URL construction, and result classification. Do not recreate those decisions in prose or with ad hoc shell commands.

## From another skill

Invoke the script with exactly three arguments:

```bash
<skill-directory>/scripts/publish-artifact.sh <producer-slug> <absolute-source-file> <relative-primary-name>
```

- Use a stable lowercase producer slug such as `architecture-report`.
- Finish writing the source before invoking the publisher, and do not mutate it during publication.
- Pass the source file's basename as its relative primary name.
- Run it from the producing repository or workspace; the working directory supplies repository context.

Read its single JSON result. `published` returns `path` and `url`; `unconfigured` means the default optional mapping is absent. An `error` result is nonzero and carries one stable `category`: `invalid-call`, `configuration`, `dependency`, or `publication`. Never silently fall back after an error, and never make an HTTP request to verify a returned URL.

## Direct human invocation

When a person invokes this skill with a file, form its absolute path without following a source symlink, confirm it is a regular file, infer its basename as the primary name, and invoke the same script with producer `manual`. Return the script's result. Do not add flags or another wrapper interface.

If the person supplies a directory, explain that this version publishes one completed file only and ask them to name that file.

## Host configuration

The default configuration is `${XDG_CONFIG_HOME:-$HOME/.config}/faviann-skills/artifacts.json`. `FAVIANN_SKILLS_ARTIFACT_CONFIG` explicitly selects another file for the current invocation. The JSON object requires:

```json
{
  "directory": "/existing/web/root",
  "baseUrl": "https://artifacts.example.com/files"
}
```

`baseUrl` accepts an HTTP(S) URL with a non-bracketed host authority, an optional port, and no query or fragment. Bracketed IP literals are not supported in this version.

The host owns creation, permissions, serving, access control, and retention for `directory`. The publisher supports Linux with Bash and `jq`; Git is additionally required when a linked worktree needs its primary-checkout grouping derived. Outside Git, the invocation-directory name remains the grouping fallback. The publisher does not create the configured root, manage it, inspect artifact content, or verify HTTP reachability.
