export const modes = ['manual', 'filling', 'draining', 'cycle', 'noisy'];
export function number(value, name, min, max) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max)
    throw new Error(`${name} must be a number between ${min} and ${max}.`);
  return value;
}
export function makeBins(count = 9) {
  number(count, 'Bin count', 1, 1000);
  if (!Number.isInteger(count)) throw new Error('Bin count must be a whole number.');
  return Array.from({ length: count }, (_, i) => {
    const warehouseId = `warehouse-${String.fromCharCode(97 + i % 3)}`;
    const capacityKg = [10, 50, 100][i % 3];
    return { id: `bin-${String(i + 1).padStart(3, '0')}`, warehouseId, capacityKg,
      weightKg: +(capacityKg * (0.15 + (i % 5) * 0.12)).toFixed(3),
      mode: 'manual', rateKgPerMinute: +(capacityKg * 0.1).toFixed(3), online: true,
      lastPublishedAt: null, published: 0 };
  });
}
export function selectBins(bins, selector = {}) {
  const selected = bins.filter(b => (!selector.warehouseId || b.warehouseId === selector.warehouseId)
    && (!selector.binId || b.id === selector.binId));
  if (!selected.length) throw new Error('No bins match this selection.');
  return selected;
}
export function applyChanges(bins, selector, patch) {
  const selected = selectBins(bins, selector);
  const allowed = ['capacityKg', 'weightKg', 'percent', 'mode', 'rateKgPerMinute', 'online'];
  if (!patch || typeof patch !== 'object' || Array.isArray(patch)) throw new Error('Changes must be an object.');
  for (const key of Object.keys(patch)) if (!allowed.includes(key)) throw new Error(`Unknown setting: ${key}`);
  if (patch.capacityKg !== undefined) number(patch.capacityKg, 'Capacity', 0.001, 1000000);
  if (patch.weightKg !== undefined) number(patch.weightKg, 'Weight', 0, 2000000);
  if (patch.percent !== undefined) number(patch.percent, 'Weight percentage', 0, 200);
  if (patch.rateKgPerMinute !== undefined) number(patch.rateKgPerMinute, 'Rate', 0, 1000000);
  if (patch.mode !== undefined && !modes.includes(patch.mode)) throw new Error('Choose a valid scenario.');
  if (patch.online !== undefined && typeof patch.online !== 'boolean') throw new Error('Online must be true or false.');
  for (const b of selected) {
    for (const key of allowed.filter(k => k !== 'percent')) if (patch[key] !== undefined) b[key] = patch[key];
    if (patch.percent !== undefined) b.weightKg = +(b.capacityKg * patch.percent / 100).toFixed(3);
  }
  return selected;
}
export function advance(bin, seconds, random = Math.random) {
  if (!bin.online || bin.mode === 'manual') return;
  const delta = bin.rateKgPerMinute * seconds / 60;
  if (bin.mode === 'filling') bin.weightKg = Math.min(bin.capacityKg, bin.weightKg + delta);
  if (bin.mode === 'draining') bin.weightKg = Math.max(0, bin.weightKg - delta);
  if (bin.mode === 'cycle') bin.weightKg = (bin.weightKg + delta) % bin.capacityKg;
  if (bin.mode === 'noisy') bin.weightKg = Math.max(0, Math.min(bin.capacityKg, bin.weightKg + (random() - 0.5) * bin.capacityKg * 0.02));
}
export function topicFor(bin, prefix) { return `${prefix}/${bin.warehouseId}/${bin.id}/weight`; }
export function payloadFor(bin, format, timestamp = new Date().toISOString()) {
  const weightKg = +bin.weightKg.toFixed(3);
  return format === 'number' ? String(weightKg) : JSON.stringify({
    binId: bin.id, warehouseId: bin.warehouseId, weightKg,
    timestamp, simulated: true
  });
}
