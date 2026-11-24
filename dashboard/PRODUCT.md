# SmartBin digital twin dashboard

## Platform
web, local development on Windows

## Users and purpose
Warehouse operators and experience-center demonstrators inspecting the nine-bin, three-warehouse digital twin and comparing Collection and Inventory handling decisions in a general demo.

## Confirmed scope
User chose a warehouse overview with bins grouped by warehouse and a detail panel. Native MQTT ingestion is handled by Ditto. The dashboard reads Ditto independently of the simulator; it never subscribes to MQTT or forwards telemetry. Weight percentages and alerts are calculated from the latest raw reading and current imported ontology attributes.

## Handling simulation
The Scenario lab answers which bin one handling team should serve next, why, and what changes if the team starts late. Compare fixed route, threshold first and least time remaining from the same Ditto snapshot. Travel and service occupy the shared team while all selected bins continue changing. Collection receives material and is emptied to 10%; Inventory is consumed and replenished to 90%.

Show the next job and its safety margin, delayed-start consequences, separate collection overflow and unmet inventory demand, strategy comparisons, seeded trials with equal workloads, the team schedule and per-bin outcomes. Save and load local scenario drafts; changes to assumptions mark existing results as stale. Legacy linear drafts remain available through explicit conversion, and the original linear API is retained.

Starting raw readings, capacities and warehouse membership come from Ditto. Purpose, demand, alert overrides, travel and service times are editable scenario assumptions. Trial counts are synthetic demo outcomes, not calibrated failure probabilities; least time remaining is a heuristic, not a guaranteed optimum. No learned prediction or OWL reasoning is performed. Simulation and draft saves publish no MQTT and change no live Ditto Things. Physical execution and live scheduling remain unconnected.

## Facts and constraints
Nine demo bins across three warehouses. Capacities and live thresholds are illustrative imported model values. Existing snapshot overcapacity is disclosed and clamped before simulation, separately from newly simulated overflow; the observed reading stays unchanged. Travel is an assumed uniform duration within/between warehouses; supply and team carrying capacity are unlimited. A sensor receipt timestamp is not an online/offline guarantee. Keep credentials on the local server. The dashboard at port 4321 and telemetry simulator at port 4318 remain separate. The original V1 application is untouched.
