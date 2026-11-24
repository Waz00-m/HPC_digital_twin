# SmartBin starter ontology

Open `smartbin-demo.owl` in Protege with **File > Open**. If Protege asks, open it in a new window. This is a separate starter model; the earlier `digital-twin/smartbin.rdf` draft is not an import dependency.

The file is OWL expressed in RDF/XML. It uses a separate ontology IRI ending in `/demo`, so it can be opened alongside the earlier draft. No external ontology imports are required.

## What is included

- Five classes: Enterprise, Warehouse, Rack, SmartBin, Asset. All five are siblings under `owl:Thing`; a bin being inside a warehouse is a relationship, not a subclass relationship.
- Three Warehouse individuals and nine SmartBin individuals.
- `locatedIn` links every bin to a warehouse.
- `capacityKg` gives each bin a maximum load in kilograms.
- `alertThresholdPercent` sets the demo weight-alert threshold for each bin (85% in all nine examples).
- `binId`, `warehouseId` and `mqttTopic` preserve the simulator's default identifiers and topics for later mapping.
- Enterprise, Rack and Asset are reserved categories. No enterprise, rack or asset records or relationships have been invented.

| Warehouse | Bin IDs | Demo capacity of each bin |
| --- | --- | --- |
| warehouse-a | bin-001, bin-004, bin-007 | 10 kg |
| warehouse-b | bin-002, bin-005, bin-008 | 50 kg |
| warehouse-c | bin-003, bin-006, bin-009 | 100 kg |

These values match `simulator/engine.mjs`'s initial fleet. They are illustrative capacities, not confirmed physical measurements. Changed simulator settings do not automatically update the ontology.

## Look at one bin first

1. In Protege, open **Individuals by class**.
2. Select **SmartBin** in the class hierarchy. Expand `owl:Thing` if needed.
3. In **Direct instances**, select **bin-001**.
4. Under **Object property assertions**, find `locatedIn warehouse-a`.
5. Under **Data property assertions**, find `capacityKg 10.0`, `binId bin-001` and `mqttTopic smartbin/warehouse-a/bin-001/weight`.

Select **Warehouse** to see the three warehouse individuals. The nine bins appear as individuals of SmartBin; they do not appear as nine new classes.

## If you prefer the class hierarchy paste box

Select `owl:Thing`, open **Tools > Create class hierarchy**, and paste the contents of `classes.txt`. Each name is on its own line with no indentation. Leave any option for marking all these classes disjoint unchecked, since the meaning of Asset has not yet been agreed.

That box creates only the class skeleton. It does not create the twelve individuals, capacities or warehouse links. Open `smartbin-demo.owl` to get the whole starter model. Pasting a class list also does not remove earlier incorrect subclass relationships.

## Import the OWL records into Ditto

`Import-SmartBinOntology.ps1` reads the actual local RDF/XML file and maps its asserted Warehouse and SmartBin individuals to Ditto Things. It is a mapper for this starter schema, not a general OWL parser or a reasoner. Save ontology changes in Protege as RDF/XML before running it again.

From PowerShell:

```powershell
cd D:\projects\V1_SmartBin-main\digital-twin\ontology

# Show the JSON mapping without contacting Ditto or asking for credentials:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Import-SmartBinOntology.ps1 -Preview

# Import to the local server on port 8090; enter your Ditto credentials when prompted:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Import-SmartBinOntology.ps1
```

For the unchanged sample installation, the username and password are both `ditto`. The script does not save credentials. The command's execution policy applies only to that PowerShell process, allowing this local script to run without changing your saved execution policy. In a PowerShell session that already permits local scripts, you can also invoke `.\Import-SmartBinOntology.ps1` directly. For another file or server, pass `-OntologyPath` or `-DittoUrl`; `-Namespace` defaults to `smartbin`. Remote servers require HTTPS. The script supports PowerShell 5.1 and newer.

The default file produces twelve Things: `smartbin:warehouse-a` through `smartbin:warehouse-c`, and `smartbin:bin-001` through `smartbin:bin-009`.

| Source OWL fact | Ditto destination |
| --- | --- |
| Individual's Warehouse or SmartBin type | `attributes.type` |
| `warehouseId` or `binId` literal | Corresponding identifier attribute and namespaced Thing ID |
| Bin's `locatedIn` warehouse reference | `attributes.warehouseId` and `attributes.warehouseThingId` |
| `capacityKg` | `attributes.capacityKg` |
| `alertThresholdPercent` | `attributes.alertThresholdPercent` |
| `mqttTopic` | `attributes.mqttTopic` |
| Model, individual and class IRIs | `attributes.ontologyIri`, `ontologyIndividualIri`, `ontologyClassIri` |

The importer validates the whole input before contacting Ditto and reads every target before writing. It creates missing Things, merges mapped attributes into existing Things and skips unchanged records. The manually created `smartbin:bin-001` is enriched, rather than duplicated. Unrelated attributes, existing policies and all features (including later live readings) are preserved. New Things get Ditto's default policy for the authenticated creator; existing policy references are retained. Concurrent changes cause the affected write to fail rather than overwrite another writer; rerun to read fresh state. A failure during writes can leave a partial import, and rerunning resumes it. Removing or renaming an OWL individual does not delete existing Things.

Refresh the Explorer at `http://localhost:8090/ui/`, open **Things**, and click **search** with no filter. You should see twelve records. On a bin, expand **Attributes** to see its warehouse reference, capacity and ontology references. A `warehouseThingId` is an application-level reference; Ditto does not automatically enforce referential integrity or apply OWL reasoning to it.

Only explicit Warehouse and SmartBin records and the properties listed above are mapped. Enterprise, Rack, Asset, class restrictions, inferred facts and other OWL statements are not converted. External OWL imports are not followed, and the OWL source file is not changed.

## Runtime integration

The ontology defines categories, relationships and configuration. Its topic strings are metadata; configure Ditto native MQTT using ../mqtt/configure-ditto.mjs after importing. Reconfigure after adding/moving bins or changing MQTT topics.

Ditto now receives raw weights directly through its native MQTT connection. There is no standalone MQTT-to-HTTP bridge. The separate dashboard at http://127.0.0.1:4321/ reads raw weights and current model attributes, calculates weight utilization and applies the per-bin alert threshold on read. Changing an imported capacity or threshold appears on the next dashboard refresh; it no longer needs a new MQTT reading or a bridge metadata-cache wait.

The model stores alertThresholdPercent as configuration. The shared read-side calculation applies that policy; it does not infer OWL alert classes. Edit an individual's capacity/threshold in Protege, save RDF/XML, and rerun the importer. Thresholds must be greater than zero and at most 100. Older files without the threshold remain importable and produce an unconfigured alert status.

Current readings belong to runtime state, not static facts invented in the OWL file. Scenario lab uses a snapshot of this state for read-only forecasts; live execution is a later integration. Full setup and architecture are in ../README.md.
