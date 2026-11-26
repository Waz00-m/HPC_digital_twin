"""Portable importer for explicit Warehouse/SmartBin facts in the starter OWL file."""
import argparse
import base64
from decimal import Decimal, InvalidOperation
import getpass
import json
import math
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import xml.etree.ElementTree as ET

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
OWL = "http://www.w3.org/2002/07/owl#"
XML = "http://www.w3.org/XML/1998/namespace"


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError("Identifiers must use letters, digits, dots, underscores or hyphens.")
    return value


def parse_ontology(path, namespace="smartbin"):
    identifier(namespace)
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8-sig")
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("DTD/entity declarations are not supported.")
    root = ET.fromstring(text)
    if root.tag != "{" + RDF + "}RDF" or root.findall(".//{" + OWL + "}imports"):
        raise ValueError("Use a self-contained starter ontology in RDF/XML without OWL imports.")
    bases = {}
    def walk(element, base):
        base = urljoin(base, element.get("{" + XML + "}base", ""))
        bases[id(element)] = base
        for child in element:
            walk(child, base)
    walk(root, path.as_uri())
    def iri(element, attribute="about"):
        value = element.get("{" + RDF + "}" + attribute)
        if value is None and attribute == "about":
            value = "#" + element.get("{" + RDF + "}ID") if element.get("{" + RDF + "}ID") else None
        if value is None:
            raise ValueError("Expected a named RDF resource.")
        return urljoin(bases[id(element)], value)
    ontologies = root.findall("{" + OWL + "}Ontology")
    if len(ontologies) != 1:
        raise ValueError("Expected one ontology declaration.")
    ontology_iri = iri(ontologies[0])
    classes = {iri(element).split("#")[-1].split("/")[-1]: iri(element) for element in root.findall("{" + OWL + "}Class")}
    if not all(name in classes for name in ("SmartBin", "Warehouse")):
        raise ValueError("Declare SmartBin and Warehouse classes explicitly.")
    schema = classes["SmartBin"][:-len("SmartBin")]
    if classes["Warehouse"] != schema + "Warehouse":
        raise ValueError("SmartBin and Warehouse must use the same schema namespace.")
    records = {}
    for element in root:
        if element.get("{" + RDF + "}about") is None and element.get("{" + RDF + "}ID") is None:
            continue
        record = records.setdefault(iri(element), {"elements": [], "types": set()})
        record["elements"].append(element)
        record["types"].add(element.tag.removeprefix("{").replace("}", ""))
        record["types"].update(iri(child, "resource") for child in element.findall("{" + RDF + "}type"))
    def one(record, name, resource=False, optional=False):
        values = set()
        for element in record["elements"]:
            for child in element.findall("{" + schema + "}" + name):
                if resource:
                    values.add(iri(child, "resource"))
                else:
                    if len(child) or child.get("{" + RDF + "}resource") is not None:
                        raise ValueError(name + " must be a literal.")
                    values.add((child.text or "").strip())
        if not values and optional:
            return None
        if len(values) != 1 or "" in values:
            raise ValueError("Expected exactly one explicit " + name + ".")
        return next(iter(values))
    def number(value, name):
        try:
            decimal = Decimal(value)
            value = float(decimal)
        except (InvalidOperation, ValueError, OverflowError):
            raise ValueError(name + " must be a positive finite decimal.") from None
        if not math.isfinite(value) or value <= 0:
            raise ValueError(name + " must be a positive finite decimal.")
        return value
    targets, warehouses, ids = [], {}, set()
    def add(identity, attributes):
        thing_id = namespace + ":" + identity
        if thing_id in ids:
            raise ValueError("Duplicate Thing ID: " + thing_id)
        ids.add(thing_id)
        targets.append({"thingId": thing_id, "attributes": attributes})
    for subject, record in records.items():
        if classes["Warehouse"] not in record["types"]:
            continue
        if classes["SmartBin"] in record["types"]:
            raise ValueError("An individual cannot be both Warehouse and SmartBin in this mapper.")
        identity = identifier(one(record, "warehouseId"))
        warehouses[subject] = identity
        add(identity, {"type": "Warehouse", "warehouseId": identity, "ontologyIri": ontology_iri,
                       "ontologyIndividualIri": subject, "ontologyClassIri": classes["Warehouse"]})
    for subject, record in records.items():
        if classes["SmartBin"] not in record["types"]:
            continue
        identity, warehouse = identifier(one(record, "binId")), one(record, "locatedIn", resource=True)
        if warehouse not in warehouses:
            raise ValueError(identity + " references a warehouse which is not explicitly defined.")
        capacity = number(one(record, "capacityKg"), "capacityKg")
        threshold_text = one(record, "alertThresholdPercent", optional=True)
        threshold = number(threshold_text, "alertThresholdPercent") if threshold_text is not None else None
        if threshold is not None and threshold > 100:
            raise ValueError("alertThresholdPercent must not exceed 100.")
        topic = one(record, "mqttTopic")
        if any(character in topic for character in ("+", "#", "\0")):
            raise ValueError("Use a concrete MQTT topic without wildcard/null characters.")
        add(identity, {"type": "SmartBin", "binId": identity, "warehouseId": warehouses[warehouse],
                       "warehouseThingId": namespace + ":" + warehouses[warehouse], "capacityKg": capacity,
                       "mqttTopic": topic, "alertThresholdPercent": threshold, "ontologyIri": ontology_iri,
                       "ontologyIndividualIri": subject, "ontologyClassIri": classes["SmartBin"]})
    if not warehouses or len(targets) == len(warehouses):
        raise ValueError("Expected a nonempty warehouse/bin fleet.")
    return sorted(targets, key=lambda target: (target["attributes"]["type"] != "Warehouse", target["thingId"]))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def import_targets(targets, origin, username, password):
    url = urlsplit(origin)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
        raise ValueError("Use a Ditto origin without credentials, path or query.")
    if url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Remote Ditto requires HTTPS.")
    authorization = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
    opener = build_opener(ProxyHandler({}), NoRedirect())
    def request(method, path, body=None, headers=None):
        payload = json.dumps(body, allow_nan=False).encode() if body is not None else None
        request_headers = {"Authorization": authorization, "Accept": "application/json", **(headers or {})}
        if payload is not None:
            request_headers["Content-Type"] = "application/merge-patch+json" if method == "PATCH" else "application/json"
        try:
            response = opener.open(Request(origin.rstrip("/") + "/api/2" + path, data=payload, headers=request_headers, method=method), timeout=30)
        except HTTPError as error:
            if method == "GET" and error.code == 404:
                return 404, None, None
            raise RuntimeError("Ditto HTTP " + str(error.code) + " for " + method + " " + path) from None
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None, (response.headers.get("ETag") or "").removeprefix("W/")
    request("GET", "/whoami")
    plan = []
    for target in targets:
        path = "/things/" + quote(target["thingId"], safe="")
        status, existing, etag = request("GET", path)
        current = (existing or {}).get("attributes", {})
        changes = {key: value for key, value in target["attributes"].items()
                   if key not in current or current[key] != value or isinstance(current[key], bool) != isinstance(value, bool)}
        if status != 404 and changes and not etag:
            raise RuntimeError("Missing concurrency token; no import started.")
        plan.append((path, status, changes, etag))
    summary = {"created": 0, "updated": 0, "unchanged": 0, "warehouses": sum(t["attributes"]["type"] == "Warehouse" for t in targets)}
    summary["bins"] = len(targets) - summary["warehouses"]
    for path, status, changes, etag in plan:
        if status == 404:
            request("PUT", path, {"attributes": changes}, {"If-None-Match": "*"}); summary["created"] += 1
        elif changes:
            request("PATCH", path, {"attributes": changes}, {"If-Match": etag}); summary["updated"] += 1
        else:
            summary["unchanged"] += 1
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ontology", type=Path, default=Path(__file__).with_name("smartbin-demo.owl"))
    parser.add_argument("--namespace", default=os.getenv("DITTO_NAMESPACE", "smartbin"))
    parser.add_argument("--url", default=os.getenv("DITTO_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Use the public local sample credentials when no environment overrides are set")
    args = parser.parse_args()
    records = parse_ontology(args.ontology, args.namespace)
    if args.preview:
        print(json.dumps(records, indent=2))
    else:
        user = os.getenv("DITTO_USERNAME", "ditto")
        password = os.getenv("DITTO_PASSWORD") or ("ditto" if args.demo else getpass.getpass("Ditto password: "))
        print(json.dumps(import_targets(records, args.url, user, password), indent=2))
