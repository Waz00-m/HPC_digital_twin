import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "macos"))
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
owl = load("portable_ontology", ROOT / "ontology/import_ontology.py")
compose = load("mac_compose", ROOT / "macos/prepare_stack.py")
from fingerprint import fingerprint


class PortableTests(unittest.TestCase):
    def test_runtime_fingerprints_ignore_docs_but_track_code_changes(self):
        with tempfile.TemporaryDirectory(prefix="smartbin-mac-fingerprint-") as directory:
            root = Path(directory)
            self.assertTrue(root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
            self.assertTrue(root.name.startswith("smartbin-mac-fingerprint-"))
            (root / "dashboard").mkdir(); (root / "dashboard/server.mjs").write_text("initial")
            images = {"node:24-bookworm-slim": {"reference": "pinned-node"}}
            first = fingerprint(root, "node", images)
            (root / "dashboard/README.md").write_text("changed instructions")
            self.assertEqual(fingerprint(root, "node", images), first)
            (root / "dashboard/server.mjs").write_text("new runtime")
            self.assertNotEqual(fingerprint(root, "node", images), first)

    def test_starter_mapping_is_complete_and_rejects_invalid_relationship(self):
        targets = owl.parse_ontology(ROOT / "ontology/smartbin-demo.owl")
        self.assertEqual(len(targets), 12)
        self.assertEqual(sum(t["attributes"]["type"] == "SmartBin" for t in targets), 9)
        bin_value = next(t for t in targets if t["thingId"] == "smartbin:bin-002")["attributes"]
        self.assertEqual(bin_value["capacityKg"], 50)
        self.assertEqual(bin_value["warehouseThingId"], "smartbin:warehouse-b")
        self.assertEqual(bin_value["alertThresholdPercent"], 85)
        with tempfile.TemporaryDirectory(prefix="smartbin-mac-test-") as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()))
            self.assertTrue(Path(directory).name.startswith("smartbin-mac-test-"))
            path = Path(directory) / "invalid.owl"
            text = (ROOT / "ontology/smartbin-demo.owl").read_text()
            path.write_text(text.replace('rdf:resource="#warehouse-a"', 'rdf:resource="#warehouse-missing"'))
            with self.assertRaisesRegex(ValueError, "not explicitly defined"):
                owl.parse_ontology(path)
            path.write_text('<!DOCTYPE rdf:RDF [<!ENTITY x "a">]>' + text)
            with self.assertRaisesRegex(ValueError, "DTD/entity"):
                owl.parse_ontology(path)

    def test_compose_is_isolated_persistent_and_uses_supported_pinned_architectures(self):
        images = json.loads((ROOT / "macos/images.lock.json").read_text())["images"]
        names = {"mongodb": "mongo:7.0", "nginx": "nginx:1.27-alpine", "swagger-ui": "swaggerapi/swagger-ui:v5.9.1"}
        for service in ("policies", "things", "things-search", "connectivity", "gateway", "ditto-ui"):
            names[service] = "eclipse/" + (service if service == "ditto-ui" else "ditto-" + service) + ":latest"
        base = {"services": {name: {"image": image, "ports": ["0.0.0.0:27017:27017"], "networks": {"default": {}}} for name, image in names.items()}}
        hashes = {"node": "a" * 64, "python": "b" * 64}
        result = compose.prepare(base, images, "/Users/boss/SmartBin Demo", hashes)
        self.assertEqual(result["name"], "smartbin-mac")
        self.assertNotIn("ports", result["services"]["mongodb"])
        self.assertNotIn("ports", result["services"]["gateway"])
        self.assertIn("mongo-data:/data/db", result["services"]["mongodb"]["volumes"])
        for service in result["services"].values():
            self.assertTrue(all(port.startswith("127.0.0.1:") for port in service.get("ports", [])))
        for name in ("dashboard", "simulator", "history"):
            service = result["services"][name]
            self.assertEqual(service["network_mode"], "service:nginx")
            self.assertEqual(service["environment"]["DITTO_URL"], "http://127.0.0.1:80")
            self.assertNotIn("ports", service)
            self.assertEqual(service["build"]["labels"]["smartbin.source-fingerprint"], hashes["python" if name == "history" else "node"])
        self.assertIn("/Users/boss/SmartBin Demo/history/.data:/data", result["services"]["history"]["volumes"])
        for image in images.values():
            self.assertIn("@sha256:", image["reference"])
            self.assertTrue(any(platform.startswith("linux/arm64") for platform in image["platforms"]))
            self.assertIn("linux/amd64", image["platforms"])


if __name__ == "__main__":
    unittest.main()
