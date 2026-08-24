#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
readonly PUBLISHER="$ROOT/skills/engineering/publish-artifact/scripts/publish-artifact.sh"
readonly FIXTURE_ROOT="$(mktemp -d)"
trap 'chmod -R u+rwx "$FIXTURE_ROOT" 2>/dev/null || true; rm -rf "$FIXTURE_ROOT"' EXIT

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
scenario() { printf 'scenario: %s\n' "$1"; }
assert_json() { jq -e . >/dev/null <<<"$1" || fail "not JSON: $1"; }
assert_error() {
  local expected="$1" output="$2"
  assert_json "$output"
  [[ "$(jq -r .status <<<"$output")" == error ]] || fail "not an error: $output"
  [[ "$(jq -r .category <<<"$output")" == "$expected" ]] || fail "expected $expected error: $output"
}
write_config() {
  local path="$1" directory="$2" base_url="$3"
  mkdir -p "$(dirname "$path")"
  jq -cn --arg directory "$directory" --arg baseUrl "$base_url" \
    '{directory:$directory,baseUrl:$baseUrl,ignored:true}' > "$path"
}
invoke() {
  local cwd="$1" home="$2"; shift 2
  (cd "$cwd" && HOME="$home" XDG_CONFIG_HOME="$home/config" "$PUBLISHER" "$@")
}

source_file="$FIXTURE_ROOT/report name é.html"
printf '<h1>opaque ${SECRET}</h1>\n' > "$source_file"

scenario 'an absent default configuration is a successful unconfigured result'
home="$FIXTURE_ROOT/unconfigured-home"; repo="$FIXTURE_ROOT/unconfigured-repo"
mkdir -p "$home" "$repo"
output="$(invoke "$repo" "$home" architecture-report "$source_file" "$(basename "$source_file")")"
[[ "$output" == '{"status":"unconfigured"}' ]] || fail "unexpected result: $output"
[[ "$(wc -l <<<"$output")" -eq 1 ]] || fail 'unconfigured result was not one line'

scenario 'invalid calls have a stable category'
set +e
output="$(invoke "$repo" "$home" Bad-Slug "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'invalid producer succeeded'
assert_error invalid-call "$output"

scenario 'default configuration publishes one file and encodes its URL'
publish_root="$FIXTURE_ROOT/web root"; mkdir -p "$publish_root"
config="$home/config/faviann-skills/artifacts.json"
write_config "$config" "$publish_root" 'https://artifacts.example.test/public/'
mode_before="$(stat -c %a "$publish_root")"
owner_before="$(stat -c %u:%g "$publish_root")"
network_bin="$FIXTURE_ROOT/network-bin"; mkdir "$network_bin"
for command_name in curl wget; do
  printf '#!/usr/bin/env bash\ntouch %q\nexit 99\n' "$FIXTURE_ROOT/http-attempted" > "$network_bin/$command_name"
  chmod +x "$network_bin/$command_name"
done
output="$(cd "$repo" && HOME="$home" XDG_CONFIG_HOME="$home/config" PATH="$network_bin:$PATH" \
  "$PUBLISHER" architecture-report "$source_file" "$(basename "$source_file")")"
