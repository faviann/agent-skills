#!/usr/bin/env bash
# SessionStart hook for the herdr-playbook skill (matcher: startup|resume|clear|compact).
# Inside herdr (HERDR_ENV=1) it prints a short primer that Claude Code adds to the session context.
# Elsewhere it prints nothing. It never calls herdr, the socket, or the network, and always exits 0.
trap '' PIPE
[ "${HERDR_ENV:-}" = 1 ] || exit 0

pane=${HERDR_PANE_ID//[^A-Za-z0-9:_.-]/}
tab=${HERDR_TAB_ID//[^A-Za-z0-9:_.-]/}
workspace=${HERDR_WORKSPACE_ID//[^A-Za-z0-9:_.-]/}
pane=${pane:0:32} tab=${tab:0:32} workspace=${workspace:0:32}

printf '%s\n' \
  "herdr: this Claude Code session runs in herdr pane ${pane:-unknown} (tab ${tab:-unknown}, workspace ${workspace:-unknown}), the user's live view of this conversation. Never send input to that pane or close it." \
  "Use herdr on your own initiative and say what you did: panes for servers, tests, and logs the user would watch; cheap helper agents in visible panes for parallel or grunt work; worktrees for parallel branches; reading the user's other panes and agents instead of asking for pastes; a herd check before destructive git; a review pane when a change needs the user's eyes; deferred work parked on their tsk board; reaching the user on desktop and phone. When a herdr feature the user hasn't used fits, point it out." \
  "Before your first substantive action, invoke the herdr-playbook skill with the Skill tool unless it is already loaded in this session: it catalogs every herdr capability with its verified command." \
  2>/dev/null
exit 0
