// A bounded, seeded shared-resource model. No network clients or live twin writes.
export const policies = [
  { id: 'fixed', name: 'Fixed route' },
  { id: 'threshold', name: 'Threshold first' },
  { id: 'deadline', name: 'Least time remaining' }
];
const EPS = 1e-8, DT = 0.25;
function keys(value, allowed) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Provide a scenario object.');
  for (const key of Object.keys(value)) if (!allowed.includes(key)) throw new Error('Unknown scenario field: ' + key);
}
function bounded(value, name, min, max, fallback, quarter = false) {
  const n = value ?? fallback;
  if (!Number.isFinite(n) || n < min || n > max || (quarter && Math.abs(n * 4 - Math.round(n * 4)) > EPS)) {
    throw new Error(name + ' must be between ' + min + ' and ' + max + (quarter ? ', in 0.25 minute increments.' : '.'));
  }
  return n;
}
export function validateOperations(input) {
  keys(input, ['kind', 'name', 'warehouseId', 'horizonMinutes', 'travelMinutes', 'localTravelMinutes', 'delayMinutes', 'variabilityPercent', 'runs', 'seed', 'burst', 'bins']);
  if (input.kind !== 'operations') throw new Error('Choose an operations scenario.');
  if (typeof input.name !== 'string' || !input.name.trim() || input.name.trim().length > 80) throw new Error('Give the scenario a name of 1–80 characters.');
  const warehouseId = input.warehouseId || null;
  if (warehouseId !== null && (typeof warehouseId !== 'string' || !/^[A-Za-z0-9_.-]{1,100}$/.test(warehouseId))) throw new Error('Choose a valid warehouse.');
  const horizonMinutes = bounded(input.horizonMinutes, 'Duration', 5, 240, 60, true);
  const runs = bounded(input.runs, 'Trial count', 1, 50, 20), seed = bounded(input.seed, 'Seed', 1, 2147483647, 42);
  if (!Number.isInteger(runs) || !Number.isInteger(seed)) throw new Error('Trial count and seed must be whole numbers.');
  if (!Array.isArray(input.bins) || !input.bins.length || input.bins.length > 100) throw new Error('Configure between 1 and 100 bins.');
  if (input.bins.length * horizonMinutes * runs > 250000) throw new Error('Reduce the number of bins, duration or trials (250,000 bin-minutes per comparison).');
  const ids = new Set();
  const bins = input.bins.map(bin => {
    keys(bin, ['id', 'mode', 'rateKgPerMinute', 'alertPercent', 'serviceMinutes']);
    if (typeof bin.id !== 'string' || !/^[A-Za-z0-9_.-]{1,100}$/.test(bin.id) || ids.has(bin.id)) throw new Error('Each bin needs a unique valid ID.');
    ids.add(bin.id);
    if (!['collection', 'inventory'].includes(bin.mode)) throw new Error('Choose Collection or Inventory for ' + bin.id + '.');
    const alertPercent = bounded(bin.alertPercent, 'Alert percentage for ' + bin.id, 1, 99);
    // Service restores collection bins to 10%, inventory bins to 90%.
    if (bin.mode === 'collection' ? alertPercent <= 10 : alertPercent >= 90) throw new Error('Alert must be above 10% for collection or below 90% for inventory.');
    return { id: bin.id, mode: bin.mode, alertPercent,
      rateKgPerMinute: bounded(bin.rateKgPerMinute, 'Demand for ' + bin.id, 0, 10000),
      serviceMinutes: bounded(bin.serviceMinutes, 'Service time for ' + bin.id, 0.25, 60, 2, true) };
  });
  let burst = null;
  if (input.burst != null) {
    keys(input.burst, ['startMinute', 'durationMinutes', 'multiplier']);
    burst = { startMinute: bounded(input.burst.startMinute, 'Burst start', 0, horizonMinutes, 20, true),
      durationMinutes: bounded(input.burst.durationMinutes, 'Burst duration', 0.25, horizonMinutes, 10, true),
      multiplier: bounded(input.burst.multiplier, 'Burst multiplier', 1, 10, 2) };
    if (burst.startMinute + burst.durationMinutes > horizonMinutes) throw new Error('The demand burst must fit inside the scenario duration.');
  }
  return { kind: 'operations', name: input.name.trim(), warehouseId, horizonMinutes,
    travelMinutes: bounded(input.travelMinutes, 'Travel between warehouses', 0.25, 60, 3, true),
    localTravelMinutes: bounded(input.localTravelMinutes, 'Travel within a warehouse', 0.25, 60, 0.5, true),
    delayMinutes: bounded(input.delayMinutes, 'Delayed team start', 0, horizonMinutes, 10, true),
    variabilityPercent: bounded(input.variabilityPercent, 'Demand variation', 0, 100, 30), runs, seed, burst, bins };
}
function noise(seed, id, minute) {
  let h = (seed ^ Math.imul(minute + 1, 0x9e3779b9)) >>> 0;
  for (let i = 0; i < id.length; i++) h = Math.imul(h ^ id.charCodeAt(i), 16777619) >>> 0;
  h ^= h >>> 16; h = Math.imul(h, 0x7feb352d); h ^= h >>> 15; h = Math.imul(h, 0x846ca68b); h ^= h >>> 16;
  return (h >>> 0) / 4294967296;
}
function demand(bin, minute, scenario, seed, variation) {
  const burst = scenario.burst;
  const multiplier = burst && minute >= burst.startMinute && minute < burst.startMinute + burst.durationMinutes ? burst.multiplier : 1;
  return bin.rateKgPerMinute * multiplier * (1 + variation / 100 * (2 * noise(seed, bin.id, Math.floor(minute)) - 1));
}
function travel(from, bin, scenario) {
  return from === bin.warehouseId ? scenario.localTravelMinutes : scenario.travelMinutes;
}
function candidate(bin, minute, location, scenario, rate) {
  const collection = bin.mode === 'collection', percent = bin.weightKg / bin.capacityKg * 100;
  const room = collection ? bin.capacityKg - bin.weightKg : bin.weightKg;
  const deadlineIn = rate > EPS ? room / rate : null;
  const travelMinutes = travel(location, bin, scenario), completionIn = travelMinutes + bin.serviceMinutes;
  const thresholdKg = bin.capacityKg * bin.alertPercent / 100;
  const alertIn = rate > EPS ? Math.max(0, collection ? thresholdKg - bin.weightKg : bin.weightKg - thresholdKg) / rate : null;
  return { binId: bin.id, warehouseId: bin.warehouseId, mode: bin.mode, weightKg: bin.weightKg, percent,
    rateKgPerMinute: rate, deadlineIn, alertIn, travelMinutes, serviceMinutes: bin.serviceMinutes, completionIn,
    slackMinutes: deadlineIn === null ? null : deadlineIn - completionIn,
    needsAttention: collection ? percent >= bin.alertPercent - EPS : percent <= bin.alertPercent + EPS,
    useful: collection ? percent > 10 + EPS : percent < 90 - EPS,
    minute };
}
function runScenario(model, scenario, policy, { seed = scenario.seed, variation = 0, delay = 0, details = false } = {}) {
  const bins = model.map(bin => ({ ...bin, weightKg: Math.min(bin.capacityKg, bin.weightKg), overflowKg: 0, unmetKg: 0,
    lostMinutes: 0, firstLossAt: null, services: 0 }));
  const byId = new Map(bins.map(bin => [bin.id, bin]));
  let location = [...new Set(bins.map(bin => bin.warehouseId))].sort()[0], job = null, cursor = 0;
  let travelTotal = 0, serviceTotal = 0;
  const jobs = [], samples = [], initial = bins.map(bin => ({ id: bin.id, weightKg: bin.weightKg }));
  function sample(minute) {
    if (details) samples.push({ minute, overflowKg: bins.reduce((s, b) => s + b.overflowKg, 0), unmetKg: bins.reduce((s, b) => s + b.unmetKg, 0) });
  }
  sample(0);
  for (let tick = 0; tick < Math.round(scenario.horizonMinutes / DT); tick++) {
    const minute = tick * DT;
    if (!job && minute >= delay - EPS) {
      const options = bins.map(bin => candidate(bin, minute, location, scenario, demand(bin, minute, scenario, seed, variation))).filter(c => c.useful);
      let selected;
      if (policy === 'fixed') {
        for (let n = 0; n < bins.length; n++) {
          const index = (cursor + n) % bins.length;
          selected = options.find(c => c.binId === bins[index].id);
          if (selected) { cursor = (index + 1) % bins.length; break; }
        }
      } else if (policy === 'threshold') {
        selected = options.filter(c => c.needsAttention).sort((a, b) =>
          (a.mode === 'collection' ? 100 - a.percent : a.percent) - (b.mode === 'collection' ? 100 - b.percent : b.percent) || a.travelMinutes - b.travelMinutes || a.binId.localeCompare(b.binId))[0];
      } else {
        selected = options.filter(c => c.needsAttention || (c.alertIn !== null && c.alertIn <= c.completionIn + 5))
          .sort((a, b) => (a.slackMinutes ?? Infinity) - (b.slackMinutes ?? Infinity) || a.binId.localeCompare(b.binId))[0];
      }
      if (selected) {
        job = { ...selected, departAt: minute, arriveAt: minute + selected.travelMinutes,
          completeAt: minute + selected.completionIn, completed: false };
        if (details) jobs.push(job);
      }
    }
    // All bins change while the single team travels or services. There is no second worker.
    for (const bin of bins) {
      const rate = demand(bin, minute, scenario, seed, variation), amount = rate * DT;
      const room = bin.mode === 'collection' ? bin.capacityKg - bin.weightKg : bin.weightKg;
      const lost = Math.max(0, amount - room);
      bin.weightKg = bin.mode === 'collection' ? Math.min(bin.capacityKg, bin.weightKg + amount) : Math.max(0, bin.weightKg - amount);
      if (lost > EPS) {
        if (bin.firstLossAt === null) bin.firstLossAt = minute + room / rate;
        bin.lostMinutes += lost / rate;
        if (bin.mode === 'collection') bin.overflowKg += lost; else bin.unmetKg += lost;
      }
    }
    const end = (tick + 1) * DT;
    if (job) {
      travelTotal += Math.max(0, Math.min(end, job.arriveAt) - Math.max(minute, job.departAt));
      serviceTotal += Math.max(0, Math.min(end, job.completeAt) - Math.max(minute, job.arriveAt));
      if (end >= job.completeAt - EPS) {
        const bin = byId.get(job.binId);
        job.weightBeforeServiceKg = bin.weightKg;
        bin.weightKg = bin.capacityKg * (bin.mode === 'collection' ? 0.1 : 0.9);
        job.weightAfterServiceKg = bin.weightKg; job.completed = true; bin.services++;
        location = bin.warehouseId; job = null;
      }
    }
    if (Number.isInteger(end) || end === scenario.horizonMinutes) sample(end);
  }
  const overflowKg = bins.reduce((s, b) => s + b.overflowKg, 0), unmetKg = bins.reduce((s, b) => s + b.unmetKg, 0);
  return { policy, overflowKg, unmetKg, lossKg: overflowKg + unmetKg,
    binsWithLoss: bins.filter(b => b.firstLossAt !== null).length, lossMinutes: bins.reduce((s, b) => s + b.lostMinutes, 0),
    completedServices: bins.reduce((s, b) => s + b.services, 0), travelMinutes: travelTotal, serviceMinutes: serviceTotal,
    busyPercent: (travelTotal + serviceTotal) / scenario.horizonMinutes * 100,
    ...(details ? { initial, jobs, samples, bins: bins.map(({ id, warehouseId, mode, capacityKg, weightKg, overflowKg, unmetKg, firstLossAt, lostMinutes, services }) =>
      ({ id, warehouseId, mode, capacityKg, weightKg, overflowKg, unmetKg, firstLossAt, lostMinutes, services })) } : {}) };
}
export function compareOperations(fleet, input) {
  const scenario = validateOperations(input);
  const selected = fleet.bins.filter(bin => !scenario.warehouseId || bin.warehouseId === scenario.warehouseId).sort((a, b) => a.id.localeCompare(b.id));
  if (!selected.length) throw new Error('No imported bins match this scenario.');
  if (selected.length !== scenario.bins.length || selected.some(bin => !scenario.bins.some(b => b.id === bin.id))) throw new Error('Configure every bin in the selected warehouse scope, then run again.');
  if (selected.some(bin => !bin.hasReading || !Number.isFinite(bin.weightKg) || bin.weightKg < 0 || !Number.isFinite(bin.capacityKg) || bin.capacityKg <= 0)) throw new Error('Send a valid initial reading and capacity for every selected bin before comparing.');
  const model = selected.map(bin => ({ ...bin, ...scenario.bins.find(b => b.id === bin.id) }));
  const comparisons = policies.map(policy => {
    const baseline = runScenario(model, scenario, policy.id, { details: true });
    const trials = Array.from({ length: scenario.runs }, (_, i) => runScenario(model, scenario, policy.id, { seed: scenario.seed + i, variation: scenario.variabilityPercent }));
    const mean = key => trials.reduce((sum, run) => sum + run[key], 0) / trials.length;
    const sorted = trials.map(run => run.lossKg).sort((a, b) => a - b);
    return { ...policy, baseline, trials: { count: trials.length, withLoss: trials.filter(run => run.lossKg > EPS).length,
      meanLossKg: mean('lossKg'), meanOverflowKg: mean('overflowKg'), meanUnmetKg: mean('unmetKg'), p90LossKg: sorted[Math.ceil(sorted.length * 0.9) - 1] } };
  });
  const preferred = comparisons.find(item => item.id === 'deadline');
  const delayed = runScenario(model, scenario, 'deadline', { delay: scenario.delayMinutes, details: true });
  const first = preferred.baseline.jobs[0] || null;
  const ranking = model.map(bin => candidate({ ...bin, weightKg: Math.min(bin.weightKg, bin.capacityKg) }, 0,
    [...new Set(model.map(b => b.warehouseId))].sort()[0], scenario, demand(bin, 0, scenario, scenario.seed, 0)))
    .sort((a, b) => (a.slackMinutes ?? Infinity) - (b.slackMinutes ?? Infinity) || a.binId.localeCompare(b.binId));
  return { kind: 'operations', previewOnly: true, generatedAt: new Date().toISOString(), startingReadAt: fleet.readAt, scenario,
    model: model.map(bin => ({ id: bin.id, warehouseId: bin.warehouseId, capacityKg: bin.capacityKg, initialWeightKg: bin.weightKg,
      mode: bin.mode, rateKgPerMinute: bin.rateKgPerMinute, alertPercent: bin.alertPercent, serviceMinutes: bin.serviceMinutes })),
    initialExcessKg: model.reduce((sum, bin) => sum + Math.max(0, bin.weightKg - bin.capacityKg), 0),
    recommendation: first, ranking, comparisons, delayed,
    delayImpact: { lossKg: delayed.lossKg - preferred.baseline.lossKg, binsWithLoss: delayed.binsWithLoss - preferred.baseline.binsWithLoss },
    assumptions: [
      'One team starts in ' + [...new Set(model.map(b => b.warehouseId))].sort()[0] + '; travel and service occupy it exclusively. Service takes effect at completion.',
      'Collection empties to 10%; inventory replenishes to 90%. Supply and cart carrying capacity are unlimited; bins keep changing during service.',
      'Collection is capped at rated kg: excess becomes overflow. Inventory stops at zero: further demand becomes unmet kg. Pre-existing excess is reported separately and removed at the snapshot boundary.',
      'Fixed route cycles through bin IDs. Threshold first waits for the configured alert and ranks by distance to full/empty. Least time remaining ranks current-rate safety margin after travel and service; it dispatches at an alert or within five minutes of predicted alert at completion.',
      'Decisions occur every 0.25 minute; rates vary each minute by a seeded uniform factor. The optional burst multiplies every bin’s demand. All strategies use identical workloads per trial.',
      'Main results and delay comparison use nominal demand including the burst. Trial counts use synthetic variation, not measured failure probabilities. Least time remaining is a heuristic, not a proven optimum.',
      'Capacities come from the current Ditto model imported from OWL. Purpose, demand, alert overrides, travel and service are explicit scenario assumptions. No OWL reasoning or learned prediction is performed.',
      'This comparison reads a snapshot only. It never publishes MQTT or changes a live Ditto Thing.'
    ] };
}
