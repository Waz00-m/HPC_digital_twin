import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createDittoClient } from '../shared/ditto-client.mjs';
const dashboard = process.env.DASHBOARD_URL || 'http://127.0.0.1:4321';
const client = createDittoClient();
const before = await client.readThings({ refresh: true });
const response = await fetch(dashboard + '/api/fleet');
assert.equal(response.status, 200);
const fleet = await response.json();
assert.equal(fleet.bins.length, 9, 'This verification targets the nine-bin demo.');
const config = { kind: 'operations', name: 'Nine bins · one handling team', horizonMinutes: 60, delayMinutes: 10,
  travelMinutes: 3, localTravelMinutes: 0.5, variabilityPercent: 30, runs: 20, seed: 42,
  burst: { startMinute: 20, durationMinutes: 10, multiplier: 2 },
  bins: fleet.bins.map((bin, index) => ({ id: bin.id, mode: index % 2 ? 'inventory' : 'collection',
    rateKgPerMinute: Number((bin.capacityKg * [0.015, 0.012, 0.018, 0.02, 0.01][index % 5]).toFixed(3)),
    alertPercent: index % 2 ? 20 : (bin.alertThresholdPercent || 85), serviceMinutes: 2 })) };
const simulation = await fetch(dashboard + '/api/simulation/preview', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(config) });
const result = await simulation.json();
assert.equal(simulation.status, 200, JSON.stringify(result));
assert.equal(result.comparisons.length, 3);
const after = await client.readThings({ refresh: true });
assert.deepEqual(after, before, 'Live Ditto model, telemetry and revisions must remain unchanged. Pause auto-publishing before this verification.');
for (const policy of result.comparisons) {
  const jobs = policy.baseline.jobs;
  for (let i = 1; i < jobs.length; i++) assert.ok(jobs[i].departAt >= jobs[i - 1].completeAt);
}
const summary = { snapshot: result.startingReadAt, unchangedThings: before.length, nextJob: result.recommendation,
  comparisons: result.comparisons.map(p => ({ strategy: p.name, overflowKg: p.baseline.overflowKg, unmetKg: p.baseline.unmetKg,
    completedServices: p.baseline.completedServices, trials: p.trials })), delayImpact: result.delayImpact };
const directory = fileURLToPath(new URL('./.results/', import.meta.url));
await mkdir(directory, { recursive: true });
await writeFile(new URL('./.results/operations-demo.json', import.meta.url), JSON.stringify({ summary, result }, null, 2) + '\n');
console.log(JSON.stringify(summary, null, 2));
