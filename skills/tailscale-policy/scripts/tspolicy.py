#!/usr/bin/env python3
"""Pull, check, and push a Tailscale tailnet policy file without overwriting concurrent edits."""
import difflib
import hashlib
import http.client
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("TSPOLICY_API", "https://api.tailscale.com/api/v2").rstrip("/")
CREDENTIALS = pathlib.Path(os.environ.get("TSPOLICY_CREDENTIALS", "~/.agents/tailscale-policy/oauth")).expanduser()
STATE = pathlib.Path(os.environ.get("TSPOLICY_DIR", "~/.cache/tailscale-policy")).expanduser()
BASE, ETAG, POLICY, CHECKED = (STATE / n for n in ("base.hujson", "base.etag", "policy.hujson", "checked"))
ACL = f"{API}/tailnet/-/acl"

EXIT_INVALID, EXIT_SETUP, EXIT_LIVE_CHANGED, EXIT_UNPUSHED, EXIT_UNCHECKED = 1, 2, 3, 4, 5


def read(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    path.write_text(text, encoding="utf-8", newline="")


def same_endings(text, like):
    """Give text the line endings of like, so an editor that switched them makes no edit."""
    lf = text.replace("\r\n", "\n")
    return lf.replace("\n", "\r\n") if "\r\n" in like else lf


def die(code, message):
    print(message, file=sys.stderr)
    sys.exit(code)


def read_credentials():
    if not CREDENTIALS.is_file():
        die(EXIT_SETUP, f"No credential at {CREDENTIALS}. Create the Bitwarden item dotfiles/tailscale-policy-oauth (an OAuth client with only the policy_file scope), then run workstation-update --refresh-secrets.")
    if os.name != "nt" and CREDENTIALS.stat().st_mode & 0o077:
        print(f"Warning: other users can read {CREDENTIALS}. Run: chmod 600 {CREDENTIALS}", file=sys.stderr)
    values = dict(line.split("=", 1) for line in CREDENTIALS.read_text(encoding="utf-8-sig").splitlines() if "=" in line)
    try:
        return unquote(values["TS_OAUTH_CLIENT_ID"]), unquote(values["TS_OAUTH_CLIENT_SECRET"])
    except KeyError as missing:
        die(EXIT_SETUP, f"{CREDENTIALS} lacks {missing.args[0]}")


def unquote(value):
    value = value.strip()
    return value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'" else value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would resend the Authorization header to wherever a redirect points."""

    def redirect_request(self, *args):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def request(method, url, body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with OPENER.open(req, timeout=30) as resp:
            return resp.status, resp.headers, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.headers, err.read().decode()
    except (OSError, http.client.HTTPException) as err:
        die(EXIT_SETUP, f"{method} {url} failed: {err!r}. If this was a push, it may have landed: run check.")


def auth_headers():
    client_id, secret = read_credentials()
    form = urllib.parse.urlencode({"client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"}).encode()
    status, _, body = request("POST", f"{API}/oauth/token", form, {"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200:
        die(EXIT_SETUP, f"OAuth token request returned {status}: {body}")
    return {"Authorization": f"Bearer {json.loads(body)['access_token']}"}


def get_live(auth):
    """Return (policy, etag), or a message saying why the read failed."""
    status, headers, body = request("GET", ACL, headers={**auth, "Accept": "application/hujson"})
    if status == 200 and headers.get("ETag"):
        return body, headers["ETag"]
    return f"GET policy returned {status}: {body}"


def fetch_live(auth):
    live = get_live(auth)
    if isinstance(live, str):
        die(EXIT_SETUP, live)
    return live


def validate(auth, text):
    status, _, body = request("POST", f"{ACL}/validate", text.encode(), {**auth, "Content-Type": "application/hujson"})
    if status == 400:
        return body.strip() or "validate returned 400 with an empty body"
    if status != 200:
        die(EXIT_SETUP, f"validate returned {status}: {body}")
    result = json.loads(body) if body.strip() else {}
    return json.dumps(result, indent=2) if result.get("message") else None


def diff(old, new, old_name, new_name):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), old_name, new_name))


def fingerprint(policy, etag):
    return hashlib.sha256(f"{etag}\n{policy}".encode()).hexdigest()


def require_pulled():
    missing = [path.name for path in (BASE, ETAG, POLICY) if not path.is_file()]
    if len(missing) == 3:
        die(EXIT_SETUP, "Nothing pulled yet. Run: tspolicy.py pull")
    if missing:
        die(EXIT_SETUP, f"The local state in {STATE} is incomplete ({', '.join(missing)} missing). Tell the user: a pull would replace policy.hujson.")
    base = read(BASE)
    return base, read(ETAG).strip(), same_endings(read(POLICY), base)


def has_unconfirmed_edits():
    return POLICY.is_file() and (not BASE.is_file() or same_endings(read(POLICY), read(BASE)) != read(BASE))


def save_state(base, etag, policy):
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    CHECKED.unlink(missing_ok=True)
    # The etag goes last: a save cut short keeps the old etag, so the next check merges again.
    for path, text in ((POLICY, policy), (BASE, base), (ETAG, etag)):
        write(path, text)
        path.chmod(0o600)


def rebase_onto_live(base, policy, live, live_etag):
    """Merge the live policy's changes into the working copy, so they can't be dropped by the next push."""
    if live == policy:
        save_state(live, live_etag, live)
        print("The live policy already matches policy.hujson: an earlier push landed.")
        sys.exit(0)
    with tempfile.TemporaryDirectory() as tmp:
        mine, old, theirs = (pathlib.Path(tmp, n) for n in ("mine", "old", "theirs"))
        write(mine, policy)
        write(old, base)
        write(theirs, live)
        try:
            merge = subprocess.run(["git", "merge-file", "-p", "-L", "your edit", "-L", "pulled", "-L", "live", mine, old, theirs], capture_output=True)
        except FileNotFoundError:
            die(EXIT_SETUP, "git is not on the PATH. Install git, then run check: nothing was written.")
    # git merge-file exits with the number of conflicts, at most 127; more means it failed.
    if not 0 <= merge.returncode <= 127 or not merge.stdout:
        die(EXIT_SETUP, f"git merge-file failed: {merge.stderr.decode(errors='replace')}")
    save_state(live, live_etag, merge.stdout.decode("utf-8"))
    print("The live policy changed since the pull. Someone else's changes:")
    print(diff(base, live, "pulled", "live"))
    conflicts = f" with {merge.returncode} conflict(s) to resolve (marked <<<<<<<)" if merge.returncode else ""
    die(EXIT_LIVE_CHANGED, f"Merged those changes into {POLICY}{conflicts}. Run check and get the user's approval again.")


def pull(force):
    if has_unconfirmed_edits() and not force:
        die(EXIT_UNPUSHED, f"{POLICY} has edits not confirmed live. Run check: it reports whether an earlier push landed. Otherwise push them, or pass --force to set them aside.")
    live, etag = fetch_live(auth_headers())
    if has_unconfirmed_edits():
        aside, n = STATE / "policy.hujson.orig", 1
        while aside.exists():
            n += 1
            aside = STATE / f"policy.hujson.orig{n}"
        POLICY.replace(aside)
        print(f"Set aside unpushed edits in {aside}")
    save_state(live, etag, live)
    print(f"Pulled the live policy. Edit {POLICY}")


def check():
    base, etag, policy = require_pulled()
    auth = auth_headers()
    live, live_etag = fetch_live(auth)
    if live_etag != etag:
        rebase_onto_live(base, policy, live, live_etag)
    print(diff(base, policy, "live", "policy.hujson") or "No edits: policy.hujson matches the live policy.")
    problem = validate(auth, policy)
    if problem:
        die(EXIT_INVALID, f"Validation or tests failed:\n{problem}")
    write(CHECKED, fingerprint(policy, etag))
    print("Valid, tests pass, and the live policy is unchanged since the pull.")


def push():
    base, etag, policy = require_pulled()
    if policy == base:
        print("No edits to push.")
        return
    if not CHECKED.is_file() or read(CHECKED) != fingerprint(policy, etag):
        die(EXIT_UNCHECKED, "policy.hujson differs from what check last validated. Run check and get the user's approval of its diff.")
    auth = auth_headers()
    status, _, body = request("POST", ACL, policy.encode(), {**auth, "Content-Type": "application/hujson", "Accept": "application/hujson", "If-Match": etag})
    if status == 412:
        rebase_onto_live(base, policy, *fetch_live(auth))
    if status == 400:
        die(EXIT_INVALID, f"Tailscale rejected the policy: {body}")
    if status != 200:
        die(EXIT_SETUP, f"POST policy returned {status}: {body}")
    refreshed = get_live(auth)
    if isinstance(refreshed, str):
        print(f"Pushed, but refreshing the local copy failed ({refreshed}). Run check before the next edit.")
    else:
        save_state(refreshed[0], refreshed[1], refreshed[0])
        print("Pushed. The live policy now matches policy.hujson.")


def main(argv):
    os.umask(0o077)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    commands = {"pull": lambda: pull("--force" in argv[1:]), "check": check, "push": push}
    if not argv or argv[0] not in commands:
        die(EXIT_SETUP, "usage: tspolicy.py pull [--force] | check | push")
    api = urllib.parse.urlsplit(API)
    if api.scheme != "https" and not (api.scheme == "http" and api.hostname in ("127.0.0.1", "localhost", "::1")):
        die(EXIT_SETUP, f"TSPOLICY_API must be https, or http to this machine: {API}")
    try:
        commands[argv[0]]()
    except Exception as err:
        die(EXIT_SETUP, f"Unexpected error: {err!r}. It says nothing about the policy itself. If it came during a push, run check: it reports whether the push landed.")


if __name__ == "__main__":
    main(sys.argv[1:])
