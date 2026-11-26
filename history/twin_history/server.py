from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .models import get_run, list_runs, run_model
from .store import canonical


def make_server(store, collector=None, port=4322, host="127.0.0.1"):
    if host not in ("127.0.0.1", "0.0.0.0"):
        raise ValueError("Use loopback or the explicit container bind host.")
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(20)

        def log_message(self, format, *args):
            pass

        def reply(self, status, value):
            body = canonical(value).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                url = urlsplit(self.path)
                query = parse_qs(url.query, keep_blank_values=True, max_num_fields=12)
                if any(len(values) != 1 for values in query.values()):
                    raise ValueError("Query parameters must not be repeated.")
                values = {key: value[0] for key, value in query.items()}
                if url.path == "/health":
                    return self.reply(200, {"status": "UP", "service": "smartbin-thing-history", "collector": collector.status() if collector else None,
                        "boss_model_connected": False, "registered_model": "pipeline-check"})
                if url.path in ("/api/latest", "/api/history", "/api/samples"):
                    allowed = {"thing_id", "warehouse_id", "include_thing"} | ({"since", "until", "limit", "valid_only"} if url.path != "/api/latest" else set())
                    if set(values) - allowed:
                        raise ValueError("Unknown query parameters: " + ", ".join(sorted(set(values) - allowed)))
                    for flag in ("include_thing", "valid_only"):
                        if flag in values:
                            if values[flag] not in ("true", "false"):
                                raise ValueError(flag + " must be true or false.")
                            values[flag] = values[flag] == "true"
                    if "limit" in values:
                        values["limit"] = int(values["limit"])
                    read = {"/api/latest": store.latest, "/api/history": store.history, "/api/samples": store.samples}[url.path]
                    rows = read(**values)
                    return self.reply(200, {"rows": rows, "count": len(rows), "source": "stored Ditto Thing snapshots"})
                if url.path == "/api/metrics":
                    return self.reply(200, {**store.metrics(), "collector": collector.status() if collector else None})
                if url.path == "/api/collector-log":
                    return self.reply(200, {"entries": store.logs()})
                if url.path == "/api/model-runs":
                    return self.reply(200, {"runs": list_runs(store)})
                if url.path.startswith("/api/model-runs/"):
                    return self.reply(200, get_run(store, url.path.removeprefix("/api/model-runs/")))
                self.reply(404, {"error": "Not found."})
            except (ValueError, TypeError) as error:
                self.reply(400, {"error": str(error)})
            except Exception:
                self.reply(500, {"error": "History read failed. Check the local service and database."})

        def do_POST(self):
            try:
                if self.path != "/api/model-runs":
                    return self.reply(404, {"error": "Not found."})
                origin = self.headers.get("Origin")
                if origin and origin != "http://" + self.headers.get("Host", ""):
                    return self.reply(403, {"error": "Open the local history service directly."})
                if self.headers.get_content_type() != "application/json":
                    return self.reply(415, {"error": "Send JSON."})
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16000:
                    raise ValueError("Provide a JSON request of at most 16 KB.")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict) or set(value) - {"model", "since", "until", "thing_id", "warehouse_id", "limit", "input_series"}:
                    raise ValueError("Provide only model, time range, Thing/warehouse filter and limit.")
                if value.pop("model", "pipeline-check") != "pipeline-check":
                    raise ValueError("Only pipeline-check is registered. Integrate the supplied model through the Python adapter first.")
                self.reply(201, run_model(store, **value))
            except (ValueError, TypeError) as error:
                self.reply(400, {"error": str(error)})
            except Exception:
                self.reply(500, {"error": "Model execution failed; inspect the stored model run."})

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
