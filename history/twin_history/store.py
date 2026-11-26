from __future__ import annotations

import hashlib
import json
import math
import queue
import sqlite3
import statistics
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
FEATURE_VERSION = 1
FEATURE_COLUMNS = (
    "snapshot_id", "thing_id", "revision", "observed_at", "ditto_modified_at", "model_type",
    "bin_id", "warehouse_id", "reading_at", "weight_kg", "capacity_kg", "weight_percent",
    "alert_threshold_percent", "alert_active", "status", "source", "quality", "feature_version",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Use an ISO 8601 timestamp with a timezone.")
    date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if date.tzinfo is None:
        raise ValueError("Timestamps must include a timezone (for example Z or +05:30).")
    return date.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def supports_safe_wal(version):
    # SQLite's WAL-reset fix: 3.51.3+, with the documented 3.50.7/3.44.6 backports.
    return version >= (3, 51, 3) or (3, 50, 7) <= version < (3, 51, 0) or (3, 44, 6) <= version < (3, 45, 0)


def features(thing, observed_at):
    attributes = thing.get("attributes") or {}
    if not isinstance(attributes, dict):
        raise ValueError("Thing attributes must be a JSON object.")
    raw = ((thing.get("features") or {}).get("load") or {}).get("properties") or {}
    if not isinstance(raw, dict):
        raw = {}
    weight, capacity, threshold = raw.get("weightKg"), attributes.get("capacityKg"), attributes.get("alertThresholdPercent")
    result = dict.fromkeys(FEATURE_COLUMNS)
    result.update(thing_id=thing["thingId"], revision=thing["_revision"], observed_at=observed_at,
                  ditto_modified_at=thing.get("_modified"), model_type=attributes.get("type"),
                  bin_id=attributes.get("binId"), warehouse_id=attributes.get("warehouseId"),
                  reading_at=raw.get("receivedAt"), source=raw.get("source"), quality="not-a-bin",
                  status="not-a-bin", feature_version=FEATURE_VERSION)
    if result["model_type"] != "SmartBin":
        return result
    if not finite(weight):
        result.update(quality="missing-or-invalid-reading", status="awaiting-reading")
        return result
    result["weight_kg"] = weight
    if raw.get("warehouseId") and raw["warehouseId"] != attributes.get("warehouseId"):
        result.update(quality="identity-mismatch", status="identity-mismatch")
        return result
    if weight < 0 or not finite(capacity) or capacity <= 0 or (threshold is not None and (not finite(threshold) or not 0 < threshold <= 100)):
        result.update(quality="invalid-model", status="invalid-model")
        return result
    if raw.get("unit", "kg") != "kg":
        result.update(quality="unsupported-unit", status="unsupported-unit")
        return result
    result.update(capacity_kg=capacity, weight_percent=weight / capacity * 100,
                  alert_threshold_percent=threshold,
                  alert_active=None if threshold is None else int(weight >= capacity * threshold / 100),
                  status="over-capacity" if weight > capacity else "unconfigured" if threshold is None else "attention" if weight >= capacity * threshold / 100 else "normal",
                  quality="valid")
    return result


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._times = defaultdict(lambda: deque(maxlen=512))
        self._lock = threading.Lock()
        self._read_pool = queue.LifoQueue(maxsize=4)
        self._pool_lock = threading.Lock()
        self._pool_count = 0
        self._closed = False
        with self.connection() as con:
            version = con.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise ValueError("Unsupported history schema version: " + str(version))
            requested_mode = "WAL" if supports_safe_wal(sqlite3.sqlite_version_info) else "DELETE"
            self.journal_mode = con.execute("PRAGMA journal_mode=" + requested_mode).fetchone()[0]
            con.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id INTEGER PRIMARY KEY, thing_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    observed_at TEXT NOT NULL, ditto_modified_at TEXT, model_type TEXT, bin_id TEXT,
                    warehouse_id TEXT, reading_at TEXT, weight_kg REAL, capacity_kg REAL, weight_percent REAL,
                    alert_threshold_percent REAL, alert_active INTEGER, status TEXT NOT NULL, source TEXT,
                    quality TEXT NOT NULL, feature_version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL, thing_json TEXT NOT NULL,
                    UNIQUE(thing_id, revision)
                );
                CREATE INDEX IF NOT EXISTS snapshots_by_thing_time ON snapshots(thing_id, observed_at, snapshot_id);
                CREATE INDEX IF NOT EXISTS snapshots_by_warehouse_time ON snapshots(warehouse_id, observed_at, snapshot_id);
                CREATE INDEX IF NOT EXISTS snapshots_by_time ON snapshots(observed_at, snapshot_id);
                CREATE TABLE IF NOT EXISTS latest_things (
                    thing_id TEXT PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
                    revision INTEGER NOT NULL, deleted_at TEXT
                );
                CREATE TABLE IF NOT EXISTS ditto_events (
                    event_id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
                    thing_id TEXT NOT NULL, observed_at TEXT NOT NULL, event_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collector_log (
                    log_id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, kind TEXT NOT NULL, details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_runs (
                    run_id TEXT PRIMARY KEY, model_name TEXT NOT NULL, model_version TEXT NOT NULL,
                    started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                    manifest_json TEXT NOT NULL, output_json TEXT, error TEXT
                );
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=FULL")
        try:
            with con:
                yield con
        finally:
            con.close()

    @contextmanager
    def read_connection(self):
        if self._closed:
            raise ValueError("The history store is closed.")
        try:
            con = self._read_pool.get_nowait()
        except queue.Empty:
            with self._pool_lock:
                create = self._pool_count < 4
                if create:
                    self._pool_count += 1
            if create:
                try:
                    con = sqlite3.connect(self.path, timeout=15, check_same_thread=False)
                    con.row_factory = sqlite3.Row
                    con.execute("PRAGMA query_only=ON")
                except Exception:
                    with self._pool_lock:
                        self._pool_count -= 1
                    raise
            else:
                con = self._read_pool.get(timeout=15)
        try:
            yield con
        finally:
            if self._closed:
                con.close()
            else:
                self._read_pool.put(con)

    def close(self):
        self._closed = True
        while True:
            try:
                self._read_pool.get_nowait().close()
            except queue.Empty:
                break

    def bind_source(self, origin, namespace):
        value = canonical({"origin": origin, "namespace": namespace})
        with self.connection() as con:
            old = con.execute("SELECT value FROM metadata WHERE key='ditto_source'").fetchone()
            if old and old[0] != value:
                raise ValueError("This database belongs to a different Ditto origin/namespace. Choose another database file.")
            con.execute("INSERT OR IGNORE INTO metadata VALUES ('ditto_source', ?)", (value,))

    def insert_snapshot(self, thing, observed_at=None):
        thing_id, revision = thing.get("thingId"), thing.get("_revision")
        if not isinstance(thing_id, str) or ":" not in thing_id or not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ValueError("A Thing needs thingId and a positive integer Ditto _revision.")
        observed_at = timestamp(observed_at) if observed_at else utc_now()
        payload = canonical(thing)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        row = features(thing, observed_at)
        columns = [column for column in FEATURE_COLUMNS if column != "snapshot_id"] + ["content_hash", "thing_json"]
        values = [row[column] for column in columns[:-2]] + [digest, payload]
        with self.connection() as con:
            existing = con.execute("SELECT snapshot_id, content_hash FROM snapshots WHERE thing_id=? AND revision=?", (thing_id, revision)).fetchone()
            if existing:
                if existing["content_hash"] != digest:
                    raise ValueError("Conflicting Thing contents for the same Ditto revision.")
                return {"inserted": False, "snapshot_id": existing["snapshot_id"]}
            previous = con.execute("SELECT revision FROM latest_things WHERE thing_id=?", (thing_id,)).fetchone()
            cursor = con.execute("INSERT INTO snapshots (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", values)
            snapshot_id = cursor.lastrowid
            con.execute("""INSERT INTO latest_things(thing_id,snapshot_id,revision) VALUES (?,?,?)
                ON CONFLICT(thing_id) DO UPDATE SET snapshot_id=excluded.snapshot_id, revision=excluded.revision, deleted_at=NULL
                WHERE excluded.revision > latest_things.revision""", (thing_id, snapshot_id, revision))
            if previous and revision > previous[0] + 1:
                self._log(con, "revision-gap", {"thing_id": thing_id, "previous": previous[0], "observed": revision,
                    "meaning": "Intermediate revisions were not stored as complete snapshots; consult retained Ditto notifications."})
        return {"inserted": True, "snapshot_id": snapshot_id}

    def insert_event(self, event, observed_at=None):
        thing_id = event.get("thingId")
        if not isinstance(thing_id, str) or ":" not in thing_id:
            raise ValueError("Ditto notification has no Thing ID.")
        payload = canonical(event)
        key = hashlib.sha256(payload.encode()).hexdigest()
        with self.connection() as con:
            cur = con.execute("INSERT OR IGNORE INTO ditto_events(event_key,thing_id,observed_at,event_json) VALUES (?,?,?,?)",
                              (key, thing_id, observed_at or utc_now(), payload))
        return cur.rowcount == 1

    def mark_deleted(self, thing_id, revision=None):
        with self.connection() as con:
            condition, args = (" AND revision<=?", [revision]) if revision is not None else ("", [])
            con.execute("UPDATE latest_things SET deleted_at=? WHERE thing_id=?" + condition, [utc_now(), thing_id] + args)
            self._log(con, "thing-deleted", {"thing_id": thing_id, "event_revision": revision})

    def _log(self, con, kind, details):
        con.execute("INSERT INTO collector_log(observed_at,kind,details_json) VALUES (?,?,?)", (utc_now(), kind, canonical(details)))

    def log(self, kind, details):
        with self.connection() as con:
            self._log(con, kind, details)

    def _measure(self, operation, started, count):
        with self._lock:
            self._times[operation].append({"ms": (time.perf_counter() - started) * 1000, "rows": count})

    def latest(self, thing_id=None, warehouse_id=None, include_thing=False):
        started = time.perf_counter()
        self._filters(thing_id, warehouse_id)
        clauses, args = ["l.deleted_at IS NULL"], []
        for column, value in (("s.thing_id", thing_id), ("s.warehouse_id", warehouse_id)):
            if value is not None:
                clauses.append(column + "=?"); args.append(value)
        columns = "s.*" if include_thing else ",".join("s." + c for c in FEATURE_COLUMNS)
        with self.read_connection() as con:
            rows = [dict(row) for row in con.execute("SELECT " + columns + " FROM latest_things l JOIN snapshots s ON s.snapshot_id=l.snapshot_id WHERE " + " AND ".join(clauses) + " ORDER BY s.thing_id", args)]
        if include_thing:
            for row in rows:
                row["thing"] = json.loads(row.pop("thing_json"))
        self._measure("latest", started, len(rows))
        return rows

    def history(self, *, thing_id=None, warehouse_id=None, since=None, until=None, limit=10000, valid_only=False, include_thing=False):
        started = time.perf_counter()
        self._filters(thing_id, warehouse_id)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50000:
            raise ValueError("History limit must be 1–50,000 rows.")
        clauses, args = [], []
        for column, op, value in (("thing_id", "=", thing_id), ("warehouse_id", "=", warehouse_id),
                                   ("observed_at", ">=", timestamp(since) if since else None), ("observed_at", "<=", timestamp(until) if until else None)):
            if value is not None:
                clauses.append(column + op + "?"); args.append(value)
        if since and until and timestamp(since) > timestamp(until):
            raise ValueError("The history start must not be after its end.")
        if valid_only:
            clauses += ["quality='valid'", "model_type='SmartBin'"]
        columns = "*" if include_thing else ",".join(FEATURE_COLUMNS)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.read_connection() as con:
            rows = [dict(row) for row in con.execute("SELECT " + columns + " FROM snapshots" + where + " ORDER BY observed_at,snapshot_id LIMIT ?", args + [limit + 1])]
        if len(rows) > limit:
            raise ValueError("The query exceeds its row limit. Narrow the time range or Thing/warehouse filter; data was not silently truncated.")
        if include_thing:
            for row in rows:
                row["thing"] = json.loads(row.pop("thing_json"))
        self._measure("history", started, len(rows))
        return rows

    @staticmethod
    def _filters(thing_id, warehouse_id):
        for name, value in (("thing_id", thing_id), ("warehouse_id", warehouse_id)):
            if value is not None and (not isinstance(value, str) or not value or len(value) > 256):
                raise ValueError(name + " must be a nonempty string of at most 256 characters.")

    def logs(self, limit=50):
        with self.read_connection() as con:
            return [dict(row) for row in con.execute("SELECT * FROM collector_log ORDER BY log_id DESC LIMIT ?", (limit,))]

    def metrics(self):
        with self.read_connection() as con:
            counts = {table: con.execute("SELECT count(*) FROM " + table).fetchone()[0] for table in ("snapshots", "latest_things", "ditto_events", "model_runs")}
        with self._lock:
            queries = {name: {"samples": len(samples), "last_rows": samples[-1]["rows"], "last_ms": samples[-1]["ms"],
                "p50_ms": statistics.median(s["ms"] for s in samples),
                "p95_ms": sorted(s["ms"] for s in samples)[math.ceil(len(samples) * .95) - 1]} for name, samples in self._times.items() if samples}
        return {"database": "SQLite", "schema_version": SCHEMA_VERSION, "feature_version": FEATURE_VERSION,
                "sqlite_version": sqlite3.sqlite_version, "journal_mode": self.journal_mode,
                "counts": counts, "query_timings": queries, "timing_scope": "Last 512 measured reads per operation in this process, including read-connection checkout and row materialization; no network latency."}
