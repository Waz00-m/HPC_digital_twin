#!/bin/bash
set -euo pipefail
if [ "${1:-}" = --help ] || [ "$#" -eq 0 ]; then
  printf 'Usage: bash macos/python.sh fetch|run-model|latest|export|metrics|benchmark [options]\nRuns the Python data pipeline inside the installed history container.\n'
  exit 0
fi
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"
require_mac
[ -f "$COMPOSE_FILE" ] || die 'Run Install-Mac.command first.'
require_local_engine
docker_cli info >/dev/null 2>&1 || die 'Start Docker Desktop and Start-Mac.command first.'
dc exec -T history python -m twin_history "$@"
