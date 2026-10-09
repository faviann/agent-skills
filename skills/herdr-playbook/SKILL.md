---
name: herdr-playbook
description: Makes Claude fluent in herdr, the terminal workspace manager this session runs in (HERDR_ENV=1), so it brings herdr into the work unprompted. It lists every capability with when to use it and its verified command. Use at session start when the herdr hook asks; whenever the user mentions herdr, panes, tabs, workspaces, worktrees, notifications, or their other agents; and whenever work would go better in a visible pane, with cheap helper agents in parallel, on a parallel worktree, with a herd check before destructive git, or by reaching the user on desktop or phone.
---

# herdr playbook

herdr runs every terminal the user sees. This session sits in one of its panes, and the user watches all of them on the desktop and, through the Collie plugin, on their phone. Treat herdr as your workbench:

- Put work the user would want to watch in panes.
- Hand parallel or grunt work to cheap agents in panes they can watch.
- Keep an eye on their other agents.
- Reach them where they are.
- Be their guide: when a feature they haven't used fits the moment, point it out.

Verified against herdr 0.9.3 on 2026-10-08. Entries marked *(help)* were checked against help output or the API schema only. If `herdr --version` differs, re-check syntax with `herdr <group>` (a bare group prints its help). `herdr --skill` is upstream's reference for mechanics.

Run herdr commands only when `test "${HERDR_ENV:-}" = 1` passes; otherwise use Claude Code's own tools.

## How to act

- **Do it, then say what you did,** when the action is visible, cheap, and reversible: a pane, a tab, a label, a cheap helper agent, a worktree, a notification, any read.
- **Ask first** for:
  - expensive runs: premium models, more than three agents, unattended runs past about 30 minutes;
  - irreversible actions: force-push, `--force` removals, deleting branches or anyone's work;
  - changes to herdr config, plugins, integrations, or machines. Suggesting these is the guide role; applying them needs a yes.
- **Hard rules:**
  - `$HERDR_PANE_ID` is the user's view of this conversation. Send it no input (`pane run`, `send-text`, `send-keys`) and never close it. Subagents inherit it, so `--current` in a subagent targets the main session's pane.
  - Touch only what you created; read anything. Pass `--no-focus` on every create, split, and move. Parse IDs from JSON responses.
  - Never run `herdr server stop`, `herdr update`, or `systemctl --user stop|restart herdr.service`, and never kill herdr, from inside herdr. Each one ends every pane process, the user's other agents included.
  - Approval, permission, and trust dialogs belong to the user, even in agents you started.
  - The user's agents run without approval gates (Codex `approval_policy = "never"`, Claude `bypassPermissions`, OpenCode `allow`). Scope every prompt you send: the task, the paths, read-only or which files to edit, and how to report.

## Show the user things

A pane is watchable live, scrollable, takes the user's keystrokes, and outlives your turn and session. Background Bash re-invokes you when a job exits, but nobody else sees it.

- Use background Bash for results only you need.
- Use a pane for anything the user would watch.
- Use both by running the job in a pane and its `wait-output` in background Bash.

**Sibling pane.** Use it for dev servers, watchers, log tails, and long builds or test runs. Start it unprompted and say where it is.

```bash
herdr pane layout --pane "$HERDR_PANE_ID" | jq -c '.result.layout.panes[] | select(.pane_id == env.HERDR_PANE_ID) | .rect'
pane=$(herdr pane split --current --direction right --cwd "$PWD" --no-focus | jq -r .result.pane.pane_id)
herdr pane rename "$pane" dev-server
herdr pane run "$pane" "npm run dev"
herdr pane wait-output "$pane" --regex 'ready in|Local:|[Ee]rror' --timeout 60000 | jq -r .result.matched_line
```

