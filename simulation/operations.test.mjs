import test from 'node:test';
import assert from 'node:assert/strict';
import { compareOperations, validateOperations } from './operations.mjs';
const fleet = { readAt: 'snapshot', bins: [
  { id: 'a', warehouseId: 'warehouse-a', weightKg: 9, capacityKg: 10, hasReading: true },
  { id: 'b', warehouseId: 'warehouse-b', weightKg: 1, capacityKg: 10, hasReading: true }
] };
const scenario = { kind: 'operations', name: 'Shared team', horizonMinutes: 20, travelMinutes: 3, localTravelMinutes: 0.5,
  delayMinutes: 5, variabilityPercent: 30, runs: 5, seed: 42,
  bins: [{ id: 'a', mode: 'collection', alertPercent: 85, rateKgPerMinute: 1, serviceMinutes: 2 },
    { id: 'b', mode: 'inventory', alertPercent: 20, rateKgPerMinute: 1, serviceMinutes: 2 }] };
test('one team cannot overlap jobs, flows continue in transit and service restores both bin purposes', () => {
  const before = structuredClone(fleet), result = compareOperations(fleet, scenario);
  assert.deepEqual(fleet, before); assert.equal(result.previewOnly, true);
  assert.equal(result.recommendation.binId, 'b'); // Same deadline, longer travel leaves less safety margin.
  for (const comparison of result.comparisons) {
    const run = comparison.baseline;
    for (let i = 1; i < run.jobs.length; i++) assert.ok(run.jobs[i].departAt >= run.jobs[i - 1].completeAt);
    assert.ok(run.busyPercent <= 100); assert.ok(run.overflowKg > 0); assert.ok(run.unmetKg > 0);
    for (const job of run.jobs.filter(j => j.completed)) {
      assert.equal(job.weightAfterServiceKg, job.mode === 'collection' ? 1 : 9);
    }
    assert.ok(run.bins.every(b => b.weightKg >= 0 && b.weightKg <= b.capacityKg));
  }
  assert.equal(result.comparisons[2].baseline.bins.find(b => b.id === 'b').firstLossAt, 1);
});
test('loss conservation, completion boundary, capped initial excess and zero-demand handling', () => {
  const one = { readAt: 'now', bins: [fleet.bins[0]] };
  const config = { ...scenario, horizonMinutes: 5, delayMinutes: 5, bins: [scenario.bins[0]] };
  const result = compareOperations(one, config);
  // No service in the delayed run: initial 9 + input 5 = held 10 + overflow 4.
  assert.equal(result.delayed.overflowKg, 4); assert.equal(result.delayed.bins[0].weightKg, 10);
  const job = result.comparisons[2].baseline.jobs[0];
  assert.equal(job.completeAt, 2.5); assert.equal(job.weightBeforeServiceKg, 10);
  assert.equal(result.comparisons[2].baseline.samples.find(p => p.minute === 2).overflowKg, 1);
  const excess = compareOperations({ ...one, bins: [{ ...one.bins[0], weightKg: 12 }] }, config);
  assert.equal(excess.initialExcessKg, 2); assert.equal(excess.delayed.overflowKg, 5);
  const idle = compareOperations({ ...one, bins: [{ ...one.bins[0], weightKg: 0 }] }, { ...config, bins: [{ ...config.bins[0], rateKgPerMinute: 0 }] });
  assert.equal(idle.recommendation, null); assert.equal(idle.comparisons[0].baseline.lossKg, 0);
});
test('repeatable trials share the same workload across policies and delay zero reproduces baseline', () => {
  const a = compareOperations(fleet, { ...scenario, delayMinutes: 0 });
  const b = compareOperations(fleet, { ...scenario, delayMinutes: 0 });
  assert.deepEqual(a.comparisons, b.comparisons);
  assert.deepEqual(a.delayed, a.comparisons[2].baseline);
  const noService = { ...scenario, horizonMinutes: 5, bins: scenario.bins.map(bin => ({ ...bin, serviceMinutes: 60 })) };
  const identical = compareOperations(fleet, noService);
  assert.ok(identical.comparisons.every(p => p.trials.meanLossKg === identical.comparisons[0].trials.meanLossKg));
  const flat = compareOperations(fleet, { ...scenario, variabilityPercent: 0 });
  for (const p of flat.comparisons) assert.ok(Math.abs(p.trials.meanLossKg - p.baseline.lossKg) < 1e-8);
  const otherSeed = compareOperations(fleet, { ...scenario, seed: 99 });
  assert.notEqual(otherSeed.comparisons[0].trials.meanLossKg, a.comparisons[0].trials.meanLossKg);
});
test('burst adds physical demand, delay affects the same nominal workload and validation is bounded', () => {
  const base = compareOperations(fleet, scenario);
  const burst = compareOperations(fleet, { ...scenario, burst: { startMinute: 5, durationMinutes: 5, multiplier: 3 } });
  assert.ok(burst.comparisons[0].baseline.lossKg > base.comparisons[0].baseline.lossKg);
  assert.equal(base.delayImpact.lossKg, base.delayed.lossKg - base.comparisons[2].baseline.lossKg);
  assert.throws(() => validateOperations({ ...scenario, runs: 1.5 }), /whole/);
  assert.throws(() => validateOperations({ ...scenario, travelMinutes: 0.3 }), /increments/);
  assert.throws(() => validateOperations({ ...scenario, publish: true }), /Unknown/);
  assert.throws(() => compareOperations(fleet, { ...scenario, bins: [scenario.bins[0]] }), /every bin/);
  assert.throws(() => compareOperations({ ...fleet, bins: [{ ...fleet.bins[0], hasReading: false }, fleet.bins[1]] }, scenario), /valid initial/);
  assert.throws(() => validateOperations({ ...scenario, burst: { startMinute: 19, durationMinutes: 5, multiplier: 2 } }), /fit inside/);
});
