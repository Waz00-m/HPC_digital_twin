import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeFleet } from './fleet.mjs';
const thing = { thingId: 'smartbin:bin-002', attributes: { type: 'SmartBin', binId: 'bin-002', warehouseId: 'warehouse-b', capacityKg: 50, alertThresholdPercent: 85 },
  features: { load: { properties: { weightKg: 42.5, warehouseId: 'warehouse-b', source: 'mqtt-native', weightPercent: 1, status: 'normal' } } } };
test('read-side calculation uses current model and raw telemetry, never obsolete stored calculations', () => {
  const input = structuredClone(thing), bin = normalizeFleet([input]).bins[0];
  assert.equal(bin.weightPercent, 85); assert.equal(bin.status, 'attention'); assert.equal(bin.source, 'mqtt-native');
  input.attributes.capacityKg = 100;
  assert.equal(normalizeFleet([input]).bins[0].weightPercent, 42.5);
  assert.equal(input.features.load.properties.weightPercent, 1, 'normalization does not write a twin');
});
test('missing readings and invalid identity/models do not become normal zero readings', () => {
  const input = structuredClone(thing); input.features = {};
  assert.equal(normalizeFleet([input]).bins[0].status, 'awaiting-reading');
  input.features = thing.features; input.attributes.capacityKg = 0;
  assert.equal(normalizeFleet([input]).bins[0].status, 'invalid-model');
  input.attributes.capacityKg = 50; input.attributes.warehouseId = 'warehouse-a';
  assert.equal(normalizeFleet([input]).bins[0].status, 'identity-mismatch');
});
