import { loadProperties } from '../shared/load-model.mjs';
import { validateOperations, compareOperations } from './operations.mjs';
export function validateScenario(input) {
  if (input?.kind === 'operations') return validateOperations(input);
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Provide a scenario object.');
  const allowed = ['name', 'warehouseId', 'rateKgPerMinute', 'horizonMinutes', 'stepMinutes', 'emptyAtMinute'];
  for (const key of Object.keys(input)) if (!allowed.includes(key)) throw new Error('Unknown scenario field: ' + key);
  if (typeof input.name !== 'string' || !input.name.trim() || input.name.trim().length > 80) throw new Error('Give the scenario a name of 1–80 characters.');
  const warehouseId = input.warehouseId || null;
  if (warehouseId !== null && (typeof warehouseId !== 'string' || !/^[A-Za-z0-9_.-]{1,100}$/.test(warehouseId))) throw new Error('Choose a valid warehouse.');
  function bounded(key, minimum, maximum, fallback) {
    const value = input[key] ?? fallback;
    if (!Number.isFinite(value) || value < minimum || value > maximum) throw new Error(key + ' must be between ' + minimum + ' and ' + maximum + '.');
    return value;
  }
  const horizonMinutes = bounded('horizonMinutes', 1, 1440, 60), stepMinutes = bounded('stepMinutes', 0.1, 60, 1);
  if (horizonMinutes / stepMinutes > 2000) throw new Error('Choose a larger time step; previews are limited to 2,000 intervals.');
  const emptyAtMinute = input.emptyAtMinute == null ? null : bounded('emptyAtMinute', 0.1, horizonMinutes);
  return { name: input.name.trim(), warehouseId, rateKgPerMinute: bounded('rateKgPerMinute', -1000000, 1000000, 1), horizonMinutes, stepMinutes, emptyAtMinute };
}
export function previewScenario(fleet, input) {
  if (input?.kind === 'operations') return compareOperations(fleet, input);
  const scenario = validateScenario(input), selected = fleet.bins.filter(bin => !scenario.warehouseId || bin.warehouseId === scenario.warehouseId);
  if (!selected.length) throw new Error('No imported bins match this scenario.');
  if (selected.some(bin => !bin.hasReading)) throw new Error('Send a valid initial reading for every selected bin before previewing.');
  if (selected.length * (Math.ceil(scenario.horizonMinutes / scenario.stepMinutes) + 1) > 20000) throw new Error('Choose a larger time step; previews are limited to 20,000 bin samples.');
  const elapsed = [];
  for (let n = 0; n * scenario.stepMinutes < scenario.horizonMinutes; n++) elapsed.push(n * scenario.stepMinutes);
  elapsed.push(scenario.horizonMinutes);
  const bins = selected.map(bin => {
    const points = elapsed.map(minute => {
      const emptied = scenario.emptyAtMinute !== null && minute >= scenario.emptyAtMinute;
      const weight = Math.max(0, (emptied ? 0 : bin.weightKg) + scenario.rateKgPerMinute * (emptied ? minute - scenario.emptyAtMinute : minute));
      return { minute, ...loadProperties(weight, bin, null) };
    });
    let thresholdAtMinute = null;
    const threshold = bin.alertThresholdPercent === null ? null : bin.capacityKg * bin.alertThresholdPercent / 100;
    if (threshold !== null) {
      if (bin.weightKg >= threshold) thresholdAtMinute = 0;
      else if (scenario.rateKgPerMinute > 0) {
        const first = (threshold - bin.weightKg) / scenario.rateKgPerMinute;
        if (first <= scenario.horizonMinutes && (scenario.emptyAtMinute === null || first < scenario.emptyAtMinute)) thresholdAtMinute = first;
        else if (scenario.emptyAtMinute !== null) {
          const afterEmpty = scenario.emptyAtMinute + threshold / scenario.rateKgPerMinute;
          if (afterEmpty <= scenario.horizonMinutes) thresholdAtMinute = afterEmpty;
        }
      }
    }
    return { id: bin.id, warehouseId: bin.warehouseId, initialWeightKg: bin.weightKg, capacityKg: bin.capacityKg, thresholdAtMinute, final: points.at(-1), points };
  });
  return { previewOnly: true, generatedAt: new Date().toISOString(), startingReadAt: fleet.readAt, scenario, bins,
    assumptions: ['Constant kg/minute per selected bin.', 'Optional single emptying event.', 'Predictions do not publish MQTT or update Ditto.', 'Illustrative projection; no physical validation or OWL reasoning.'] };
}
