---
name: publish-artifact
description: Remote browser access for a completed file or prepared directory tree through a host-configured filesystem-to-HTTP mapping. Use when an agent has produced an artifact on another machine and the person needs its direct URL.
---

# Publish Artifact

Publish one completed regular file or prepared directory tree for remote browser access. The bundled command is the publication seam: it owns configuration, repository grouping, generation allocation, copying, cleanup, URL construction, and result classification. Invoke it directly so every producer gets the same behaviour.

## Publish from another skill

1. Finish the source file or directory tree and keep it unchanged until the command returns. Pass the narrowest exact publication set: the command copies the complete tree without filtering, merging, renaming, or transforming it.
2. From the producing repository or workspace, invoke the command with exactly three arguments:

   ```bash
   <skill-directory>/scripts/publish-artifact.sh <producer-slug> <absolute-source-file-or-directory> <relative-primary-path>
   ```

   Use a stable lowercase producer slug such as `architecture-report`. For a file, pass its basename as the relative primary path; for a directory, pass the path of one contained regular file relative to that directory. The working directory supplies repository context.

   Source trees contain only real directories and regular files with valid UTF-8 names. Primary paths are relative and free of traversal and control characters. Source symlinks and special filesystem entries are refused.

3. Read the single JSON result and finish according to its `status`:

   - `published` — return its `path` and `url` without an HTTP verification request.
   - `unconfigured` — let the producer preserve its normal local handoff without advertising missing configuration.
   - `error` — treat the failure as terminal. The nonzero result carries one stable `category`: `invalid-call`, `configuration`, `dependency`, or `publication`.

## Publish an artifact named by a person

1. Resolve the named source to an absolute path without following a source symlink.
2. Confirm it is a regular file or directory. A file is its own primary; for a directory, use the person's named primary or one unambiguously implied by their request. If the primary is ambiguous, ask them to name it.
3. Invoke the same three-argument command with producer `manual` and the primary's relative path.
4. Return the command's JSON result.

## Host configuration

When the person asks to configure the host mapping, or the result is `unconfigured`, `configuration`, or `dependency`, read [HOST-CONFIGURATION.md](HOST-CONFIGURATION.md).
