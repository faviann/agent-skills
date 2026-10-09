# Plugins and Collie

## The plugin model

A herdr plugin is a directory with a `herdr-plugin.toml` manifest. It can declare:

- `[[build]]` steps, which run at install.
- `[[startup]]` commands, which run after restore or handoff.
- `[[actions]]`, invoked by ID.
- `[[events]]` hooks on herdr events.
- `[[panes]]`, each with a placement of `overlay`, `popup`, `split`, `tab`, or `zoomed`.
- `[[link_handlers]]`, which map a URL regex to an action.

Commands are argv arrays that run as the user, unsandboxed, with `HERDR_SOCKET_PATH`, `HERDR_BIN_PATH`, and `HERDR_PLUGIN_*` set. Plugins are global: every session sees the same set.

## Runtime discovery

Verified with a scratch plugin in an isolated session:

```bash
herdr plugin list --json | jq -c '.result.plugins[] | {plugin_id, enabled, description, actions: [.actions[].id], panes: [.panes[]?.id], root: .plugin_root}'
herdr plugin action list --plugin <id>                  # action_id, title, contexts
herdr plugin action invoke <action> --plugin <id>       # runs it; the response echoes the action and its context
herdr plugin log list --plugin <id> --limit 1           # status, exit_code, stdout, stderr of recent runs
herdr plugin pane open --plugin <id> --entrypoint <pane> --placement split --target-pane <pane_id> --direction right --no-focus
herdr plugin pane open --plugin <id> --entrypoint <pane> --placement tab --workspace "$HERDR_WORKSPACE_ID" --no-focus
herdr plugin pane close <pane_id>
```

- Plugin panes take the manifest pane's title as their label.
- `split` and `zoomed` placements need `--target-pane` without `--workspace`.
- `popup` and `overlay` are modal and take all input, so ask before opening one.
- Read an action's manifest command before invoking it, since it runs as the user. Actions named like status, url, version, or list are usually read-only. Anything that starts, stops, updates, installs, or rewrites keys is ask-first.
- `plugin config-dir <id>` prints a path only. Collie's directory holds a `.env` with secrets: don't read it.
- `install`, `uninstall`, `link`, `unlink`, `enable`, and `disable` change global state for every session: suggest them, and let the user decide.

## Collie

Collie (`herdr.collie`) is the user's phone view of herdr. Its bridge runs as `collie.service` over Tailscale and survives herdr restarts. The user's runbook is `~/repos/dotfiles/main/docs/runbooks/collie.md`.

### What the phone shows

Every pane in every herdr session under the user's home appears, and the phone can read and type into each one. A pane's name comes from, in order:

1. the herdr pane label (`pane rename`)
2. Claude's `/rename` name
3. the tab label, when the tab holds only that pane
4. the terminal title
5. the agent kind, or `shell`

So label what you create. Labelling someone else's pane overrides their name on every phone screen. Pins and hidden workspaces are stored per device by workspace name, so renaming a workspace drops them.

### What pushes, and when

- **Agent state.** Collie pushes when an agent's herdr state becomes `blocked` ("needs you", on by default) or `done` (on here). It waits 30 seconds first, so a dialog answered quickly never pushes.
  - **Shared slot.** All agents share one notification slot per session, rewritten as states change and withdrawn when they resolve.
  - **Content.** The title names the agent; the body names the workspace and tab, not the question.
- **Custom push.** `<plugin_root>/bin/collie push-test "<title>" "<body>" [pane_id]` sends a custom push to every subscribed device. Tapping it opens that pane. `push test` is the same verb.
  - It ignores snooze.
  - It rides the same collapse topic as the herd slot (`collie-herd`, 6 h TTL), so an offline phone keeps only the latest of the two.
  - It exits non-zero with a message when push is disabled (no VAPID keys) or no device is subscribed.
  - Its output can include per-endpoint errors; discard it.
- **Resolving the binary.** Resolve `plugin_root` through `herdr plugin list --plugin herdr.collie --json` rather than a hard-coded path; `collie` is not on PATH.
- **Checking without sending.** `bin/collie push list` reads the subscription store without sending. It prints the service host, date, user agent, and endpoint tail for each device. Report the count.
- **The plugin action.** The `push-test` plugin action takes no arguments and only sends a fixed test message.
- **What never reaches the phone.** `herdr notification show` stays on attached terminals.

### Actions

| Action | Class |
| --- | --- |
| `status`, `url`, `version` | Read: invoke, then `herdr plugin log list --plugin herdr.collie --limit 1` for the text |
| `start`, `stop`, `restart` | Ask. `stop` disables the service, so it stays off after reboot |
| `update`, `update-major`, `uninstall` | Ask. `update-major` treats the flag as consent |
| `push-test` (fixed test message), `push-keys` | Ask: test pings need consent. `push-keys` rewrites the signing keys and breaks every phone subscription |

### Effects of your herdr work on the phone

- New panes and tabs appear within seconds. Agents in them push on `blocked` and `done` like any other.
- When no desktop client is attached, splits stay narrow and the phone shows them squashed. Prefer a tab then.
- While herdr is down, the phone shows the session as unreachable and withdraws its notifications. Collie reconnects on its own.

## File Annotator

`jonasbaeumer.file-annotator` exposes the `annotator` MCP server. Drive it through its tools, whose definitions are in your tool list, not through its pane entrypoint. *(Tool names from `tools/list`; verdict shape from the plugin's docs.)*

- The verdict is `approve`, `request_changes`, `reject`, or `cancelled`, with a `summary` and `annotations` of `{file, lines, side, tag, comment}`. Tags are `fix`, `verify`, `question`, or `nit`.
- `goto` (file, line) and `focus` (file, regions) point the user at specific lines while you narrate.
