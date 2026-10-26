#!/usr/bin/env bash
set -euo pipefail
exec npx -y -p playwright@1.64.1 node "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/render-check.mjs" "$@"
