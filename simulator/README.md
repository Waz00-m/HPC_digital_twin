# SmartBin simulator

Local browser controls for virtual bin telemetry. Production demo messages go to the standalone Docker MQTT broker and Ditto native connectivity. Aedes is used only by isolated tests. No physical ESP8266/ESP32 is required; the original V1 application remains independent.

## Run on Windows

Requires Node.js 20 or newer. From this folder:

```powershell
npm.cmd ci
npm.cmd run build:css
npm.cmd start
```

Open http://127.0.0.1:4318. CSS is already built in the supplied project, so repeat the build only after changing UI source. A second MQTT application can connect to `mqtt://127.0.0.1:1884` and subscribe to `smartbin/#`.

1. Click **Connect local broker** once and wait for **Ready to send**. If it already says Ready to send, keep the current connection.
2. Choose a warehouse and bin. The first bin is selected initially. The fleet table's **Select** button also opens a bin in the controller.
3. Move the weight slider or choose **Empty**, **25%**, **50%**, **85%** or **Full**. This only previews a draft: dragging and releasing never send a reading.
4. Press **Send reading**. This switches the selected bins to Hold, applies the weight and publishes it once. Inspect **Sent readings & MQTT activity** for the topic, payload and acknowledgement.
5. For an exact number, expand **Exact values & slider options**. Enter kilograms or a percentage, then press the same Send reading button. The slider normally spans 0–100%; the optional overload scale extends it to 200%.

For a group, choose **All bins in selection**. Percentage mode applies the percentage to each bin's own capacity: 50% means 5 kg for a 10 kg bin and 25 kg for a 50 kg bin. Exact kilogram mode applies the same weight to every selected bin; its group slider is disabled so it does not imply one common percentage.

For automatic behaviour, expand **Automatic scenarios**, choose a scenario and rate, and **Apply scenario to selection**. Then **Start auto-send for all bins**. Only the selected bins change scenario, but all reporting bins publish at the interval. **Pause auto-send** freezes scenario progression and automatic publishes; manual Send reading remains available.

To operate 100 bins, expand **More bin controls & fleet setup**, pause first, and choose **Create 100 bins**. Replacement discards current weights and scenarios. Generating simulated bins does not add corresponding records to the ontology or Ditto.

The page's **How to use & controls** link opens an operating guide with variable and action tables.

The built-in broker and control panel bind to loopback only. To use another broker, expand MQTT settings, enter an `mqtt://` or `mqtts://` URL, choose credentials if needed, and apply. This does not alter the physical gateway. TLS certificate validation stays enabled. Only connect to brokers you intend to use for this experiment.

## Send readings into Ditto

Start the complete local demo using ../Start-DigitalTwin.ps1 after Docker Desktop is ready. The broker is now the standalone Mosquitto service in ../mqtt/compose.yml; the simulator no longer hosts the live broker.

1. Connect the local broker at mqtt://127.0.0.1:1884.
2. Choose a bin and press Send reading. The MQTT topic carries its identity; the payload is the calibrated demo weight.
3. Open the separate warehouse dashboard at http://127.0.0.1:4321/ to see the value read from Ditto, with percentage and alert derived from its current model.

There is no bridge:ditto command or separate MQTT-to-HTTP relay. Ditto's native connection consumes the configured topics and runs its small payload mapper internally. The raw load feature contains weightKg, unit, warehouseId, receivedAt and source mqtt-native. Percentages and alerts are calculated by the read-only dashboard API, not stored by a relay.

See ../README.md for full startup/configuration and ../mqtt/README.md for the native connection. Run npm.cmd run verify:native for the nine-bin live test; it changes the virtual readings and writes ../mqtt/native-demo-results.json. The old demo-results.json is historical evidence from the superseded bridge experiment, not the current implementation.

## Variables

| Variable | Meaning / units | Changed by |
| --- | --- | --- |
| `id` (`binId` in JSON messages) | Globally unique bin ID | Fleet generation |
| `warehouseId` | Bin location: warehouse-a, warehouse-b or warehouse-c | Fleet generation, distributed round-robin |
| Draft reading | Browser preview; not yet applied or published | Slider, presets or exact input |
| `weightKg` | Current simulated load, 0–2,000,000 kg for manual input | Send reading, Apply reading locally, active scenarios or reset |
| `capacityKg` | Configured rated load, 0.001–1,000,000 kg | Apply capacity to selection |
| `percent` | Input shortcut / derived value: `100 * weightKg / capacityKg`; 0–200% input | Percentage input; stored as a resulting weight, not an additional bin field |
| `mode` | `manual`, `filling`, `draining`, `cycle` or `noisy` | Apply scenario; a manual reading sets `manual` |
| `rateKgPerMinute` | Fill / drain / cycle speed, 0–1,000,000 kg/min | Scenario form; unused in Hold and fluctuating modes |
| `online` | Simulated reporting switch; silent bins do not auto-advance or publish | Silence selection / Restore reporting |
| `lastPublishedAt` | Timestamp attached to the last successfully acknowledged send | Read-only |
| `published` | Per-bin successful-send count | Read-only |
| `brokerUrl` | MQTT destination; default `mqtt://127.0.0.1:1884` | MQTT connection settings |
| `username`, `password` | Optional broker credentials, held only in server memory | MQTT connection settings; password is not returned by the state API |
| `prefix` | Topic prefix; default `smartbin` | MQTT connection settings |
| `format` | `number` or `json` payload | MQTT connection settings |
| `intervalMs` | Automatic send interval, 250–60,000 ms; entered as seconds | MQTT connection settings |
| `running` | Whether scenarios and automatic publishing are running | Start / Pause / Disconnect / Reset |
| Fleet count | `bins.length`, from 1 to 1,000 | Replace fleet; no separate count is stored per bin |
| `sent`, `failed` | Global broker acknowledgements and failed publish attempts | Read-only, for this server session |
| `connection.status` | Disconnected, connecting or connected | MQTT client connection events |

