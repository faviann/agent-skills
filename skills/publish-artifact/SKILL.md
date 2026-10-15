---
name: publish-artifact
description: Publish a finished file or directory tree to a stable, versioned URL through a host-configured mapping. Use whenever an agent produces something the person should open in a browser, such as an HTML report, a Markdown document, or a prototype, including another skill's output and even when nobody asked for a link; when the person asks to publish or update a published file or directory; or when they ask to configure the host mapping.
---

# Publish Artifact

Publish one completed regular file or prepared directory tree at a stable URL. Every publication is an immutable version, and publishing the same slug again adds a version behind the same URL. The bundled command is the publication seam: it owns configuration, repository grouping, artifact lookup, version allocation, copying, cleanup, the viewer page, the optional gallery, URL construction, and result classification. Invoke it directly so every producer gets the same behaviour.

## Publish from another skill

1. Finish the source file or directory tree and keep it unchanged until the command returns. Pass the narrowest exact publication set: the command copies the complete tree without filtering, merging, renaming, or transforming it.
2. From the producing repository or workspace, invoke the command with four arguments and an optional title:

   ```bash
   <skill-directory>/scripts/publish-artifact.sh <producer-slug> <artifact-slug> <absolute-source-file-or-directory> <relative-primary-path> [title]
   ```

   Use a stable lowercase producer slug such as `architecture-report`. The artifact slug names the page, such as `auth-migration-plan`. Reuse it to publish a new version of that page, including from a later session, and choose a new slug for a new page. Both slugs are lowercase letters and digits joined by single hyphens. The title heads the viewer page: pass it on the first publication and whenever it should change, up to 200 characters. Without a title, the stored one stays, and a new artifact uses its slug.

   For a file, pass its basename as the relative primary path; for a directory, pass the path of one contained regular file relative to that directory. A primary ending in `.md` renders as formatted Markdown in the viewer, so publish Markdown directly. The working directory supplies repository context.

   Source trees contain only real directories and regular files with valid UTF-8 names. Primary paths are relative and free of traversal and control characters. Symlinked ancestors outside the source are allowed. Symlinks at the source itself or within its tree and special filesystem entries are refused.

   Preparation space and publication space must not overlap: the source and configured publishing root must resolve to separate locations, with neither containing the other. The command rejects overlap as `invalid-call` before writing.

3. Read the single JSON result and finish according to its `status`:

   - `published` — return its `url` and `path` without an HTTP verification request. `url` is the viewer page for people: it follows the newest version and offers the earlier ones. Hand `latestUrl` to a service that fetches raw content, and `versionUrl` when a reference must stay pinned to this version. `galleryUrl` appears when the host configures a gallery; return it only when the person asks for their published artifacts.
   - `unconfigured` — let the producer preserve its normal local handoff without advertising missing configuration.
   - `error` — treat the failure as terminal; nothing new was published. The nonzero result carries one stable `category`: `invalid-call`, `configuration`, `dependency`, or `publication`.

## Publish an artifact named by a person

1. Resolve the named source to an absolute path without following a source symlink.
2. Confirm it is a regular file or directory. A file is its own primary; for a directory, use the person's named primary or one unambiguously implied by their request. If the primary is ambiguous, ask them to name it.
3. Invoke the same command with producer `manual`, a slug describing the artifact, and the primary's relative path. To update an earlier publication, reuse its slug, the segment of its `url` before the random suffix.
4. Return the command's JSON result.

## Host configuration

When the person asks to configure the host mapping or the gallery, or the result is `unconfigured`, `configuration`, or `dependency`, read [HOST-CONFIGURATION.md](HOST-CONFIGURATION.md).
