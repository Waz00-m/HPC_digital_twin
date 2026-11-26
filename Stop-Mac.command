#!/bin/bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd -P)"
if /bin/bash "$ROOT/macos/stop.sh"; then result=0; else result=$?; fi
printf '\nPress Return to close this window.\n'
read -r _ || true
exit "$result"
