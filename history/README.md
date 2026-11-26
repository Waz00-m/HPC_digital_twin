# Thing history and Python model inputs

This is the database/Python prerequisite for the next project stage:

~~~text
Physical gateway / spoofer -> MQTT -> Ditto Thing
                                      |
                         Thing change notifications + HTTP snapshots
                                      |
                            Indexed SQLite database
                                      |
                        Python query -> model adapter -> stored result
~~~

The collector never subscribes to MQTT. It uses Ditto's supported Thing SSE change notifications and retrieves complete Things over HTTP. The dashboard and spoofer remain separate; this service is a third local backend on port 4322. It does not write Ditto or execute the boss's models until an adapter is supplied.

SQLite is the initial local database: no additional Docker server or Python dependency is required. Indexes cover Thing/time and warehouse/time history; a current-state table provides direct latest-version reads. A pool of up to four query-only connections reuses read caches, while writes use short, fully synchronized transactions. WAL is enabled only on SQLite versions containing the documented WAL-reset fix (3.51.3+, or 3.50.7/3.44.6 backports); older runtimes use the safe rollback journal. Read/write overlap on older runtimes is serialized by SQLite locks with a 15-second busy timeout. The selected journal mode and SQLite version are reported as metrics. This is a measured choice for a single-computer demo, not a claim of being universally fastest. Networked multi-user deployment, measured ingest throughput, long-term retention and a comparison against server databases remain separate requirements.

## Start

Prerequisites: the current Ditto demo is running, and Python 3.11+ or uv is installed. No pip packages are needed. From the digital-twin repository root on Windows:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\history\Start-History.ps1
~~~

The script creates history/.venv when needed, starts a hidden Python process, and reports the API URL. To choose an installed interpreter for the first setup, add -PythonPath 'C:\path\to\python.exe'. If uv is available, setup requests Python 3.12 and keeps its cache in history/.cache. The script reuses an already-running history service and refuses a conflicting port.

To start the complete installed demo together:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-DigitalTwin.ps1 -WithHistory
~~~

To stop just this backend, run powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\history\Stop-History.ps1. It verifies the recorded process belongs to this project before stopping it; committed records stay in the database. Stop and start it after editing Python source.

Existing startup without -WithHistory keeps its previous behavior. Linux/macOS: create history/.venv with python3 -m venv history/.venv, then run npm run history -- serve. npm helpers select the platform's virtualenv interpreter and run from history/.

- Health and collector connection: http://127.0.0.1:4322/health
- Latest stored Things: http://127.0.0.1:4322/api/latest?include_thing=true
- History for one bin: http://127.0.0.1:4322/api/history?thing_id=smartbin%3Abin-002
- Live query metrics and database counts: http://127.0.0.1:4322/api/metrics
- Collector connection/gap notices: http://127.0.0.1:4322/api/collector-log
- Python model-run results: http://127.0.0.1:4322/api/model-runs

These are JSON API endpoints for later frontend integration. They are loopback-only, without cross-origin read access. POST requests require JSON and reject foreign browser origins. The HTTP interface only runs the registered pipeline-check adapter; it does not accept uploaded code or arbitrary module paths.

The default database is history/.data/things.sqlite3. Logs and PID are in ../.runtime/history.*. Database files, virtualenvs, exports and runtime results are ignored by Git. Data persists when apps restart; it is not embedded in the repository. For a consistent backup while collection is running, use Python's sqlite3.Connection.backup API; copying just the .sqlite3 file can omit an active journal.

