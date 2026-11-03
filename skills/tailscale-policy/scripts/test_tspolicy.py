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
INITIAL = '{\n  // owner note\n  "acls": [],\n  "ssh": [],\n  "groups": {},\n}\n'
SECRET = "tskey-client-secret"


class FakeTailscale(http.server.BaseHTTPRequestHandler):
    policy = INITIAL
    writes = 0
    validate_status = 200
    validate_body = None

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
            if FakeTailscale.validate_status != 200 or FakeTailscale.validate_body is not None:
                body = '{"message":"forbidden"}' if FakeTailscale.validate_body is None else FakeTailscale.validate_body
                return self.reply(FakeTailscale.validate_status, body)
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
        FakeTailscale.policy, FakeTailscale.writes, FakeTailscale.validate_status, FakeTailscale.validate_body = INITIAL, 0, 200, None
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.state = self.tmp / "state"
        self.creds = self.tmp / "oauth"
        self.creds.write_text(f"TS_OAUTH_CLIENT_ID=id-1\nTS_OAUTH_CLIENT_SECRET={SECRET}\n")
        self.creds.chmod(0o600)
        self.policy = self.state / "policy.hujson"

    def run_cli(self, *args, **env_overrides):
        env = {**os.environ, "TSPOLICY_API": f"http://127.0.0.1:{self.server.server_port}/api/v2",
               "TSPOLICY_DIR": str(self.state), "TSPOLICY_CREDENTIALS": str(self.creds), **env_overrides}
        result = subprocess.run([sys.executable, str(SCRIPT), *args], env=env, capture_output=True, encoding="utf-8", timeout=20)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        return result

    def edit(self, old, new):
        self.policy.write_bytes(self.policy.read_bytes().decode("utf-8").replace(old, new).encode("utf-8"))

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
        self.assertNotIn("conflict", pushed.stderr)
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

    def test_a_validate_400_is_an_invalid_policy(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["new"]')
        FakeTailscale.validate_status = 400
        self.assertEqual(self.run_cli("check").returncode, 1)

    def test_a_failed_refresh_after_push_recovers_on_the_next_check(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        self.run_cli("check")
        original_get = FakeTailscale.do_GET
        FakeTailscale.do_GET = lambda handler: handler.reply(500, "{}")
        try:
            self.assertEqual(self.run_cli("push").returncode, 0)
        finally:
            FakeTailscale.do_GET = original_get
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("earlier push landed", checked.stdout)
        self.assertEqual(self.run_cli("pull").returncode, 0)

    def test_pull_keeps_unpushed_edits_unless_forced(self):
        self.run_cli("pull")
        self.edit("owner note", "draft")
        blocked = self.run_cli("pull")
        self.assertEqual(blocked.returncode, 4)
        self.assertIn("Run check", blocked.stderr)
        self.assertIn("draft", self.policy.read_text())
        self.assertEqual(self.run_cli("pull", "--force").returncode, 0)
        self.assertEqual(self.policy.read_text(), INITIAL)
        self.assertIn("draft", (self.state / "policy.hujson.orig").read_text())
        self.edit("owner note", "second draft")
        self.assertEqual(self.run_cli("pull", "--force").returncode, 0)
        self.assertNotIn("second draft", (self.state / "policy.hujson.orig").read_text())
        self.assertIn("second draft", (self.state / "policy.hujson.orig2").read_text())

    @unittest.skipIf(os.name == "nt", "Windows has no Unix file modes")
    def test_state_is_private_to_the_user(self):
        self.state.mkdir(mode=0o755)
        for name in ("base.hujson", "policy.hujson"):
            (self.state / name).write_text(INITIAL)
            (self.state / name).chmod(0o644)
        self.assertEqual(self.run_cli("pull").returncode, 0)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.policy.stat().st_mode & 0o777, 0o600)

    def test_missing_credential_names_the_fix(self):
        self.creds.unlink()
        result = self.run_cli("pull")
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(self.creds), result.stderr)
        self.assertIn("policy_file", result.stderr)

    def test_a_credential_saved_with_a_bom_and_crlf_works(self):
        self.creds.write_bytes(f"\ufeffTS_OAUTH_CLIENT_ID=id-1\r\nTS_OAUTH_CLIENT_SECRET={SECRET}\r\n".encode())
        pulled = self.run_cli("pull")
        self.assertEqual(pulled.returncode, 0, pulled.stderr)

    def test_non_ascii_text_survives_pull_check_and_push(self):
        FakeTailscale.policy = INITIAL.replace("owner note", "note de l'\u00e9quipe \u2192 ops")
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["caf\u00e9"]')
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn('"caf\u00e9"', checked.stdout)
        self.assertEqual(self.run_cli("push").returncode, 0)
        self.assertIn("note de l'\u00e9quipe \u2192 ops", FakeTailscale.policy)
        self.assertIn('"caf\u00e9"', FakeTailscale.policy)

    def test_an_unexpected_reply_is_a_setup_error_not_an_invalid_policy(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["new"]')
        FakeTailscale.validate_body = "<html>proxy login</html>"
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 2, checked.stderr)
        self.assertIn("Unexpected error", checked.stderr)

    def test_a_merge_without_git_is_a_setup_error(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        self.someone_else_edits()
        empty = self.tmp / "no-git"
        empty.mkdir()
        checked = self.run_cli("check", PATH=str(empty))
        self.assertEqual(checked.returncode, 2, checked.stderr)
        self.assertIn("git is not on the PATH", checked.stderr)
        self.assertIn('"acls": ["mine"]', self.policy.read_text())

    def test_a_failed_read_names_its_status(self):
        original_get = FakeTailscale.do_GET
        FakeTailscale.do_GET = lambda handler: handler.reply(403, '{"message":"missing scope"}')
        try:
            pulled = self.run_cli("pull")
        finally:
            FakeTailscale.do_GET = original_get
        self.assertEqual(pulled.returncode, 2)
        self.assertIn("403", pulled.stderr)
        self.assertIn("missing scope", pulled.stderr)

    def test_a_crlf_policy_merges_line_by_line_and_keeps_its_endings(self):
        FakeTailscale.policy = INITIAL.replace("\n", "\r\n")
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        self.someone_else_edits()
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 3, checked.stderr)
        self.assertNotIn("conflict", checked.stderr)
        self.assertEqual(self.run_cli("check").returncode, 0)
        self.assertEqual(self.run_cli("push").returncode, 0)
        self.assertIn('"acls": ["mine"],\r\n', FakeTailscale.policy)
        self.assertIn('"groups": {"console": []},\r\n', FakeTailscale.policy)

    def test_an_editor_switching_line_endings_is_no_edit(self):
        self.run_cli("pull")
        self.policy.write_bytes(self.policy.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(self.run_cli("pull").returncode, 0)
        self.policy.write_bytes(self.policy.read_bytes().replace(b"\n", b"\r\n"))
        checked = self.run_cli("check")
        self.assertIn("No edits", checked.stdout)
        self.edit('"acls": []', '"acls": ["mine"]')
        self.run_cli("check")
        self.assertEqual(self.run_cli("push").returncode, 0)
        self.assertNotIn("\r", FakeTailscale.policy)

    def test_edits_without_a_pulled_copy_are_kept(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        (self.state / "base.hujson").unlink()
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 2)
        self.assertIn("incomplete", checked.stderr)
        self.assertNotIn("Run: tspolicy.py pull", checked.stderr)
        self.assertEqual(self.run_cli("pull").returncode, 4)
        self.assertIn('"acls": ["mine"]', self.policy.read_text())

    def test_quoted_credential_values_work(self):
        self.creds.write_text(f"TS_OAUTH_CLIENT_ID='id-1'\nTS_OAUTH_CLIENT_SECRET=\"{SECRET}\"\n")
        pulled = self.run_cli("pull")
        self.assertEqual(pulled.returncode, 0, pulled.stderr)

    @unittest.skipIf(os.name == "nt", "Windows has no Unix file modes")
    def test_a_credential_others_can_read_gets_a_warning(self):
        self.creds.chmod(0o644)
        pulled = self.run_cli("pull")
        self.assertEqual(pulled.returncode, 0, pulled.stderr)
        self.assertIn("chmod 600", pulled.stderr)

    def test_the_secret_goes_only_to_https_or_this_machine(self):
        refused = self.run_cli("pull", TSPOLICY_API="http://example.invalid/api/v2")
        self.assertEqual(refused.returncode, 2)
        self.assertIn("must be https", refused.stderr)

    def test_an_empty_validate_400_is_an_invalid_policy(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["new"]')
        FakeTailscale.validate_status, FakeTailscale.validate_body = 400, ""
        checked = self.run_cli("check")
        self.assertEqual(checked.returncode, 1)
        self.assertNotIn("tests pass", checked.stdout)
        self.assertEqual(self.run_cli("push").returncode, 5)

    def test_the_token_never_follows_a_redirect(self):
        followed = []
        original_get = FakeTailscale.do_GET

        def redirecting_get(handler):
            if handler.path == "/elsewhere":
                followed.append(handler.headers.get("Authorization"))
                return handler.reply(200, INITIAL, {"ETag": '"x"'})
            handler.reply(302, "", {"Location": "/elsewhere"})

        FakeTailscale.do_GET = redirecting_get
        try:
            pulled = self.run_cli("pull")
        finally:
            FakeTailscale.do_GET = original_get
        self.assertEqual(pulled.returncode, 2)
        self.assertIn("302", pulled.stderr)
        self.assertEqual(followed, [])

    def test_a_save_cut_short_still_merges_the_live_change(self):
        self.run_cli("pull")
        self.edit('"acls": []', '"acls": ["mine"]')
        self.someone_else_edits()
        etag = self.state / "base.etag"
        etag.chmod(0o444)  # readable, so check starts; not writable, so its save stops at the etag
        self.assertEqual(self.run_cli("check").returncode, 2)
        etag.chmod(0o600)
        self.assertEqual(self.run_cli("check").returncode, 3)
        self.assertIn('"groups": {"console": []}', self.policy.read_text())
        self.assertIn('"acls": ["mine"]', self.policy.read_text())

    def test_push_without_edits_writes_nothing(self):
        self.run_cli("pull")
        self.assertEqual(self.run_cli("push").returncode, 0)
        self.assertEqual(FakeTailscale.writes, 0)


if __name__ == "__main__":
    unittest.main()
