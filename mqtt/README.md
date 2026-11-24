# Ditto native MQTT

Start broker: docker compose up -d in this directory.

Configure Ditto: node configure-ditto.mjs from this directory, after importing the ontology.

Verify direct ingestion: node verify-native.mjs. This changes all nine virtual demo weights and leaves a mixed status example. Read native-demo-results.json for the actual readbacks.

The native connection consumes explicitly imported topics. Its incoming JavaScript mapper runs inside Ditto's connectivity service; no Node MQTT-to-HTTP relay is running. The separate dashboard only reads twin data.

Host port 1884 is loopback-only. The internal Docker alias smartbin-mqtt:1883 is available to the existing Ditto network docker_default. This standalone broker's named volume preserves its MQTT session data; do not delete volumes to restart the demo.

The setup groups addresses into three warehouse sources because the installed Ditto default permits four sources per connection. Each source's topic-to-Thing source-address enforcement and load-only policy grants constrain its writes. Re-run configuration after warehouse/topic membership changes.
