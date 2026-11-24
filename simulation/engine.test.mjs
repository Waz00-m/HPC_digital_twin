import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { previewScenario, validateScenario } from './engine.mjs';
import { createScenarioStore } from './store.mjs';
const fleet = { readAt: 'snapshot-time', bins: [{ id: 'bin-002', warehouseId: 'warehouse-b', hasReading: true, weightKg: 20, capacityKg: 50, alertThresholdPercent: 85 }] };
const config = { name: 'Test forecast', rateKgPerMinute: 2, horizonMinutes: 30, stepMinutes: 1 };
test('forecast starts from a snapshot, uses model capacity, predicts crossing and never changes its input', () => {
  const before = structuredClone(fleet), result = previewScenario(fleet, config);
  assert.deepEqual(fleet, before); assert.equal(result.previewOnly, true); assert.equal(result.startingReadAt, 'snapshot-time');
  assert.equal(result.bins[0].thresholdAtMinute, 11.25);
  assert.equal(result.bins[0].final.weightKg, 80); assert.equal(result.bins[0].final.status, 'over-capacity');
  const drained = previewScenario(fleet, { ...config, rateKgPerMinute: -2 });
  assert.equal(drained.bins[0].final.weightKg, 0); assert.equal(drained.bins[0].thresholdAtMinute, null);
});
test('emptying events precede coincident crossings and absent data/configuration is explicit', () => {
  const result = previewScenario(fleet, { ...config, emptyAtMinute: 10 });
  assert.equal(result.bins[0].final.weightKg, 40); assert.equal(result.bins[0].thresholdAtMinute, null);
  const missing = structuredClone(fleet); missing.bins[0].hasReading = false;
  assert.throws(() => previewScenario(missing, config), /initial reading/);
  const other = structuredClone(fleet); other.bins[0].alertThresholdPercent = null;
  assert.equal(previewScenario(other, config).bins[0].thresholdAtMinute, null);
  assert.throws(() => validateScenario({ ...config, stepMinutes: 0 }), /stepMinutes/);
  assert.throws(() => validateScenario({ ...config, horizonMinutes: 1440, stepMinutes: 0.1 }), /intervals/);
  assert.throws(() => validateScenario({ ...config, publish: true }), /Unknown/);
});
test('scenario drafts persist without lost concurrent writes', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'smartbin-scenarios-'));
  try {
    const path = join(directory, 'drafts.json'), store = createScenarioStore(path);
    await Promise.all([store.save({ ...config, name: 'One' }), store.save({ ...config, name: 'Two' })]);
    const saved = await createScenarioStore(path).list();
    assert.equal(saved.length, 2); assert.notEqual(saved[0].id, saved[1].id);
    assert.ok(saved.every(draft => !('weightKg' in draft.config)));
  } finally { assert.ok(resolve(directory).startsWith(resolve(tmpdir()) + sep + 'smartbin-scenarios-')); await rm(directory, { recursive: true, force: true }); }
});
