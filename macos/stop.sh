#!/bin/bash
set -euo pipefail
if [ "${1:-}" = --help ]; then printf 'Run on a Mac: bash macos/stop.sh\nStops only the smartbin-mac project, preserving database volumes and host data.\n'; exit 0; fi
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"
require_mac
[ -f "$COMPOSE_FILE" ] || die 'No Mac demo installation was found.'
require_local_engine
if ! docker_cli info >/dev/null 2>&1; then printf 'Docker is stopped already. Your data is preserved.\n'; exit 0; fi
dc stop
printf '\nSmartBin demo stopped. Database volumes and history/drafts were preserved.\n'
