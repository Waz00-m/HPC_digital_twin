"""Content fingerprints for runtime builds and ontology provisioning (not timestamps)."""
import hashlib
from pathlib import Path

EXCLUDED = {"node_modules", ".venv", ".cache", "__pycache__", ".data", ".results", ".impeccable"}


def fingerprint(root, target, images):
    root = Path(root)
    if target == "node":
        paths = [root / folder for folder in ("simulator", "dashboard", "shared", "simulation", "mqtt")]
        paths += [root / "macos/check.mjs", root / "macos/history-readiness.mjs", root / "macos/Dockerfile", root / "package.json"]
        extensions = {".js", ".mjs", ".json", ".css", ".html"}
        bases = ("node:24-bookworm-slim",)
    elif target == "python":
        paths = [root / "history/twin_history", root / "history/fetch_smartbin_data.py", root / "history/pyproject.toml", root / "ontology", root / "macos/Dockerfile"]
        extensions = {".py", ".toml", ".owl"}
        bases = ("python:3.12-slim-bookworm",)
    elif target == "provision":
        paths = [root / name for name in ("ontology/smartbin-demo.owl", "ontology/import_ontology.py", "mqtt/configure-ditto.mjs", "mqtt/incoming-mapping.js", "shared/ditto-client.mjs", "macos/check.mjs")]
        extensions, bases = {".owl", ".py", ".mjs", ".js"}, ()
    else:
        raise ValueError("Unknown fingerprint target.")
    files = set()
    for path in paths:
        for item in path.rglob("*") if path.is_dir() else [path]:
            if not item.is_file() or item.is_symlink() or any(part in EXCLUDED for part in item.relative_to(root).parts):
                continue
            if item.name == "Dockerfile" or item.suffix in extensions:
                files.add(item)
    digest = hashlib.sha256(("smartbin-mac-runtime-v1:" + target).encode())
    for image in bases:
        digest.update(images[image]["reference"].encode())
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()