- **Direction.** Split `right` when the pane is at least 160 columns wide and `down` when it is at least 50 rows tall. Otherwise use a tab, so you don't squash the user's view: a phone, a narrow window, or the 120x40 size herdr uses when no desktop is attached.
- **Pattern.** `wait-output` searches what is already on screen, including the command you typed, so the pattern must not appear in that command. With no match it exits 1 with a `timeout` error.

**Environment tab.** Use it for "set me up", a fresh clone, or whenever a server, tests, and logs belong together.

```bash
dev=$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" --label dev --no-focus | jq -r .result.root_pane.pane_id)
herdr pane rename "$dev" server && herdr pane run "$dev" "npm run dev"
tests=$(herdr pane split "$dev" --direction right --cwd "$PWD" --no-focus | jq -r .result.pane.pane_id)
herdr pane rename "$tests" tests && herdr pane run "$tests" "npm run test:watch"
logs=$(herdr pane split "$tests" --direction down --cwd "$PWD" --no-focus | jq -r .result.pane.pane_id)
herdr pane rename "$logs" logs && herdr pane run "$logs" "tail -F logs/api.log"
```

Always pass `--workspace`. Without it, the tab lands in whatever workspace the user has focused.

**More pane moves:**

- **One-shot job with an exit code** (tests or a build the user may watch). End the command with a fresh marker, since old output matches too:
  `tag=hp-$(date +%s); herdr pane run "$pane" "make test; echo $tag exit=\$?"; herdr pane wait-output "$pane" --regex "$tag exit=[0-9]+" --timeout 1800000`.
  Run waits longer than about 9 minutes in background Bash.
- **Read a pane** on demand: `herdr pane read <id> --source recent-unwrapped --lines 120` returns plain text. On agent panes start with `--source visible`: a large `--lines` makes herdr scroll an idle agent's history where the user sees it.
- **Find what the user points at** ("my other pane", "the server output", "that error") instead of asking for a paste. Run `herdr pane list --workspace "$HERDR_WORKSPACE_ID" | jq -r '.result.panes[] | [.pane_id, (.label // "-"), (.agent // "-"), .agent_status, (.terminal_title_stripped // "-"), (.foreground_cwd // .cwd)] | @tsv'` (drop `--workspace` to search everywhere), check `herdr pane process-info --pane <id>`, then read the pane.
- **Label every pane you create:** `herdr pane rename <id> <label>`. The label names the pane in the sidebar and on the phone.
- **Stop, move, or close your panes:**
  - `herdr pane send-keys <id> ctrl+c` stops what's running.
  - `herdr pane move <id> --new-tab --label <label> --no-focus` moves it out of the way.
  - `herdr pane close <id>` closes it; closing a tab's last pane closes the tab.
- **Zoom a pane** for a phone-sized screen with `herdr pane zoom <id> --on|--off`. Zoom also focuses the pane, so offer it rather than doing it.
- **Take the user there** only when they ask: `herdr agent focus <name>` *(help)*, `herdr tab focus <id>`, `herdr workspace focus <id>`.

**Ask for the user's review.** The `annotator` MCP server, from the File Annotator plugin, opens a diff review pane beside you. The user marks lines from the desktop or phone, and you get their verdict back as JSON. Use it when you finish a change worth a human look, or when the user says they want to review first. Skip it for trivial edits.

