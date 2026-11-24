# SmartBin simulator
<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
SmartBin developers and experience-center demonstrators operating virtual bins.

## Product Purpose
Generate controllable load-cell readings and publish them over MQTT during software development and digital twin demonstrations before physical bins are available. Start with three bins in each of three warehouses and support 100 bins.

## Operating Context
The physical arrangement is ESP8266 bin nodes communicating over ESP-NOW to an ESP32 gateway, which publishes MQTT. This simulator replaces the gateway's telemetry output during software development.

## Capabilities and Constraints
User confirmed a local browser control panel and subsequently authorized native Ditto MQTT ingestion, a separate warehouse dashboard and scenario groundwork. Keep the original SmartBin application untouched. Preserve bin identity in topics. Demo defaults, not hardware facts: kilograms, nine bins with illustrative capacities, local broker at port 1884, one-second publishing interval, 85% weight alert configured per bin in the ontology. Actual gateway topic and payload format remain unconfirmed.

The simulator at port 4318 controls and publishes virtual readings. Its Send reading action applies the draft and publishes once; moving the slider only previews. Local state and broker acknowledgements are separate from Ditto receipt. The simulator links to the independent dashboard at port 4321 for the received weights, current model attributes, derived weight percentages and alerts. A broker acknowledgement is not proof of a Ditto update. A reading receipt timestamp is not a device-online guarantee.

The external Mosquitto broker feeds Ditto's native MQTT connection. Its in-Ditto mapper accepts numeric kg or matching JSON and updates only the matching bin's load feature. There is no separate Node MQTT-to-HTTP relay. The dashboard reads Ditto without MQTT subscription or telemetry forwarding; it derives percentage and alert state from raw readings and current model capacity/threshold on read. Model changes therefore appear without another reading. Additional simulator bins or changed topics require corresponding model import and native connection configuration.

Simulator auto-send modes operate on the local fleet and publish when started. Separately, the dashboard's Scenario lab saves validated local drafts and makes deterministic projections from a current Ditto snapshot. Those previews do not publish MQTT or write live twins; live scenario execution and scheduling are later work. Capacities, thresholds and forecast assumptions are illustrative rather than physical validation or OWL reasoning. Simulator fleet state remains in server memory and resets on restart.

## Stack
Implementation choice: Node.js local service and plain browser HTML/JavaScript, MQTT.js and locally compiled Tailwind/daisyUI. The live demo uses external Docker Mosquitto and Ditto; embedded Aedes is created only by isolated tests that explicitly request it. No cloud hosting is required. Ditto credentials stay on the local server and are not sent to the browser.
