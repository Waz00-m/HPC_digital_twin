from __future__ import annotations

import hashlib
import math
import statistics
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import FEATURE_COLUMNS, Store, canonical, features


def benchmark(directory, bins=100, revisions=1000, queries=30):
    if not 1 <= bins <= 200 or not 10 <= revisions <= 10000 or bins * revisions > 250000 or not 5 <= queries <= 200:
        raise ValueError("Benchmark limits: 1–200 bins, 10–10,000 revisions, ≤250,000 rows, 5–200 queries.")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("benchmark-" + uuid.uuid4().hex + ".sqlite3")
    store = Store(path)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    columns = [key for key in FEATURE_COLUMNS if key != "snapshot_id"] + ["content_hash", "thing_json"]

    def records():
        for revision in range(1, revisions + 1):
            at = (base + timedelta(minutes=revision)).isoformat(timespec="microseconds").replace("+00:00", "Z")
            for index in range(bins):
                capacity = (10, 50, 100)[index % 3]
                thing = {"thingId": "benchmark:bin-" + str(index).zfill(3), "_revision": revision, "_modified": at,
                    "attributes": {"type": "SmartBin", "binId": "bin-" + str(index).zfill(3), "warehouseId": "warehouse-" + "abc"[index % 3],
                                   "capacityKg": capacity, "alertThresholdPercent": 85},
                    "features": {"load": {"properties": {"weightKg": capacity * ((revision * 37 + index * 11) % 1001) / 1000,
                                "receivedAt": at, "source": "benchmark-synthetic", "unit": "kg"}}}}
                row = features(thing, at)
                payload = canonical(thing)
                yield [row[column] for column in columns[:-2]] + [hashlib.sha256(payload.encode()).hexdigest(), payload]

    started = time.perf_counter()
    with store.connection() as con:
        con.executemany("INSERT INTO snapshots (" + ",".join(columns) + ") VALUES (" + ",".join("?" for _ in columns) + ")", records())
        con.execute("INSERT INTO latest_things(thing_id,snapshot_id,revision) SELECT thing_id,snapshot_id,revision FROM snapshots WHERE revision=?", (revisions,))
        con.execute("ANALYZE")
    insert_seconds = time.perf_counter() - started
    since = (base + timedelta(minutes=max(1, revisions - 59))).isoformat().replace("+00:00", "Z")
    cases = {"latest_fleet": lambda: store.latest(),
             "one_bin_last_60_minutes": lambda: store.history(thing_id="benchmark:bin-000", since=since),
             "one_warehouse_last_60_minutes": lambda: store.history(warehouse_id="warehouse-a", since=since)}
    measured = {}
    for name, action in cases.items():
        action()  # Explicit warm-up; results are warm-cache timings.
        durations, rows = [], 0
        for _ in range(queries):
            started = time.perf_counter(); rows = len(action()); durations.append((time.perf_counter() - started) * 1000)
        measured[name] = {"returned_rows": rows, "queries": queries, "p50_ms": statistics.median(durations),
                          "p95_ms": sorted(durations)[math.ceil(queries * .95) - 1], "max_ms": max(durations)}
    with store.connection() as con:
        plans = {"one_bin": [row[3] for row in con.execute("EXPLAIN QUERY PLAN SELECT * FROM snapshots WHERE thing_id=? AND observed_at>=? ORDER BY observed_at,snapshot_id", ("benchmark:bin-000", since))],
                 "warehouse": [row[3] for row in con.execute("EXPLAIN QUERY PLAN SELECT * FROM snapshots WHERE warehouse_id=? AND observed_at>=? ORDER BY observed_at,snapshot_id", ("warehouse-a", since))]}
    result = {"database": "SQLite", "synthetic": True, "bins": bins, "revisions_per_bin": revisions,
              "sqlite_version": store.metrics()["sqlite_version"], "journal_mode": store.journal_mode,
              "snapshot_rows": bins * revisions, "seed_seconds": insert_seconds, "database_file": str(path.resolve()),
              "database_bytes": path.stat().st_size, "warm_cache": True,
              "timing_scope": "This computer, pooled read-connection checkout + indexed SQL retrieval + Python row materialization. Excludes HTTP and model inference; not a comparison with other database products.",
              "retrieval": measured, "query_plans": plans}
    (directory / "benchmark.json").write_text(canonical(result) + "\n", encoding="utf-8")
    store.close()
    return result