Capacity changes affect only simulator configuration. To keep the ontology and Ditto aligned, update the OWL capacities and rerun the ontology importer separately. The 85% highlight is a display convention; it does not suppress messages or create a Ditto alarm.

## Actions and scope

| UI action | Scope | What happens |
| --- | --- | --- |
| Move slider / choose preset / type a value | Browser draft | Preview only; no server update or MQTT publish |
| Send reading | Selected bins | Apply manual weight, then publish once for selected reporting bins |
| Apply reading locally | Selected bins | Apply manual weight without an immediate publish; running auto-send can publish it on its next interval |
| Resend current reading | Selected reporting bins | Publish the current server weight; ignore an unsent browser draft |
| Apply scenario | Selected bins | Change mode and rate; does not itself start or stop auto-send |
| Apply capacity | Selected bins | Set the same capacity for the selection; does not change current weight |
| Start auto-send for all bins | Entire fleet | Advance each active scenario and publish all reporting bins at the interval |
| Pause auto-send | Entire fleet | Freeze scenario progression and automatic sending; manual Send remains available |
| Silence / Restore reporting | Selected bins | Stop / permit publishing and scenario progression; no offline message is emitted |
| Connect / Apply & connect | Entire simulator | Change MQTT connection; pause auto-send |
| Disconnect | Entire simulator | Disconnect MQTT and pause auto-send |
| Replace fleet / Create 100 bins | Entire fleet | Replace bins, capacities, initial weights and scenarios; pause first; old message counters/log remain session records |
| Empty all & pause | Entire fleet | Set weights to zero, mode to Hold and reporting on; pause without an immediate publish |
| Export fleet | Entire fleet | Download JSON snapshot; no MQTT publish or mutation |

Filling clamps at capacity; draining clamps at zero. Cycle fills to capacity and resets to zero rather than gradually draining. Fluctuating mode uses a bounded random walk, with up to 1% of capacity change per 250 ms step. Scenarios advance only when auto-send is running.

## Initial fleet and units

Three bins per warehouse, nine bins total; unique global bin IDs `bin-001` through `bin-009`. Demo capacities are 10 kg in Warehouse A, 50 kg in B, 100 kg in C. These and initial weights are illustrative, editable values. Fleet generation distributes IDs round-robin over A, B, C.

Readings are simulated calibrated weight in kilograms, not raw ADC values and not volume fullness. A manually set value may exceed capacity (up to 200% when using percentages), useful for overload demonstrations. Gradual fill/empty clamp at capacity/zero; cycle reaches capacity then resets to zero; fluctuating readings perform a bounded random walk of up to 1% capacity per simulation step (250 ms). Silent bins freeze and emit no messages, including manual publishing. They do not publish an offline event; downstream software must detect staleness.

85% is only a display highlight, not a publishing filter: readings publish at every weight. Capacities and scenarios remain simulator configuration; default payload contains weight only.

## MQTT contract

Default topic: `smartbin/{warehouseId}/{binId}/weight`

Default payload: `7.2` (UTF-8 numeric text, kilograms). Topic preserves identity even though payload contains only the load-cell value.

Optional JSON payload:

```json
{"binId":"bin-001","warehouseId":"warehouse-a","weightKg":7.2,"timestamp":"2026-11-19T06:00:00.000Z","simulated":true}
```

QoS 1 (at least once), retain false, clean MQTT 3.1.1 session. Duplicate readings are possible under QoS 1. The activity table records broker acknowledgements, not downstream processing. During broker outages the engine advances running scenarios but skips new publishes; it resumes with current values after reconnection. A batch already in flight may be retried by MQTT.js. There is no historical replay of skipped samples.

The actual ESP32 contract has not yet been supplied. This is a proposed contract to agree before connecting physical hardware; the prefix and numeric/JSON format are configurable. The bridge maps this development contract into Ditto. No physical radio, gateway firmware, sensor calibration, or physical fault behavior is validated by software simulation.

## State, ports, and tests

Fleet state is in memory and shared across tabs. Reloading the page keeps current server state; restarting the service resets it. **Export fleet** downloads a JSON snapshot (no credentials). Import is not part of this version. Credentials live only in server memory and the current browser form; they are not returned by the API or written to disk.

Use `PORT` and `MQTT_PORT` environment variables to change ports before launching. If either port is occupied, stop the other application or choose a free port.

```powershell
npm.cmd test
```

For a demo, begin with one bin: set 2 kg, publish, set 9 kg, publish, empty it, publish. Then use warehouse-wide percentage changes to demonstrate different capacities under one rule. Real and simulated producers should not publish the same bin identities at the same time.
