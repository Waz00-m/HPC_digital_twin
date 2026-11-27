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

## Fetch data for the models

The ready-to-run script is `history/fetch_smartbin_data.py`. It reads the existing database in read-only mode; it does not contact MQTT/Ditto, initialize an empty database, deduplicate equal weights, install a model library or run a prediction. Its default series is timed samples, including repeated weights. Full original Thing JSON is included, so values outside the flattened feature columns remain accessible.

From the repository root on Windows, after starting the history service:

~~~powershell
# Fetch all stored timed SmartBin samples as JSON.
npm.cmd run fetch:data

# Export one bin, keeping full Thing JSON alongside model-friendly columns.
npm.cmd run fetch:data -- --thing-id smartbin:bin-002 --output ../exports/bin-002.json

# CSV for every bin in one warehouse. Bounds require UTC Z or a timezone offset.
npm.cmd run fetch:data -- --warehouse-id warehouse-b --since 2026-11-26T00:00:00Z --until 2026-11-27T00:00:00Z --format csv --output ../exports/warehouse-b.csv

# Separate series: observed revisions, or only the latest stored state.
npm.cmd run fetch:data -- --series revisions --thing-id smartbin:bin-002
npm.cmd run fetch:data -- --series latest --no-thing
~~~

The npm helper runs from `history/`, so `../exports` means the repository's exports folder. A direct interpreter invocation keeps your current working directory: `python history/fetch_smartbin_data.py --db history/.data/things.sqlite3 --output exports/all-bins.json`. Use the configured virtualenv interpreter on Windows if plain `python` is unavailable.

On the Mac Docker edition, no host Python installation is required:

~~~bash
bash macos/python.sh fetch --thing-id smartbin:bin-002 --output /exports/bin-002.json
bash macos/python.sh fetch --format csv --output /exports/all-bins.csv
~~~

The function for the boss's Python code (run from `history/`, or add that folder to his Python import path) is:

~~~python
from twin_history.reader import fetch_data

data = fetch_data(
    thing_id="smartbin:bin-002",
    since="2026-11-26T00:00:00Z",
    until="2026-11-27T00:00:00Z",
)
rows = data["rows"]  # list of dictionaries; feed this to the supplied model later
# Each row includes weight_kg, capacity_kg, warehouse_id, sampled_at,
# reading_at, quality and the full original Thing under row["thing"].
~~~

The JSON envelope includes the selected series, time axis, source identity, columns, filters and a SHA256 of its rows. CSV serializes the full Thing into its `thing` cell; `--no-thing` omits it. Invalid/awaiting readings stay visible with quality flags unless `--valid-only` is explicitly selected. Limit defaults to 50,000 rows and fails visibly if exceeded; narrow the time window or bin/warehouse filter instead of silently losing model inputs. Empty results remain an empty list. The existing database can be fetched while the collector is stopped; missing databases and old schemas produce an actionable error without being created or migrated by the fetcher.

`quality="valid"` checks the value and model context; it does not mean the sensor reading is fresh. The model must use `reading_at` to apply its own freshness policy. A timed snapshot of yesterday's last reading still retains yesterday's `reading_at`.

## Timed samples and unchanged weights

The history service now polls Ditto independently every **30 seconds**, starting immediately, as well as listening for change notifications. A successful poll creates a `samples` row for each returned Thing even when its weight and revision are unchanged. The complete immutable Thing remains stored once per revision in `snapshots`; timed rows point to it through `snapshot_id`.

For example, 20 kg at 10:00:00 and 20 kg at 10:00:30 produce two sample IDs. `sampled_at` changes; `reading_at` stays at the original load-reading receipt time if no new reading arrived. This is a timed observation of the digital twin, not evidence of a new physical measurement. No values are interpolated, no new sensor timestamps are invented and failed polls create a `sample-gap` notice instead of fake data. Polls never overlap; a slow GET may delay the next sample. Historical gaps are not backfilled.

To change the interval on Windows, stop the history backend and start it with `history/Start-History.ps1 -SampleSeconds 10`. The Python CLI accepts `serve --sample-seconds 10` or `collect --sample-seconds 10`; supported values are 1–3,600 whole seconds. `TWIN_SAMPLE_SECONDS` provides the default when the Python command has no explicit interval. On Mac, run `TWIN_SAMPLE_SECONDS=10 bash macos/setup.sh`; that interval is saved for subsequent setup/start runs. Stop/start the history service after source changes.

Database schema 2 adds the sample table and indexes while preserving existing snapshots, notifications, model runs and IDs. Timed rows begin when this version first runs; old revision history is not turned into fabricated historical timed samples. The health/metrics response reports `sample_seconds`, `last_sampled_at` and `last_sample_error` separately from the SSE connection state.

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
- Timed samples, including unchanged values: http://127.0.0.1:4322/api/samples?thing_id=smartbin%3Abin-002
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
| samples | Successful timed Ditto observations, each linked to a stored snapshot; unchanged weights/revisions remain separate timed rows |
| latest_things | Pointer to the highest observed revision, with a deletion flag |
| ditto_events | Original post-Ditto notifications, including changed fields and protocol context |
| collector_log | Connection, outage, deletion and observed-revision-gap notices |
| model_runs | Model name/version, exact input manifest, completion/failure and JSON output |
| metadata | Database source identity |

All currently imported Things are captured at startup. Notifications trigger a complete Thing GET; reconnect reconciles the current fleet, and healthy stream heartbeats allow periodic reconciliation (nominally 30 seconds). Repeat observations of the same revision do not duplicate the snapshot. Older revisions cannot replace a newer latest pointer. Conflicting payloads with the same revision raise an error.

JSON numbers with equal values, such as `10` and `10.0`, are treated as equivalent when checking an existing revision. This handles integer/decimal serialization changes without rewriting stored payloads, hashes or model inputs. Booleans, strings, missing fields and different numeric values remain distinct. A genuine conflict reports the Thing ID, revision and changed top-level fields and leaves the original record intact.

SSE may contain only the changed fields, so it is not treated as a full Thing. The separately fetched snapshot can be newer than the triggering event. Original notifications remain available, but the collector does not claim every intermediate revision became a complete snapshot. Reconnect has no change-event replay guarantee: offline intervals are recorded and current state is reconciled; missed historical readings cannot be invented. Discovery supports up to 200 imported Things and fails visibly rather than silently dropping later pages.

Observation time, Ditto modification time and reading receipt time are distinct. Revision-history query windows use observed_at, the first database capture of that revision; timed-sample windows use sampled_at. Revisions caused by model changes can repeat the same reading_at. Timed polls also retain the original reading_at. Adapters must choose their intended series/time axis and any sensor-reading deduplication; polling does not imply evenly spaced physical sensor measurements. No interpolation or learned feature calculation is applied automatically. Percentages use capacity from that historical Thing version, not today's capacity.

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

Timed-series model inputs additionally include sample_id and sampled_at. Run `npm.cmd run history -- run-model --input-series samples --limit 50000` to verify this DB-to-model route without a supplied model. The default runner series remains `revisions` for compatibility; it never silently switches series. Input manifests retain the selected series, exact sample/snapshot IDs and a hash; replay preserves repeated rows even after new samples arrive. The local model-run API also accepts `input_series: "samples"`.

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
npm.cmd run history -- run-model --input-series samples --adapter models/boss_adapter.py --thing-id smartbin:bin-002
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
