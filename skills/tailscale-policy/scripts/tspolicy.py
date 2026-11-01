#!/usr/bin/env python3
"""Pull, check, and push a Tailscale tailnet policy file without overwriting concurrent edits."""
import difflib
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("TSPOLICY_API", "https://api.tailscale.com/api/v2").rstrip("/")
CREDENTIALS = pathlib.Path(os.environ.get("TSPOLICY_CREDENTIALS", "~/.agents/tailscale-policy/oauth")).expanduser()
STATE = pathlib.Path(os.environ.get("TSPOLICY_DIR", "~/.cache/tailscale-policy")).expanduser()
BASE, ETAG, POLICY, LIVE = (STATE / n for n in ("base.hujson", "base.etag", "policy.hujson", "live.hujson"))
ACL = f"{API}/tailnet/-/acl"

EXIT_INVALID, EXIT_SETUP, EXIT_LIVE_CHANGED, EXIT_UNPUSHED = 1, 2, 3, 4


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
    except urllib.error.URLError as err:
        die(EXIT_SETUP, f"{method} {url} failed: {err.reason}")


def auth_headers():
    client_id, secret = read_credentials()
    form = urllib.parse.urlencode({"client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"}).encode()
    status, _, body = request("POST", f"{API}/oauth/token", form, {"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200:
        die(EXIT_SETUP, f"OAuth token request returned {status}: {body}")
    return {"Authorization": f"Bearer {json.loads(body)['access_token']}"}


def fetch_live(auth):
    status, headers, body = request("GET", ACL, headers={**auth, "Accept": "application/hujson"})
    if status != 200 or not headers.get("ETag"):
        die(EXIT_SETUP, f"GET policy returned {status}: {body}")
    return body, headers["ETag"]


def validate(auth, text):
    status, _, body = request("POST", f"{ACL}/validate", text.encode(), {**auth, "Content-Type": "application/hujson"})
    if status != 200:
        return f"validate returned {status}: {body}"
    result = json.loads(body) if body.strip() else {}
    return json.dumps(result, indent=2) if result.get("message") else None


def diff(old, new, old_name, new_name):
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), old_name, new_name))


def require_pulled():
    if not (BASE.is_file() and ETAG.is_file() and POLICY.is_file()):
        die(EXIT_SETUP, "Nothing pulled yet. Run: tspolicy.py pull")
    return BASE.read_text(), ETAG.read_text().strip(), POLICY.read_text()


def save_base(text, etag):
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    BASE.write_text(text)
    ETAG.write_text(etag)
    POLICY.write_text(text)
    LIVE.unlink(missing_ok=True)


def pull(force):
    if POLICY.is_file() and BASE.is_file() and POLICY.read_text() != BASE.read_text():
        if not force:
            die(EXIT_UNPUSHED, f"{POLICY} has unpushed edits. Push them, or pass --force to set them aside.")
        POLICY.replace(STATE / "policy.hujson.orig")
        print(f"Set aside unpushed edits in {STATE / 'policy.hujson.orig'}")
    save_base(*fetch_live(auth_headers()))
    print(f"Pulled the live policy. Edit {POLICY}")


def report_live_change(base, live):
    LIVE.write_text(live)
    print(f"The live policy changed since the pull. Its changes, saved to {LIVE}:")
    print(diff(base, live, "base.hujson", "live.hujson"))
    die(EXIT_LIVE_CHANGED, "Show these changes to the user, then run pull --force and reapply the edit.")


def check():
    base, etag, policy = require_pulled()
    auth = auth_headers()
    print(diff(base, policy, "base.hujson", "policy.hujson") or "No edits: policy.hujson matches the pulled policy.")
    live, live_etag = fetch_live(auth)
    if live_etag != etag:
        report_live_change(base, live)
    problem = validate(auth, policy)
    if problem:
        die(EXIT_INVALID, f"Validation or tests failed:\n{problem}")
    print("Valid, tests pass, and the live policy is unchanged since the pull.")


def push():
    base, etag, policy = require_pulled()
    if policy == base:
        print("No edits to push.")
        return
    auth = auth_headers()
    problem = validate(auth, policy)
    if problem:
        die(EXIT_INVALID, f"Validation or tests failed:\n{problem}")
    status, _, body = request("POST", ACL, policy.encode(), {**auth, "Content-Type": "application/hujson", "Accept": "application/hujson", "If-Match": etag})
    if status == 412:
        report_live_change(base, fetch_live(auth)[0])
    if status != 200:
        die(EXIT_INVALID, f"POST policy returned {status}: {body}")
    save_base(*fetch_live(auth))
    print("Pushed. The live policy now matches policy.hujson.")


def main(argv):
    commands = {"pull": lambda: pull("--force" in argv[1:]), "check": check, "push": push}
    if not argv or argv[0] not in commands:
        die(EXIT_SETUP, "usage: tspolicy.py pull [--force] | check | push")
    commands[argv[0]]()


if __name__ == "__main__":
    main(sys.argv[1:])
