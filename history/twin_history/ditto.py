from __future__ import annotations

import base64
import json
import os
import re
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

FIELDS = "thingId,policyId,definition,attributes,features,_revision,_modified,_created"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DittoClient:
    def __init__(self, origin=None, username=None, password=None, namespace=None, timeout=20):
        self.origin = (origin or os.getenv("DITTO_URL", "http://127.0.0.1:8090")).rstrip("/")
        parts = urlsplit(self.origin)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.path or parts.query or parts.fragment:
            raise ValueError("Use a Ditto origin without credentials, path or query.")
        if parts.scheme == "http" and parts.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Remote Ditto servers require HTTPS.")
        self.namespace = namespace or os.getenv("DITTO_NAMESPACE", "smartbin")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.namespace):
            raise ValueError("Invalid Ditto namespace.")
        self.timeout = timeout
        auth = (username if username is not None else os.getenv("DITTO_USERNAME", "ditto")) + ":" + (password if password is not None else os.getenv("DITTO_PASSWORD", "ditto"))
        self._authorization = "Basic " + base64.b64encode(auth.encode()).decode()
        # Do not forward credentials across redirects or through a system HTTP proxy.
        self._opener = build_opener(ProxyHandler({}), NoRedirect())

    def _open(self, path, accept="application/json", timeout=None):
        request = Request(self.origin + "/api/2" + path, headers={"Authorization": self._authorization, "Accept": accept})
        try:
            return self._opener.open(request, timeout=timeout or self.timeout)
        except HTTPError as error:
            raise RuntimeError("Ditto HTTP " + str(error.code) + " for " + path.split("?")[0]) from None

    def _json(self, path):
        with self._open(path) as response:
            return json.load(response)

    def thing(self, thing_id):
        if not thing_id.startswith(self.namespace + ":"):
            raise ValueError("Thing is outside the configured namespace.")
        return self._json("/things/" + quote(thing_id, safe="") + "?" + urlencode({"fields": FIELDS}))

    def things(self):
        query = {"namespaces": self.namespace,
                 "filter": 'or(eq(attributes/type,"SmartBin"),eq(attributes/type,"Warehouse"))',
                 "fields": "thingId", "option": "size(200)"}
        result = self._json("/search/things?" + urlencode(query))
        if result.get("cursor") or result.get("nextPage"):
            raise ValueError("History discovery supports up to 200 Things. Narrow the namespace before collecting more.")
        ids = [item["thingId"] for item in result["items"]]
        things = []
        for start in range(0, len(ids), 50):
            things.extend(self._json("/things?" + urlencode({"ids": ",".join(ids[start:start + 50]), "fields": FIELDS})))
        return things

    def stream(self):
        query = {"namespaces": self.namespace, "fields": "thingId,attributes,features,policyId,_revision,_modified,_context"}
        response = self._open("/things?" + urlencode(query), accept="text/event-stream", timeout=45)
        if "text/event-stream" not in response.headers.get("Content-Type", ""):
            response.close()
            raise RuntimeError("Ditto did not return an SSE change stream.")
        return response


def sse_messages(lines):
    """Bounded SSE framing; comments/heartbeats yield None to permit reconciliation."""
    data, size = [], 0
    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line = line.rstrip("\r\n")
        if not line:
            payload = "\n".join(data)
            yield json.loads(payload) if payload.strip() else None
            data, size = [], 0
        elif line.startswith("data:"):
            value = line[5:].removeprefix(" ")
            size += len(value)
            if size > 2_000_000:
                raise ValueError("Ditto notification exceeds 2 MB.")
            data.append(value)
        elif len(line) > 2_000_000:
            raise ValueError("SSE line exceeds 2 MB.")


def bounded_lines(response):
    while True:
        line = response.readline(2_000_001)
        if not line:
            return
        if len(line) > 2_000_000:
            raise ValueError("SSE line exceeds 2 MB.")
        yield line
