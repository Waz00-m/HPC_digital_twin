# SmartBin digital twin — MacBook setup and operation

Updated 26 November 2026. Use the supplied SmartBin-Mac-Demo.zip package with this guide. The illustrated Word edition is [SmartBin-MacBook-Guide.docx](SmartBin-MacBook-Guide.docx); it includes browser screenshots and the timed-sample fetch pipeline.

## Before starting

This package runs three warehouses and nine virtual bins. Physical bins are not needed. The Mac edition installs Docker Desktop if it is missing and uses containers for Ditto, MQTT, the spoofer, dashboard and Python history service. Separate Git, Homebrew, Node.js, Python and PowerShell installations are unnecessary. Protégé is optional for later ontology editing; the supplied OWL file is imported automatically.

Use a Docker Desktop-supported version of macOS, an administrator account/password, a reliable internet connection and at least 20 GB of free storage. A Mac with 8 GB RAM is the practical minimum for this full demo; 16 GB is recommended. Docker must have at least 2 CPU cores and 4 GB memory available; 6 GB memory is preferred when the Mac has enough physical RAM. Apple Silicon and Intel image variants have been checked in the pinned upstream image manifests.

Setup detects Apple Silicon or Intel automatically. If Docker is already running locally, its installation is skipped. If Docker Desktop is installed but stopped, setup opens that copy and waits. Detection covers /Applications, ~/Applications, the Docker CLI and custom app locations registered with Spotlight. A fresh Docker installation is downloaded only when none is found. Keep the Mac awake and Terminal open; the installer does not accept Docker's terms, enter your password or dismiss permission prompts for you.

## First-time installation

1. Download SmartBin-Mac-Demo.zip and open it in Finder to extract SmartBinDemo.
2. Move SmartBinDemo into your Home folder: Finder > Go > Home. The resulting location should be ~/SmartBinDemo. Keep the whole folder together.
3. Open Terminal with Command+Space, type Terminal, and press Return.
4. Paste these two commands, pressing Return after each:

~~~bash
cd "$HOME/SmartBinDemo"
bash macos/setup.sh
~~~

Alternatively, open Install-Mac.command in that folder. If Finder does not execute a downloaded command file, use the Terminal method above; do not disable macOS security protections.

5. If requested, enter your Mac administrator password for Docker's official installer. Terminal normally shows no characters while you type a password.
6. If Docker Desktop opens with first-run screens, complete its terms and required macOS permissions. The script waits for the engine and continues automatically. An already-running installation needs no first-run setup.
7. If the script asks for more Docker resources, open Docker Desktop > Settings > Resources. Allocate at least 2 CPUs and 4 GB memory (6GB preferred), choose Apply & Restart, and rerun the same setup command.
8. Wait for “Setup complete”. The warehouse dashboard and spoofer open in your browser. A successful setup report is saved in .runtime/mac/setup-report.json.

Setup checks each stage before doing work. It reuses the downloaded Ditto deployment and cached native images, and skips Node/Python image builds when their runtime source and base images are unchanged. On first setup it imports three warehouses and nine bins from ontology/smartbin-demo.owl and configures native MQTT. Later setup skips provisioning if its source fingerprint is unchanged and the live model/connection check succeeds; otherwise it reapplies source-managed setup. It starts the apps, seeds only missing readings and runs the DB-to-Python check. Existing readings, databases and scenario drafts are preserved. Missing cached components are downloaded or rebuilt on a rerun.

The Mac's existing Node.js, Python, Homebrew or Git versions do not matter: this edition uses its own container runtimes and does not install those tools on the host. No need to identify which Mac already has which of those tools. Keep using the same SmartBinDemo folder so its saved files and container ownership stay together.

## Everyday use

Open Start-Mac.command to start everything after a restart. Docker Desktop is opened if needed. Existing readings, history and scenario drafts are preserved. The spoofer's controls are restored from current Ditto values; normal startup does not publish replacement readings.

Open Stop-Mac.command to stop only this demo's containers. It keeps MongoDB, MQTT state, Python history and drafts. Open Status-Mac.command to inspect container and pipeline status without changing bin values.

The same actions work from Terminal after cd "$HOME/SmartBinDemo":

~~~bash
bash macos/start.sh
bash macos/stop.sh
bash macos/status.sh
~~~