assert_json "$output"
[[ "$(jq -r .status <<<"$output")" == published ]] || fail "not published: $output"
published_path="$(jq -r .path <<<"$output")"; published_url="$(jq -r .url <<<"$output")"
[[ -f "$published_path" && ! -L "$published_path" ]] || fail 'published path is not a regular file'
cmp -s "$source_file" "$published_path" || fail 'published bytes changed'
[[ "$published_url" == https://artifacts.example.test/public/*/architecture-report/*/report%20name%20%C3%A9.html ]] || fail "unexpected URL: $published_url"
[[ "$(stat -c %a "$publish_root")" == "$mode_before" ]] || fail 'root mode changed'
[[ "$(stat -c %u:%g "$publish_root")" == "$owner_before" ]] || fail 'root ownership changed'
[[ ! -e "$FIXTURE_ROOT/http-attempted" ]] || fail 'publisher attempted an HTTP request'
relative_published="${published_path#"$publish_root/"}"
[[ "$relative_published" == unconfigured-repo/architecture-report/* ]] || fail 'non-Git grouping did not use invocation directory name'
generation="$(basename "$(dirname "$published_path")")"
[[ "$generation" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{24}$ ]] || fail "generation is not timestamped and collision resistant: $generation"
[[ "$(wc -l <<<"$output")" -eq 1 ]] || fail 'success result was not one line'

scenario 'a selected configuration overrides the default and is reread next invocation'
selected_root="$FIXTURE_ROOT/selected"; next_root="$FIXTURE_ROOT/next"; mkdir -p "$selected_root" "$next_root"
selected_config="$FIXTURE_ROOT/selected.json"
write_config "$selected_config" "$selected_root" 'http://localhost:8080/one/'
output="$(cd "$repo" && HOME="$home" XDG_CONFIG_HOME="$home/config" FAVIANN_SKILLS_ARTIFACT_CONFIG="$selected_config" "$PUBLISHER" prototype "$source_file" "$(basename "$source_file")")"
[[ "$(jq -r .path <<<"$output")" == "$selected_root"/* ]] || fail 'selector was ignored'
write_config "$selected_config" "$next_root" 'http://localhost:8080/two'
output="$(cd "$repo" && HOME="$home" XDG_CONFIG_HOME="$home/config" FAVIANN_SKILLS_ARTIFACT_CONFIG="$selected_config" "$PUBLISHER" prototype "$source_file" "$(basename "$source_file")")"
[[ "$(jq -r .path <<<"$output")" == "$next_root"/* ]] || fail 'changed configuration was not reread'
[[ "$(jq -r .url <<<"$output")" == http://localhost:8080/two/* ]] || fail 'base URL was not reread'

scenario 'missing selected and invalid present configurations fail as configuration errors'
for kind in missing malformed incomplete relative-root missing-root query-url fragment-url space-url empty-host invalid-authority malformed-bracket ftp-url unreadable; do
  bad="$FIXTURE_ROOT/config-$kind.json"
  case "$kind" in
    missing) ;;
    malformed) printf '{' > "$bad" ;;
    incomplete) printf '{"directory":"%s"}\n' "$publish_root" > "$bad" ;;
    relative-root) write_config "$bad" relative 'https://example.test' ;;
    missing-root) write_config "$bad" "$FIXTURE_ROOT/not-created" 'https://example.test' ;;
    query-url) write_config "$bad" "$publish_root" 'https://example.test/x?q=1' ;;
    fragment-url) write_config "$bad" "$publish_root" 'https://example.test/x#y' ;;
    space-url) write_config "$bad" "$publish_root" 'https://example.test/not encoded' ;;
    empty-host) write_config "$bad" "$publish_root" 'https://:443/base' ;;
    invalid-authority) write_config "$bad" "$publish_root" 'https://user@@example.test/base' ;;
    malformed-bracket) write_config "$bad" "$publish_root" 'https://[::::]/base' ;;
    ftp-url) write_config "$bad" "$publish_root" 'ftp://example.test/x' ;;
    unreadable) write_config "$bad" "$publish_root" 'https://example.test'; chmod 000 "$bad" ;;
  esac
  set +e
  output="$(cd "$repo" && HOME="$home" FAVIANN_SKILLS_ARTIFACT_CONFIG="$bad" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
  set -e
  [[ "$status" -ne 0 ]] || fail "$kind configuration succeeded"
  assert_error configuration "$output"
  [[ ! -e "$FIXTURE_ROOT/not-created" ]] || fail 'publisher created a configured root'
done
chmod 600 "$FIXTURE_ROOT/config-unreadable.json"

scenario 'HTTP schemes are case-insensitive'
uppercase_config="$FIXTURE_ROOT/uppercase-url.json"
write_config "$uppercase_config" "$publish_root" 'HTTPS://artifacts.example.test/base/'
output="$(cd "$repo" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$uppercase_config" \
  "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"
[[ "$(jq -r .url <<<"$output")" == HTTPS://artifacts.example.test/base/* ]] \
  || fail "uppercase HTTPS scheme was not accepted: $output"

scenario 'configured publication without jq is a dependency error'
set +e
output="$(cd "$repo" && HOME="$home" XDG_CONFIG_HOME="$home/config" PATH=/usr/bin:/bin /bin/bash "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
if [[ -x /usr/bin/jq || -x /bin/jq ]]; then
  printf '  skipped: jq exists in the restricted system PATH\n'
else
  [[ "$status" -ne 0 ]] || fail 'configured publication without jq succeeded'; assert_error dependency "$output"
fi

scenario 'a present but broken jq emits one stable dependency result'
broken_jq_bin="$FIXTURE_ROOT/broken-jq-bin"; mkdir "$broken_jq_bin"
printf '#!/usr/bin/env bash\nexit 76\n' > "$broken_jq_bin/jq"; chmod +x "$broken_jq_bin/jq"
set +e
output="$(cd "$repo" && PATH="$broken_jq_bin:$PATH" FAVIANN_SKILLS_ARTIFACT_CONFIG="$config" \
  "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'configured publication with broken jq succeeded'
assert_error dependency "$output"
[[ "$(wc -l <<<"$output")" -eq 1 ]] || fail 'broken jq did not emit exactly one JSON line'

scenario 'jq failure while serializing an error uses the dependency fallback'
serializer_jq_bin="$FIXTURE_ROOT/serializer-jq-bin"; mkdir "$serializer_jq_bin"
real_jq="$(command -v jq)"
printf '%s\n' '#!/usr/bin/env bash' \
  'for argument in "$@"; do [[ "$argument" == category ]] && exit 77; done' \
  "exec $(printf '%q' "$real_jq") \"\$@\"" > "$serializer_jq_bin/jq"
chmod +x "$serializer_jq_bin/jq"
set +e
output="$(cd "$repo" && PATH="$serializer_jq_bin:$PATH" FAVIANN_SKILLS_ARTIFACT_CONFIG="$FIXTURE_ROOT/config-empty-host.json" \
  "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'error serialization with failed jq succeeded'
assert_error dependency "$output"
[[ "$(jq -r .message <<<"$output")" == 'jq failed while serializing an error result' ]] \
  || fail "serializer fallback message changed: $output"
[[ "$(wc -l <<<"$output")" -eq 1 ]] || fail 'serializer fallback did not emit exactly one JSON line'

scenario 'a host without Bash receives a dependency result'
empty_path="$FIXTURE_ROOT/empty-path"; mkdir "$empty_path"
set +e
output="$(cd "$repo" && PATH="$empty_path" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'publication without Bash succeeded'
assert_error dependency "$output"

scenario 'a root symlink is accepted but descendant symlinks are refused'
real_root="$FIXTURE_ROOT/real-root"; root_link="$FIXTURE_ROOT/root-link"; mkdir -p "$real_root"; ln -s "$real_root" "$root_link"
symlink_config="$FIXTURE_ROOT/symlink-config.json"; write_config "$symlink_config" "$root_link" 'https://example.test/files'
output="$(cd "$repo" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$symlink_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"
[[ "$(jq -r .path <<<"$output")" == "$real_root"/* ]] || fail 'root was not canonicalized'
repo_group="$(jq -r .path <<<"$output" | sed "s#^$real_root/##" | cut -d/ -f1)"
rm -rf "$real_root/$repo_group/producer"; ln -s "$FIXTURE_ROOT" "$real_root/$repo_group/producer"
set +e
output="$(cd "$repo" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$symlink_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'descendant symlink succeeded'; assert_error publication "$output"

scenario 'linked worktrees share repository grouping and unrelated repositories do not'
git_repo="$FIXTURE_ROOT/project-main"; worktree="$FIXTURE_ROOT/branch-worktree"; other_repo="$FIXTURE_ROOT/other-project"
git init -q "$git_repo"; git -C "$git_repo" config user.email test@example.test; git -C "$git_repo" config user.name Test
printf x > "$git_repo/tracked"; git -C "$git_repo" add tracked; git -C "$git_repo" commit -qm init
git -C "$git_repo" worktree add -q -b artifact-test "$worktree"; git init -q "$other_repo"
group_root="$FIXTURE_ROOT/group-root"; mkdir "$group_root"; group_config="$FIXTURE_ROOT/group.json"; write_config "$group_config" "$group_root" 'https://example.test/group'
main_output="$(cd "$git_repo" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$group_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"
worktree_output="$(cd "$worktree" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$group_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"
other_output="$(cd "$other_repo" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$group_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"
group_of() { jq -r .path <<<"$1" | sed "s#^$group_root/##" | cut -d/ -f1; }
[[ "$(group_of "$main_output")" == "$(group_of "$worktree_output")" ]] || fail 'linked worktree grouping differs'
[[ "$(group_of "$main_output")" != "$(group_of "$other_output")" ]] || fail 'unrelated repository grouping collided'

scenario 'linked worktrees fail stably rather than grouping by worktree name when Git fails'
broken_git_bin="$FIXTURE_ROOT/broken-git-bin"; mkdir "$broken_git_bin"
printf '#!/usr/bin/env bash\nexit 74\n' > "$broken_git_bin/git"; chmod +x "$broken_git_bin/git"
set +e
output="$(cd "$worktree" && PATH="$broken_git_bin:$PATH" FAVIANN_SKILLS_ARTIFACT_CONFIG="$group_config" \
  "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'linked worktree publication with broken Git succeeded'
assert_error dependency "$output"
[[ ! -e "$group_root/branch-worktree" ]] || fail 'linked worktree basename leaked into grouping'

scenario 'linked worktrees also fail stably when Git is unavailable'
no_git_bin="$FIXTURE_ROOT/no-git-bin"; mkdir "$no_git_bin"
for dependency in bash jq uname realpath iconv date od tr mkdir cp rm sed; do
  ln -s "$(command -v "$dependency")" "$no_git_bin/$dependency"
done
mkdir "$worktree/nested-context"
set +e
output="$(cd "$worktree/nested-context" && PATH="$no_git_bin" FAVIANN_SKILLS_ARTIFACT_CONFIG="$group_config" \
  "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'linked worktree publication without Git succeeded'
assert_error dependency "$output"
[[ ! -e "$group_root/nested-context" ]] || fail 'nested worktree basename leaked into grouping'

scenario 'outside Git retains invocation-directory grouping when Git fails'
outside_root="$FIXTURE_ROOT/outside-root"; outside_repo="$FIXTURE_ROOT/outside-context"; mkdir "$outside_root" "$outside_repo"
outside_config="$FIXTURE_ROOT/outside.json"; write_config "$outside_config" "$outside_root" 'https://example.test/outside'
output="$(cd "$outside_repo" && PATH="$broken_git_bin:$PATH" FAVIANN_SKILLS_ARTIFACT_CONFIG="$outside_config" \
  "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"
[[ "$(jq -r .path <<<"$output")" == "$outside_root/outside-context/"* ]] \
  || fail "outside-Git fallback changed: $output"

scenario 'concurrent publications allocate distinct generations without overwriting'
concurrent_root="$FIXTURE_ROOT/concurrent"; mkdir "$concurrent_root"; concurrent_config="$FIXTURE_ROOT/concurrent.json"; write_config "$concurrent_config" "$concurrent_root" 'https://example.test/c'
pids=(); outputs=()
for i in $(seq 1 20); do
  result="$FIXTURE_ROOT/concurrent-$i.json"; outputs+=("$result")
  (cd "$git_repo" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$concurrent_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")" > "$result") & pids+=("$!")
done
for pid in "${pids[@]}"; do wait "$pid" || fail 'concurrent invocation failed'; done
paths="$FIXTURE_ROOT/paths"; for result in "${outputs[@]}"; do jq -r .path "$result"; done > "$paths"
[[ "$(sort -u "$paths" | wc -l)" -eq 20 ]] || fail 'generation collision occurred'
while IFS= read -r path; do cmp -s "$source_file" "$path" || fail "concurrent output changed: $path"; done < "$paths"

scenario 'random-suffix command failure is one stable dependency result'
for failed_command in od tr; do
  random_failure_bin="$FIXTURE_ROOT/random-failure-$failed_command"; mkdir "$random_failure_bin"
  printf '#!/usr/bin/env bash\nexit 75\n' > "$random_failure_bin/$failed_command"
  chmod +x "$random_failure_bin/$failed_command"
  set +e
  output="$(cd "$repo" && PATH="$random_failure_bin:$PATH" FAVIANN_SKILLS_ARTIFACT_CONFIG="$concurrent_config" \
    "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
  set -e
  [[ "$status" -ne 0 ]] || fail "publication with failed $failed_command succeeded"
  assert_error dependency "$output"
  [[ "$(wc -l <<<"$output")" -eq 1 ]] || fail "$failed_command failure did not emit exactly one JSON line"
done

scenario 'invalid source shapes and primary names are caller errors'
mkdir "$FIXTURE_ROOT/source-dir"; ln -s "$source_file" "$FIXTURE_ROOT/source-link"
check_invalid_call() {
  set +e
  output="$(cd "$repo" && FAVIANN_SKILLS_ARTIFACT_CONFIG="$config" "$PUBLISHER" "$@")"; status=$?
  set -e
  [[ "$status" -ne 0 ]] || fail "invalid call succeeded: $*"; assert_error invalid-call "$output"
}
check_invalid_call producer relative-file file
check_invalid_call producer "$FIXTURE_ROOT/source-dir" source-dir
check_invalid_call producer "$FIXTURE_ROOT/source-link" source-link
check_invalid_call producer "$source_file" wrong.html
check_invalid_call producer "$source_file" "../$(basename "$source_file")"
invalid_utf8="$FIXTURE_ROOT/invalid-"$'\xff'
printf x > "$invalid_utf8"
check_invalid_call producer "$invalid_utf8" "${invalid_utf8##*/}"

scenario 'copy failure cleans only its generation and cleanup failure reports residue'
failure_root="$FIXTURE_ROOT/failure-root"; mkdir "$failure_root"; failure_config="$FIXTURE_ROOT/failure.json"; write_config "$failure_config" "$failure_root" 'https://example.test/failure'
fake_bin="$FIXTURE_ROOT/fake-bin"; mkdir "$fake_bin"; printf '#!/usr/bin/env bash\nexit 71\n' > "$fake_bin/cp"; chmod +x "$fake_bin/cp"
mkdir "$failure_root/unrelated"; printf keep > "$failure_root/unrelated/marker"
set +e
output="$(cd "$repo" && PATH="$fake_bin:$PATH" FAVIANN_SKILLS_ARTIFACT_CONFIG="$failure_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'injected copy failure succeeded'; assert_error publication "$output"
[[ "$(jq -r '.residualPath // empty' <<<"$output")" == '' ]] || fail 'successful cleanup reported residue'
[[ -f "$failure_root/unrelated/marker" ]] || fail 'cleanup touched a sibling'
printf '#!/usr/bin/env bash\nexit 72\n' > "$fake_bin/rm"; chmod +x "$fake_bin/rm"
set +e
output="$(cd "$repo" && PATH="$fake_bin:$PATH" FAVIANN_SKILLS_ARTIFACT_CONFIG="$failure_config" "$PUBLISHER" producer "$source_file" "$(basename "$source_file")")"; status=$?
set -e
[[ "$status" -ne 0 ]] || fail 'copy plus cleanup failure succeeded'; assert_error publication "$output"
residual="$(jq -r .residualPath <<<"$output")"
[[ "$residual" == "$failure_root"/* && -d "$residual" ]] || fail "bad residual path: $residual"
[[ -f "$failure_root/unrelated/marker" ]] || fail 'failed cleanup touched a sibling'

printf 'All publish-artifact scenarios passed.\n'
