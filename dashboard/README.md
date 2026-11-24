# Warehouse dashboard

Run node server.mjs here, then open http://127.0.0.1:4321/. The dashboard does not require the simulator to be running.

The warehouse view reads the latest raw weights and model attributes from Ditto every three seconds. Percentage and alert status are calculated on read. Choose a warehouse/status filter or select a bin for details. Missing readings and invalid models are shown explicitly; connection failures retain values labelled last known.

Open Scenario lab to compare how one handling team serves the selected bins. Start with the saved “Nine bins · one handling team” draft or the defaults, then press Compare strategies. The result identifies the first job, explains its safety margin, re-runs the queue with a delayed start, and compares three rules under identical demand. Inspect strategy changes the schedule and per-bin outcomes. On small screens a completed comparison moves focus to the result; View results returns there from the form.

Open Bin purposes & demand to configure each bin as Collection (incoming material, empty to 10%) or Inventory (outgoing material, replenish to 90%). Demand is a nonnegative kg/minute magnitude; the purpose controls its direction. Alert percentage is high for Collection, low for Inventory. Capacity and starting weight come from Ditto. Purpose, rates, alert overrides and service times are local scenario assumptions, not changes to the ontology or live bins. The warehouse overview continues to use the imported live high-weight alert model.

Duration, delayed team start and travel times are above the expandable settings. Demand burst & uncertainty controls an optional twofold demand burst, minute-to-minute variation, trial count and seed. A seed makes synthetic trials repeatable. The nominal result includes the burst but no random variation; the trial table adds variation. Trial counts are illustrative outcomes, not calibrated real-world probabilities.

Drafts persist in .data/scenarios.json. Loading an old linear draft explicitly converts its signed rate to Collection/Inventory demand; the old single-emptying event is replaced by team service. Settings changes mark previous results as stale. Every comparison starts from a current Ditto snapshot, independent of continuing live readback. Saved drafts contain configuration, not frozen telemetry or simulation results. Physical execution is not connected; neither comparisons nor saves publish MQTT or write Ditto.

Build CSS after HTML/CSS/class changes with npm.cmd run build:css. It uses the installed Tailwind/daisyUI tools from ../simulator/node_modules; no second dependency tree is needed.

Run the root digital-twin tests with npm.cmd test from the parent folder. See the parent README for startup, credentials and native MQTT configuration.
