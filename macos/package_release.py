"""Producer helper: create a clean Mac handoff ZIP from current tracked/unignored source."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".runtime/releases/SmartBin-Mac-Demo.zip"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
required = ["Install-Mac.command", "Start-Mac.command", "Stop-Mac.command", "Status-Mac.command",
            "macos/setup.sh", "macos/images.lock.json", "history/twin_history/__main__.py", "docs/SmartBin-MacBook-Guide.pdf"]
raw = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard", "-z"])
paths = sorted(set(raw.decode("utf-8").split("\0")) - {""})
manifest = {"prepared_date": "2026-11-25", "root_folder": "SmartBinDemo", "files": []}


def add(archive, relative, data):
    entry = zipfile.ZipInfo("SmartBinDemo/" + relative, (2026, 11, 25, 12, 0, 0))
    entry.create_system = 3
    executable = relative.endswith((".sh", ".command"))
    entry.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
    entry.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(entry, data)


with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for relative in paths:
        path = ROOT / relative
        parts = PurePosixPath(relative).parts
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            continue
        if any(part in (".git", "node_modules", ".venv", ".runtime", ".data", ".results", ".impeccable", "__pycache__", "exports", "ditto") for part in parts):
            raise ValueError("Local-only content must not enter the archive: " + relative)
        data = path.read_bytes()
        if relative.endswith((".sh", ".command")):
            data = data.replace(b"\r\n", b"\n")
        add(archive, relative, data)
        manifest["files"].append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    included = {item["path"] for item in manifest["files"]}
    if not set(required) <= included:
        raise ValueError("Missing handoff files: " + ", ".join(sorted(set(required) - included)))
    add(archive, "release-manifest.json", json.dumps(manifest, indent=2).encode() + b"\n")
with zipfile.ZipFile(OUTPUT) as archive:
    if archive.testzip() is not None:
        raise ValueError("ZIP integrity check failed.")
    for title in ("Install", "Start", "Stop", "Status"):
        entry = archive.getinfo("SmartBinDemo/" + title + "-Mac.command")
        if not (entry.external_attr >> 16) & stat.S_IXUSR:
            raise ValueError("The Mac launcher is not executable in the archive.")
digest = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
OUTPUT.with_suffix(".zip.sha256").write_text(digest + "  " + OUTPUT.name + "\n", encoding="utf-8")
print(json.dumps({"archive": str(OUTPUT), "source_files": len(manifest["files"]), "bytes": OUTPUT.stat().st_size, "sha256": digest}, indent=2))
