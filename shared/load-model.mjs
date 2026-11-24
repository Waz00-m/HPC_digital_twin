export function loadProperties(weightKg, model, receivedAt) {
  if (!Number.isFinite(weightKg) || weightKg < 0 || !Number.isFinite(model.capacityKg) || model.capacityKg <= 0) throw new Error('A nonnegative weight and positive model capacity are required.');
  const threshold = model.alertThresholdPercent ?? null;
  if (threshold !== null && (!Number.isFinite(threshold) || threshold <= 0 || threshold > 100)) throw new Error('Model alertThresholdPercent must be greater than 0 and at most 100.');
  const alertThresholdKg = threshold === null ? null : model.capacityKg * threshold / 100;
  const alertActive = threshold === null ? null : weightKg >= alertThresholdKg;
  return { weightKg, capacityKg: model.capacityKg, weightPercent: weightKg / model.capacityKg * 100,
    alertThresholdPercent: threshold, alertThresholdKg, alertActive,
    status: weightKg > model.capacityKg ? 'over-capacity' : threshold === null ? 'unconfigured' : alertActive ? 'attention' : 'normal',
    unit: 'kg', receivedAt };
}
