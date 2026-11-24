import test from 'node:test';
import assert from 'node:assert/strict';
import { loadProperties } from './load-model.mjs';

test('the nine-bin demo applies a model threshold at the boundary and clears it below the boundary', () => {
  for (const capacityKg of [10, 50, 100]) {
    const model = { capacityKg, alertThresholdPercent: 85 };
    const boundary = capacityKg * 0.85;
    assert.equal(loadProperties(boundary - 0.001, model, '').status, 'normal');
    const at = loadProperties(boundary, model, 'receipt-time');
    assert.equal(at.status, 'attention');
    assert.equal(at.alertActive, true);
    assert.equal(at.alertThresholdKg, boundary);
    assert.equal(at.weightPercent, 85);
    assert.equal(loadProperties(capacityKg, model, '').status, 'attention');
    assert.equal(loadProperties(capacityKg + 0.001, model, '').status, 'over-capacity');
    assert.equal(loadProperties(0, model, '').alertActive, false);
  }
  assert.deepEqual([10, 50, 100].map(capacityKg => loadProperties(8.5, { capacityKg, alertThresholdPercent: 85 }, '').weightPercent), [85, 17, 8.5]);
});

test('thresholds are per-bin model values; absent configuration never claims a normal alert state', () => {
  assert.equal(loadProperties(35, { capacityKg: 50, alertThresholdPercent: 70 }, '').status, 'attention');
  assert.equal(loadProperties(35, { capacityKg: 50, alertThresholdPercent: 85 }, '').status, 'normal');
  const absent = loadProperties(35, { capacityKg: 50 }, '');
  assert.equal(absent.status, 'unconfigured'); assert.equal(absent.alertActive, null);
  for (const threshold of [0, -1, 101, '85', NaN]) assert.throws(() => loadProperties(20, { capacityKg: 50, alertThresholdPercent: threshold }, ''));
  assert.throws(() => loadProperties(20, { capacityKg: 0 }, ''));
});
