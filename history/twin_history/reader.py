"""Read-only model inputs. No Ditto/MQTT connection and no model dependency."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

from .store import FEATURE_COLUMNS, FEATURE_VERSION, SAMPLE_COLUMNS, Store, canonical, timestamp, utc_now

DEFAULT_DB = Path(__file__).resolve().parents[1] / ".data/things.sqlite3"


def fetch_data(db_path=None, *, series="samples", thing_id=None, warehouse_id=None,
               since=None, until=None, limit=50000, valid_only=False, include_thing=True):
    """Return stored SmartBin rows, retaining repeated weights and quality flags.

    samples uses sampled_at; revisions uses observed_at; latest has no window.
    Raises on missing/incompatible DB or excessive rows instead of dropping data.
    """
    if series not in ("samples", "revisions", "latest"):
        raise ValueError("Use samples, revisions or latest.")
    if series == "latest" and (since or until):
        raise ValueError("Latest is current stored state; use samples or revisions for a time window.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50000:
        raise ValueError("Limit must be 1–50,000 rows.")
    since, until = (timestamp(value) if value else None for value in (since, until))
    store = Store(db_path or os.getenv("TWIN_HISTORY_DB") or DEFAULT_DB, readonly=True)
    try:
        query = dict(thing_id=thing_id, warehouse_id=warehouse_id, since=since, until=until, limit=limit)
        if series == "latest":
            rows = store.latest(thing_id=thing_id, warehouse_id=warehouse_id, include_thing=include_thing)
            rows = [row for row in rows if row["model_type"] == "SmartBin" and (not valid_only or row["quality"] == "valid")]
            if len(rows) > limit:
                raise ValueError("Query exceeds its row limit; data was not silently truncated.")
        else:
            read = store.samples if series == "samples" else store.history
            rows = read(**query, valid_only=valid_only, include_thing=include_thing, bins_only=True)
        rows = [row for row in rows if row["model_type"] == "SmartBin" and (not valid_only or row["quality"] == "valid")]
        with store.read_connection() as con:
            source = con.execute("SELECT value FROM metadata WHERE key='ditto_source'").fetchone()
        columns = list(SAMPLE_COLUMNS if series == "samples" else FEATURE_COLUMNS)
        if include_thing:
            columns += ["content_hash", "thing"]
        return {"input_schema_version": FEATURE_VERSION, "series": series,
            "time_axis": "sampled_at" if series == "samples" else "observed_at",
            "fetched_at": utc_now(), "database_file": str(store.path),
            "ditto_source": json.loads(source[0]) if source else None,
            "query": {**query, "valid_only": valid_only, "include_thing": include_thing},
            "columns": columns, "count": len(rows), "rows": rows,
            "input_sha256": hashlib.sha256(canonical(rows).encode()).hexdigest(),
            "note": "Timed rows record successful Ditto HTTP observations, not new physical measurements. Repeated weights are retained. reading_at is the original receipt timestamp; gaps are not backfilled."}
    finally:
        store.close()


def add_arguments(parser):
    parser.add_argument("--series", choices=("samples", "revisions", "latest"), default="samples")
    parser.add_argument("--thing-id"); parser.add_argument("--warehouse-id")
    parser.add_argument("--since"); parser.add_argument("--until")
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--valid-only", action="store_true", help="Explicitly exclude invalid/awaiting readings")
    parser.add_argument("--no-thing", action="store_true", help="Omit full original Thing JSON")
    parser.add_argument("--format", choices=("json", "csv"), default="json")
    parser.add_argument("--output", type=Path, help="Omitted: print data to stdout; paths are relative to your current directory")


def fetch_command(args):
    result = fetch_data(args.db, series=args.series, thing_id=args.thing_id, warehouse_id=args.warehouse_id,
        since=args.since, until=args.until, limit=args.limit, valid_only=args.valid_only, include_thing=not args.no_thing)
    def write(stream):
        if args.format == "json":
            json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2); stream.write("\n")
        else:
            writer = csv.DictWriter(stream, fieldnames=result["columns"])
            writer.writeheader()
            for row in result["rows"]:
                writer.writerow({key: canonical(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})
    if args.output is None:
        write(sys.stdout)
        return
    output = args.output.resolve()
    database = Path(result["database_file"])
    if output in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm"), Path(str(database) + "-journal")) or (output.exists() and output.samefile(database)):
        raise ValueError("Export output must not replace the history database or its journal files.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=output.parent, prefix=".smartbin-export-", delete=False) as stream:
            temporary = Path(stream.name); write(stream)
        temporary.replace(output)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print(json.dumps({"exported_rows": result["count"], "series": args.series, "output": str(output), "input_sha256": result["input_sha256"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Fetch stored SmartBin data for a supplied model. Read-only; no extra packages required.")
    parser.add_argument("--db", default=os.getenv("TWIN_HISTORY_DB", str(DEFAULT_DB)))
    add_arguments(parser)
    try:
        fetch_command(parser.parse_args())
        return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1
