#!/bin/bash
set -euo pipefail
if [ "${1:-}" = --help ]; then
  printf 'Run on a Mac: bash macos/setup.sh\nInstalls Docker Desktop if missing, prepares dependencies, imports OWL and starts the full demo.\n'
  exit 0
fi
source "$(cd "$(dirname "$0")" && pwd -P)/common.sh"
require_mac
mkdir -p "$RUNTIME" "$ROOT/history/.data" "$ROOT/dashboard/.data" "$ROOT/exports"
trap 'code=$?; printf "\nSetup stopped. Fix the message above and rerun Install-Mac.command; committed data is preserved.\n" >&2; exit "$code"' ERR
say 'Checking this Mac'
printf 'macOS %s; %s\n' "$(sw_vers -productVersion)" "$(uname -m)"
ram="$(/usr/sbin/sysctl -n hw.memsize)"
[ "$ram" -ge 8000000000 ] || die 'This full demo needs a Mac with at least 8 GB physical memory; 16 GB is recommended.'
free_kb="$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')"
[ "$free_kb" -ge 1000000 ] || die 'Free at least 1 GB of disk space before starting services or installing anything.'
if [ ! -f "$COMPOSE_FILE" ]; then
  [ "$free_kb" -ge 20000000 ] || die 'Free at least 20 GB for the initial demo images and databases, even if Docker is already installed.'
fi
architecture="$(uname -m)"
if [ "$(/usr/sbin/sysctl -n hw.optional.arm64 2>/dev/null || true)" = 1 ]; then architecture=arm64; fi
case "$architecture" in arm64) docker_arch=arm64 ;; x86_64) docker_arch=amd64 ;; *) die 'Expected an Apple Silicon or Intel Mac.' ;; esac
installation="$(docker_install_state)"
case "$installation" in
  running) say 'Reusing the running local Docker engine; Docker installation skipped' ;;
  installed-stopped) say 'Docker Desktop is already installed; installation skipped' ;;
  missing)
  [ "$free_kb" -ge 20000000 ] || die 'Free at least 20 GB for a first Docker installation and demo images, then rerun.'
  say "Downloading Docker Desktop for $architecture from Docker's official server"
  /usr/bin/curl --fail --location --retry 3 --connect-timeout 20 --max-time 3600 \
    "https://desktop.docker.com/mac/main/$docker_arch/Docker.dmg" -o "$RUNTIME/Docker.dmg.download"
  mv "$RUNTIME/Docker.dmg.download" "$RUNTIME/Docker.dmg"
  mountpoint="$RUNTIME/docker-installer"
  mkdir -p "$mountpoint"
  hdiutil attach -quiet -nobrowse -readonly -mountpoint "$mountpoint" "$RUNTIME/Docker.dmg"
  trap 'hdiutil detach -quiet "$mountpoint" >/dev/null 2>&1 || true' EXIT
  printf '\nThe official Docker installer now needs your Mac administrator password.\n'
  sudo "$mountpoint/Docker.app/Contents/MacOS/install" --user "$(id -un)"
  hdiutil detach -quiet "$mountpoint"
  trap - EXIT
  # The CLI may not yet have been linked into PATH by Docker's first launch.
  DOCKER_BIN=''
  ;;
  *) die 'Could not classify the local Docker installation.' ;;
esac
wait_docker
resources
revision="$(tr -d '\r\n' < "$MACOS_DIR/upstream-revision.txt")"
[[ "$revision" =~ ^[0-9a-f]{40}$ ]] || die 'Invalid pinned Ditto revision.'
upstream="$RUNTIME/ditto-$revision"
if [ ! -f "$upstream/.download-complete" ] || [ ! -f "$upstream/deployment/docker/docker-compose.yml" ] || [ ! -f "$upstream/deployment/docker/nginx.conf" ]; then
  say 'Downloading the pinned Eclipse Ditto deployment files'
  /usr/bin/curl --fail --location --retry 3 --connect-timeout 20 --max-time 1800 \
    "https://codeload.github.com/eclipse-ditto/ditto/tar.gz/$revision" -o "$RUNTIME/ditto.tar.gz.download"
  mv "$RUNTIME/ditto.tar.gz.download" "$RUNTIME/ditto.tar.gz"
  mkdir -p "$upstream"
  /usr/bin/tar -xzf "$RUNTIME/ditto.tar.gz" --strip-components=1 -C "$upstream"
  touch "$upstream/.download-complete"
else
  printf 'Reusing cached Eclipse Ditto deployment files.\n'
fi
printf 'DITTO_EXTERNAL_PORT=8090\n' > "$RUNTIME/ditto.env"
say 'Preparing the isolated Docker stack and persistent database mounts'
docker_cli compose --project-name "$PROJECT" --project-directory "$upstream/deployment/docker" \
  --env-file "$RUNTIME/ditto.env" -f "$upstream/deployment/docker/docker-compose.yml" config --format json > "$RUNTIME/base-compose.json"
python_image="$(tr -d '\r\n' < "$MACOS_DIR/python-image.txt")"
case "$python_image" in python:3.12-slim-bookworm@sha256:*) ;; *) die 'Invalid pinned Python image.' ;; esac
ensure_image "$python_image"
docker_cli run --rm --network none --user "$(id -u):$(id -g)" -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$ROOT:/workspace" "$python_image" python /workspace/macos/prepare_stack.py \
  --base /workspace/.runtime/mac/base-compose.json --root "$ROOT" --output /workspace/.runtime/mac/compose.json
dc config --quiet
say 'Checking cached images and app runtimes'
while IFS= read -r required_image; do
  [ -n "$required_image" ] && ensure_image "$required_image"
done < "$RUNTIME/required-images.txt"
ensure_app_image dashboard smartbin-mac-node:local "$(tr -d '\r\n' < "$RUNTIME/node-fingerprint")"
ensure_app_image history smartbin-mac-python:local "$(tr -d '\r\n' < "$RUNTIME/python-fingerprint")"
say 'Starting Ditto, its database and native MQTT broker'
dc up -d --no-build --pull never mongodb policies things things-search connectivity gateway ditto-ui swagger-ui nginx mqtt
wait_ditto
provision="$(tr -d '\r\n' < "$RUNTIME/provision-fingerprint")"
previous_provision="$(cat "$RUNTIME/provision-complete" 2>/dev/null || true)"
if [ "$provision" = "$previous_provision" ] && dc run --rm --no-deps -T dashboard node macos/check.mjs --check-provisioned; then
  say 'Reusing the existing ontology model and native MQTT configuration'
else
  say 'Importing missing or changed model setup from the supplied OWL source'
  dc run --rm --no-deps -T history python /app/ontology/import_ontology.py --demo
  say 'Configuring missing or changed Ditto native MQTT setup'
  dc run --rm --no-deps -T dashboard node macos/check.mjs --configure
fi
say 'Starting the spoofer, warehouse dashboard and Python Thing-history service'
dc up -d --no-build --pull never dashboard simulator history
say 'Seeding only missing readings and checking the complete Thing-to-Python pipeline'
dc exec -T dashboard node macos/check.mjs --seed-missing --report
printf '%s\n' "$provision" > "$RUNTIME/provision-complete"
printf '\nSetup complete. Future use: Start-Mac.command. Stop-Mac.command preserves your databases.\n'
open_tools
