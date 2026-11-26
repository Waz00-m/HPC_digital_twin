#!/bin/bash
set -euo pipefail
if [ "${1:-}" = --help ]; then printf 'Run on a Mac: bash macos/start.sh\nStarts the installed demo and restores simulator controls from stored Thing values.\n'; exit 0; fi
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"
require_mac
[ -f "$COMPOSE_FILE" ] || die 'Run Install-Mac.command once before using Start-Mac.command.'
wait_docker
resources
say 'Starting the installed demo; database volumes and existing readings are preserved'
dc up -d --no-build --pull never mongodb policies things things-search connectivity gateway ditto-ui swagger-ui nginx mqtt
wait_ditto
dc up -d --no-build --pull never dashboard simulator history
dc exec -T dashboard node macos/check.mjs
open_tools