- **`mcp__annotator__show_changes`** opens the review without blocking. Pass `note` to say what to check, and `baseline` to set the diff base. Keep working, then call `mcp__annotator__collect_review` (`wait_seconds` 0–120) when the server nudges your pane.
- **`mcp__annotator__review_changes`** blocks until the verdict arrives. Use it only when you can't continue without the answer. An unanswered review returns `cancelled` after 30 minutes.
- **The verdict** is `approve`, `request_changes`, `reject`, or `cancelled`. It comes with a `summary` and `annotations` of `{file, lines, side, tag, comment}`, where the tag is `fix`, `verify`, `question`, or `nit`. Apply the `fix` annotations, answer the `question` ones, and say which you did.
- **`goto`** (file, line) and **`focus`** (file, regions) point the user at specific lines.
- If the tools are missing, check `claude mcp get annotator`. MCP servers load at session start. *(Tool names from `tools/list`; verdict shape from the plugin's docs. Not yet run end to end.)*

## Run and delegate work in parallel

Helpers in visible panes run while you keep working, and the user can watch them, steer them, and keep talking to them after you finish.

**Cheap helpers.** Use them for parallel research, review, triage, or grunt edits. Start up to three Claude Sonnet agents without asking and say what you started:

```bash
pane=$(herdr pane split --current --direction down --cwd "$PWD" --no-focus | jq -r .result.pane.pane_id)
herdr pane rename "$pane" scan-payments
herdr agent start scan-payments --kind claude --pane "$pane" -- --model sonnet
herdr agent prompt scan-payments "Read-only: <task>. Read only services/payments/. Report findings as file:line, one line each." --wait --timeout 540000
herdr agent read scan-payments --source recent-unwrapped --lines 150
```

- **Several helpers** go in one tab (`tab create`, then `pane split` from its root pane) rather than in repeated splits of your own pane.
- **Run each `prompt --wait` in background Bash** so the helpers work in parallel and you're re-invoked as each one finishes.
- **Other vendors** for a second opinion or their strengths: `--kind codex|opencode|pi|omp`, all with herdr integrations here. Their defaults are premium models, so offer unless the user asked. Cheaper variants *(help)*:
  - Codex: `-- -m <model>` or `-- -c model_reasoning_effort=low`
  - OpenCode: `-- -m provider/model`
  - Pi and OMP: `-- --model <pattern> --thinking low`
- **Names** match `[a-z][a-z0-9_-]{0,31}` and must be unique among live agents; check `herdr agent list`.
- **`agent start`** returns once the agent is ready (default 30 s; `--timeout` up to 300000). A `timeout` or `agent_not_ready` usually means a login or folder-trust dialog: read the pane and hand it to the user.
- **`agent prompt --wait`** returns at the next settled state. A `timeout` doesn't prove the prompt was lost; read before resending.
- **`agent read`** returns `agent_not_idle` while the agent works. For long answers, ask the agent to write a file under /tmp and reply with the path.
- **Interrupt your own agent** with `herdr agent send-keys <name> esc` or `ctrl+c`; rename it with `herdr agent rename <name> <new>`.
- **Use a Claude subagent instead** (Agent tool, or the codex plugin) when you need the answer in your context fast and nobody needs to watch.
- **Clean up:** close helper panes once you've collected their output, unless the user may want to keep talking to them.

## Watch the herd

- **See every agent and its state:**
  `herdr agent list | jq -r '.result.agents[] | [.pane_id, .agent, .agent_status, (.name // "-"), (.foreground_cwd // .cwd)] | @tsv'`.
  `herdr api snapshot` returns workspaces, tabs, panes, agents, and layouts in one call. `idle` and `done` both mean ready for input; `done` means nobody has looked yet.
- **Herd check** before checkout, switch, rebase, reset, stash, clean, branch deletion, force-push, or worktree removal. Run this skill's `scripts/herd-check.sh [repo-path]` by its full path.
  - `same-checkout`: don't change that checkout under the agent. Do the work in a worktree (below) and say so, or ask.
  - `other-worktree`: leave that agent's branch and worktree alone.
- **Blocked agents:** when any check shows one, tell the user which pane and what it waits for (`herdr agent read <pane_id> --source visible`). The answer is theirs to give.
- **Glance at the herd** when you finish a long task or the user comes back. Mention agents that are `blocked`, or `done` and unseen.
- **"Tell me when it's done"** for any agent: run `herdr agent wait <pane_id> --timeout 3600000` in background Bash, then read and report. Waiting and reading are read-only.
- **Explain a state:** `herdr agent explain <target>` shows the detection rule and evidence behind an `unknown` or stuck state.
- **Version skew:** `herdr status` shows client and server versions when a command fails with an unknown method.

## Parallel branches

- **Worktree.** Create one whenever work should proceed on two branches at once (a variant to compare, a fix while you continue, a helper that edits code), and say so. From inside the repository, run this skill's `scripts/new-worktree.sh <branch> [base-ref]` by its full path.
  - It runs `herdr worktree create` at the user's `~/worktrees/<repo>/<branch-with-slashes-as-dashes>`, with `--no-focus` and your HEAD as the base. It works from the main worktree, because herdr refuses a linked one.
  - Start the helper in `.result.root_pane.pane_id`.
- **List and open:** `herdr worktree list --cwd "$PWD"` shows checkouts and their workspaces; `herdr worktree open --path <path> --no-focus` opens an existing one.
- **Remove:** `herdr worktree remove --workspace <id>` deletes the checkout and closes its workspace and panes, keeps the branch, and refuses a dirty tree. `--force` is ask-first.

## Track work on the user's board

`tsk` (CLI on PATH, v0.11.6) is the user's task board. A board belongs to the repository's project, or to the user's desk outside Git. Run `tsk guide` before your first tsk command in a session: it holds the workflow and exit codes. Read with `--json`; the human output is for the user.

- **Park what the user defers** ("later", "after this", a follow-up you spotted): `tsk add -t "<title>" -n "<context>"`. Say what you parked.
- **What's next** at session start or when asked: `tsk list --ready --json`. For blocked and review items, use `tsk list --json` and filter on `status`.
- **Work a task:**
  - Start with `tsk status T12 started`, and tick its steps as you go.
  - Hand it back with `tsk status T12 review`, plus one line on what to check. `done` is the user's call.
- **Show the board:** run `tsk` in a labeled pane. The user edits it live; re-read it with `tsk list --json`.

## Reach the user on desktop and phone

- **Your own state covers your own work.** Ending your turn sets `done`; asking a question sets `blocked`. herdr sounds and toasts on the desktop, and Collie pushes "claude is done" or "claude needs you" to the phone after 30 seconds. When the news is your own result, finish your turn and make its first line readable on a phone.
- **Phone push for everything else.** Use it for events your own state won't announce: a deploy finishing or a background pane's tests failing while you keep working, or another agent you watched finishing. Send one push per event:
  ```bash
  root=$(herdr plugin list --plugin herdr.collie --json | jq -r '.result.plugins[].plugin_root')
  "$root/bin/collie" push-test "<title>" "<body>" "<pane_id>" >/dev/null 2>&1 || echo "push unavailable"
  ```
  - The push reaches every subscribed device and ignores the user's snooze. Tapping it opens `<pane_id>`.
  - It shares Collie's herd notification slot, so a later herd update can replace it.
  - It exits non-zero when push is off or no device is subscribed.
  - Discard its output, which can carry endpoint URLs.
  - `"$root/bin/collie" push list` counts subscribed devices without sending anything.
  - The `push-test` plugin action takes no arguments and sends only a fixed test message.
  - *(Checked against the code and `push list`; no test push was sent.)*
- **Desktop heads-up mid-turn,** when the user asked to hear about an event before you finish:
  `herdr notification show "<title>" --body "<detail>" --sound done|request | jq -c .result`.
  - It reaches attached terminals only, never the phone.
  - `"shown": false` (`no_foreground_client`, `rate_limited`) means nobody saw it.
  - Send one per event.

## Other machines and sessions

- **Saved SSH machines** *(help; none saved yet)*: `herdr machine list --json`, then `herdr --machine <label> agent list`. Run every later `pane`, `agent`, and `worktree` command with the same prefix, using IDs discovered there. When the user mentions work on another box, suggest `herdr machine add`; it's theirs to run.
- **Isolated experiments** belong in a named session; see [recipes](references/recipes.md#isolated-session). Never target `default`.
- **Sessions:** `herdr session list --json` lists them. Collie shows every session under the user's home on the phone, named ones included.

## React to events through the API

The CLI covers most needs. The socket at `$HERDR_SOCKET_PATH` (newline-delimited JSON, one request per connection) adds:

- **`events.subscribe`** streams `pane.exited`, `pane.agent_status_changed` (needs `pane_id`), `pane.output_matched`, and workspace and tab events to a background watcher.
- **`layout.apply`** builds a labelled multi-pane tab running commands in one call; **`layout.export`** reads a tab's split tree.
- **`events.wait`** only matches agent status in 0.9.3; use `herdr agent wait`.

Clients and recipes are in [recipes](references/recipes.md#socket-api). `herdr api schema --json | jq '.schemas.request.oneOf[].properties.method.const'` lists every method.

## Plugins

Discover what's installed at runtime; new plugins become usable without editing this skill:

```bash
herdr plugin list --json | jq -c '.result.plugins[] | {plugin_id, enabled, description, actions: [.actions[].id], panes: [.panes[]?.id]}'
herdr plugin action list --plugin <id>
herdr plugin action invoke <action> --plugin <id>      # its output: herdr plugin log list --plugin <id> --limit 1
herdr plugin pane open --plugin <id> --entrypoint <pane> --placement split --target-pane <pane_id> --direction right --no-focus
```

- **Actions:** invoke read-only ones (status, url, version, list) freely. Actions that change or restart something are ask-first.
- **Plugin panes:** for `--placement tab`, pass `--workspace` instead of `--target-pane`; passing both fails. Popups and overlays are modal: ask first.
- **Install, enable, disable, link:** suggest them; the user decides.
- **Collie** is installed and is the user's phone view. Read [plugins](references/plugins.md) before touching it. Its `status`, `url`, and `version` actions are safe, and its CLI's `push-test` is the phone channel described under "Reach the user".
- **File Annotator** (`jonasbaeumer.file-annotator`) is installed. Drive it through its `annotator` MCP tools (see "Ask for the user's review"), not its pane entrypoint.

## Settings worth suggesting

You're the guide. When one of these fits the moment, mention it in a sentence and offer to apply it. Editing `~/.config/herdr/config.toml` needs a yes; `herdr server reload-config` *(help)* then applies it without restarting panes.

- `[ui] agent_panel_sort = "priority"` lists blocked and done agents first.
- `[keys] next_agent`, `previous_agent`, and `focus_agent = "prefix+alt+1..9"` jump between agents. All are unbound by default.
- `[[keys.command]]` with `type = "popup"` or `"pane"` binds a key to lazygit, a test runner, or a log view.
- `[ui.toast] delivery` (`herdr`, `terminal`, `system`) and `[ui.sound.agents]` control how herdr alerts, and for which agents.
- `[ui] show_agent_labels_on_pane_borders = true`, and `mobile_width_threshold` for phone terminals.
- `[worktrees] directory = "~/worktrees"` brings herdr's own worktree default close to the user's rule.
- `[experimental] pane_history = true` keeps pane output across server restarts. It can hold secrets.
- Keys: the prefix is `ctrl+b`. `prefix+?` is help, `prefix+g` goto, `prefix+w` the workspace picker, `prefix+o` jumps to a notification's target, `prefix+z` zooms. TUI toggles persist per client in `~/.local/state/herdr/client-shell/`.
- `herdr integration status` shows agents that won't resume after a restart. The user's `chezmoi apply` reinstalls integrations.

## Before you finish

Every pane, tab, workspace, worktree, and agent you created is either closed or listed in your final message with its label, ID, and the reason it stays open.

## References

- [references/recipes.md](references/recipes.md): socket clients, `layout.apply`, event streams, isolated sessions, remote machines, nested Claude runs.
- [references/gotchas.md](references/gotchas.md): rare traps, by area.
- [references/plugins.md](references/plugins.md): the plugin model and Collie.
