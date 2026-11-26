"""Adapt the pinned upstream Ditto deployment into one isolated, persistent Mac stack."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from fingerprint import fingerprint


def prepare(base, images, root, fingerprints=None, sample_seconds=30):
    if not isinstance(sample_seconds, int) or isinstance(sample_seconds, bool) or not 1 <= sample_seconds <= 3600:
        raise ValueError("Sample interval must be 1–3,600 whole seconds.")
    root = str(root).rstrip("/\\")
    if not root or not isinstance(base.get("services"), dict):
        raise ValueError("Provide the repository root and normalized upstream Compose JSON.")
    services = deepcopy(base["services"])
    required = {"mongodb", "policies", "things", "things-search", "connectivity", "gateway", "ditto-ui", "swagger-ui", "nginx"}
    if not required <= services.keys():
        raise ValueError("The upstream deployment no longer matches the supported service set.")
    for name, service in services.items():
        image = service["image"].removeprefix("docker.io/")
        if image not in images:
            raise ValueError("No pinned image for " + image)
        service["image"] = images[image]["reference"]
        service.pop("ports", None)
        service.pop("container_name", None)
        service["restart"] = "unless-stopped"
    services["mongodb"]["volumes"] = ["mongo-data:/data/db", "mongo-config:/data/configdb"]
    services["mongodb"]["command"] = ["mongod", "--storageEngine", "wiredTiger", "--noscripting", "--wiredTigerCacheSizeGB", "0.25"]
    services["mongodb"].setdefault("deploy", {}).setdefault("resources", {}).setdefault("limits", {})["memory"] = "512m"
    services["nginx"]["ports"] = ["127.0.0.1:8090:80", "127.0.0.1:4318:4318", "127.0.0.1:4321:4321", "127.0.0.1:4322:4322"]
    services["nginx"]["healthcheck"] = {"test": ["CMD-SHELL", "wget -q -O /dev/null http://127.0.0.1/health || exit 1"],
        "interval": "5s", "timeout": "5s", "retries": 60, "start_period": "120s"}
    services["mqtt"] = {"image": images["eclipse-mosquitto:2"]["reference"], "restart": "unless-stopped",
        "ports": ["127.0.0.1:1884:1883"], "volumes": [root + "/mqtt/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro", "mqtt-data:/mosquitto/data"],
        "networks": {"default": {"aliases": ["smartbin-mqtt"]}}, "mem_limit": "64m",
        "healthcheck": {"test": ["CMD", "mosquitto_pub", "-h", "127.0.0.1", "-t", "health/broker", "-n"], "interval": "5s", "timeout": "5s", "retries": 20}}
    environment = {"DITTO_URL": "http://127.0.0.1:80", "DITTO_NAMESPACE": "smartbin", "SMARTBIN_BIND_HOST": "0.0.0.0",
                   "MQTT_BROKER_URL": "mqtt://smartbin-mqtt:1883"}
    build_args = {"NODE_BASE": images["node:24-bookworm-slim"]["reference"], "PYTHON_BASE": images["python:3.12-slim-bookworm"]["reference"]}
    for name in ("dashboard", "simulator", "history"):
        python = name == "history"
        command = ["python", "-m", "twin_history", "serve", "--host", "0.0.0.0"] if python else ["node", name + "/server.mjs"]
        services[name] = {"image": "smartbin-mac-" + ("python" if python else "node") + ":local",
            "build": {"context": root, "dockerfile": "macos/Dockerfile", "target": "python-app" if python else "node-app", "args": build_args},
            "command": command, "network_mode": "service:nginx", "environment": dict(environment),
            "depends_on": {"nginx": {"condition": "service_healthy"}, "mqtt": {"condition": "service_healthy"}},
            "restart": "unless-stopped", "mem_limit": "256m"}
        if fingerprints:
            services[name]["build"]["labels"] = {"smartbin.source-fingerprint": fingerprints["python" if python else "node"]}
    services["history"]["environment"]["TWIN_HISTORY_DB"] = "/data/things.sqlite3"
    services["history"]["environment"]["TWIN_SAMPLE_SECONDS"] = str(sample_seconds)
    services["history"]["volumes"] = [root + "/history/.data:/data", root + "/exports:/exports", root + "/history/models:/app/history/models:ro"]
    services["dashboard"]["volumes"] = [root + "/dashboard/.data:/app/dashboard/.data", root + "/.runtime/mac:/artifacts"]
    # Sharing nginx's network namespace makes Ditto a loopback HTTP peer. The
    # existing clients retain their remote-HTTPS requirement unchanged. Only
    # nginx publishes app ports, each bound to host loopback.
    return {"name": "smartbin-mac", "services": services,
            "networks": {"default": {}}, "volumes": {"mongo-data": {}, "mongo-config": {}, "mqtt-data": {}}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--images", type=Path, default=Path(__file__).with_name("images.lock.json"))
    parser.add_argument("--sample-seconds", type=int, default=30)
    args = parser.parse_args()
    images = json.loads(args.images.read_text(encoding="utf-8"))["images"]
    source = Path(__file__).resolve().parents[1]
    hashes = {target: fingerprint(source, target, images) for target in ("node", "python", "provision")}
    result = prepare(json.loads(args.base.read_text(encoding="utf-8")), images, args.root, hashes, args.sample_seconds)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for target, value in hashes.items():
        args.output.with_name(target + "-fingerprint").write_text(value + "\n", encoding="ascii")
    args.output.with_name("required-images.txt").write_text("\n".join(item["reference"] for key, item in images.items() if key not in ("node:24-bookworm-slim", "python:3.12-slim-bookworm")) + "\n", encoding="ascii")
    print("Prepared isolated Mac stack with pinned images, persistent databases and loopback ports.")
