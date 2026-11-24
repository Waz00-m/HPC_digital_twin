import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { createDashboard } from './server.mjs';
test('dashboard reads twins without writing and previews never issue Ditto or MQTT commands', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'smartbin-dashboard-'));
  const calls = [], thing = { thingId: 'smartbin:bin-002', attributes: { type: 'SmartBin', binId: 'bin-002', warehouseId: 'warehouse-b', capacityKg: 50, alertThresholdPercent: 85 },
    features: { load: { properties: { weightKg: 20, warehouseId: 'warehouse-b', source: 'mqtt-native' } } } };
  const client = { readThings: async () => [thing], request: async (path, options) => { calls.push({ path, options }); return { liveStatus: 'open' }; } };
  const app = await createDashboard({ port: 0, client, storePath: join(dir, 'scenarios.json') });
  const scenario = { name: 'Preview', rateKgPerMinute: 2, horizonMinutes: 30, stepMinutes: 1 };
  try {
    const fleet = await (await fetch(app.url + '/api/fleet')).json();
    assert.equal(fleet.bins[0].weightPercent, 40);
    const before = structuredClone(thing);
    const response = await fetch(app.url + '/api/simulation/preview', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(scenario) });
    assert.equal(response.status, 200); assert.equal((await response.json()).bins[0].thresholdAtMinute, 11.25);
    assert.deepEqual(thing, before); assert.ok(calls.every(call => !call.options.method || call.options.method === 'GET'));
    const operation = { kind: 'operations', name: 'One team', horizonMinutes: 30, runs: 3,
      bins: [{ id: 'bin-002', mode: 'inventory', rateKgPerMinute: 2, alertPercent: 20, serviceMinutes: 2 }] };
    const compared = await fetch(app.url + '/api/simulation/preview', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(operation) });
    assert.equal(compared.status, 200); assert.equal((await compared.json()).comparisons.length, 3);
    assert.deepEqual(thing, before); assert.ok(calls.every(call => !call.options.method || call.options.method === 'GET'));
    const forbidden = await fetch(app.url + '/api/scenarios', { method: 'POST', headers: { origin: 'https://example.com', 'content-type': 'application/json' }, body: JSON.stringify(scenario) });
    assert.equal(forbidden.status, 403);
    const saved = await fetch(app.url + '/api/scenarios', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(scenario) });
    assert.equal(saved.status, 201); assert.equal((await (await fetch(app.url + '/api/scenarios')).json()).scenarios.length, 1);
  } finally { await app.close(); assert.ok(resolve(dir).startsWith(resolve(tmpdir()) + sep + 'smartbin-dashboard-')); await rm(dir, { recursive: true, force: true }); }
});
