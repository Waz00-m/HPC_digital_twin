import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from twin_history.collector import Collector
from twin_history.ditto import DittoClient, sse_messages
from twin_history.models import Adapter, get_run, list_runs, run_inputs, run_model
from twin_history.server import make_server
from twin_history.store import Store, timestamp, supports_safe_wal, same_json_value


def thing(revision=1, weight=20, capacity=50, **changes):
    value = {"thingId": "smartbin:bin-002", "_revision": revision, "_modified": "2026-11-25T10:00:00Z",
        "attributes": {"type": "SmartBin", "binId": "bin-002", "warehouseId": "warehouse-b", "capacityKg": capacity, "alertThresholdPercent": 85},
        "features": {"load": {"properties": {"weightKg": weight, "unit": "kg", "receivedAt": "2026-11-25T10:00:00Z", "source": "mqtt-native", "warehouseId": "warehouse-b"}},
                     "otherFeature": {"properties": {"retained": True}}}}
    value.update(changes)
    return value


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="smartbin-history-")
        self.assertTrue(Path(self.temp.name).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
        self.assertTrue(Path(self.temp.name).name.startswith("smartbin-history-"))
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.store = Store(self.path)
        self.addCleanup(self.store.close)

    def test_persistence_deduplication_full_thing_and_immutable_model_context(self):
        original = thing()
        first = self.store.insert_snapshot(original, "2026-11-25T10:00:00Z")
        self.assertTrue(first["inserted"])
        self.assertFalse(self.store.insert_snapshot(original)["inserted"])
        self.store.insert_snapshot(thing(2, capacity=100), "2026-11-25T10:01:00Z")
        stored = Store(self.path)
        self.addCleanup(stored.close)
        history = stored.history(thing_id="smartbin:bin-002", include_thing=True)
        self.assertEqual([row["weight_percent"] for row in history], [40, 20])
        self.assertEqual(history[0]["thing"], original)
        self.assertEqual(stored.latest()[0]["capacity_kg"], 100)
        self.assertEqual(stored.metrics()["counts"]["snapshots"], 2)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.store.insert_snapshot(thing(weight=21))

    def test_old_revisions_do_not_replace_latest_and_gaps_are_visible(self):
        self.store.insert_snapshot(thing(4))
        self.store.insert_snapshot(thing(2))
        self.assertEqual(self.store.latest()[0]["revision"], 4)
        self.store.insert_snapshot(thing(7))
        self.assertEqual(self.store.logs()[0]["kind"], "revision-gap")
        self.store.mark_deleted("smartbin:bin-002")
        self.assertEqual(self.store.latest(), [])
        self.assertEqual(len(self.store.history()), 3)

    def test_equivalent_json_numbers_do_not_conflict_or_rewrite_saved_inputs(self):
        original = thing(weight=20, capacity=50)
        first = self.store.insert_snapshot(original)
        variant = thing(weight=20.0, capacity=50.0)
        variant["attributes"]["alertThresholdPercent"] = 85.0
        again = self.store.insert_snapshot(variant)
        self.assertFalse(again["inserted"])
        self.assertEqual(first["snapshot_id"], again["snapshot_id"])
        self.assertEqual(self.store.latest(include_thing=True)[0]["thing"], original)
        with self.assertRaisesRegex(ValueError, 'smartbin:bin-002.*revision 1.*features'):
            self.store.insert_snapshot(thing(weight=21))
        self.assertFalse(same_json_value({"weight": True}, {"weight": 1}))
        self.assertFalse(same_json_value({"weight": None}, {}))
        self.assertFalse(same_json_value(9007199254740993, 9007199254740992.0))

    def test_quality_gates_and_sql_filters(self):
        invalid = thing(2)
        invalid["features"]["load"]["properties"]["warehouseId"] = "warehouse-c"
        self.store.insert_snapshot(thing(), "2026-11-25T10:00:00Z")
        self.store.insert_snapshot(invalid, "2026-11-25T10:01:00Z")
        self.store.insert_snapshot(thing(3, weight=True), "2026-11-25T10:02:00Z")
        self.assertEqual(len(self.store.history(valid_only=True)), 1)
        self.assertEqual(self.store.latest()[0]["quality"], "missing-or-invalid-reading")
        self.assertEqual(self.store.history(thing_id="' OR 1=1 --"), [])
        with self.assertRaisesRegex(ValueError, "not silently truncated"):
            self.store.history(limit=1)
        with self.assertRaises(ValueError):
            self.store.history(thing_id=[])
        with self.assertRaises(ValueError):
            self.store.history(limit=True)
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.store.history(since="2026-11-25T10:00:00")
        self.assertEqual(timestamp("2026-11-25T15:30:00+05:30"), "2026-11-25T10:00:00.000000Z")
        with self.store.connection() as con:
            plan = con.execute("EXPLAIN QUERY PLAN SELECT * FROM snapshots WHERE thing_id=? AND observed_at>=?", ("smartbin:bin-002", "2026")).fetchone()[3]
        self.assertIn("INDEX snapshots_by_thing_time", plan)

    def test_model_runner_uses_db_only_and_records_provenance_and_failures(self):
        self.store.insert_snapshot(thing(), "2026-11-25T10:00:00Z")
        bad = thing(2, capacity=0)
        self.store.insert_snapshot(bad, "2026-11-25T10:01:00Z")
        run = run_model(self.store, since="2026-11-25T09:00:00Z", until="2026-11-25T11:00:00Z")
        self.assertEqual(run["status"], "completed")
        self.assertFalse(run["output"]["prediction"])
        self.assertEqual(len(run["manifest"]["snapshot_ids"]), 1)
        self.assertEqual(len(run["manifest"]["excluded_snapshot_ids"]), 1)
        def failure(rows, context):
            raise ValueError("Fixture model failure")
        with self.assertRaisesRegex(RuntimeError, "Fixture model failure"):
            run_model(self.store, Adapter("fixture", "1", failure), since="2026-11-25T09:00:00Z", until="2026-11-25T11:00:00Z")
        self.assertEqual(list_runs(self.store)[0]["status"], "failed")
        self.assertEqual(get_run(self.store, run["run_id"])["manifest"], run["manifest"])
        self.assertEqual([row["snapshot_id"] for row in run_inputs(self.store, run["run_id"])], run["manifest"]["snapshot_ids"])

    def test_collector_preserves_notification_and_fetches_whole_thing(self):
        calls = []
        class Client:
            origin = "http://127.0.0.1:8090"
            namespace = "smartbin"
            def things(self):
                calls.append("GET things"); return [thing()]
            def thing(self, identity):
                calls.append("GET " + identity); return thing(2)
        collector = Collector(self.store, Client())
        collector.reconcile()
        event = {"thingId": "smartbin:bin-002", "features": {"load": {"properties": {"weightKg": 20}}}}
        collector.handle(event); collector.handle(event)
        self.assertEqual(self.store.metrics()["counts"]["ditto_events"], 1)
        self.assertEqual(self.store.metrics()["counts"]["snapshots"], 2)
        self.assertIn("otherFeature", self.store.latest(include_thing=True)[0]["thing"]["features"])
        self.assertTrue(all(call.startswith("GET") for call in calls))
        collector.handle({"thingId": "smartbin:bin-002", "_context": {"path": "/", "topic": "smartbin/bin-002/things/twin/events/deleted", "headers": {"entity-revision": "2"}}})
        self.assertEqual(self.store.latest(), [])
        self.store.insert_snapshot(thing(3))
        self.store.mark_deleted("smartbin:bin-002", 2)
        self.assertEqual(self.store.latest()[0]["revision"], 3)
        with self.assertRaisesRegex(ValueError, "different Ditto"):
            self.store.bind_source("http://localhost:9000", "smartbin")

    def test_sse_framing_and_origin_validation(self):
        stream = [b": keepalive\r\n", b"\r\n", b'data: {"thingId":\n', b'data: "smartbin:bin-002"}\n', b"\n"]
        self.assertEqual(list(sse_messages(stream)), [None, {"thingId": "smartbin:bin-002"}])
        self.assertEqual(list(sse_messages([b"data:\n", b"\n"])), [None])
        with self.assertRaises(ValueError):
            list(sse_messages(["data:" + "x" * 2_000_001]))
        with self.assertRaises(ValueError):
            DittoClient(origin="http://example.org")
        with self.assertRaises(ValueError):
            DittoClient(origin="https://user:password@example.org")
        for version in ((3, 50, 4), (3, 51, 2), (3, 49, 0)):
            self.assertFalse(supports_safe_wal(version))
        for version in ((3, 50, 7), (3, 44, 6), (3, 51, 3), (3, 52, 0)):
            self.assertTrue(supports_safe_wal(version))

    def test_stream_disconnect_records_gap_and_reconciles_current_state(self):
        store = self.store
        class Stop:
            stopped = False
            def is_set(self):
                return self.stopped
            def wait(self, seconds):
                self.stopped = True
        class Client:
            namespace = "smartbin"
            origin = "http://127.0.0.1:8090"
            def stream(self):
                return io.BytesIO(b'data: {"thingId":"smartbin:bin-002"}\n\n')
            def things(self):
                return [thing()]
            def thing(self, identity):
                return thing(2)
        collector = Collector(store, Client())
        collector.run(Stop())
        self.assertEqual(store.metrics()["counts"]["snapshots"], 2)
        self.assertEqual(store.logs()[0]["kind"], "stream-gap")
        self.assertFalse(collector.status()["connected"])

    def test_concurrent_readers_reuse_connections_and_do_not_block_committed_history(self):
        from concurrent.futures import ThreadPoolExecutor
        self.store.insert_snapshot(thing())
        def read():
            for _ in range(10):
                rows = self.store.latest()
                self.assertEqual(len(rows), 1)
                self.assertGreaterEqual(rows[0]["revision"], 1)
        def write():
            for revision in range(2, 12):
                self.store.insert_snapshot(thing(revision))
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = [pool.submit(read) for _ in range(5)] + [pool.submit(write)]
            for job in jobs:
                job.result(timeout=20)
        self.assertEqual(self.store.latest()[0]["revision"], 11)
        self.assertEqual(len(self.store.history()), 11)
        self.assertLessEqual(self.store._pool_count, 4)

    def test_local_http_queries_and_only_registered_model_can_run(self):
        self.store.insert_snapshot(thing())
        server = make_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        origin = "http://127.0.0.1:" + str(server.server_port)
        with urlopen(origin + "/api/latest?include_thing=true") as response:
            self.assertEqual(json.load(response)["count"], 1)
        with urlopen(origin + "/api/metrics") as response:
            self.assertIn("latest", json.load(response)["query_timings"])
        request = Request(origin + "/api/model-runs", data=b'{}', headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            self.assertEqual(response.status, 201)
        for data, extra, expected in ((b'{"model":"unknown"}', {}, 400), (b'{}', {"Origin": "https://example.org"}, 403)):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(origin + "/api/model-runs", data=data, headers={"Content-Type": "application/json", **extra}))
            self.assertEqual(caught.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
