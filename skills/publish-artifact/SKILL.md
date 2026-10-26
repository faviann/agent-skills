---
name: publish-artifact
description: Publish a finished file or directory tree to a stable, versioned URL through a host-configured mapping. Use whenever an agent produces something the person should open in a browser, such as an HTML report, a Markdown document, or a prototype, including another skill's output and even when nobody asked for a link; when the person asks to publish or update a published file or directory; or when they ask to configure the host mapping.
---

# Publish Artifact

Publish a finished file or directory tree to artifact-server, check that it renders, and hand the person its private review link. `<skill-directory>` below is the directory holding this file.

## Publish

1. Finish the source and keep it unchanged until the command returns. Stage only the files to publish in one directory, because the whole tree is uploaded. A directory opens its `index.html`, so add one when the report has another name. A single file is its own entry.
2. Publish:

   ```bash
   <skill-directory>/scripts/publish.sh <path> [--name <name>]
   ```

   Pass a short `--name` for a new artifact. The artifact stays private, and the command never makes it public.
3. Read the JSON result.

   - `links.review` is present — the artifact is published. Keep `artifact.id` and `artifact.currentVersionId`.
   - `{"status":"unconfigured"}` — let the producer preserve its normal local handoff without advertising missing configuration.
   - `status` is `error` — treat it as terminal. `category` is `invalid-call`, `configuration`, `dependency`, or `publication`. Read [HOST-CONFIGURATION.md](HOST-CONFIGURATION.md) for `configuration` and `dependency`. When a `publication` message says the input changed while an earlier attempt is pending, publish a copy of the directory at a new path.
4. Check the render before you hand the link over:

   ```bash
   <skill-directory>/scripts/render-check.sh <artifact.id>
   ```

   Exit 1 means the page broke and `consoleErrors` or `pageErrors` say how. Fix the source, publish a new version, and check again. Exit 2 or 3 means the check could not run, so fix the invocation or the environment and leave the page alone. Always read `failedRequests`, and open the PNG named by `screenshot` to confirm the page shows what you meant to publish.
5. Hand the person the `links.review` of the final version and no other link. A review link pins its version, so a link from an earlier version shows the earlier page.

## Publish a new version

Publish again with the artifact and its current version, to keep one artifact and one comment history:

```bash
<skill-directory>/scripts/publish.sh <path> --artifact <artifact-id> --expected-version <version-id>
```

After your own publish, `artifact.currentVersionId` is the version id. In a later session, read it from the MCP tool `artifact_get`. The result's `links.review` is the new link.

## Read and answer comments

When the person says they left comments, or before you publish a revision, list the threads over MCP. The `artifact-server` MCP tools exist when the host registers the server.

1. `comment_list` with `artifactId` and `dispatched: "include"`.
2. Act on each thread. Answer with `comment_reply` (`artifactId`, `threadId`, `body`, and an `idempotencyKey` of at least 16 characters). Call `comment_resolve` (`artifactId`, `threadId`, `resolved: true`) once the change is published.

## Make an artifact public

Only when the person asks. Call `artifact_get` for `artifact.currentVersionId`, then `artifact_set_visibility` with `accessSetting: "public_link"`, that id as `expectedCurrentVersionId`, and a fresh `idempotencyKey`. Return `links.artifact` from the result. It opens without sign-in and follows the newest version. `accessSetting: "account_required"` makes the artifact private again.

## Host configuration

When the person asks to configure publishing, or the result is `unconfigured`, `configuration`, or `dependency`, read [HOST-CONFIGURATION.md](HOST-CONFIGURATION.md).
