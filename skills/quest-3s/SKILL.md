---
name: quest-3s
description: Connect to and drive the user's Meta Quest 3S headset (tailnet host quest-3s-1) over adb through Tailscale. Use whenever a task touches the Quest, the headset, or VR on it: connecting, sideloading an APK, logcat, a screenshot of what the headset shows, or inspecting its apps and state.
---

# Quest 3S

The user's Meta Quest 3S (Horizon OS on Android 14, adb model `Quest_3S`) is the tailnet host `quest-3s-1`. Network adb listens on port 5555. A reboot turns it off; a keeper on the user's Windows PC, `powerpc`, turns it back on once the headset is plugged into that PC by USB.

## Connect

1. Run `scripts/quest-connect.sh` by its full path under this skill's directory; any working directory works.
2. Take the serial from the last stdout line, `QUEST_SERIAL=<serial>`, and pass `-s <serial>` to every adb command. The serial is `127.0.0.1:5556` through the forwarder, or `<ip>:5555` when the host reaches the tailnet directly.

The step is done when the script exits 0. On any other exit, relay its stderr message to the user and stop: each failure needs a person at the headset or the Windows PC.

| Exit | Meaning | The user's move |
|---|---|---|
| 1, "offline" | Tailscale gets no answer from the headset | Power it on; confirm Tailscale runs on it |
| 1, "adb is not listening" | The headset rebooted | Plug it into `powerpc` by USB so the keeper re-enables adb |
| 2 | This host's adb key isn't accepted | Put on the headset and allow USB debugging with "Always allow" |
| 3 | adb, tailscale or python3 missing | Install it on this host |

### Userspace networking

On a host whose tailscaled runs with `--tun=userspace-networking` (no `tailscale0` interface, as in a container without `/dev/net/tun`), `tailscale ping` succeeds while `adb connect` and `nc` to the same IP time out. That looks like a firewall or ACL block, and it isn't one: only `tailscale` subcommands enter the tailnet there. A port scan misleads further on the user's workstation, whose LAN gateway answers TCP 53 for every IP. The script detects the case and starts `scripts/tailnet-forward.py` in the background, which carries each local connection over `tailscale nc`. The forwarder outlives the session and the script reuses it; its log is `~/.cache/quest-3s/forward.log`.

## Headset specifics

- **Asleep or awake:** `adb -s <serial> shell dumpsys power | grep mWakefulness=`. The headset sleeps when nobody wears it, and adb stays connected while it sleeps.
- **Wake it and keep the display on** with the headset off the user's face: `adb -s <serial> shell am broadcast -a com.oculus.vrpowermanager.prox_close`. When you're done, restore normal proximity behaviour with `com.oculus.vrpowermanager.automation_disable`. After a sleep, the cameras and microphones stay off until someone presses the power button, so the woken view is a black prompt saying exactly that, not the room.
- **Screenshot:** `adb -s <serial> exec-out screencap -p > shot.png` gives a 3664×1920 PNG with both eyes side by side. While the headset sleeps it exits 0 and writes an empty file, so check the file size. It includes the passthrough camera, so it shows the user's room: keep it local and ask before uploading or publishing it.
- **Screen recording:** `screenrecord` writes 0-byte files on this headset.
- **Horizon OS version:** `getprop ro.vros.build.version`.
