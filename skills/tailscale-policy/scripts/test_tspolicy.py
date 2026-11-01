#!/usr/bin/env python3
"""Drives tspolicy.py against a fake Tailscale API; no test reaches the network."""
import hashlib
import http.server
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest

SCRIPT = pathlib.Path(__file__).with_name("tspolicy.py")
INITIAL = '{\n  // owner note\n  "acls": [],\n  "groups": {},\n}\n'
SECRET = "tskey-client-secret"


class FakeTailscale(http.server.BaseHTTPRequestHandler):
    policy = INITIAL
    writes = 0
    validate_status = 200

    def log_message(self, *_):
        pass

    def etag(self):
        return '"' + hashlib.sha256(FakeTailscale.policy.encode()).hexdigest()[:12] + '"'

    def reply(self, status, body="", headers=None):
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body.encode())

    def body(self):
        return self.rfile.read(int(self.headers["Content-Length"])).decode()

    def authorized(self):
        if self.headers.get("Authorization") == "Bearer token-1":
            return True
        self.reply(401, '{"message":"unauthorized"}')
        return False

    def do_GET(self):
        if self.path == "/api/v2/tailnet/-/acl" and self.authorized():
            self.reply(200, FakeTailscale.policy, {"ETag": self.etag()})

    def do_POST(self):
        body = self.body()
        if self.path == "/api/v2/oauth/token":
            ok = "client_id=id-1" in body and f"client_secret={SECRET}" in body
            return self.reply(200, '{"access_token":"token-1"}') if ok else self.reply(401, "{}")
        if not self.authorized():
            return
        failing = "FAILING-TEST" in body
        if self.path == "/api/v2/tailnet/-/acl/validate":
            if FakeTailscale.validate_status != 200:
                return self.reply(FakeTailscale.validate_status, '{"message":"forbidden"}')
            return self.reply(200, '{"message":"test(s) failed","data":[]}' if failing else "")
        if self.path == "/api/v2/tailnet/-/acl":
            if self.headers.get("If-Match") not in (None, self.etag()):
                return self.reply(412, '{"message":"precondition failed"}')
            if failing:
                return self.reply(400, '{"message":"test(s) failed"}')
            FakeTailscale.policy = body
            FakeTailscale.writes += 1
            self.reply(200, body)


class TsPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeTailscale)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeTailscale.policy, FakeTailscale.writes, FakeTailscale.validate_status = INITIAL, 0, 200
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.state = self.tmp / "state"
        self.creds = self.tmp / "oauth"
        self.creds.write_text(f"TS_OAUTH_CLIENT_ID=id-1\nTS_OAUTH_CLIENT_SECRET={SECRET}\n")
        self.policy = self.state / "policy.hujson"

    def run_cli(self, *args):
        env = {**os.environ, "TSPOLICY_API": f"http://127.0.0.1:{self.server.server_port}/api/v2",
               "TSPOLICY_DIR": str(self.state), "TSPOLICY_CREDENTIALS": str(self.creds)}
        result = subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=20)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        return result

    def edit(self, old, new):
        self.policy.write_text(self.policy.read_text().replace(old, new))

    def someone_else_edits(self):
        FakeTailscale.policy = FakeTailscale.policy.replace('"groups": {}', '"groups": {"console": []}')

    def test_pull_edit_check_push_applies_the_edit_and_keeps_comments(self):
        self.assertEqual(self.run_cli("pull").returncode, 0)
        self.assertEqual(self.policy.read_text(), INITIAL)
        self.edit('"acls": []', '"acls": ["new"]')
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn('+  "acls": ["new"],', checked.stdout)
        pushed = self.run_cli("push")
        self.assertEqual(pushed.returncode, 0, pushed.stderr)
        self.assertIn('"acls": ["new"]', FakeTailscale.policy)
        self.assertIn("// owner note", FakeTailscale.policy)

    def test_push_refuses_an_edit_made_after_the_check(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["reviewed"]')
        self.run_cli("check")
        self.edit('"reviewed"', '"unreviewed"')
        self.assertEqual(self.run_cli("push").returncode, 5)
        self.assertEqual(FakeTailscale.writes, 0)

    def test_push_refuses_an_unchecked_edit(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["new"]')
        self.assertEqual(self.run_cli("push").returncode, 5)
        self.assertEqual(FakeTailscale.writes, 0)

    def test_concurrent_edit_is_merged_and_survives_the_next_push(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        self.run_cli("check")
        self.someone_else_edits()
        pushed = self.run_cli("push")
        self.assertEqual(pushed.returncode, 3)
        self.assertIn('+  "groups": {"console": []},', pushed.stdout)
        self.assertEqual(FakeTailscale.writes, 0)
        self.assertIn('"groups": {"console": []}', self.policy.read_text())
        self.assertIn('"acls": ["mine"]', self.policy.read_text())
        self.assertEqual(self.run_cli("push").returncode, 5)
        self.assertEqual(self.run_cli("check").returncode, 0)
        self.assertEqual(self.run_cli("push").returncode, 0)
        self.assertIn('"groups": {"console": []}', FakeTailscale.policy)
        self.assertIn('"acls": ["mine"]', FakeTailscale.policy)

    def test_check_merges_a_live_change_before_review(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        self.someone_else_edits()
        self.assertEqual(self.run_cli("check").returncode, 3)
        self.assertIn('"groups": {"console": []}', self.policy.read_text())

    def test_overlapping_edits_leave_conflict_markers_and_block_the_push(self):
        self.run_cli("pull")
        self.edit('"groups": {}', '"groups": {"mine": []}')
        self.someone_else_edits()
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 3)
        self.assertIn("1 conflict", checked.stderr)
        self.assertIn("<<<<<<<", self.policy.read_text())
        self.assertEqual(self.run_cli("push").returncode, 5)

    def test_check_after_an_unconfirmed_push_recognizes_it_landed(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        FakeTailscale.policy = self.policy.read_text()
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("earlier push landed", checked.stdout)

    def test_failing_policy_tests_block_the_push(self):
        self.run_cli("pull")
        self.edit("owner note", "FAILING-TEST")
        self.assertEqual(self.run_cli("check").returncode, 1)
        self.assertEqual(self.run_cli("push").returncode, 5)
        self.assertEqual(FakeTailscale.writes, 0)

    def test_an_auth_error_during_check_is_a_setup_error(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["new"]')
        FakeTailscale.validate_status = 403
        self.assertEqual(self.run_cli("check").returncode, 2)

    def test_pull_keeps_unpushed_edits_unless_forced(self):
        self.run_cli("pull")
        self.edit("owner note", "draft")
        self.assertEqual(self.run_cli("pull").returncode, 4)
        self.assertIn("draft", self.policy.read_text())
        self.assertEqual(self.run_cli("pull", "--force").returncode, 0)
        self.assertEqual(self.policy.read_text(), INITIAL)
        self.assertIn("draft", (self.state / "policy.hujson.orig").read_text())

    def test_state_is_private_to_the_user(self):
        self.state.mkdir(mode=0o755)
        (self.state / "policy.hujson").write_text(INITIAL)
        (self.state / "policy.hujson").chmod(0o644)
        self.run_cli("pull")
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o600)

    def test_missing_credential_names_the_fix(self):
        self.creds.unlink()
        result = self.run_cli("pull")
        self.assertEqual(result.returncode, 2)
        self.assertIn("dotfiles/tailscale-policy-oauth", result.stderr)

    def test_push_without_edits_writes_nothing(self):
        self.run_cli("pull")
        self.assertEqual(self.run_cli("push").returncode, 0)
        self.assertEqual(FakeTailscale.writes, 0)


if __name__ == "__main__":
    unittest.main()
