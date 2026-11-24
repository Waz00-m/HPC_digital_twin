# SmartBin digital twin demo

Three warehouses, nine virtual bins. The original V1 SmartBin application remains separate.

## Clone and set up a new computer

This repository contains the digital twin demo only. Eclipse Ditto is a submodule pinned to the version used by the demo. Install Git, Node.js 20 or newer and Docker Desktop with Linux containers. Start Docker Desktop before the Docker commands.

~~~powershell
git clone --recurse-submodules https://github.com/Waz00-m/HPC_digital_twin.git
cd HPC_digital_twin
npm.cmd --prefix simulator ci

# Configure the local Ditto sample deployment on port 8090.
Set-Content -LiteralPath .\ditto\deployment\docker\.env -Value 'DITTO_EXTERNAL_PORT=8090'
docker compose --project-name docker --project-directory .\ditto\deployment\docker --env-file .\ditto\deployment\docker\.env -f .\ditto\deployment\docker\docker-compose.yml up -d
~~~

If you cloned without submodules, run git submodule update --init --recursive first. Wait for http://localhost:8090/health to report status UP. Then import the starter model and start the two apps:

~~~powershell
# The importer prompts for the sample Ditto credentials: ditto / ditto.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\ontology\Import-SmartBinOntology.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-DigitalTwin.ps1
~~~

Open the telemetry simulator, connect its broker, and send initial readings. Then open the warehouse dashboard and Scenario lab. The repository does not include Docker volumes, installed dependencies, local credentials, saved drafts or recorded sensor state. It contains development sample authentication settings; use the local demo on a development machine.

## Open the tools

- Warehouse dashboard: http://127.0.0.1:4321/
- Telemetry simulator: http://127.0.0.1:4318/
- Ditto Explorer: http://localhost:8090/ui/

The dashboard reads Ditto without depending on the simulator being open or running. It shows the last received weight, current model capacity, weight percentage and model-based alert. Select a bin for its source, topic, threshold and ontology identity.

## Start after a restart

Start Docker Desktop first. From this folder:

~~~powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-DigitalTwin.ps1
~~~

This starts the existing Ditto containers without deleting data, starts the MQTT broker, configures Ditto's native connection, and starts the dashboard and simulator as hidden local Node processes if their ports are free. Logs are in .runtime/. It assumes the installed Ditto project/network is docker / docker_default, port 8090, and an already imported ontology.

On a fresh checkout, install dependencies with npm.cmd ci in simulator/ and build CSS with npm.cmd run build:css in both simulator/ and dashboard/. Built CSS is supplied. Dashboard/server and simulation code use Node's standard library; no additional dashboard dependency installation is required.

## How data flows

~~~text
Simulator / physical gateway
          → MQTT broker
          → Ditto native MQTT connection
          → raw bin load feature
          → read-only dashboard API
          → warehouse dashboard

Protégé OWL → ontology importer → Ditto model attributes
Ditto snapshot → scenario preview engine → projected results (no live writes)
~~~

There is no separate MQTT-to-HTTP JavaScript bridge. The small incoming-mapping.js script executes inside Ditto's supported connectivity service. It accepts numeric kg readings or matching JSON and replaces only that bin's load feature. Imported attributes, policies and other features are preserved.

The dashboard derives percentage and alert state on read using the current capacityKg and alertThresholdPercent attributes. These calculated results are not telemetry fields stored by Ditto. Model changes appear in the dashboard without another weight reading. A receipt timestamp is not a device-online guarantee. This measures weight utilization, not volume fullness.

## Native MQTT

The broker is Mosquitto in mqtt/compose.yml. Host clients use mqtt://127.0.0.1:1884; Ditto uses tcp://smartbin-mqtt:1883 on its Docker network. The published host port remains loopback-only. The development broker allows anonymous access inside that network.

Run node mqtt/configure-ditto.mjs to create/update smartbin-native-mqtt, with one source per warehouse and explicitly imported bin topics. Warehouse-scoped subjects receive only load-feature access; source-address enforcement binds each topic bin to its target Thing. Reconfigure after adding/moving bins or changing topics. Capacity/threshold changes require only the ontology import.

Compatibility with the installed Ditto version: a connection allows four sources by default, so the nine topic addresses are grouped into three warehouse sources. MQTT enforcement accepts source:address; the generic header placeholder example is not accepted for MQTT enforcement by this installation. No upstream Ditto code or global limits were changed.

Credentials stay in server process memory. Defaults match the local sample installation: main ditto / ditto; DevOps devops / foobar. Override DITTO_URL, DITTO_USERNAME, DITTO_PASSWORD, DITTO_DEVOPS_USERNAME, DITTO_DEVOPS_PASSWORD, or DITTO_NAMESPACE as needed. No credentials are sent to the browser.

## Handling simulation

Open the dashboard's Scenario lab and press Compare strategies. It answers which bin one team should handle next, why, and what changes if that team starts late. It compares a fixed route, threshold-first handling and a least-time-remaining rule, with travel/service occupying one shared team while other bins keep filling or being consumed.

Bin purposes & demand configures Collection or Inventory per bin, assumed demand, alert and service time. Demand burst & uncertainty controls workload bursts, synthetic variation and repeatable trials. Results show separate collection overflow and unmet inventory demand, strategy tradeoffs, the team's schedule and per-bin outcomes. Saved drafts live in dashboard/.data/scenarios.json. Existing linear drafts are preserved with an explicit conversion when loaded.

These are read-only scenario runs. Capacities/starting readings come from Ditto; purposes, demand, travel and service are demo assumptions. Comparisons publish no MQTT, change no live twins and operate no physical devices. The least-time-remaining rule is a heuristic; OWL reasoning, learned demand and physical calibration are not implemented. See simulation/README.md for model rules and limits.

## Verification

~~~powershell
npm.cmd test
npm.cmd run verify:native
npm.cmd run verify:operations
~~~

Native verification deliberately changes all nine virtual bin weights, verifies actual Ditto revisions/source/identity, checks invalid payload rejection, and leaves three normal, three attention and three overloaded bins. It requires the removed bridge's port 4320 to be closed. Report: mqtt/native-demo-results.json. Ordinary tests use isolated fixtures and prove previews do not change twin inputs.

Operations verification publishes nothing: it compares the nine-bin scenario and asserts all12 Ditto Things (models, telemetry and revisions) are unchanged. Pause spoofer auto-publishing first so independent telemetry does not invalidate that check. Report: simulation/.results/operations-demo.json.
