"""Verify stored Things -> Python. Optional one-reading test uses the existing spoofer."""
import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from twin_history.ditto import DittoClient


def request(origin, path, body=None):
    value = None if body is None else json.dumps(body).encode()
    with urlopen(Request(origin + path, data=value, headers={"Content-Type": "application/json"}), timeout=20) as response:
        return json.load(response)


def verify(publish=False):
    origin = "http://127.0.0.1:4322"
    health = request(origin, "/health")
    assert health["service"] == "smartbin-thing-history"
    assert health["collector"]["connected"], "Ditto collector must be connected before verification."
    latest = request(origin, "/api/latest?include_thing=true")
    assert latest["count"] == 12, "This verification targets three warehouses and nine bins."
    assert sum(row["model_type"] == "SmartBin" and row["quality"] == "valid" for row in latest["rows"]) == 9
    target = "smartbin:bin-002"
    before = next(row for row in latest["rows"] if row["thing_id"] == target)
    client = DittoClient()
    initial = client.things()
    change = None
    if publish:
        previous_events = request(origin, "/api/metrics")["counts"]["ditto_events"]
        state = request("http://127.0.0.1:4318", "/api/state")
        assert not state["running"], "Pause automatic spoofer publishing before this optional test."
        bin_value = next(bin for bin in state["bins"] if bin["id"] == "bin-002")
        assert bin_value["online"] and state["connection"]["status"] == "connected"
        assert abs(bin_value["weightKg"] - before["weight_kg"]) < .0001, "Spoofer and Thing weights differ. Match them before the optional publish test."
        request("http://127.0.0.1:4318", "/api/action", {"action": "publish", "selector": {"binId": "bin-002"}})
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            rows = request(origin, "/api/latest?thing_id=smartbin%3Abin-002&include_thing=true")["rows"]
            if rows and rows[0]["revision"] > before["revision"] and request(origin, "/api/metrics")["counts"]["ditto_events"] > previous_events:
                break
            time.sleep(.2)
        else:
            raise AssertionError("The new Ditto revision was not captured in the database.")
        after = rows[0]
        assert after["weight_kg"] == before["weight_kg"]
        assert after["thing"]["attributes"] == before["thing"]["attributes"]
        history = request(origin, "/api/history?thing_id=smartbin%3Abin-002")["rows"]
        assert {before["revision"], after["revision"]} <= {row["revision"] for row in history}
        assert request(origin, "/api/metrics")["counts"]["ditto_events"] > 0
        change = {"thing_id": target, "previous_revision": before["revision"], "captured_revision": after["revision"],
                  "weight_kg_unchanged": after["weight_kg"], "source": "Existing spoofer -> MQTT -> Ditto -> history collector"}
    # Model execution itself must not change any live Thing.
    before_model = client.things()
    run = request(origin, "/api/model-runs", {"model": "pipeline-check"})
    after_model = client.things()
    assert before_model == after_model, "Reading the DB / running Python must not write live twins."
    assert run["status"] == "completed" and run["output"]["prediction"] is False
    assert len(run["output"]["bins"]) == 9
    assert request(origin, "/api/model-runs/" + run["run_id"])["manifest"] == run["manifest"]
    if not publish:
        assert initial == after_model
    result = {"stored_things": latest["count"], "valid_bins": 9, "publish_check": change,
              "python_run_id": run["run_id"], "input_rows": run["output"]["input_rows"], "model": run["model_name"],
              "boss_model_connected": False, "live_things_unchanged_by_model": len(after_model),
              "metrics": request(origin, "/api/metrics")}
    directory = Path(__file__).parent / ".results"
    directory.mkdir(exist_ok=True)
    report_name = "live-publish-verification.json" if publish else "live-verification.json"
    (directory / report_name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-demo-reading", action="store_true", help="Republish bin-002's existing weight through the spoofer; advances its Ditto revision/receipt time.")
    verify(parser.parse_args().publish_demo_reading)