Configuration is read from process environment: DITTO_URL (default http://127.0.0.1:8090), DITTO_USERNAME / DITTO_PASSWORD (sample ditto/ditto), DITTO_NAMESPACE (smartbin), and optional TWIN_HISTORY_DB. Credentials remain in process memory. Remote Ditto requires HTTPS; redirects and system HTTP proxies are disabled for the credentialed requests. Each database is bound to one Ditto origin/namespace to prevent mixing sources.

## Data retained

| Table | Purpose |
| --- | --- |
| snapshots | Complete observed Thing JSON plus immutable feature columns, unique by Thing ID/revision |
| latest_things | Pointer to the highest observed revision, with a deletion flag |
| ditto_events | Original post-Ditto notifications, including changed fields and protocol context |
| collector_log | Connection, outage, deletion and observed-revision-gap notices |
| model_runs | Model name/version, exact input manifest, completion/failure and JSON output |
| metadata | Database source identity |

All currently imported Things are captured at startup. Notifications trigger a complete Thing GET; reconnect reconciles the current fleet, and healthy stream heartbeats allow periodic reconciliation (nominally 30 seconds). Repeat observations of the same revision do not duplicate the snapshot. Older revisions cannot replace a newer latest pointer. Conflicting payloads with the same revision raise an error.

SSE may contain only the changed fields, so it is not treated as a full Thing. The separately fetched snapshot can be newer than the triggering event. Original notifications remain available, but the collector does not claim every intermediate revision became a complete snapshot. Reconnect has no change-event replay guarantee: offline intervals are recorded and current state is reconciled; missed historical readings cannot be invented. Discovery supports up to 200 imported Things and fails visibly rather than silently dropping later pages.

Observation time, Ditto modification time and reading receipt time are distinct. Query windows currently use observed_at, the database capture time. Revisions caused by model changes may repeat the same reading_at. Adapters must choose their intended time axis and deduplication; no regular sampling, resampling, interpolation or learned feature calculation is applied automatically. Percentages use capacity from that historical Thing version, not today's capacity.

## Retrieve and export

Run from the repository root:

~~~powershell
# Capture current complete Things once, without opening an ongoing stream.
npm.cmd run history -- collect --once

# Latest current state, optionally with full original Thing JSON.
npm.cmd run history -- latest --include-thing

# Use explicit timezone offsets or UTC Z for query bounds.
npm.cmd run history -- export --thing-id smartbin:bin-002 --since 2026-11-25T00:00:00Z --until 2026-11-26T00:00:00Z --format csv --output .results/bin-002.csv

# Run DB-to-Python plumbing and save its result; this performs no prediction.
npm.cmd run history -- run-model
~~~

Export paths are relative to history/. Filters support one Thing, one warehouse, and a UTC-normalized time range. Results are ascending observations with a stable snapshot-ID tie-breaker. Default limit 10,000; maximum 50,000. A larger result fails with a narrowing instruction instead of silently truncating model inputs. Export includes quality flags; the model runner explicitly excludes invalid readings and non-bin records and lists excluded snapshot IDs in its manifest. Invalid inputs never become zero-weight normal bins.

Model input columns (schema version 1): snapshot_id, thing_id, revision, observed_at, ditto_modified_at, model_type, bin_id, warehouse_id, reading_at, weight_kg, capacity_kg, weight_percent, alert_threshold_percent, alert_active, status, source, quality, feature_version. Weights/capacities are calibrated kg; volume fullness and raw ADC values are not inferred.

## Connect the supplied model later

models/boss_adapter.py is the intentionally unimplemented integration point. It defines:

~~~python
MODEL_NAME = "the-model-name"
MODEL_VERSION = "the-supplied-version"
REQUIRED_COLUMNS = ("thing_id", "observed_at", "weight_kg", "capacity_kg")

def run(rows, context):
    # rows: ordered dictionaries retrieved from immutable stored snapshots.
    # context: query window, source, feature schema, snapshot IDs/hash and capture notices.
    # Convert to the model's required DataFrame/array/tensor, invoke it,
    # and return JSON-serializable output.
    ...
~~~

Once its code is implemented and its actual framework dependencies are installed in history/.venv:

~~~powershell
npm.cmd run history -- run-model --adapter models/boss_adapter.py --thing-id smartbin:bin-002
npm.cmd run history -- get-run RUN_ID --include-inputs
~~~

The placeholder currently fails honestly with model-not-supplied. The working pipeline-check adapter reports input rows and the latest stored weights; its output has prediction=false. Results are stored in model_runs, never written to live Things. Failures are retained as failed runs. Each completed run records model identity, source, time range, exact snapshot IDs and an input SHA256. get-run --include-inputs reconstructs and verifies those original inputs, even after new data arrives. A process interruption can leave a run marked running; it does not imply a completed model output.

Before integration, obtain the model artifact/code, framework/version, feature names/order, expected units/time window, preprocessing and output format. Those details determine the adapter and dependencies; no TensorFlow/PyTorch/scikit-learn model is fabricated here.

## Performance metrics and checks

~~~powershell
npm.cmd run test:history
npm.cmd run verify:history
npm.cmd run history -- benchmark --bins 100 --revisions 1000 --queries 30
~~~

verify:history checks 12 stored Things, nine valid bins and the DB-to-Python result, asserting that model execution does not change live Things. It requires the history API/collector to be running. Optional --publish-demo-reading republishes bin-002's existing weight through the separate spoofer, waits for both its new Ditto revision and notification to be archived, and verifies history. This optional check advances the reading timestamp/revision; it preserves weight and model attributes and requires paused auto-publishing with matching simulator/Thing values.

Benchmark data is synthetic and isolated in .results/benchmark-<id>.sqlite3; it never enters live history. The report .results/benchmark.json records 100,000 snapshots by default, 30 reads per case, returned-row counts, p50/p95/max durations and actual SQLite query plans. One warm-up precedes each case. Timings include checking out a pooled read connection, querying and materializing Python rows; they exclude HTTP, inference and concurrent ingest. The final pooled-read benchmark on this machine recorded:

| Query | Rows | Median (p50) | p95 |
| --- | ---: | ---: | ---: |
| Latest fleet | 100 | 1.03 ms | 1.59 ms |
| One bin, last 60 observations | 60 | 0.75 ms | 1.38 ms |
| One warehouse, last hour | 2,040 | 22.36 ms | 33.48 ms |

These are warm-read measurements of this workload on SQLite 3.50.4 with the safe rollback journal, not a comparison proving SQLite faster than other products. /api/metrics separately reports this service process's last 512 measured reads per operation, row counts and collector state.

Primary references: [Ditto Thing SSE notifications](https://eclipse.dev/ditto/httpapi-sse.html), [Python sqlite3](https://docs.python.org/3/library/sqlite3.html), [SQLite WAL](https://www.sqlite.org/wal.html).
