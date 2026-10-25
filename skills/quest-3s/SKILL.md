---
name: quest-3s
description: Connect adb to the user's Meta Quest 3S headset over Tailscale and handle its quirks. Use for any task on the Quest or VR apps on it: sideloading an APK, logcat, a screenshot of what it shows, or inspecting its apps and state.
---

# Quest 3S

The user's Meta Quest 3S (Horizon OS on Android 14, adb model `Quest_3S`) is the tailnet host `quest-3s-1`, with network adb on port 5555.

## Connect

1. Run `scripts/quest-connect.sh` from this skill's directory, by full path, from any working directory.
2. Pass `-s <serial>` to every adb command, taking the serial from the script's last stdout line, `QUEST_SERIAL=<serial>`.

The step is done when the script exits 0. On any other exit, relay its stderr message to the user and stop.

| Exit | Meaning | The user's move |
|---|---|---|
| 1, "offline" | Tailscale gets no answer from the headset | Power it on and confirm Tailscale runs on it |
| 1, "adb is not listening" | The headset rebooted, which turns network adb off | Plug it by USB into the Windows PC `powerpc`, where a keeper turns network adb back on |
| 2 | The headset hasn't accepted this host's adb key | Put on the headset and allow USB debugging with "Always allow" |
| 3 | adb, tailscale or python3 is missing | Install it on this host |

### Userspace networking

When tailscaled runs with `--tun=userspace-networking` (no `tailscale0` interface, as in a container without `/dev/net/tun`), only `tailscale` subcommands reach the tailnet. `tailscale ping` succeeds while `adb connect` and `nc` to the same IP time out, which looks like a firewall or ACL block. A port scan from the user's workstation adds a second false lead, because its LAN gateway answers TCP 53 for every IP.

The script handles this case. It starts `scripts/tailnet-forward.py` in the background, which carries each local connection over `tailscale nc`. The forwarder keeps running after the session, and later runs reuse it. Its log is `~/.cache/quest-3s/forward.log`.

## Headset specifics

- **Sleep state.** `adb -s <serial> shell dumpsys power | grep mWakefulness=`. The headset sleeps when nobody wears it, and adb stays connected while it sleeps.
- **Keep it awake.** `adb -s <serial> shell am broadcast -a com.oculus.vrpowermanager.prox_close` wakes it and keeps the display on while nobody wears it. Leave it awake when you finish, and never broadcast `com.oculus.vrpowermanager.automation_disable` or send `KEYCODE_SLEEP`. After a sleep, the cameras and microphones stay off until someone presses the power button. Until then `com.oculus.os.vrlockscreen/.SensorLockActivity` covers every app with a black screen that asks for that press, and no adb key event clears it.
- **Check what is in front** before you run anything on it, with `adb -s <serial> shell dumpsys activity activities | grep -m1 topResumedActivity`. `SensorLockActivity` means someone must press the power button. `com.oculus.guardian/...GuardianDialogActivity` ("Finding position in room") means the headset lost tracking, for example in a dark room or lying face down. Someone must select **Continue without tracking**, and the back key does not dismiss it. A benchmark that ran behind this dialog measured slower, so measure only once your app is in front.
- **Screenshot.** `adb -s <serial> exec-out screencap -p > shot.png` writes a 3664×1920 PNG with both eyes side by side. While the headset sleeps, it exits 0 and writes an empty file, so check the file size. The image includes the passthrough camera and shows the user's room: keep it local, and ask the user before uploading or publishing it.
- **Screen recording.** `screenrecord` writes 0-byte files on this headset.
- **Horizon OS version.** `adb -s <serial> shell getprop ro.vros.build.version`.
