---
name: publish-artifact
description: Remote browser access for a completed one-file artifact through a host-configured filesystem-to-HTTP mapping. Use when an agent has produced a file on another machine and the person needs its direct URL.
---

# Publish Artifact

Publish one completed regular file for remote browser access. The bundled command is the publication seam: it owns configuration, repository grouping, generation allocation, copying, cleanup, URL construction, and result classification. Invoke it directly so every producer gets the same behaviour.

## Publish from another skill

1. Finish the source file and keep it unchanged until the command returns.
2. From the producing repository or workspace, invoke the command with exactly three arguments:

   ```bash
   <skill-directory>/scripts/publish-artifact.sh <producer-slug> <absolute-source-file> <relative-primary-name>
   ```

   Use a stable lowercase producer slug such as `architecture-report`. Pass the source file's basename as its relative primary name. The working directory supplies repository context.

3. Read the single JSON result and finish according to its `status`:

   - `published` — return its `path` and `url` without an HTTP verification request.
   - `unconfigured` — report that the optional default mapping is absent so the producer can preserve its normal local handoff.
   - `error` — treat the failure as terminal. The nonzero result carries one stable `category`: `invalid-call`, `configuration`, `dependency`, or `publication`.

## Publish a file named by a person

1. Resolve the named file to an absolute path without following a source symlink.
2. Confirm it is a regular file.
3. Invoke the same three-argument command with producer `manual` and the file's basename as its primary name.
4. Return the command's JSON result.

If the person supplies a directory, explain that this version publishes one completed file only and ask them to name that file.

## Host configuration

When the person asks to configure the host mapping, or the result is `unconfigured`, `configuration`, or `dependency`, read [HOST-CONFIGURATION.md](HOST-CONFIGURATION.md).
