#!/bin/bash
# Compatible with the Bash 3.2 shipped by macOS.
set -euo pipefail
MACOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$MACOS_DIR/.." && pwd -P)"
RUNTIME="$ROOT/.runtime/mac"
COMPOSE_FILE="$RUNTIME/compose.json"
PROJECT=smartbin-mac
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
say() { printf '\n== %s ==\n' "$*"; }
require_mac() {
  [ "$(uname -s)" = Darwin ] || die 'These launchers run on macOS. Use the existing Windows launchers on Windows.'
  [ "$(id -u)" -ne 0 ] || die 'Run this as your normal Mac account, not with sudo. The Docker installer will request admin permission when needed.'
}
source "$MACOS_DIR/docker.sh"
dc() {
  require_local_engine
  require_project_owner
  docker_cli compose --project-name "$PROJECT" -f "$COMPOSE_FILE" "$@"
}
wait_docker() {
  discover_docker_cli || die 'Docker Desktop is not installed. Run Install-Mac.command first.'
  require_local_engine
  if ! docker_cli info >/dev/null 2>&1; then
    DOCKER_APP="$(find_docker_app || true)"
    [ -n "$DOCKER_APP" ] || die 'Docker CLI is installed but its local engine is stopped and no Docker Desktop app was found. Start the existing engine, then rerun; it was not replaced.'
    open -a "$DOCKER_APP"
    say 'Complete Docker Desktop first-run screens, including its terms and any macOS permission prompts'
    printf 'Leave this Terminal open. Setup resumes when the Docker engine is running.\n'
    local deadline=$((SECONDS + 900))
    until docker_cli info >/dev/null 2>&1; do
      [ "$SECONDS" -lt "$deadline" ] || die 'Docker did not become ready. Finish Docker Desktop setup, then run this launcher again.'
      sleep 5
    done
  fi
  docker_cli compose version >/dev/null 2>&1 || die 'The existing Docker installation lacks Compose. Finish or repair Docker Desktop; it was not reinstalled.'
  local version
  version="$(docker_cli compose version --short)"; version="${version#v}"
  [ "${version%%.*}" -ge 2 ] || die 'Docker Compose v2 or newer is required. Update the existing installation; setup did not replace it.'
  engine_platform >/dev/null
  require_project_owner
}
resources() {
  local memory cpus
  memory="$(docker_cli info --format '{{.MemTotal}}')"
  cpus="$(docker_cli info --format '{{.NCPU}}')"
  [ "$memory" -ge 3500000000 ] || die 'Allocate at least 4 GB memory to Docker Desktop (6 GB preferred) in Settings > Resources, Apply & Restart, then rerun this launcher.'
  [ "$cpus" -ge 2 ] || die 'Allocate at least 2 CPU cores to Docker Desktop, Apply & Restart, then rerun.'
}
wait_ditto() {
  say 'Waiting for Ditto to become healthy (first startup may take several minutes)'
  local deadline=$((SECONDS + 900))
  until /usr/bin/curl --fail --silent --max-time 5 http://127.0.0.1:8090/health >/dev/null; do
    [ "$SECONDS" -lt "$deadline" ] || die 'Ditto is not healthy. Run Status-Mac.command and see the troubleshooting section in docs/MACBOOK-GUIDE.md.'
    sleep 5
  done
}
open_tools() {
  open 'http://127.0.0.1:4321/'
  open 'http://127.0.0.1:4318/'
  printf '\nDashboard: http://127.0.0.1:4321/\nSpoofer:   http://127.0.0.1:4318/\nHistory:   http://127.0.0.1:4322/api/metrics\nDitto:     http://127.0.0.1:8090/ui/\n'
}
