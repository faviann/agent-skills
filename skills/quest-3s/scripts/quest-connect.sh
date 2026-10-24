#!/usr/bin/env bash
# Connect adb to the Quest 3S over Tailscale and print the serial to use.
#
# Tries the headset's tailnet IP directly. When this host's tailscaled runs with
# --tun=userspace-networking, ordinary sockets can't reach the tailnet, so it starts
# tailnet-forward.py (127.0.0.1:$QUEST_LOCAL_PORT -> headset:5555 via `tailscale nc`)
# in the background and connects adb to that instead. Safe to rerun.
#
# Usage: quest-connect.sh
# Env:   QUEST_HOST (default quest-3s-1), QUEST_LOCAL_PORT (default 5556)
# Stdout, last line: QUEST_SERIAL=<serial>
# Exit:  0 connected and authorized; 1 headset unreachable or adb off; 2 key not accepted;
#        3 missing tool.
set -uo pipefail

host=${QUEST_HOST:-quest-3s-1}
local_port=${QUEST_LOCAL_PORT:-5556}
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
log_dir=${XDG_CACHE_HOME:-$HOME/.cache}/quest-3s

say() { printf 'quest-connect: %s\n' "$1" >&2; }
for tool in adb tailscale python3; do
  command -v "$tool" >/dev/null || { say "missing $tool on PATH"; exit 3; }
done

ip=$(tailscale ip -4 "$host" 2>/dev/null) || { say "no tailnet peer named $host"; exit 1; }

tcp_open() { timeout 3 bash -c "</dev/tcp/$1/$2" 2>/dev/null; }

if tcp_open "$ip" 5555; then
  serial=$ip:5555
else
  probe=$(timeout 8 tailscale nc "$ip" 5555 </dev/null 2>&1)
  case $? in
    0) ;;
    124)
      say "$host ($ip) is offline: check it is powered on and Tailscale is running on it"
      exit 1 ;;
    *)
      if [[ $probe == *refused* ]]; then
        say "$host is up but adb is not listening on 5555: the headset rebooted."
        say "Ask the user to plug it into powerpc by USB; the keeper there re-enables network adb."
      else
        say "tailscale nc to $host:5555 failed: $probe"
      fi
      exit 1 ;;
  esac
  if ! tcp_open 127.0.0.1 "$local_port"; then
    mkdir -p "$log_dir"
    setsid nohup python3 "$here/tailnet-forward.py" "$ip" 5555 "$local_port" \
      >>"$log_dir/forward.log" 2>&1 </dev/null &
    for _ in 1 2 3 4 5 6 7 8 9 10; do tcp_open 127.0.0.1 "$local_port" && break; sleep 0.3; done
    tcp_open 127.0.0.1 "$local_port" || { say "forwarder failed to start; see $log_dir/forward.log"; exit 1; }
    say "started forwarder 127.0.0.1:$local_port -> $ip:5555 (log: $log_dir/forward.log)"
  fi
  serial=127.0.0.1:$local_port
fi

timeout 20 adb connect "$serial" >&2
state=unknown
for _ in 1 2 3 4 5; do
  state=$(adb -s "$serial" get-state 2>&1)
  [[ $state == device ]] && break
  sleep 1
done
case $state in
  device) ;;
  *unauthorized*)
    say "adb key not accepted: ask the user to put on the headset and allow USB debugging with 'Always allow', then rerun"
    echo "QUEST_SERIAL=$serial"; exit 2 ;;
  *)
    say "adb connected but state is: $state"; exit 1 ;;
esac
echo "QUEST_SERIAL=$serial"
