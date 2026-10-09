# herdr gotchas

Rare traps behind the entries in [SKILL.md](../SKILL.md), grouped by area. Each one was observed on herdr 0.9.3 unless marked.

## Targeting and focus

- An omitted pane target can resolve to whatever pane another client has focused: the user's desktop, or another agent. Pass `--current`, an ID, or a name.
- `tab create` without `--workspace` lands in the focused workspace, even when your own `HERDR_WORKSPACE_ID` says otherwise.
- `pane zoom --on` also focuses the zoomed pane.
- A Claude Code subagent inherits `HERDR_PANE_ID`, so its `--current` is the main session's pane.
- `--session <name>` beats an inherited `HERDR_SOCKET_PATH`; `HERDR_SESSION` loses to it.
- A `pane move` into another workspace assigns a new pane ID. Read `.result.move_result.pane.pane_id`.

## Waiting and reading

- `pane wait-output` matches what is already on screen, including the command line you just typed and old runs. Keep the pattern out of the command, and use a fresh marker per run.
- `wait-output` matches one line at a time with Rust regex syntax. A timeout prints a JSON error on stderr and exits 1; without `--timeout` it waits forever.
- A large `--lines` on an idle full-screen agent (Claude Code, OpenCode) makes herdr scroll that agent's history, where the user sees it. It is also slow: about 14 s for 400 lines, per Collie's notes.
- `agent read` returns `agent_not_idle` while the agent works.
- Codex can sit at `unknown` after a response, so a wait for `idle` can time out.
- An agent stuck at a login or folder-trust dialog shows `unknown`, not `blocked`, so `agent start` times out instead of returning `agent_not_ready`. Its name isn't bound until startup succeeds.
- `agent start` needs the pane at an idle shell prompt.

## Layout and lifetime

- Closing a tab's last pane closes the tab, and a workspace's last tab closes the workspace. `tab close` ends every pane in the tab.
- With no desktop client attached, herdr lays out at 120x40. Splits made then stay narrow, and closing them doesn't widen the survivor; the phone shows them squashed.
- `layout.apply` command panes close when their command exits. Chain `; exec bash` to keep output.
- `pane_exited` carries no exit code, and `events.wait` only matches agent status in 0.9.3.
- After a server restart, panes come back as fresh shells in their saved directories. A directory that no longer exists shows as `restore_error`. Agents resume only through current integrations.

## Worktrees

- `worktree create` refuses a linked worktree as its source (`linked_worktree_source`). Pass the main worktree as `--cwd`: the first entry of `git worktree list`, which is `.bare` in a bare-repository layout. The branch then forks from that checkout's HEAD unless you pass `--base`. `scripts/new-worktree.sh` handles all of this.
- herdr's default location is `<worktrees.directory>/<repo>/<slug>`. The slug lowercases the branch and turns punctuation into dashes (`Agent/Fix_Login.v2` becomes `agent-fix-login-v2`), so it differs from the user's rule. Pass `--path`.
- `worktree remove` closes the worktree's workspace and every pane in it, keeps the branch, and refuses a dirty tree without `--force`.

## Notifications and output

- `notification show` exits 0 even when nothing was shown. Check `.result.shown` and `.result.reason`.
- Notifications are rate-limited to one per second. Titles are capped at 80 characters and bodies at 240.
- `pane run`, `pane send-keys`, and `pane report-metadata` print nothing on success. CLI server errors are JSON on stderr with exit 1; syntax errors exit 2.
- `pane report-metadata --title/--token` sets display metadata. It shows only where the user's `[ui.sidebar]` rows reference it.

## Plugins

- `plugin pane open --placement split|zoomed` needs `--target-pane`. Adding `--workspace` drops the target and the call fails. Use `--workspace` only with `--placement tab`.
- `plugin action invoke` runs plugin code as the user; its stdout lands in `plugin log list`.
- Plugins are global: linking or enabling one affects every session.

## Sessions and processes

- Collie mirrors every session under the real home to the phone, scratch sessions included. Agents finishing there can push.
- A nested `claude -p` re-points your pane's resume record unless you strip `HERDR_*`; see [recipes](recipes.md#nested-claude-runs).
- A herdr socket path longer than 108 bytes fails (`sun_path`).
- The TUI saves toggles such as `agent_panel_sort` and `sidebar_width` per client in `~/.local/state/herdr/client-shell/*.json`. A saved value explains a `config.toml` change that doesn't take effect.
- Launching the TUI from inside a pane is blocked unless `[experimental] allow_nested = true`. `herdr server` has no such check.
