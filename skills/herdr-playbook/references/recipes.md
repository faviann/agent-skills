# Long herdr recipes

Verified against herdr 0.9.3 in an isolated named session, except where marked. The everyday recipes are in [SKILL.md](../SKILL.md).

Contents: [Socket API](#socket-api) · [Dev environment in one call](#dev-environment-in-one-call) · [Stream events](#stream-events) · [Isolated session](#isolated-session) · [Remote machines](#remote-machines) · [Nested Claude runs](#nested-claude-runs) · [Other vendors](#other-vendors) · [Sessions](#sessions)

## Socket API

The socket at `$HERDR_SOCKET_PATH` speaks newline-delimited JSON, one request per connection: `{"id":"<string>","method":"...","params":{...}}`. A reply carries `result` or `error`. A one-line client:

```bash
herdr_api() { python3 -c 'import os,socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(os.environ["HERDR_SOCKET_PATH"]); s.sendall(sys.argv[1].encode()+b"\n"); print(s.makefile().readline(), end="")' "$1"; }
herdr_api '{"id":"1","method":"layout.export","params":{"tab_id":"'"$HERDR_TAB_ID"'"}}'
```

- Methods missing from the CLI: `layout.apply`, `layout.export`, `layout.set_split_ratio`, `events.subscribe`, `events.wait`, `pane.scroll`, `pane.clear`, `pane.selection.read`, `pane.link.resolve`, `workspace.move`, `tab.move`, and `agent.view.set`/`agent.view.clear`.
- Internal to the TUI, not for you: `command.invoke`, `client_shell.*`, `popup.close`, and `client.window_title.*`.
- Never send `server.stop` or `server.live_handoff`. They are the pane-killing operations under another name.

## Dev environment in one call

`layout.apply` builds a whole tab of labelled panes running commands. A pane whose command exits closes, and its tab closes once empty. Chain `exec bash` so each pane keeps a shell and its output:

```bash
req=$(jq -cn --arg ws "$HERDR_WORKSPACE_ID" --arg cwd "$PWD" '{id:"1", method:"layout.apply", params:{
  workspace_id:$ws, tab_label:"dev", focus:false,
  root:{type:"split", direction:"right", ratio:0.5,
    first:{type:"pane", label:"server", cwd:$cwd, command:["bash","-lc","npm run dev; exec bash"]},
    second:{type:"split", direction:"down", ratio:0.5,
      first:{type:"pane", label:"tests", cwd:$cwd, command:["bash","-lc","npm run test:watch; exec bash"]},
      second:{type:"pane", label:"logs", cwd:$cwd, command:["bash","-lc","tail -F logs/api.log; exec bash"]}}}}}')
herdr_api "$req" | jq -c '.result.layout | {tab_id, panes: [.. | objects | select(.type? == "pane") | {label, pane_id}]}'
```

The CLI sequence in SKILL.md does the same with commands you can watch step by step. Prefer it unless you want the whole tab in one call. Passing `tab_id` replaces that tab and kills its processes; that is ask-first.

## Stream events

`events.subscribe` streams events until you close the connection. Run it in background Bash with a `timeout`:

```bash
timeout 1800 python3 -c '
import json, os, socket, sys
s = socket.socket(socket.AF_UNIX); s.connect(os.environ["HERDR_SOCKET_PATH"])
s.sendall(json.dumps({"id": "sub", "method": "events.subscribe", "params": {"subscriptions": json.loads(sys.argv[1])}}).encode() + b"\n")
for line in s.makefile():
    print(line, end="", flush=True)
' '[{"type":"pane.exited"},{"type":"pane.agent_status_changed","pane_id":"<pane_id>"}]'
```

- **Acknowledgement and events.** The first line is `{"result":{"type":"subscription_started"}}`. Events then arrive as `{"event":"pane_exited","data":{...}}`.
- **Event types:**
  - `workspace.*`, `worktree.created|opened|removed`, `tab.*`
  - `pane.created|closed|updated|focused|moved|exited|agent_detected`
  - `pane.agent_status_changed` and `pane.scroll_changed`, both of which need `pane_id`
  - `pane.output_matched`, which needs `pane_id`, `source` (`recent_unwrapped`), and `match:{type:"regex"|"substring", value}`
  - `layout.updated`
- **No exit code.** `pane_exited` doesn't carry one.
- **Strict subscriptions.** One unknown type or missing pane rejects the whole subscription.
- **Slow readers.** A reader that falls behind gets `events_lost`: resubscribe, then read `herdr api snapshot`.

## Isolated session

Use one to try something that must not touch the user's session, such as a destructive command, a plugin, or a layout experiment.

- **Scratch `HOME`.** It keeps the session out of Collie, which mirrors every session under the real home to the phone. It also keeps the plugin registry separate.
- **Short path.** A socket path longer than 108 bytes fails with `sun_path`, so keep the scratch home short.

```bash
scratch=$HOME/.cache/hx; mkdir -p "$scratch"
scrub=(env -u HERDR_ENV -u HERDR_PANE_ID -u HERDR_TAB_ID -u HERDR_WORKSPACE_ID -u HERDR_SOCKET_PATH -u HERDR_BIN_PATH HOME="$scratch")
"${scrub[@]}" setsid nohup herdr --session hx server </dev/null >"$scratch/server.log" 2>&1 &
sleep 2
"${scrub[@]}" herdr --session hx workspace list | jq '.result.workspaces | length'   # 0 proves the target
"${scrub[@]}" herdr --session hx workspace create --cwd "$PWD" --label scratch --no-focus
# Agents need the real home to log in. Give their pane HOME explicitly:
"${scrub[@]}" herdr --session hx pane split <pane_id> --direction down --cwd "$PWD" --env HOME="$HOME" --no-focus
# ... experiment, always through "${scrub[@]}" herdr --session hx ...
"${scrub[@]}" herdr session stop hx && "${scrub[@]}" herdr session delete hx && rm -rf "$scratch"
```

- **Defense in depth.** The scrubbed environment means a dropped `--session` can't hit the user's session: `--session` beats an inherited `HERDR_SOCKET_PATH`, and the scrub covers the rest.
- **Empty start.** A fresh session has no workspace. Create one before `tab create`.
- **`pane report-agent`** fakes an agent and its state in a scratch pane (`--source test --agent codex --state working|blocked|idle`), for testing herd logic.

## Remote machines

*(help only; check `herdr machine list --json` for saved machines)*

```bash
herdr machine list --json
herdr machine status <label> --json
herdr --machine <label-or-id> agent list
herdr --machine <label-or-id> agent prompt <remote-name> "Reply with your current status." --wait --timeout 120000
```

- **Same prefix throughout.** Use the same `--machine` prefix for discovery and every later command, with IDs discovered there. `--current` doesn't apply, and `--session` and `--remote` don't combine with `--machine`.
- **Paths.** Remote worktree paths must be absolute or start with `~/`.
- **Failures.** A connection failure doesn't prove a mutation failed: inspect before you retry. `machine reconnect` needs the user's SSH authentication.
- **Adding a machine.** `herdr machine add <ssh-target>` installs and starts herdr on the remote. Suggest it; the user runs it.

## Nested Claude runs

A `claude -p` started from your pane inherits `HERDR_*`. herdr's Claude SessionStart hook (`~/.claude/hooks/herdr-agent-state.sh`) then reports the nested session against your pane, which re-points the pane's resume record. Start nested runs with:

```bash
env -u HERDR_ENV -u HERDR_PANE_ID -u HERDR_TAB_ID -u HERDR_WORKSPACE_ID -u HERDR_SOCKET_PATH claude -p "..."
```

Claude Code subagents run no SessionStart hook, so they are unaffected. A helper started with `herdr agent start` gets its own pane, so it is unaffected too.

## Other vendors

Helpers of `--kind codex|opencode|pi|omp` all have herdr integrations here. Their defaults are premium models; cheaper variants *(help)*:

- Codex: `-- -m <model>` or `-- -c model_reasoning_effort=low`
- OpenCode: `-- -m provider/model`
- Pi and OMP: `-- --model <pattern> --thinking low`

Interrupt your own agent with `herdr agent send-keys <name> esc` or `ctrl+c`; rename it with `herdr agent rename <name> <new>`.

## Sessions

- `herdr session list --json` lists sessions. Collie shows every session under the user's home on the phone, named ones included.
- `herdr api schema --json | jq '.schemas.request.oneOf[].properties.method.const'` lists every socket method.
- `herdr --skill` is upstream's reference for mechanics.