| Tool | Browser address | Purpose |
| --- | --- | --- |
| Warehouse dashboard | http://127.0.0.1:4321/ | Current Thing values, alerts and Scenario lab |
| Separate spoofer | http://127.0.0.1:4318/ | Set a bin's weight and send an MQTT reading |
| Thing-history metrics | http://127.0.0.1:4322/api/metrics | JSON counts, collector status and query timings |
| Stored latest Things | http://127.0.0.1:4322/api/latest?include_thing=true | Original Thing data and prepared feature rows |
| Model-run results | http://127.0.0.1:4322/api/model-runs | Recorded Python adapter runs |
| Ditto Explorer | http://127.0.0.1:8090/ui/ | Inspect Things, policies and native MQTT configuration |

For Ditto Explorer choose the local environment. Its public sample credentials are ditto / ditto; optional DevOps credentials are devops / foobar. These are local development defaults. Host ports are bound to Mac loopback, and the internal MongoDB/gateway ports are not published.

## A five-minute demonstration

### Send one bin reading

1. Open the spoofer. Setup connects it to the MQTT broker; if it shows disconnected, use its Connect control.
2. Choose Warehouse B, then bin-002. Its demo capacity is 50 kg.
3. Move the weight slider to 30 kg and press Send reading. Slider movement previews a value; Send reading publishes it.
4. Open the warehouse dashboard. Within the normal refresh interval it should show 30 kg and 60% of rated weight for bin-002.
5. Select that bin to inspect its capacity, warehouse, MQTT source and timestamps. The history service records the new Ditto revision as well.

On a first installation the seeded fleet has three bins at 40%, three at 85% and three at 110%. These are illustrative load levels, including overload cases, not measurements from physical hardware. Percentages describe rated weight, not occupied volume.

### Compare handling decisions

1. In the dashboard open Scenario lab.
2. Open Bin purposes & demand to review Collection or Inventory purpose and the assumed rate/service time for each bin.
3. Review duration, travel time and delayed start. The optional demand burst and uncertainty settings are expandable.
4. Press Compare strategies.
5. Read the recommended next job, its safety margin and the consequences of starting late. Inspect strategy switches the displayed schedule and per-bin outcomes.

One shared team is simulated while all bins continue changing. Fixed route, threshold first and least time remaining use the same workload. Simulation results do not publish MQTT or alter live Things. Demand/service assumptions and synthetic trial outcomes are illustrative; the rule is not a guaranteed optimum or a trained prediction model.

## Stored Things and Python models

The data path is spoofer > MQTT > Ditto Thing > history database > Python adapter > stored result. History reads post-Ditto change notifications and complete Thing snapshots, not the MQTT stream. It stores original JSON, warehouse/capacity context, revisions and timestamps. Connection gaps are recorded; offline periods cannot be assumed to contain complete history.

The current history service also saves a timed observation every 30 seconds, even if a weight is unchanged. `sampled_at` is the observation time; `reading_at` retains the original load-reading receipt time. Failed polls are logged, never backfilled. Fetch stored model inputs with `bash macos/python.sh fetch --output /exports/all-bins.json`, or add `--format csv`. The read-only Python function, interval configuration and sample-based model-run options are documented in history/README.md.

To run the existing pipeline check, open Terminal in SmartBinDemo:

~~~bash
bash macos/python.sh run-model
~~~

The output must say model_name=pipeline-check, status=completed and prediction=false. This proves database retrieval and the Python adapter. It does not execute your boss's model, which has not been supplied. The pending integration file is history/models/boss_adapter.py. Actual model code, framework/version, columns, units, time window and output format are needed before connecting it.

Other useful commands:

~~~bash
# Read current stored state.
bash macos/python.sh latest --include-thing

# Export one bin's observed history to the visible exports folder.
bash macos/python.sh export --thing-id smartbin:bin-002 \
  --format csv --output /exports/bin-002.csv

# Optional benchmark: synthetic data is separate from live history.
bash macos/python.sh benchmark --bins 100 --revisions 1000 \
  --directory /exports/benchmarks
~~~

Exported files appear in SmartBinDemo/exports on the Mac. Benchmark timings are measured on that Mac and include warm database retrieval plus Python row preparation; they exclude HTTP and model inference. Do not present another machine's timings as this Mac's measured performance.

