import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import csv
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from twin_history.collector import Collector
from twin_history.models import run_inputs, run_model
from twin_history.reader import fetch_command, fetch_data
from twin_history.server import make_server
from twin_history.store import Store
from test_pipeline import thing


class SamplingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smartbin-samples-")
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(self.root.name.startswith("smartbin-samples-"))
        self.addCleanup(self.temp.cleanup)
        self.path = self.root / "history.sqlite3"
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.store.bind_source("http://127.0.0.1:8090", "smartbin")

    def seed(self):
        for stamp in ("2026-11-26T10:00:00Z", "2026-11-26T10:00:30Z", "2026-11-26T10:01:00Z"):
            self.store.record_samples([thing()], stamp)

    def test_unchanged_revision_has_three_timed_rows_without_new_sensor_times(self):
        self.seed()
        rows = self.store.samples(include_thing=True)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(self.store.history()), 1)
        self.assertEqual([r["weight_kg"] for r in rows], [20, 20, 20])
        self.assertEqual(len({r["sample_id"] for r in rows}), 3)
        self.assertEqual(len({r["sampled_at"] for r in rows}), 3)
        self.assertEqual(len({r["reading_at"] for r in rows}), 1)
        self.assertEqual(len({r["snapshot_id"] for r in rows}), 1)
        self.assertEqual(rows[0]["thing"], thing())
        self.store.record_samples([thing()], "2026-11-26T10:00:00Z")
        self.assertEqual(len(self.store.samples()), 3)

    def test_new_reading_with_same_weight_is_preserved_as_another_revision(self):
        self.store.record_samples([thing()], "2026-11-26T10:00:00Z")
        updated = thing(2)
        updated["features"]["load"]["properties"]["receivedAt"] = "2026-11-26T10:00:25Z"
        self.store.record_samples([updated], "2026-11-26T10:00:30Z")
        rows = fetch_data(self.path)["rows"]
        self.assertEqual([r["weight_kg"] for r in rows], [20, 20])
        self.assertNotEqual(rows[0]["reading_at"], rows[1]["reading_at"])
        self.assertEqual(len(self.store.history()), 2)

    def test_readonly_fetch_filters_keeps_quality_and_never_initializes_missing_db(self):
        self.seed()
        invalid = thing(2, weight=-1)
        self.store.record_samples([invalid], "2026-11-26T10:01:30Z")
        before = self.store.metrics()["counts"]
        data = fetch_data(self.path, since="2026-11-26T15:30:30+05:30", until="2026-11-26T10:01:30Z")
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["time_axis"], "sampled_at")
        self.assertEqual(data["rows"][-1]["quality"], "invalid-model")
        self.assertEqual(fetch_data(self.path, valid_only=True)["count"], 3)
        self.assertEqual(fetch_data(self.path, thing_id="' OR 1=1 --")["count"], 0)
        self.assertEqual(fetch_data(self.path, warehouse_id="warehouse-c")["count"], 0)
        self.assertEqual(before, self.store.metrics()["counts"])
        warehouse = {"thingId": "smartbin:warehouse-b", "_revision": 1, "attributes": {"type": "Warehouse"}}
        self.store.insert_snapshot(warehouse)
        before = self.store.metrics()["counts"]
        self.assertEqual(fetch_data(self.path, series="latest", limit=1)["count"], 1)
        # The warehouse is deliberately excluded from a SmartBin model input.
        self.assertEqual(before, self.store.metrics()["counts"])
        with self.assertRaisesRegex(ValueError, "not silently truncated"):
            fetch_data(self.path, limit=1)
        with self.assertRaisesRegex(ValueError, "timezone"):
            fetch_data(self.path, since="2026-11-26T10:00:00")
        missing = self.root / "absent.sqlite3"
        with self.assertRaisesRegex(ValueError, "does not exist"):
            fetch_data(missing)
        self.assertFalse(missing.exists())
        reader = Store(self.path, readonly=True)
        self.addCleanup(reader.close)
        with reader.read_connection() as con:
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("DELETE FROM samples")

    def test_timer_runs_during_idle_stream_and_outage_never_creates_fake_samples(self):
        class Client:
            origin = "http://127.0.0.1:8090"
            namespace = "smartbin"
            calls = 0
            def things(self):
                self.calls += 1
                if self.calls == 2:
                    raise ConnectionError("Fixture Ditto outage")
                return [thing()]
        class Clock:
            waits = 0
            def is_set(self):
                return self.waits >= 3
            def wait(self, seconds):
                self.waits += 1
        client = Client()
        collector = Collector(self.store, client)
        collector._sample_loop(Clock())  # no SSE events/heartbeats and no real sleeps
        self.assertEqual(client.calls, 3)
        self.assertEqual(len(self.store.samples()), 2)
        self.assertEqual(len(self.store.history()), 1)
        self.assertIn("sample-gap", [r["kind"] for r in self.store.logs()])
        self.assertIsNone(collector.status()["last_sample_error"])
        self.assertEqual(collector.status()["sample_seconds"], 30)

    def test_sample_based_model_run_replays_exact_repeated_inputs(self):
        self.seed()
        run = run_model(self.store, input_series="samples", since="2026-11-26T10:00:00Z", until="2026-11-26T11:00:00Z")
        self.assertEqual(run["output"]["input_rows"], 3)
        self.assertFalse(run["output"]["prediction"])
        self.assertEqual(len(set(run["manifest"]["snapshot_ids"])), 1)
        self.assertEqual(len(set(run["manifest"]["sample_ids"])), 3)
        before = run_inputs(self.store, run["run_id"])
        self.store.record_samples([thing(2, weight=25)], "2026-11-26T10:02:00Z")
        self.assertEqual(run_inputs(self.store, run["run_id"]), before)

    def test_concurrent_sse_and_timer_first_observation_is_idempotent(self):
        barrier = threading.Barrier(4)
        def observe(index):
            barrier.wait()
            if index % 2:
                return self.store.record_samples([thing()], f"2026-11-26T10:00:0{index}Z")
            return self.store.insert_snapshot(thing())
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(observe, range(4)))
        self.assertEqual(len(self.store.history()), 1)
        self.assertEqual(len(self.store.samples()), 2)

    def test_existing_database_migrates_additively_and_does_not_invent_past_samples(self):
        self.store.insert_snapshot(thing())
        before = self.store.history(include_thing=True)
        with self.store.connection() as con:
            con.execute("DROP TABLE samples"); con.execute("PRAGMA user_version=1")
        with self.assertRaisesRegex(ValueError, "read-only fetcher did not change"):
            fetch_data(self.path)
        upgraded = Store(self.path)
        self.addCleanup(upgraded.close)
        self.assertEqual(upgraded.history(include_thing=True), before)
        self.assertEqual(upgraded.samples(), [])
        with upgraded.read_connection() as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_json_csv_export_preserves_full_values_and_refuses_database_output(self):
        self.seed()
        options = dict(db=str(self.path), series="samples", thing_id=None, warehouse_id=None, since=None, until=None,
            limit=50000, valid_only=False, no_thing=False, format="json", output=self.root / "data.json")
        with redirect_stdout(io.StringIO()):
            fetch_command(argparse.Namespace(**options))
        self.assertEqual(json.loads((self.root / "data.json").read_text())["count"], 3)
        options.update(format="csv", output=self.root / "data.csv")
        with redirect_stdout(io.StringIO()):
            fetch_command(argparse.Namespace(**options))
        with (self.root / "data.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 3)
        self.assertEqual(json.loads(rows[0]["thing"]), thing())
        options["output"] = self.path
        with self.assertRaisesRegex(ValueError, "must not replace"):
            fetch_command(argparse.Namespace(**options))

    def test_samples_api_and_registered_model_use_the_same_timed_series(self):
        self.seed()
        server = make_server(self.store, port=0)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        origin = "http://127.0.0.1:" + str(server.server_port)
        with urlopen(origin + "/api/samples?thing_id=smartbin%3Abin-002&include_thing=true") as response:
            data = json.load(response)
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["rows"][0]["thing"], thing())
        body = json.dumps({"input_series": "samples", "since": "2026-11-26T00:00:00Z", "until": "2026-11-27T00:00:00Z"}).encode()
        with urlopen(Request(origin + "/api/model-runs", data=body, headers={"Content-Type": "application/json"})) as response:
            run = json.load(response)
        self.assertEqual(run["output"]["input_rows"], 3)
        self.assertEqual(run["manifest"]["input_series"], "samples")


if __name__ == "__main__":
    unittest.main()
