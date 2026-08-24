#!/bin/sh

if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
  fi
  printf '{"status":"error","category":"dependency","message":"Bash is required"}\n'
  exit 4
fi

set -euo pipefail

fixed_error() {
  local category="$1" message="$2" code="$3"
  printf '{"status":"error","category":"%s","message":"%s"}\n' "$category" "$message"
  exit "$code"
}

[[ "$#" -eq 3 ]] || fixed_error invalid-call 'expected producer, absolute source file, and relative primary name' 2
producer="$1"; source_file="$2"; primary_name="$3"

[[ "$producer" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] \
  || fixed_error invalid-call 'producer must be a lowercase slug' 2
[[ "$source_file" == /* && -f "$source_file" && ! -L "$source_file" ]] \
  || fixed_error invalid-call 'source must be an absolute regular file, not a symlink' 2
[[ -n "$primary_name" && "$primary_name" != */* && "$primary_name" != '.' && "$primary_name" != '..' ]] \
  || fixed_error invalid-call 'primary name must be one relative filename' 2
[[ "$primary_name" == "${source_file##*/}" ]] \
  || fixed_error invalid-call 'primary name must match the source filename' 2

selector_set=false
if [[ -n "${FAVIANN_SKILLS_ARTIFACT_CONFIG+x}" ]]; then
  selector_set=true
  config_path="${FAVIANN_SKILLS_ARTIFACT_CONFIG}"
  [[ -n "$config_path" ]] || fixed_error configuration 'selected artifact configuration is invalid' 3
else
  [[ -n "${HOME:-}" ]] || fixed_error configuration 'HOME is required for default artifact configuration' 3
  if [[ "${XDG_CONFIG_HOME:-}" == /* ]]; then
    config_home="$XDG_CONFIG_HOME"
  else
    config_home="$HOME/.config"
  fi
  config_path="$config_home/faviann-skills/artifacts.json"
fi

if [[ "$selector_set" == false && ! -e "$config_path" && ! -L "$config_path" ]]; then
  printf '{"status":"unconfigured"}\n'
  exit 0
fi
[[ -f "$config_path" && -r "$config_path" ]] \
  || fixed_error configuration 'artifact configuration is missing, unreadable, or not a regular file' 3

command -v jq >/dev/null 2>&1 \
  || fixed_error dependency 'jq is required when artifact publication is configured' 4
if ! jq_probe="$(jq -cn 'true' 2>/dev/null)" || [[ "$jq_probe" != true ]]; then
  fixed_error dependency 'jq is present but not operational' 4
fi

json_error() {
  local category="$1" message="$2" code="$3" residual="${4:-}"
  local escaped_category escaped_message escaped_residual
  json_escape "$category"; escaped_category="$JSON_ESCAPED"
  json_escape "$message"; escaped_message="$JSON_ESCAPED"
  if [[ -n "$residual" ]]; then
    json_escape "$residual"; escaped_residual="$JSON_ESCAPED"
    printf '{"status":"error","category":"%s","message":"%s","residualPath":"%s"}\n' \
      "$escaped_category" "$escaped_message" "$escaped_residual"
  else
    printf '{"status":"error","category":"%s","message":"%s"}\n' \
      "$escaped_category" "$escaped_message"
  fi
  exit "$code"
}

json_escape() {
  local input="$1" output='' character escaped code index
  for ((index = 0; index < ${#input}; index++)); do
    character="${input:index:1}"
    case "$character" in
      '"') output+='\"' ;;
      '\') output+='\\' ;;
      $'\b') output+='\b' ;;
      $'\f') output+='\f' ;;
      $'\n') output+='\n' ;;
      $'\r') output+='\r' ;;
      $'\t') output+='\t' ;;
      *)
        printf -v code '%d' "'$character"
        if (( code < 32 )); then
          printf -v escaped '\\u%04x' "$code"
          output+="$escaped"
        else
          output+="$character"
        fi
        ;;
    esac
  done
  JSON_ESCAPED="$output"
}

valid_ipv4() {
  local address="$1" octet
  local -a octets
  local LC_ALL=C
  IFS=. read -r -a octets <<<"$address"
  [[ "${#octets[@]}" -eq 4 ]] || return 1
  for octet in "${octets[@]}"; do
    [[ "$octet" =~ ^(0|[1-9][0-9]{0,2})$ ]] || return 1
    (( 10#$octet <= 255 )) || return 1
  done
}

count_ipv6_groups() {
  local side="$1" group
  local -a groups
  local LC_ALL=C
  if [[ -z "$side" ]]; then
    IPV6_GROUP_COUNT=0
    return 0
  fi
  [[ "$side" != :* && "$side" != *: ]] || return 1
  IFS=: read -r -a groups <<<"$side"
  for group in "${groups[@]}"; do
    [[ "$group" =~ ^[0-9A-Fa-f]{1,4}$ ]] || return 1
  done
  IPV6_GROUP_COUNT="${#groups[@]}"
}

valid_ipv6() {
  local address="$1" ipv4 left right left_count right_count
  if [[ "$address" == *.* ]]; then
    [[ "$address" == *:* ]] || return 1
    ipv4="${address##*:}"
    valid_ipv4 "$ipv4" || return 1
    address="${address%:*}:0:0"
  fi
  if [[ "$address" == *::* ]]; then
    left="${address%%::*}"
    right="${address#*::}"
    [[ "$right" != *::* ]] || return 1
    count_ipv6_groups "$left" || return 1; left_count="$IPV6_GROUP_COUNT"
    count_ipv6_groups "$right" || return 1; right_count="$IPV6_GROUP_COUNT"
    (( left_count + right_count < 8 ))
  else
    count_ipv6_groups "$address" || return 1
    (( IPV6_GROUP_COUNT == 8 ))
  fi
}

valid_authority_component() {
  local value="$1" allow_colon="$2" character escape index
  local LC_ALL=C
  [[ -n "$value" ]] || return 1
  for ((index = 0; index < ${#value}; index++)); do
    character="${value:index:1}"
    case "$character" in
      [A-Za-z0-9._~-]|'!'|'$'|'&'|"'"|'('|')'|'*'|'+'|','|';'|'=') ;;
      ':') [[ "$allow_colon" == true ]] || return 1 ;;
      '%')
        escape="${value:index+1:2}"
        [[ "${#escape}" -eq 2 && "$escape" =~ ^[0-9A-Fa-f]{2}$ ]] || return 1
        ((index += 2))
        ;;
      *) return 1 ;;
    esac
  done
}

valid_port() {
  local port="$1" numeric_port
  local LC_ALL=C
  [[ "$port" =~ ^0*([0-9]{1,5})$ ]] || return 1
  numeric_port="${BASH_REMATCH[1]}"
  (( 10#$numeric_port <= 65535 ))
}

valid_base_url() {
  local url="$1" remainder authority userinfo host_port host suffix ipv6
  [[ ! "$url" =~ [[:space:][:cntrl:]] && "$url" != *\?* && "$url" != *\#* ]] || return 1
  [[ "$url" =~ ^[Hh][Tt][Tt][Pp]([Ss])?:// ]] || return 1
  remainder="${url#*://}"
  authority="${remainder%%/*}"
  [[ -n "$authority" ]] || return 1
  host_port="$authority"
  if [[ "$authority" == *@* ]]; then
    userinfo="${authority%%@*}"
    host_port="${authority#*@}"
    [[ -n "$userinfo" && -n "$host_port" && "$host_port" != *@* ]] || return 1
    valid_authority_component "$userinfo" true || return 1
  fi
  if [[ "$host_port" == \[* ]]; then
    [[ "$host_port" == *']'* ]] || return 1
    ipv6="${host_port#\[}"; ipv6="${ipv6%%]*}"
    suffix="${host_port#*]}"
    [[ -n "$ipv6" && "$ipv6" != *'['* && "$ipv6" != *']'* ]] || return 1
    if [[ -n "$suffix" ]]; then
      [[ "$suffix" == :* ]] || return 1
      valid_port "${suffix#:}" || return 1
    fi
    valid_ipv6 "$ipv6"
  else
    [[ "$host_port" != *'['* && "$host_port" != *']'* ]] || return 1
    host="${host_port%%:*}"
    [[ -n "$host" ]] || return 1
    if [[ "$host_port" == *:* ]]; then
      suffix="${host_port#*:}"
      valid_port "$suffix" || return 1
    fi
    if [[ "$host" == *.* && "$host" =~ ^[0-9.]+$ ]]; then
      valid_ipv4 "$host"
    else
      valid_authority_component "$host" false
    fi
  fi
}

# Snapshot the selected file once. A later invocation deliberately reads it again.
if ! config_json=$(<"$config_path"); then
  json_error configuration 'artifact configuration could not be read' 3
fi
if ! jq -e '
  type == "object" and
  (.directory | type == "string") and
  (.baseUrl | type == "string")
' >/dev/null 2>&1 <<<"$config_json"; then
  json_error configuration 'artifact configuration must contain string directory and baseUrl values' 3
fi
if ! configured_root="$(jq -r .directory <<<"$config_json")"; then
  json_error dependency 'jq failed while reading configured directory' 4
fi
if ! base_url="$(jq -r .baseUrl <<<"$config_json")"; then
  json_error dependency 'jq failed while reading configured base URL' 4
fi
[[ "$configured_root" == /* && -d "$configured_root" ]] \
  || json_error configuration 'configured directory must be an existing absolute directory' 3
if ! valid_base_url "$base_url"; then
  json_error configuration 'baseUrl must be an absolute HTTP(S) URL without query or fragment' 3
fi
while [[ "$base_url" == */ ]]; do base_url="${base_url%/}"; done

required_commands=(uname realpath iconv date od tr mkdir cp rm sed jq)
for dependency in "${required_commands[@]}"; do
  command -v "$dependency" >/dev/null 2>&1 \
    || json_error dependency "required Linux command is unavailable: $dependency" 4
done
[[ "$(uname -s 2>/dev/null)" == Linux ]] \
  || json_error dependency 'publish-artifact supports Linux only' 4
[[ -r /dev/urandom ]] || json_error dependency '/dev/urandom is required' 4

valid_utf8() { printf '%s' "$1" | iconv -f UTF-8 -t UTF-8 >/dev/null 2>&1; }
valid_utf8 "$primary_name" || json_error invalid-call 'primary name must be valid UTF-8' 2
[[ ! "$primary_name" =~ [[:cntrl:]] ]] || json_error invalid-call 'primary name must not contain control characters' 2

if ! canonical_root="$(realpath -e -- "$configured_root" 2>/dev/null)"; then
  json_error configuration 'configured directory could not be canonicalized' 3
fi
[[ -d "$canonical_root" && ! -L "$canonical_root" ]] \
  || json_error configuration 'canonical configured root must be a directory' 3

repository_name="${PWD##*/}"
git_marker=''
marker_search="$PWD"
while :; do
  if [[ -e "$marker_search/.git" || -L "$marker_search/.git" ]]; then
    git_marker="$marker_search/.git"
    break
  fi
  [[ "$marker_search" == / ]] && break
  marker_search="${marker_search%/*}"
  [[ -n "$marker_search" ]] || marker_search=/
done
git_grouping_derived=false
if command -v git >/dev/null 2>&1; then
  if common_dir="$(git -C "$PWD" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)"; then
    if canonical_common="$(realpath -e -- "$common_dir" 2>/dev/null)"; then
      if [[ "${canonical_common##*/}" == .git ]]; then
        primary_checkout="${canonical_common%/.git}"
        repository_name="${primary_checkout##*/}"
      else
        repository_name="${canonical_common##*/}"
      fi
      git_grouping_derived=true
    fi
  fi
fi
if [[ "$git_grouping_derived" == false && -n "$git_marker" ]]; then
  if [[ ! -d "$git_marker" || -L "$git_marker" ]]; then
    json_error dependency 'Git is required to derive primary-checkout grouping for this worktree' 4
  fi
  repository_name="${git_marker%/.git}"
  repository_name="${repository_name##*/}"
fi
if ! repository_group="$(LC_ALL=C printf '%s' "$repository_name" \
  | sed -E 's/[^A-Za-z0-9._-]+/-/g; s/^-+//; s/-+$//')"; then
  json_error dependency 'repository grouping could not be normalized' 4
fi
[[ -n "$repository_group" && "$repository_group" != '.' && "$repository_group" != '..' ]] \
  || repository_group=repository

ensure_owned_directory() {
  local path="$1"
  if [[ -L "$path" ]]; then
    return 1
  fi
  if [[ -e "$path" ]]; then
    [[ -d "$path" ]] || return 1
  else
    mkdir -- "$path" >/dev/null 2>&1 || [[ -d "$path" && ! -L "$path" ]] || return 1
  fi
  [[ -d "$path" && ! -L "$path" ]]
}

repository_directory="$canonical_root/$repository_group"
producer_directory="$repository_directory/$producer"
ensure_owned_directory "$repository_directory" \
  || json_error publication 'repository grouping is not a real usable directory' 5
ensure_owned_directory "$producer_directory" \
  || json_error publication 'producer grouping is not a real usable directory' 5

generation_directory=''
timestamp="$(date -u +%Y%m%dT%H%M%SZ 2>/dev/null)" \
  || json_error dependency 'UTC timestamp generation failed' 4
for _ in {1..16}; do
  if ! suffix="$(od -An -N12 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n')"; then
    json_error dependency 'random suffix generation failed' 4
  fi
  [[ "${#suffix}" -eq 24 && "$suffix" =~ ^[0-9a-f]{24}$ ]] \
    || json_error dependency 'random suffix generation failed' 4
  candidate="$producer_directory/$timestamp-$suffix"
  if mkdir -- "$candidate" >/dev/null 2>&1; then
    generation_directory="$candidate"
    break
  fi
  [[ -e "$candidate" || -L "$candidate" ]] \
    || json_error publication 'generation directory could not be allocated' 5
done
[[ -n "$generation_directory" ]] \
  || json_error publication 'collision-resistant generation allocation was exhausted' 5

publication_failure() {
  local message="$1"
  if rm -rf -- "$generation_directory" >/dev/null 2>&1; then
    json_error publication "$message" 5
  else
    json_error publication "$message; cleanup also failed" 5 "$generation_directory"
  fi
}

destination="$generation_directory/$primary_name"
if ! cp -- "$source_file" "$destination" >/dev/null 2>&1; then
  publication_failure 'source file could not be copied'
fi
[[ -f "$destination" && ! -L "$destination" ]] \
  || publication_failure 'published result is not a real regular file'
if ! canonical_destination="$(realpath -e -- "$destination" 2>/dev/null)"; then
  publication_failure 'published result could not be canonicalized'
fi
[[ "$canonical_destination" == "$canonical_root/"* ]] \
  || publication_failure 'published result escaped the configured root'

relative_path="${canonical_destination#"$canonical_root/"}"
if ! encoded_path="$(jq -rn --arg path "$relative_path" '$path | split("/") | map(@uri) | join("/")')"; then
  publication_failure 'published URL could not be encoded'
fi
if ! result="$(jq -cn --arg path "$canonical_destination" --arg url "$base_url/$encoded_path" \
  '{status:"published",path:$path,url:$url}')"; then
  publication_failure 'published result could not be serialized'
fi
printf '%s\n' "$result"