## Where data is saved

| Data | Location |
| --- | --- |
| Ditto Things and policies | Named Docker volume smartbin-mac_mongo-data |
| MongoDB configuration | Named Docker volume smartbin-mac_mongo-config |
| MQTT session persistence | Named Docker volume smartbin-mac_mqtt-data |
| Thing history and Python results | SmartBinDemo/history/.data/things.sqlite3 |
| Scenario drafts | SmartBinDemo/dashboard/.data/scenarios.json |
| Exports | SmartBinDemo/exports |
| Generated stack / setup report | SmartBinDemo/.runtime/mac |

Folders beginning with a dot are hidden in Finder; Command+Shift+Period toggles their visibility. Keep the project folder in place while using it. Stop-Mac.command preserves these records. Removing Docker volumes or deleting the project data is a separate reset, not an everyday stop procedure. A backup of just the source ZIP does not include runtime databases.

## Troubleshooting

**Docker first-run screens are still open.** Finish them and leave Terminal open. If setup timed out, rerun Install-Mac.command. Repeating setup is supported.

**Docker exists in a custom folder but is not detected.** Normal and Spotlight-registered locations are detected automatically. For an unregistered copy, run this from SmartBinDemo, replacing the example with its actual path:

~~~bash
SMARTBIN_DOCKER_APP="/path/to/Docker.app" bash macos/setup.sh
~~~

**Existing Docker needs repair.** An incomplete Docker.app or an installation without Compose is reported clearly and left in place. Finish or repair that installation, then rerun. A stopped local engine with only a CLI is not treated as permission to install a second Docker.

**Remote Docker context selected.** Setup needs the engine on this Mac. Select its local context using your Docker controls and rerun. The launcher does not silently switch contexts or deploy to another machine.

**Another SmartBinDemo folder already owns the stack.** Use the launchers in that original folder. A second extracted copy refuses to replace its containers or attach its own history files to that stack. Other Docker projects are left alone.

**Not enough Docker memory.** Set the resources described above, Apply & Restart, and try again. Close other heavy apps if an 8 GB Mac is under pressure. Do not allocate all physical memory to Docker.

**Port is already allocated.** Another app or another copy of the demo may be using 8090, 1884, 4318, 4321 or 4322. Stop that known app or the other demo through its own controls; do not kill unrelated processes blindly. Then rerun Start-Mac.command.

**Missing readings or disconnected collector.** Use Status-Mac.command, confirm http://127.0.0.1:8090/health is healthy, and inspect logs. Initial images and Java services can take several minutes to start. On a clean install use Install-Mac.command, not Start-Mac.command, so the model and missing sample readings are created.

~~~bash
bash macos/logs.sh history
bash macos/logs.sh gateway
bash macos/logs.sh mqtt
~~~

**Image download fails.** Check internet access and retry. The image lock lists native Apple Silicon and Intel variants. Use the Docker Desktop version supported by the Mac's macOS release; the vendor installer enforces its compatibility requirements.

**After editing OWL or app source.** Rerun Install-Mac.command. It rebuilds only affected runtime images and reapplies provisioning when its inputs changed or the live check fails, preserving telemetry, policy references and saved history. Guide-only edits do not rebuild the runtimes. Adding the boss's real model may require extra Python libraries in the container image; that integration is a later step.

**Validation scope.** The portable importer was checked against the existing 12 Things without changing them; its mapping matches the Windows importer. Shell syntax, generated Compose configuration and Linux container runtimes are checked on the development machine. Mocked Docker tests cover existing/running and stopped installations, custom app locations, CLI-only and missing installations, cached-image reuse, changed-runtime builds, missing Compose, remote contexts and another folder's existing stack. The native macOS installer and its GUI approval steps require the target Mac; they cannot be fully exercised on this Windows workstation.

## Official references

- Docker Desktop installation and supported macOS: https://docs.docker.com/desktop/setup/install/mac-install/
- Ditto resource requirements: https://eclipse.dev/ditto/installation-running.html
- Ditto Thing change notifications: https://eclipse.dev/ditto/httpapi-sse.html
- Source repository: https://github.com/Waz00-m/HPC_digital_twin

The provided Mac ZIP is the handoff source snapshot for this guide. A different repository checkout must contain macos/, history/ and the Mac launchers before these instructions apply.
