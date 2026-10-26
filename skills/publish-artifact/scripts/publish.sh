#!/usr/bin/env bash
# Publish a file or directory through the artifact-server CLI. Prints the CLI's
# JSON, `{"status":"unconfigured"}` without host configuration, or one error
# object with a nonzero exit: 2 invalid-call, 3 configuration, 4 dependency,
# 5 publication.
set -euo pipefail

fail() {
  jq -cn --arg category "$1" --arg message "$2" '{status: "error", category: $category, message: $message}' 2>/dev/null \
    || printf '{"status":"error","category":"%s","message":"%s"}\n' "$1" "$2"
  exit "$3"
}

source_path='' name='' artifact='' expected_version=''
while (($#)); do
  case "$1" in
    --name|--artifact|--expected-version)
      (($# >= 2)) || fail invalid-call "$1 needs a value" 2
      [[ -n "$2" && "$2" != -* ]] || fail invalid-call "$1 needs a value that does not start with a dash" 2
      case "$1" in
        --name) name="$2" ;;
        --artifact) artifact="$2" ;;
        --expected-version) expected_version="$2" ;;
      esac
      shift 2 ;;
    -*) fail invalid-call "unknown option $1" 2 ;;
    *)
      [[ -z "$source_path" ]] || fail invalid-call 'expected exactly one path' 2
      source_path="$1"; shift ;;
  esac
done
[[ -n "$source_path" ]] || fail invalid-call 'usage: publish.sh <path> [--name <name>] [--artifact <id> --expected-version <version-id>]' 2
[[ -e "$source_path" ]] || fail invalid-call 'path does not exist' 2
[[ -z "$artifact" && -z "$expected_version" || -n "$artifact" && -n "$expected_version" ]] \
  || fail invalid-call '--artifact and --expected-version go together' 2
[[ -z "$artifact" || -z "$name" ]] || fail invalid-call '--name applies only to a new artifact' 2

config_home="${XDG_CONFIG_HOME:-}"
[[ "$config_home" == /* ]] || config_home="${HOME:-}/.config"
config="$config_home/faviann-skills/artifact-server.json"
if [[ ! -e "$config" && ! -L "$config" ]]; then
  printf '{"status":"unconfigured"}\n'
  exit 0
fi
[[ -f "$config" && -r "$config" ]] || fail configuration 'artifact-server.json is not a readable regular file' 3

command -v jq >/dev/null 2>&1 || fail dependency 'jq is required' 4
server="$(jq -er '.server | select(type == "string" and test("^https?://[^/?#]+/?$"))' "$config" 2>/dev/null)" \
  || fail configuration 'artifact-server.json needs a "server" origin such as https://host' 3
token_file="$(jq -er '.tokenFile | select(type == "string" and startswith("/"))' "$config" 2>/dev/null)" \
  || fail configuration 'artifact-server.json needs a "tokenFile" absolute path' 3
[[ -f "$token_file" && -r "$token_file" ]] || fail configuration "token file $token_file is missing or unreadable" 3
command -v artifactserver >/dev/null 2>&1 || fail dependency 'artifactserver is not on PATH' 4

args=(publish --server "$server" --token-file "$token_file")
[[ -z "$name" ]] || args+=(--name "$name")
[[ -z "$artifact" ]] || args+=(--artifact "$artifact" --expected-version "$expected_version")

stderr_file="$(mktemp)"
trap 'rm -f "$stderr_file"' EXIT
if output="$(artifactserver "${args[@]}" -- "$source_path" 2>"$stderr_file")"; then
  printf '%s\n' "$output"
else
  fail publication "$(<"$stderr_file")" 5
fi
