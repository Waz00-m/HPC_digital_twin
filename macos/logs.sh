#!/bin/bash
set -euo pipefail
if [ "${1:-}" = --help ]; then printf 'Usage: bash macos/logs.sh [history|dashboard|simulator|gateway|nginx|mqtt]\nPrints recent logs for this project only.\n'; exit 0; fi
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"
require_mac
[ -f "$COMPOSE_FILE" ] || die 'Run Install-Mac.command first.'
dc logs --tail 100 "$@"
