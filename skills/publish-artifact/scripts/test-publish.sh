#!/usr/bin/env bash
set -euo pipefail

readonly SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly FIXTURE_ROOT="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$FIXTURE_ROOT"' EXIT

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
scenario() { printf 'scenario: %s\n' "$1"; }

stub_bin="$FIXTURE_ROOT/stub-bin"; calls="$FIXTURE_ROOT/calls"; mkdir "$stub_bin"
cat > "$stub_bin/artifactserver" <<STUB
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$calls"
[[ -z "\${STUB_FAIL:-}" ]] || { echo "Artifact Server: \$STUB_FAIL" >&2; exit 1; }
echo '{"links":{"review":"https://artifact.example/review?artifact=art_1"}}'
STUB
cat > "$stub_bin/npx" <<STUB
#!/usr/bin/env bash
printf '%s\n' "npx \$*" >> "$calls"
STUB
chmod +x "$stub_bin"/*

home="$FIXTURE_ROOT/home"; config_dir="$home/config/faviann-skills"
mkdir -p "$config_dir"
printf 'as_key_fixture\n' > "$home/token"
jq -n --arg tokenFile "$home/token" '{server: "https://artifact.example", tokenFile: $tokenFile}' > "$config_dir/artifact-server.json"
site="$FIXTURE_ROOT/site"; mkdir "$site"; echo '<h1>hi</h1>' > "$site/index.html"

publish() { HOME="$home" XDG_CONFIG_HOME="$home/config" PATH="$stub_bin:$PATH" "$SCRIPTS/publish.sh" "$@"; }
assert_error() {
  local expected="$1" code="$2" status=0 output
  shift 2
  output="$("$@")" || status=$?
  [[ "$status" -eq "$code" ]] || fail "expected exit $code, got $status: $output"
  [[ "$(jq -r .status <<<"$output")" == error ]] || fail "not an error: $output"
  [[ "$(jq -r .category <<<"$output")" == "$expected" ]] || fail "expected $expected error: $output"
}

scenario 'publishing passes the server, token file, and path to the CLI and never --public'
: > "$calls"
output="$(publish "$site")"
[[ "$(jq -r .links.review <<<"$output")" == https://artifact.example/review* ]] || fail "CLI JSON not printed: $output"
[[ "$(<"$calls")" == "publish --server https://artifact.example --token-file $home/token -- $site" ]] \
  || fail "unexpected CLI arguments: $(<"$calls")"
grep -q -- '--public' "$calls" && fail 'publish.sh passed --public'
grep -q as_key_fixture "$calls" && fail 'the key reached the CLI arguments'
[[ "$output" != *as_key_fixture* ]] || fail 'the key reached the output'

scenario 'a name is passed through'
: > "$calls"; publish "$site" --name 'Quarterly report' >/dev/null
grep -q -- '--name Quarterly report' "$calls" || fail "name missing: $(<"$calls")"

scenario 'a new version passes the artifact and the expected version'
: > "$calls"; publish "$site" --artifact art_1 --expected-version ver_1 >/dev/null
grep -q -- '--artifact art_1 --expected-version ver_1' "$calls" || fail "version flags missing: $(<"$calls")"

scenario 'a path written with a leading ./ and a dash reaches the CLI as a path'
: > "$calls"; (cd "$FIXTURE_ROOT" && mkdir -- -odd && echo x > -odd/index.html && publish ./-odd >/dev/null)
grep -q -- '-- ./-odd$' "$calls" || fail "dash path mangled: $(<"$calls")"

scenario 'a call that cannot work is an invalid-call error'
assert_error invalid-call 2 publish
assert_error invalid-call 2 publish "$site" "$site"
assert_error invalid-call 2 publish "$site/missing"
assert_error invalid-call 2 publish "$site" --artifact art_1
assert_error invalid-call 2 publish "$site" --expected-version ver_1
assert_error invalid-call 2 publish "$site" --name
assert_error invalid-call 2 publish "$site" --name --public
assert_error invalid-call 2 publish "$site" --name ''
assert_error invalid-call 2 publish "$site" --public
assert_error invalid-call 2 publish "$site" --name report --artifact art_1 --expected-version ver_1

scenario 'an absent configuration prints unconfigured and exits 0 without the CLI'
: > "$calls"
output="$(HOME="$FIXTURE_ROOT/empty" XDG_CONFIG_HOME="$FIXTURE_ROOT/empty/config" PATH="$stub_bin:$PATH" "$SCRIPTS/publish.sh" "$site")"
[[ "$output" == '{"status":"unconfigured"}' ]] || fail "unexpected result: $output"
[[ ! -s "$calls" ]] || fail 'CLI ran without configuration'

scenario 'a token file that is missing is a configuration error'
mv "$home/token" "$home/token.away"
assert_error configuration 3 publish "$site"
mv "$home/token.away" "$home/token"

scenario 'a configuration without a usable server or tokenFile is a configuration error'
saved="$(<"$config_dir/artifact-server.json")"
for bad in '{"tokenFile":"/x"}' '{"server":"ftp://x","tokenFile":"/x"}' '{"server":"https://x/api","tokenFile":"/x"}' '{"server":"https://x"}' '{"server":"https://x","tokenFile":"relative"}' 'not json'; do
  printf '%s\n' "$bad" > "$config_dir/artifact-server.json"
  assert_error configuration 3 publish "$site"
done
printf '%s\n' "$saved" > "$config_dir/artifact-server.json"

scenario 'a missing artifactserver is a dependency error'
jq_only="$FIXTURE_ROOT/jq-only"; mkdir "$jq_only"; ln -s "$(command -v jq)" "$jq_only/jq"
assert_error dependency 4 env HOME="$home" XDG_CONFIG_HOME="$home/config" PATH="$jq_only" "$(command -v bash)" "$SCRIPTS/publish.sh" "$site"

scenario 'a CLI failure is a publication error carrying the CLI message'
status=0; output="$(STUB_FAIL='The publication input could not be read.' publish "$site")" || status=$?
[[ "$status" -eq 5 && "$(jq -r .category <<<"$output")" == publication ]] || fail "expected publication error: $output"
[[ "$(jq -r .message <<<"$output")" == *'could not be read'* ]] || fail "CLI message lost: $output"

scenario 'render-check.sh runs the script under the pinned Playwright through npx'
: > "$calls"
PATH="$stub_bin:$PATH" "$SCRIPTS/render-check.sh" art_1 --out x.png
[[ "$(<"$calls")" == "npx -y -p playwright@1.64.1 node $SCRIPTS/render-check.mjs art_1 --out x.png" ]] \
  || fail "unexpected npx call: $(<"$calls")"

scenario 'render-check.mjs parses'
node --check "$SCRIPTS/render-check.mjs" || fail 'render-check.mjs has a syntax error'

scenario 'render-check.mjs takes its server and token from the host configuration'
bare_path="$(dirname "$(command -v node)"):/usr/bin:/bin"
render() { HOME="$home" XDG_CONFIG_HOME="$home/config" PATH="$bare_path" node "$SCRIPTS/render-check.mjs" "$@" 2>&1; }
status=0; output="$(render art_00000000-0000-0000-0000-000000000000)" || status=$?
[[ "$output" == *'playwright not found'* ]] || fail "host configuration not applied: $output"
status=0; output="$(HOME="$FIXTURE_ROOT/empty" XDG_CONFIG_HOME="$FIXTURE_ROOT/empty/config" PATH="$bare_path" node "$SCRIPTS/render-check.mjs" art_00000000-0000-0000-0000-000000000000 2>&1)" || status=$?
[[ "$status" -eq 2 && "$output" == *'host configuration'* ]] || fail "missing configuration not reported: $output"

scenario 'render-check.mjs exits 0 for a clean page, 1 for a broken page, and 3 when the check cannot run'
fake_pw="$FIXTURE_ROOT/fake-pw/node_modules"; mkdir -p "$fake_pw/.bin" "$fake_pw/playwright"
cat > "$fake_pw/playwright/index.mjs" <<'FAKE'
const mode = process.env.FAKE_PW;
const handlers = {};
const page = {
  on(event, handler) { handlers[event] = handler; },
  async goto() {
    if (mode === "goto-fail") throw new Error("net::ERR_CONNECTION_REFUSED");
    if (mode === "page-error") handlers.pageerror?.(new Error("boom"));
    if (mode === "favicon") handlers.console?.({type: () => "error", text: () => "404", location: () => ({url: "https://x.example/favicon.ico"})});
    return {status: () => 200};
  },
  async waitForLoadState() {},
  async screenshot() {},
  url: () => "https://x.example/",
};
export const chromium = {
  async launch() {
    if (mode === "launch-fail") throw new Error("no browser");
    return {newContext: async () => ({newPage: async () => page}), close: async () => {}};
  },
};
FAKE
check_page() { FAKE_PW="$1" PATH="$fake_pw/.bin:$bare_path" node "$SCRIPTS/render-check.mjs" https://x.example/ --out "$FIXTURE_ROOT/out.png" 2>&1; }
status=0; check_page clean >/dev/null || status=$?; [[ "$status" -eq 0 ]] || fail "clean page exited $status"
status=0; check_page favicon >/dev/null || status=$?; [[ "$status" -eq 0 ]] || fail "favicon 404 failed the check ($status)"
status=0; output="$(check_page page-error)" || status=$?
[[ "$status" -eq 1 && "$output" == *boom* ]] || fail "page error exited $status: $output"
for mode in launch-fail goto-fail; do
  status=0; output="$(check_page "$mode")" || status=$?
  [[ "$status" -eq 3 && "$(jq -r .status <<<"$output")" == error ]] || fail "$mode exited $status: $output"
done

printf 'ok\n'
