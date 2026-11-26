from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import sys
import threading
from pathlib import Path

from .benchmark import benchmark
from .collector import Collector
from .ditto import DittoClient
from .models import PIPELINE_CHECK, get_run, load_adapter, run_inputs, run_model
from .server import make_server
from .store import Store, FEATURE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description="Ditto Thing history and Python model prerequisites")
    parser.add_argument("--db", default=os.getenv("TWIN_HISTORY_DB", str(ROOT / ".data" / "things.sqlite3")))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    collect = commands.add_parser("collect")
    collect.add_argument("--once", action="store_true")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=4322)
    serve.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    serve.add_argument("--no-collect", action="store_true", help="Serve stored data without contacting Ditto")
    latest = commands.add_parser("latest")
    latest.add_argument("--thing-id")
    latest.add_argument("--warehouse-id")
    latest.add_argument("--include-thing", action="store_true")
    for name in ("export", "run-model"):
        command = commands.add_parser(name)
        command.add_argument("--thing-id"); command.add_argument("--warehouse-id")
        command.add_argument("--since"); command.add_argument("--until"); command.add_argument("--limit", type=int, default=10000)
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--format", choices=("json", "csv"), default="json")
        else:
            command.add_argument("--adapter", type=Path, help="Supplied local Python adapter; omitted = pipeline-check only")
    commands.add_parser("metrics")
    run = commands.add_parser("get-run"); run.add_argument("run_id"); run.add_argument("--include-inputs", action="store_true")
    bench = commands.add_parser("benchmark")
    bench.add_argument("--bins", type=int, default=100); bench.add_argument("--revisions", type=int, default=1000)
    bench.add_argument("--queries", type=int, default=30); bench.add_argument("--directory", type=Path, default=ROOT / ".results")
    args = parser.parse_args()
    if args.command == "benchmark":
        result = benchmark(args.directory, args.bins, args.revisions, args.queries)
    else:
        store = Store(args.db)
        if args.command == "init":
            result = {"database_file": str(store.path), **store.metrics()}
        elif args.command == "latest":
            result = store.latest(thing_id=args.thing_id, warehouse_id=args.warehouse_id, include_thing=args.include_thing)
        elif args.command == "metrics":
            result = store.metrics()
        elif args.command == "get-run":
            result = get_run(store, args.run_id)
            if args.include_inputs:
                result["input_rows"] = run_inputs(store, args.run_id)
        elif args.command in ("export", "run-model"):
            query = {key: getattr(args, key) for key in ("thing_id", "warehouse_id", "since", "until", "limit")}
            if args.command == "run-model":
                result = run_model(store, load_adapter(args.adapter) if args.adapter else PIPELINE_CHECK, **query)
            else:
                rows = store.history(**query)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("w", encoding="utf-8", newline="") as out:
                    if args.format == "json":
                        json.dump({"input_schema_version": 1, "query": query, "rows": rows}, out, ensure_ascii=False, allow_nan=False, indent=2)
                    else:
                        writer = csv.DictWriter(out, fieldnames=FEATURE_COLUMNS); writer.writeheader(); writer.writerows(rows)
                result = {"exported_rows": len(rows), "output": str(args.output.resolve())}
        else:
            stop = threading.Event()
            def stop_signal(*_):
                stop.set()
                raise KeyboardInterrupt
            signal.signal(signal.SIGINT, stop_signal)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, stop_signal)
            collector = None if getattr(args, "no_collect", False) else Collector(store, DittoClient())
            if args.command == "collect":
                if args.once:
                    result = collector.reconcile()
                else:
                    try:
                        collector.run(stop)
                    except KeyboardInterrupt:
                        stop.set()
                    return
            else:
                server = make_server(store, collector, args.port, host=args.host)
                if collector:
                    threading.Thread(target=collector.run, args=(stop,), daemon=True).start()
                print("Thing history API: http://127.0.0.1:" + str(server.server_port), flush=True)
                print("Database: " + str(store.path), flush=True)
                try:
                    server.serve_forever(poll_interval=.5)
                except KeyboardInterrupt:
                    pass
                finally:
                    stop.set(); server.server_close()
                return
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
