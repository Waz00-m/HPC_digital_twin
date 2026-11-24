# Bin handling simulation

The Scenario lab now uses operations.mjs: a bounded shared-resource simulation from an immutable normalized Ditto snapshot. engine.mjs dispatches kind: operations requests to it and retains the original linear API for compatibility. store.mjs saves validated drafts atomically with serialized writes.

## Operations model

One team starts in the alphabetically first selected warehouse. Every travel and service interval occupies that team exclusively. All bins continue changing during travel/service. At service completion Collection is emptied to 10% of capacity, Inventory replenished to 90%. Supply and carrying capacity are unlimited. Travel is a uniform scenario value between warehouses and a second value within one warehouse, not a measured floor plan.

Collection weight stops at rated capacity; further arrivals become overflow kg. Inventory stops at zero; further requests become unmet demand kg. Output separates these metrics; combined lost kg is only a convenient demo comparison objective. Existing overcapacity is removed at the snapshot boundary and separately disclosed, not counted as newly simulated overflow. No observed sensor reading is changed.

Decision/flow intervals are 0.25 minute. Quarter-minute travel, service and burst boundaries align exactly. The team acts at interval boundaries; completion is applied after demand for that interval. Within each constant-rate interval the first loss time and duration are calculated analytically. The queue is simulated, rather than resetting every bin simultaneously.

Three rules use the same initial snapshot and workload:

- Fixed route: cycle through sorted bin IDs, skipping bins already at/beyond their service target.
- Threshold first: dispatch only for an alert, rank by percentage distance to full/empty, then travel time and ID.
- Least time remaining: rank eligible bins by (kg remaining to full/empty ÷ current demand rate) minus travel and service time. Dispatch at an alert or when alert is predicted within five minutes after service completion. This is a heuristic, not an optimizer with a performance guarantee; it uses current demand, not advance knowledge of future bursts.

The nominal comparison and delayed-start counterfactual include the configured burst with no random variation. Synthetic trials multiply each bin/minute rate by a seeded uniform factor in [1 − variation/100, 1 + variation/100]. A hash of seed, bin ID and minute makes each trial workload identical across rules regardless of their actions. Report empirical counts with any loss, mean combined loss and the nearest-rank 90th percentile; these are not calibrated probabilities.

Inputs: kind: operations, name, optional warehouseId, horizonMinutes (5–240), travelMinutes, localTravelMinutes, delayMinutes, variabilityPercent (0–100), runs (1–50), integer seed, optional burst {startMinute, durationMinutes, multiplier}, bins [{id, mode, rateKgPerMinute, alertPercent, serviceMinutes}]. Every selected bin needs a valid reading/capacity and exactly one configuration. Modes are collection/inventory. Demand is nonnegative; alert must be >10% for Collection or <90% for Inventory. Limit: 100 bins and 250,000 bin-minutes across trials. Results include jobs, outcomes, cumulative loss series, three policy summaries/trial aggregates, initial ranking and the delayed run.

Capacities and warehouse membership are read from OWL-imported Ditto attributes. Purposes, demand, alert overrides, service and travel times are scenario assumptions. The default mix and rates are illustrative. No general OWL reasoner, learned demand estimator, material compatibility, cart capacity or physical calibration is present.

## API and verification

Dashboard API:

- GET /api/scenarios: saved drafts.
- POST /api/scenarios: validate and save a draft.
- POST /api/simulation/preview: simulate a configuration from a current Ditto snapshot.

No simulation path contains MQTT publishing or Ditto writes. There is no live-run or physical scheduling endpoint. Drafts are configuration only; legacy linear drafts remain stored and can be explicitly converted in the frontend. The old API accepts signed constant kg/minute, duration, time step and a single emptying event; it retains its old unrestricted overcapacity projection semantics.

From digital-twin run npm.cmd test for isolated resource, conservation, reproducibility, validation, persistence, MQTT and HTTP tests. Run npm.cmd run verify:operations with Ditto/dashboard running and spoofer auto-publishing paused to compare all nine current bins and assert all 12 Ditto Things, including revisions, are unchanged. It publishes nothing and saves simulation/.results/operations-demo.json. By contrast verify:native deliberately publishes new readings; it serves a different ingestion check.
