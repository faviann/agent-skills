#!/bin/sh

if [ -z "${BASH_VERSION:-}" ]; then
  if command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
  fi
  printf '{"status":"error","category":"dependency","message":"Bash is required"}\n'
  exit 4
fi

set -euo pipefail
set +f
shopt -u failglob

fixed_error() {
  local category="$1" message="$2" code="$3"
  printf '{"status":"error","category":"%s","message":"%s"}\n' "$category" "$message"
  exit "$code"
}

[[ "$#" -eq 4 || "$#" -eq 5 ]] \
  || fixed_error invalid-call 'expected producer, slug, absolute source file or directory, relative primary path, and optional title' 2
producer="$1"; slug="$2"; source_path="$3"; primary_path="$4"
title_given=false; title=''
if [[ "$#" -eq 5 ]]; then title_given=true; title="$5"; fi

[[ "$producer" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] \
  || fixed_error invalid-call 'producer must be a lowercase slug' 2
[[ "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] \
  || fixed_error invalid-call 'slug must be a lowercase slug' 2
# Remove trailing directory syntax without resolving the source entry itself.
while [[ "$source_path" != / && ( "$source_path" == */ || "$source_path" == */. ) ]]; do
  source_path="${source_path%/}"; source_path="${source_path%/.}"
  [[ -n "$source_path" ]] || source_path=/
done
[[ "$source_path" == /* && ( -f "$source_path" || -d "$source_path" ) && ! -L "$source_path" ]] \
  || fixed_error invalid-call 'source must be an absolute regular file or directory, not a symlink' 2
safe_relative_path() {
  [[ -n "$1" && "$1" != /* && "$1" != */ && "$1" != *//* &&
     "/$1/" != */./* && "/$1/" != */../* && ! "$1" =~ [[:cntrl:]] ]]
}
safe_relative_path "$primary_path" \
  || fixed_error invalid-call 'primary must be a relative path without traversal or control characters' 2
if [[ -f "$source_path" ]]; then
  [[ "$primary_path" == "${source_path##*/}" ]] \
    || fixed_error invalid-call 'primary name must match the source filename' 2
else
  [[ -f "$source_path/$primary_path" && ! -L "$source_path/$primary_path" ]] \
    || fixed_error invalid-call 'primary must identify a regular file inside the source directory' 2
fi

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
gallery=''
if ! gallery_configured="$(jq -r 'has("gallery")' <<<"$config_json")"; then
  json_error dependency 'jq failed while reading configured gallery' 4
fi
if [[ "$gallery_configured" == true ]]; then
  if ! gallery="$(jq -r 'if (.gallery | type) == "string" then .gallery else "" end' <<<"$config_json")"; then
    json_error dependency 'jq failed while reading configured gallery' 4
  fi
  [[ "$gallery" =~ ^[A-Za-z0-9_-]{16,}$ ]] \
    || json_error configuration 'gallery must be one path segment of at least 16 letters, digits, underscores, or hyphens' 3
fi

required_commands=(uname realpath iconv date od tr mkdir cp mv rm sed jq flock)
for dependency in "${required_commands[@]}"; do
  command -v "$dependency" >/dev/null 2>&1 \
    || json_error dependency "required Linux command is unavailable: $dependency" 4
done
[[ "$(uname -s 2>/dev/null)" == Linux ]] \
  || json_error dependency 'publish-artifact supports Linux only' 4
[[ -r /dev/urandom ]] || json_error dependency '/dev/urandom is required' 4

valid_utf8() { printf '%s' "$1" | iconv -f UTF-8 -t UTF-8 >/dev/null 2>&1; }
valid_utf8 "$primary_path" || json_error invalid-call 'primary name must be valid UTF-8' 2
[[ ! "$primary_path" =~ [[:cntrl:]] ]] || json_error invalid-call 'primary name must not contain control characters' 2
if [[ "$title_given" == true ]]; then
  valid_utf8 "$title" || json_error invalid-call 'title must be valid UTF-8' 2
  if ! title_valid="$(jq -rn --arg title "$title" '$title | length > 0 and length <= 200 and (test("\\p{Cc}") | not)')"; then
    json_error dependency 'jq failed while validating the title' 4
  fi
  [[ "$title_valid" == true ]] \
    || json_error invalid-call 'title must be 1 to 200 characters without control characters' 2
fi

if ! script_path="$(realpath -e -- "${BASH_SOURCE[0]}" 2>/dev/null)" ||
   ! viewer_html="$(<"${script_path%/*/*}/assets/viewer.html")" ||
   ! gallery_html="$(<"${script_path%/*/*}/assets/gallery.html")"; then
  json_error dependency 'bundled viewer assets could not be read' 4
fi

if ! canonical_root="$(realpath -e -- "$configured_root" 2>/dev/null)"; then
  json_error configuration 'configured directory could not be canonicalized' 3
fi
[[ -d "$canonical_root" && ! -L "$canonical_root" ]] \
  || json_error configuration 'canonical configured root must be a directory' 3
root_prefix="${canonical_root%/}/"

if ! canonical_source="$(realpath -e -- "$source_path" 2>/dev/null)"; then
  json_error invalid-call 'source could not be canonicalized' 2
fi
if [[ "$canonical_source" == "$canonical_root" ||
      "$canonical_source" == "$root_prefix"* ||
      "$canonical_root" == "${canonical_source%/}/"* ]]; then
  json_error invalid-call 'source and publishing root must not overlap' 2
fi

# Validate the complete prepared tree before allocating a version. Keep the
# source unchanged during publication; this inventory is also the copy set.
source_entries=(); source_types=()
validate_tree() {
  local directory="$1" prefix="$2" entry relative
  [[ -r "$directory" && -x "$directory" ]] \
    || json_error publication 'source directory could not be read' 5
  for entry in "$directory"/*; do
    relative="$prefix${entry##*/}"
    safe_relative_path "$relative" && valid_utf8 "$relative" \
      || json_error invalid-call 'source paths must be relative, control-free valid UTF-8 without traversal' 2
    [[ ! -L "$entry" ]] || json_error invalid-call 'source symlinks are not supported' 2
    source_entries+=("$relative")
    if [[ -d "$entry" ]]; then
      source_types+=(directory)
      validate_tree "$entry" "$relative/"
    elif [[ -f "$entry" ]]; then
      source_types+=(file)
    else
      json_error invalid-call 'source contains an entry other than a regular file or directory' 2
    fi
  done
}
if [[ -d "$source_path" ]]; then
  shopt -s dotglob nullglob
  validate_tree "$source_path" ''
  shopt -u dotglob nullglob
else
  source_entries+=("$primary_path"); source_types+=(file)
fi

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
      if [[ "${canonical_common##*/}" == .git || "${canonical_common##*/}" == .bare ]]; then
        primary_checkout="${canonical_common%/*}"
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

[[ -z "$gallery" || "$repository_group" != "$gallery" ]] \
  || json_error invalid-call 'repository grouping collides with the configured gallery' 2

if ! published_at="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"; then
  json_error dependency 'UTC timestamp generation failed' 4
fi
if ! suffix="$(od -An -N12 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n')"; then
  json_error dependency 'random suffix generation failed' 4
fi
[[ "${#suffix}" -eq 24 && "$suffix" =~ ^[0-9a-f]{24}$ ]] \
  || json_error dependency 'random suffix generation failed' 4

replace_file() {
  local temporary="${1%/*}/.${1##*/}.tmp"
  printf '%s\n' "$2" > "$temporary" && mv -T -- "$temporary" "$1"
}

rebuild_gallery() {
  local gallery_directory="$root_prefix$gallery" file relative entry entries='' listing
  ensure_owned_directory "$gallery_directory" || return 1
  shopt -s dotglob nullglob
  for file in "$root_prefix"*/*/*/artifact.json; do
    relative="${file#"$root_prefix"}"; relative="${relative%/artifact.json}"
    [[ "$(realpath -e -- "$file" 2>/dev/null)" == "$file" ]] || continue
    entry="$(jq -c --arg base "$base_url" --arg path "$relative" '
      . as $artifact | ($path | split("/")) as [$repository, $producer, $id]
      | select(.schema == 1 and (.slug | type) == "string" and (.title | type) == "string"
          and (.versions | type) == "array" and (.versions | length) > 0
          and ($id | startswith($artifact.slug + "-"))
          and ($id[($artifact.slug | length) + 1:] | test("^[0-9a-f]{24}$")))
      | {repository: $repository, producer: $producer, slug: .slug, title: .title,
         url: "\($base)/\($path | split("/") | map(@uri) | join("/"))/",
         versions: (.versions | length), updatedAt: .versions[-1].publishedAt}
    ' "$file" 2>/dev/null)" || continue
    [[ -z "$entry" ]] || entries+="$entry"$'\n'
  done
  shopt -u dotglob nullglob
  listing="$(jq -s 'sort_by(.updatedAt) | reverse' <<<"$entries")" || return 1
  replace_file "$gallery_directory/index.html" "$gallery_html" &&
    replace_file "$gallery_directory/gallery.json" "$listing"
}

# Slug lookup, version numbering, the latest swap, and the gallery scan all read
# state that concurrent publications write, so one root lock serializes them.
if ! { exec {lock_fd}<"$canonical_root"; } 2>/dev/null; then
  json_error publication 'publishing root could not be opened for locking' 5
fi
flock -w 60 "$lock_fd" >/dev/null 2>&1 \
  || json_error publication 'publication lock was not acquired within 60 seconds' 5

repository_directory="$root_prefix$repository_group"
producer_directory="$repository_directory/$producer"
ensure_owned_directory "$repository_directory" \
  || json_error publication 'repository grouping is not a real usable directory' 5
ensure_owned_directory "$producer_directory" \
  || json_error publication 'producer grouping is not a real usable directory' 5

artifact_directory=''
shopt -s nullglob
for candidate in "$producer_directory/$slug"-*; do
  [[ "${candidate##*/}" =~ ^$slug-[0-9a-f]{24}$ ]] || continue
  [[ -z "$artifact_directory" ]] || json_error publication 'more than one artifact directory uses this slug' 5
  [[ -d "$candidate" && ! -L "$candidate" ]] || json_error publication 'artifact is not a real directory' 5
  artifact_directory="$candidate"
done
shopt -u nullglob
artifact_created=false
if [[ -z "$artifact_directory" ]]; then
  artifact_directory="$producer_directory/$slug-$suffix"
  mkdir -- "$artifact_directory" >/dev/null 2>&1 \
    || json_error publication 'artifact directory could not be allocated' 5
  artifact_created=true
fi

metadata_path="$artifact_directory/artifact.json"
latest_path="$artifact_directory/latest"
latest_staging="$artifact_directory/.latest-staging"
previous_metadata=''
if [[ -e "$metadata_path" || -L "$metadata_path" ]]; then
  if [[ ! -f "$metadata_path" || -L "$metadata_path" ]] || ! previous_metadata="$(<"$metadata_path")"; then
    json_error publication 'artifact metadata is not a readable regular file' 5
  fi
  jq -e '
    type == "object" and .schema == 1 and (.title | type) == "string" and (.versions | type) == "array" and
    all(.versions[]; (.version | type) == "number" and .version >= 1 and .version == (.version | floor))
  ' >/dev/null 2>&1 <<<"$previous_metadata" \
    || json_error publication 'artifact metadata is not valid schema 1 metadata' 5
fi

version_directory=''
metadata_committed=false; latest_exchanged=false; latest_created=false
# Every failure restores the previous metadata, latest copy, and gallery, so an
# error result never leaves a new version visible.
publication_failure() {
  local message="$1" residual=''
  if [[ "$artifact_created" == true ]]; then
    rm -rf -- "$artifact_directory" >/dev/null 2>&1 || residual="$artifact_directory"
  else
    if [[ "$latest_exchanged" == true ]]; then
      mv --exchange -T -- "$latest_staging" "$latest_path" >/dev/null 2>&1 || residual="$latest_path"
    elif [[ "$latest_created" == true ]]; then
      rm -rf -- "$latest_path" >/dev/null 2>&1 || residual="$latest_path"
    fi
    if [[ "$metadata_committed" == true && -n "$previous_metadata" ]]; then
      replace_file "$metadata_path" "$previous_metadata" >/dev/null 2>&1 || residual="$metadata_path"
    elif [[ "$metadata_committed" == true ]]; then
      rm -f -- "$metadata_path" >/dev/null 2>&1 || residual="$metadata_path"
    fi
    if [[ -n "$version_directory" ]]; then
      rm -rf -- "$latest_staging" "$version_directory" >/dev/null 2>&1 || residual="$version_directory"
    fi
  fi
  if [[ "$metadata_committed" == true && -n "$gallery" ]]; then
    rebuild_gallery >/dev/null 2>&1 || residual="$root_prefix$gallery"
  fi
  if [[ -n "$residual" ]]; then
    json_error publication "$message; cleanup also failed" 5 "$residual"
  fi
  json_error publication "$message" 5
}

if ! version="$(jq -r '(.versions // [] | map(.version) | max // 0) + 1' <<<"${previous_metadata:-null}")"; then
  publication_failure 'version number could not be allocated'
fi
next_version="$artifact_directory/v$version"
# A crash between copying and recording a version leaves an unrecorded directory.
if [[ -e "$next_version" || -L "$next_version" ]]; then
  rm -rf -- "$next_version" >/dev/null 2>&1 \
    || json_error publication 'unrecorded version directory could not be removed' 5 "$next_version"
fi
mkdir -- "$next_version" >/dev/null 2>&1 \
  || publication_failure 'version directory could not be allocated'
version_directory="$next_version"

destination="$version_directory/$primary_path"
for index in "${!source_entries[@]}"; do
  relative="${source_entries[index]}"
  entry_destination="$version_directory/$relative"
  if [[ "${source_types[index]}" == directory ]]; then
    ensure_owned_directory "$entry_destination" \
      || publication_failure 'source directory could not be copied'
  else
    entry_source="$source_path"
    [[ ! -d "$source_path" ]] || entry_source="$source_path/$relative"
    if ! cp -P -T -- "$entry_source" "$entry_destination" >/dev/null 2>&1; then
      publication_failure 'source file could not be copied'
    fi
    [[ -f "$entry_destination" && ! -L "$entry_destination" ]] \
      || publication_failure 'published result is not a real regular file'
  fi
  if ! canonical_entry="$(realpath -e -- "$entry_destination" 2>/dev/null)"; then
    publication_failure 'published result could not be canonicalized'
  fi
  [[ "$canonical_entry" == "$version_directory/$relative" ]] \
    || publication_failure 'published result escaped its version or traversed a symlink'
done
[[ -f "$destination" && ! -L "$destination" ]] \
  || publication_failure 'published result is not a real regular file'
if ! canonical_destination="$(realpath -e -- "$destination" 2>/dev/null)"; then
  publication_failure 'published result could not be canonicalized'
fi
[[ "$canonical_destination" == "$root_prefix"* ]] \
  || publication_failure 'published result escaped the configured root'

if ! result="$(jq -cn --arg base "$base_url" --arg artifact "${artifact_directory#"$root_prefix"}" \
  --arg primary "$primary_path" --argjson version "$version" --arg path "$canonical_destination" \
  --arg gallery "$gallery" '
  def encode: split("/") | map(@uri) | join("/");
  "\($base)/\($artifact | encode)/" as $url
  | {status: "published", url: $url, version: $version,
     versionUrl: "\($url)v\($version)/\($primary | encode)",
     latestUrl: "\($url)latest/\($primary | encode)", path: $path}
    + if $gallery == "" then {} else {galleryUrl: "\($base)/\($gallery)/"} end')"; then
  publication_failure 'published URL could not be encoded'
fi
if ! metadata="$(jq --arg repository "$repository_group" --arg producer "$producer" --arg slug "$slug" \
  --arg title "$title" --argjson titled "$title_given" --argjson version "$version" \
  --arg primary "$primary_path" --arg publishedAt "$published_at" '
  {schema: 1, repository: $repository, producer: $producer, slug: $slug,
   title: (if $titled then $title else .title // $slug end),
   versions: ((.versions // []) + [{version: $version, primary: $primary, publishedAt: $publishedAt}])}
  ' <<<"${previous_metadata:-null}")"; then
  publication_failure 'artifact metadata could not be serialized'
fi

{ rm -rf -- "$latest_staging" && cp -R -P -T -- "$version_directory" "$latest_staging"; } >/dev/null 2>&1 \
  || publication_failure 'latest copy could not be prepared'
replace_file "$artifact_directory/index.html" "$viewer_html" >/dev/null 2>&1 \
  || publication_failure 'artifact viewer could not be written'
replace_file "$metadata_path" "$metadata" >/dev/null 2>&1 \
  || publication_failure 'artifact metadata could not be written'
metadata_committed=true
if [[ -e "$latest_path" || -L "$latest_path" ]]; then
  mv --exchange -T -- "$latest_staging" "$latest_path" >/dev/null 2>&1 \
    || publication_failure 'latest version could not be swapped'
  latest_exchanged=true
else
  mv -T -- "$latest_staging" "$latest_path" >/dev/null 2>&1 \
    || publication_failure 'latest version could not be placed'
  latest_created=true
fi
if [[ -n "$gallery" ]]; then
  rebuild_gallery >/dev/null 2>&1 || publication_failure 'gallery could not be rebuilt'
fi

if ! printf '%s\n' "$result"; then
  publication_failure 'published result could not be emitted'
fi
rm -rf -- "$latest_staging" >/dev/null 2>&1 || :
