# Settings worth suggesting

Mention one in a sentence when it fits the moment, and offer to apply it. Editing `~/.config/herdr/config.toml` needs a yes; `herdr server reload-config` *(help)* then applies it without restarting panes. Read the current file first, so you suggest only what is unset.

- `[ui] agent_panel_sort = "priority"` lists blocked and done agents first.
- `[keys] next_agent`, `previous_agent`, and `focus_agent = "prefix+alt+1..9"` jump between agents. All are unbound by default.
- `[[keys.command]]` with `type = "popup"` or `"pane"` binds a key to lazygit, a test runner, or a log view.
- `[ui.toast] delivery` (`herdr`, `terminal`, `system`) and `[ui.sound.agents]` control how herdr alerts, and for which agents.
- `[ui] show_agent_labels_on_pane_borders = true`, and `mobile_width_threshold` for phone terminals.
- `[worktrees] directory = "~/worktrees"` brings herdr's own worktree default close to the user's rule.
- `[experimental] pane_history = true` keeps pane output across server restarts. It can hold secrets.
- Keys: the prefix is `ctrl+b`. `prefix+?` is help, `prefix+g` goto, `prefix+w` the workspace picker, `prefix+o` jumps to a notification's target, `prefix+z` zooms. TUI toggles persist per client in `~/.local/state/herdr/client-shell/`, and a saved toggle there overrides `config.toml`.
- `herdr integration status` shows agents that won't resume after a restart. The user's `chezmoi apply` reinstalls integrations.
- Saved SSH machines: when the user mentions work on another box, suggest `herdr machine add <ssh-target>`; it's theirs to run.
