from __future__ import annotations

import hashlib
import importlib.util
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import FEATURE_COLUMNS, FEATURE_VERSION, canonical, timestamp, utc_now


@dataclass(frozen=True)
class Adapter:
    name: str
    version: str
    run: object
    required_columns: tuple = ("thing_id", "observed_at", "weight_kg", "capacity_kg")


def pipeline_check(rows, context):
    latest = {}
    for row in rows:
        latest[row["thing_id"]] = row
    return {"kind": "pipeline-check", "prediction": False, "input_rows": len(rows),
            "bins": [{"thing_id": key, "snapshot_id": row["snapshot_id"], "weight_kg": row["weight_kg"],
                      "capacity_kg": row["capacity_kg"]} for key, row in sorted(latest.items())],
            "message": "Database retrieval and Python adapter work. The boss's model has not been connected."}


PIPELINE_CHECK = Adapter("pipeline-check", "1.0.0", pipeline_check)


def load_adapter(path):
    """CLI-only integration point for a supplied, trusted Python adapter file."""
    path = Path(path).resolve(strict=True)
    if path.suffix != ".py":
        raise ValueError("Provide a Python adapter .py file.")
    spec = importlib.util.spec_from_file_location("smartbin_supplied_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for field in ("MODEL_NAME", "MODEL_VERSION", "run"):
        if not hasattr(module, field):
            raise ValueError("Adapter must define MODEL_NAME, MODEL_VERSION and run(rows, context).")
    if not callable(module.run) or not isinstance(module.MODEL_NAME, str) or not module.MODEL_NAME or not isinstance(module.MODEL_VERSION, str) or not module.MODEL_VERSION:
        raise ValueError("Adapter needs a callable run and nonempty model name/version.")
    required = tuple(getattr(module, "REQUIRED_COLUMNS", PIPELINE_CHECK.required_columns))
    if not required or any(column not in FEATURE_COLUMNS for column in required):
        raise ValueError("Adapter requires unsupported input columns.")
    return Adapter(module.MODEL_NAME, module.MODEL_VERSION, module.run, required)


def run_model(store, adapter=PIPELINE_CHECK, *, since=None, until=None, thing_id=None, warehouse_id=None, limit=10000):
    until = timestamp(until) if until else utc_now()
    since = timestamp(since) if since else (datetime.fromisoformat(until.replace("Z", "+00:00")) - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    # Preserve all selected rows in the manifest, including quality exclusions.
    selected = store.history(since=since, until=until, thing_id=thing_id, warehouse_id=warehouse_id, limit=limit)
    rows = [row for row in selected if row["model_type"] == "SmartBin" and row["quality"] == "valid"]
    if not rows:
        raise ValueError("No valid SmartBin history is available for this model window. Collect Things with valid readings first.")
    if any(any(row.get(column) is None for column in adapter.required_columns) for row in rows):
        raise ValueError("Required model input is missing. Review the adapter's input contract.")
    run_id = str(uuid.uuid4())
    included_ids = {row["snapshot_id"] for row in rows}
    with store.connection() as con:
        source = con.execute("SELECT value FROM metadata WHERE key='ditto_source'").fetchone()
    manifest = {"input_schema_version": FEATURE_VERSION, "columns": list(FEATURE_COLUMNS),
                "query": {"since": since, "until": until, "thing_id": thing_id, "warehouse_id": warehouse_id, "limit": limit},
                "snapshot_ids": [row["snapshot_id"] for row in rows],
                "excluded_snapshot_ids": [row["snapshot_id"] for row in selected if row["snapshot_id"] not in included_ids],
                "input_sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
                "ditto_source": json.loads(source[0]) if source else None,
                "sampling": "Observed Thing revisions, not regularly sampled or interpolated sensor data.",
                "capture_limits": "SSE outages and intermediate revisions may be absent as complete snapshots. Review collector_log and ditto_events.",
                "recent_collector_notices": store.logs(10)}
    with store.connection() as con:
        con.execute("INSERT INTO model_runs(run_id,model_name,model_version,started_at,status,manifest_json) VALUES (?,?,?,?,?,?)",
                    (run_id, adapter.name, adapter.version, utc_now(), "running", canonical(manifest)))
    try:
        output = adapter.run(rows, manifest)
        serialized = canonical(output)
        if len(serialized.encode()) > 5_000_000:
            raise ValueError("Model output exceeds the 5 MB result limit.")
        with store.connection() as con:
            con.execute("UPDATE model_runs SET status='completed', finished_at=?, output_json=? WHERE run_id=?", (utc_now(), serialized, run_id))
    except Exception as error:
        with store.connection() as con:
            con.execute("UPDATE model_runs SET status='failed', finished_at=?, error=? WHERE run_id=?", (utc_now(), type(error).__name__ + ": " + str(error), run_id))
        raise RuntimeError("Model run " + run_id + " failed: " + str(error)) from error
    return get_run(store, run_id)


def get_run(store, run_id):
    with store.connection() as con:
        row = con.execute("SELECT * FROM model_runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise ValueError("Model run was not found.")
    result = dict(row)
    result["manifest"] = json.loads(result.pop("manifest_json"))
    raw = result.pop("output_json")
    result["output"] = json.loads(raw) if raw else None
    return result


def list_runs(store, limit=50):
    with store.connection() as con:
        return [dict(row) for row in con.execute("SELECT run_id,model_name,model_version,started_at,finished_at,status,error FROM model_runs ORDER BY started_at DESC LIMIT ?", (limit,))]


def run_inputs(store, run_id):
    manifest = get_run(store, run_id)["manifest"]
    ids = manifest["snapshot_ids"]
    found = {}
    with store.connection() as con:
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            for row in con.execute("SELECT " + ",".join(FEATURE_COLUMNS) + " FROM snapshots WHERE snapshot_id IN (" + ",".join("?" for _ in chunk) + ")", chunk):
                found[row["snapshot_id"]] = dict(row)
    if len(found) != len(ids):
        raise ValueError("Stored model input snapshots are missing.")
    rows = [found[identity] for identity in ids]
    if hashlib.sha256(canonical(rows).encode()).hexdigest() != manifest["input_sha256"]:
        raise ValueError("Stored model inputs no longer match the recorded hash.")
    return rows
