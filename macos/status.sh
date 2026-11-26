#!/bin/bash
set -euo pipefail
if [ "${1:-}" = --help ]; then printf 'Run on a Mac: bash macos/status.sh\nShows container state and read-only pipeline status.\n'; exit 0; fi
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"
require_mac
[ -f "$COMPOSE_FILE" ] || die 'No prepared Mac stack was found. Run Install-Mac.command.'
require_local_engine
docker_cli info >/dev/null 2>&1 || die 'Docker Desktop is not running.'
dc ps --all
if dc ps --status running --services | grep -qx dashboard; then
  dc exec -T dashboard node macos/check.mjs --status
else
  printf '\nThe dashboard is stopped. Use Start-Mac.command to start the installed stack.\n'
fi
