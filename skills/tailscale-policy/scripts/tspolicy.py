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


def die(code, message):
    print(message, file=sys.stderr)
    sys.exit(code)


def read_credentials():
    if not CREDENTIALS.is_file():
        die(EXIT_SETUP, f"No credential at {CREDENTIALS}. Create the Bitwarden item dotfiles/tailscale-policy-oauth, then run workstation-update --refresh-secrets.")
    values = dict(line.split("=", 1) for line in CREDENTIALS.read_text().splitlines() if "=" in line)
    try:
        return values["TS_OAUTH_CLIENT_ID"].strip(), values["TS_OAUTH_CLIENT_SECRET"].strip()
    except KeyError as missing:
        die(EXIT_SETUP, f"{CREDENTIALS} lacks {missing.args[0]}")


def request(method, url, body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
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
    status, headers, body = request("GET", ACL, headers={**auth, "Accept": "application/hujson"})
    return (body, headers["ETag"]) if status == 200 and headers.get("ETag") else None


def fetch_live(auth):
    return get_live(auth) or die(EXIT_SETUP, "GET policy failed")


def validate(auth, text):
    status, _, body = request("POST", f"{ACL}/validate", text.encode(), {**auth, "Content-Type": "application/hujson"})
    if status == 400:
        return body
    if status != 200:
        die(EXIT_SETUP, f"validate returned {status}: {body}")
    result = json.loads(body) if body.strip() else {}
    return json.dumps(result, indent=2) if result.get("message") else None


def diff(old, new, old_name, new_name):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), old_name, new_name))


def fingerprint(policy, etag):
    return hashlib.sha256(f"{etag}\n{policy}".encode()).hexdigest()


def require_pulled():
    if not (BASE.is_file() and ETAG.is_file() and POLICY.is_file()):
        die(EXIT_SETUP, "Nothing pulled yet. Run: tspolicy.py pull")
    return BASE.read_text(), ETAG.read_text().strip(), POLICY.read_text()


def save_state(base, etag, policy):
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    for path, text in ((BASE, base), (ETAG, etag), (POLICY, policy)):
        path.write_text(text)
        path.chmod(0o600)
    CHECKED.unlink(missing_ok=True)


def rebase_onto_live(base, policy, live, live_etag):
    """Merge the live policy's changes into the working copy, so they can't be dropped by the next push."""
    if live == policy:
        save_state(live, live_etag, live)
        print("The live policy already matches policy.hujson: an earlier push landed.")
        sys.exit(0)
    with tempfile.TemporaryDirectory() as tmp:
        mine, old, theirs = (pathlib.Path(tmp, n) for n in ("mine", "old", "theirs"))
        mine.write_text(policy)
        old.write_text(base)
        theirs.write_text(live)
        merge = subprocess.run(["git", "merge-file", "-p", "-L", "your edit", "-L", "pulled", "-L", "live", mine, old, theirs], capture_output=True, text=True)
    if merge.returncode < 0 or not merge.stdout:
        die(EXIT_SETUP, f"git merge-file failed: {merge.stderr}")
    save_state(live, live_etag, merge.stdout)
    print("The live policy changed since the pull. Someone else's changes:")
    print(diff(base, live, "pulled", "live"))
    conflicts = f" with {merge.returncode} conflict(s) to resolve (marked <<<<<<<)" if merge.returncode else ""
    die(EXIT_LIVE_CHANGED, f"Merged those changes into {POLICY}{conflicts}. Run check and get the user's approval again.")


def pull(force):
    if POLICY.is_file() and BASE.is_file() and POLICY.read_text() != BASE.read_text() and not force:
        die(EXIT_UNPUSHED, f"{POLICY} has unpushed edits. Push them, or pass --force to set them aside.")
    live, etag = fetch_live(auth_headers())
    if POLICY.is_file() and BASE.is_file() and POLICY.read_text() != BASE.read_text():
        POLICY.replace(STATE / "policy.hujson.orig")
        print(f"Set aside unpushed edits in {STATE / 'policy.hujson.orig'}")
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
    CHECKED.write_text(fingerprint(policy, etag))
    print("Valid, tests pass, and the live policy is unchanged since the pull.")


def push():
    base, etag, policy = require_pulled()
    if policy == base:
        print("No edits to push.")
        return
    if not CHECKED.is_file() or CHECKED.read_text() != fingerprint(policy, etag):
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
    if refreshed:
        save_state(refreshed[0], refreshed[1], refreshed[0])
        print("Pushed. The live policy now matches policy.hujson.")
    else:
        print("Pushed, but refreshing the local copy failed. Run check before the next edit.")


def main(argv):
    os.umask(0o077)
    commands = {"pull": lambda: pull("--force" in argv[1:]), "check": check, "push": push}
    if not argv or argv[0] not in commands:
        die(EXIT_SETUP, "usage: tspolicy.py pull [--force] | check | push")
    commands[argv[0]]()


if __name__ == "__main__":
    main(sys.argv[1:])
