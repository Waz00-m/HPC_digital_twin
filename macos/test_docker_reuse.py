"""Exercise installer decisions with fake CLIs: no Docker installation or daemon writes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")
MOCK = r'''#!/bin/bash
printf '%s\n' "$*" >> "$CALLS"
case "$1 $2" in
  'context inspect') printf '%s\n' "${MOCK_ENDPOINT:-unix:///var/run/docker.sock}" ;;
  'info --format')
    case "$3" in *OSType*) echo linux ;; *Architecture*) echo amd64 ;; *MemTotal*) echo 8000000000 ;; *NCPU*) echo 4 ;; esac ;;
  'info ')
    if [ "${MOCK_RUNNING:-1}" = 1 ] || [ -f "$READY" ]; then exit 0; else exit 1; fi ;;
  'compose version') [ "${MOCK_COMPOSE:-1}" = 1 ] || exit 1; echo 2.35.0 ;;
  'ps --all') [ -z "${MOCK_OWNER:-}" ] || echo container-123 ;;
  'inspect --format') printf '%s\n' "${MOCK_OWNER:-}" ;;
  'image inspect')
    [ "${MOCK_IMAGE:-1}" = 1 ] || exit 1
    case "$4" in *fingerprint*) printf '%s\n' "$MOCK_FINGERPRINT" ;; *) echo linux/amd64 ;; esac ;;
  'exec fixture-nginx'|'exec fixture-dashboard'|'exec fixture-simulator') printf 'net:[1]\n' ;;
  'exec fixture-history') printf '%s\n' "${MOCK_HISTORY_NAMESPACE:-net:[1]}" ;;
esac
exit 0
'''


@unittest.skipUnless(BASH, "A Bash interpreter is needed for shell decision tests.")
class DockerReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smartbin-docker-reuse-")
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(self.root.name.startswith("smartbin-docker-reuse-"))
        self.addCleanup(self.temp.cleanup)
        self.bin = self.root / "bin"; self.bin.mkdir()
        self.calls = self.root / "calls"
        self.home = self.root / "home"; self.home.mkdir()
        self.write(self.bin / "fake-docker", MOCK)
        self.write(self.bin / "open", '#!/bin/bash\nprintf "open %s\\n" "$*" >> "$CALLS"\ntouch "$READY"\n')
        self.write(self.bin / "mdfind", '#!/bin/bash\nprintf "%s\\n" "${SPOTLIGHT_APP:-}"\n')
        self.env = {**os.environ, "HOME": self.home.as_posix(), "CALLS": self.calls.as_posix(), "READY": (self.root / "ready").as_posix(),
            "DOCKER_BIN": (self.bin / "fake-docker").as_posix(), "DOCKER_APP": "", "MOCK_RUNNING": "1", "MOCK_COMPOSE": "1", "MOCK_IMAGE": "1",
            "MOCK_FINGERPRINT": "a" * 64, "MOCK_OWNER": "", "DOCKER_HOST": "", "DOCKER_CONTEXT": "", "MOCK_ENDPOINT": "unix:///var/run/docker.sock"}
        self.env["PATH"] = self.bin.as_posix() + (";" if os.name == "nt" else ":") + os.environ["PATH"]

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n"); path.chmod(0o755)

    def app(self, folder):
        path = folder / "Docker.app"
        self.write(path / "Contents/Resources/bin/docker", MOCK)
        self.write(path / "Contents/Info.plist", '<?xml version="1.0"?><plist version="1.0"><dict><key>CFBundleIdentifier</key><string>com.docker.docker</string></dict></plist>')
        return path

    def shell(self, code, **environment):
        # Restrict app discovery to the fixture tree, even if tests run on a Mac
        # that has a real Docker.app. Actual CLI calls always go to fake-docker.
        prefix = 'source "' + (ROOT / "macos/common.sh").as_posix() + '"\n'
        prefix += 'export PATH="' + self.bin.as_posix() + ':$PATH"\n'
        prefix += 'TEST_ROOT="$(cd "$TEST_ROOT" && pwd -P)"\n'
        prefix += 'is_docker_app() { local target; target="$(cd "$1" 2>/dev/null && pwd -P)" || return 1; case "$target" in "$TEST_ROOT"/*) [ -x "$1/Contents/Resources/bin/docker" ] ;; *) return 1 ;; esac; }\n'
        result = subprocess.run([BASH, "-c", prefix + code], env={**self.env, "TEST_ROOT": self.root.as_posix(), **environment}, capture_output=True, text=True, timeout=15)
        return result, self.calls.read_text(encoding="utf-8") if self.calls.exists() else ""

    def test_running_local_engine_is_reused_without_opening_or_installing(self):
        result, calls = self.shell('docker_install_state; wait_docker')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("running", result.stdout)
        self.assertNotIn("open ", calls); self.assertNotIn("pull ", calls)

    def test_user_app_is_found_and_started_without_reinstallation(self):
        app = self.app(self.home / "Applications")
        result, calls = self.shell('docker_install_state; wait_docker', MOCK_RUNNING="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("installed-stopped", result.stdout)
        self.assertIn("open -a ", calls)
        self.assertIn("/home/Applications/Docker.app", calls.replace("\\", "/"))

    def test_custom_application_location_is_discovered(self):
        app = self.app(self.root / "Other Apps")
        result, _ = self.shell('find_docker_app', SPOTLIGHT_APP=app.as_posix())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), app.as_posix())

    def test_no_cli_or_app_reports_missing(self):
        result, calls = self.shell('discover_docker_cli() { return 1; }; docker_install_state')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "missing")
        self.assertEqual(calls, "")

    def test_remote_context_is_refused_without_switching_it(self):
        result, calls = self.shell('docker_install_state', MOCK_ENDPOINT="ssh://another-machine")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote", result.stderr)
        self.assertNotIn("context use", calls); self.assertNotIn("open ", calls)

    def test_cli_only_stopped_engine_is_not_replaced_with_another_install(self):
        result, calls = self.shell('docker_install_state', MOCK_RUNNING="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not install a second Docker", result.stderr)
        self.assertNotIn("open ", calls); self.assertNotIn("pull ", calls)

    def test_explicit_context_takes_precedence_over_docker_host(self):
        result, calls = self.shell('docker_install_state', MOCK_ENDPOINT="ssh://another-machine", DOCKER_CONTEXT="remote-context", DOCKER_HOST="unix:///var/run/docker.sock")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote", result.stderr)
        self.assertIn("context inspect remote-context", calls)

    def test_missing_compose_reports_repair_without_reinstall(self):
        result, calls = self.shell('wait_docker', MOCK_COMPOSE="0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lacks Compose", result.stderr)
        self.assertNotIn("open ", calls)

    def test_cached_image_is_skipped_and_missing_image_is_pulled(self):
        result, calls = self.shell('ensure_image example:tag@sha256:123')
        self.assertEqual(result.returncode, 0, result.stderr); self.assertNotIn("pull ", calls)
        result, calls = self.shell('ensure_image example:tag@sha256:123', MOCK_IMAGE="0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pull --platform linux/amd64", calls)

    def test_unchanged_app_is_skipped_and_changed_app_is_built(self):
        result, calls = self.shell('ensure_app_image dashboard smartbin-mac-node:local "$MOCK_FINGERPRINT"')
        self.assertEqual(result.returncode, 0, result.stderr); self.assertNotIn("build dashboard", calls)
        result, calls = self.shell('ensure_app_image dashboard smartbin-mac-node:local "' + "b" * 64 + '"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("build dashboard", calls)

    def test_another_demo_folder_is_not_replaced(self):
        result, calls = self.shell('dc up -d', MOCK_OWNER="/Users/other/SmartBinDemo/.runtime/mac/compose.json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("did not replace", result.stderr)
        self.assertNotIn("compose --project-name", calls)

    def app_start(self, **environment):
        code = '''dc() {
  printf 'dc %s\\n' "$*" >> "$CALLS"
  if [ "$1" = ps ]; then
    local last arg
    for arg in "$@"; do last="$arg"; done
    printf 'fixture-%s\\n' "$last"
  fi
}
start_apps
'''
        return self.shell(code, **environment)

    def test_running_apps_on_current_network_are_not_recreated(self):
        result, calls = self.app_start()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--force-recreate", calls)
        self.assertIn("up -d --no-build --pull never dashboard simulator history", calls)

    def test_restart_repairs_only_the_app_with_a_stale_network_attachment(self):
        result, calls = self.app_start(MOCK_HISTORY_NAMESPACE="net:[2]")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--no-deps --no-build --pull never --force-recreate history", calls)
        self.assertNotIn("--force-recreate dashboard", calls)
        self.assertNotIn("--force-recreate simulator", calls)
        self.assertNotIn("down", calls); self.assertNotIn("--volumes", calls)


if __name__ == "__main__":
    unittest.main()
