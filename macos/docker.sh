#!/bin/bash
# Discovery and reuse helpers, compatible with macOS Bash 3.2.
DOCKER_BIN="${DOCKER_BIN:-}"
DOCKER_APP="${DOCKER_APP:-}"

is_docker_app() {
  [ -x "$1/Contents/Resources/bin/docker" ] || return 1
  if [ -x /usr/libexec/PlistBuddy ]; then
    [ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$1/Contents/Info.plist" 2>/dev/null || true)" = com.docker.docker ] || return 1
  fi
}
find_docker_app() {
  local candidate
  for candidate in "${SMARTBIN_DOCKER_APP:-}" /Applications/Docker.app "$HOME/Applications/Docker.app"; do
    if [ -n "$candidate" ] && is_docker_app "$candidate"; then printf '%s\n' "$candidate"; return 0; fi
  done
  if command -v mdfind >/dev/null 2>&1; then
    while IFS= read -r candidate; do
      if is_docker_app "$candidate"; then printf '%s\n' "$candidate"; return 0; fi
    done < <(mdfind "kMDItemCFBundleIdentifier == 'com.docker.docker'" 2>/dev/null || true)
  fi
  return 1
}
discover_docker_cli() {
  [ -n "$DOCKER_BIN" ] && [ -x "$DOCKER_BIN" ] && return 0
  local candidate
  candidate="$(command -v docker 2>/dev/null || true)"
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then DOCKER_BIN="$candidate"; return 0; fi
  for candidate in "$HOME/.docker/bin/docker" /usr/local/bin/docker /opt/homebrew/bin/docker; do
    if [ -x "$candidate" ]; then DOCKER_BIN="$candidate"; return 0; fi
  done
  DOCKER_APP="$(find_docker_app || true)"
  if [ -n "$DOCKER_APP" ]; then DOCKER_BIN="$DOCKER_APP/Contents/Resources/bin/docker"; return 0; fi
  return 1
}
docker_cli() {
  discover_docker_cli || die 'Docker CLI is unavailable. Run Install-Mac.command, or finish the existing Docker Desktop installation.'
  "$DOCKER_BIN" "$@"
}
require_local_engine() {
  local endpoint
  endpoint=''
  if [ -n "${DOCKER_CONTEXT:-}" ]; then
    endpoint="$(docker_cli context inspect "$DOCKER_CONTEXT" --format '{{.Endpoints.docker.Host}}' 2>/dev/null)" || die 'Cannot inspect the explicitly selected Docker context; no context was changed.'
  elif [ -n "${DOCKER_HOST:-}" ]; then
    endpoint="$DOCKER_HOST"
  else
    endpoint="$(docker_cli context inspect --format '{{.Endpoints.docker.Host}}' 2>/dev/null)" || die 'Cannot inspect the selected Docker context. Repair the existing Docker CLI; it was not replaced.'
  fi
  case "$endpoint" in
    unix://*|tcp://127.0.0.1:*|tcp://localhost:*|tcp://\[::1\]:*) ;;
    *) die "The selected Docker endpoint is remote ($endpoint). Select your local Mac engine and rerun; no context was changed." ;;
  esac
}
docker_install_state() {
  # No download, installation or daemon start occurs during this probe.
  local cli_present=0
  if discover_docker_cli; then
    cli_present=1
    require_local_engine
    if docker_cli info >/dev/null 2>&1; then printf 'running\n'; return 0; fi
  fi
  DOCKER_APP="$(find_docker_app || true)"
  if [ -n "$DOCKER_APP" ]; then
    printf 'installed-stopped\n'
  elif [ -d /Applications/Docker.app ] || [ -d "$HOME/Applications/Docker.app" ]; then
    die 'An existing Docker.app looks incomplete or incompatible. Repair it first; setup did not overwrite it.'
  elif [ "$cli_present" = 1 ]; then
    die 'Docker CLI is already installed but its local engine is stopped and Docker Desktop was not found. Start that engine, or set SMARTBIN_DOCKER_APP to your Docker.app location, then rerun; setup did not install a second Docker.'
  else
    printf 'missing\n'
  fi
}
engine_platform() {
  local architecture
  [ "$(docker_cli info --format '{{.OSType}}')" = linux ] || die 'This demo needs a Linux-container Docker engine. The existing installation was left unchanged.'
  architecture="$(docker_cli info --format '{{.Architecture}}')"
  case "$architecture" in arm64|aarch64) printf 'linux/arm64\n' ;; amd64|x86_64) printf 'linux/amd64\n' ;; *) die "Unsupported Docker engine architecture: $architecture" ;; esac
}
require_project_owner() {
  local ids first owner
  ids="$(docker_cli ps --all --quiet --filter "label=com.docker.compose.project=$PROJECT")"
  first="$(printf '%s\n' "$ids" | head -n 1)"
  [ -n "$first" ] || return 0
  owner="$(docker_cli inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$first")"
  [ "$owner" = "$COMPOSE_FILE" ] || die "An existing $PROJECT demo belongs to $owner. Run its launchers from that folder; this copy did not replace its containers or data."
}
ensure_image() {
  local image="$1" platform cached
  platform="$(engine_platform)"
  cached="$(docker_cli image inspect --format '{{.Os}}/{{.Architecture}}' "$image" 2>/dev/null || true)"
  if [ "$cached" = "$platform" ]; then
    printf 'Reusing cached image: %s\n' "${image%%@*}"
  else
    say "Downloading missing $platform image: ${image%%@*}"
    docker_cli pull --platform "$platform" "$image"
  fi
}
ensure_app_image() {
  local service="$1" image="$2" expected="$3" cached platform
  [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || die 'Invalid app source fingerprint.'
  cached="$(docker_cli image inspect --format '{{index .Config.Labels "smartbin.source-fingerprint"}}' "$image" 2>/dev/null || true)"
  platform="$(docker_cli image inspect --format '{{.Os}}/{{.Architecture}}' "$image" 2>/dev/null || true)"
  if [ "$cached" = "$expected" ] && [ "$platform" = "$(engine_platform)" ]; then
    printf 'Reusing unchanged app runtime: %s\n' "$service"
    return 0
  fi
  say "Building missing or changed app runtime: $service"
  dc build "$service"
}
