import { loadProperties } from './load-model.mjs';
export function normalizeFleet(things, readAt = new Date().toISOString()) {
  const warehouses = things.filter(t => t.attributes?.type === 'Warehouse').map(t => ({ id: t.attributes.warehouseId, thingId: t.thingId,
    name: t.attributes.warehouseId.replace(/^warehouse-(.*)$/, (_, name) => 'Warehouse ' + name.toUpperCase()) })).sort((a, b) => a.id.localeCompare(b.id));
  const bins = things.filter(t => t.attributes?.type === 'SmartBin').map(t => {
    const a = t.attributes, raw = t.features?.load?.properties;
    const base = { id: a.binId, thingId: t.thingId, warehouseId: a.warehouseId, capacityKg: a.capacityKg,
      alertThresholdPercent: a.alertThresholdPercent ?? null, mqttTopic: a.mqttTopic,
      ontologyIri: a.ontologyIri, ontologyIndividualIri: a.ontologyIndividualIri,
      receivedAt: raw?.receivedAt || null, source: raw?.source || null, revision: t._revision,
      raw: raw || null, hasReading: false, status: 'awaiting-reading' };
    if (!raw || !Number.isFinite(raw.weightKg)) return base;
    if (raw.warehouseId && raw.warehouseId !== a.warehouseId) return { ...base, status: 'identity-mismatch', error: 'Reading warehouse differs from the model. Check the MQTT connection and send a new reading.' };
    try { return { ...base, ...loadProperties(raw.weightKg, a, base.receivedAt), hasReading: true }; }
    catch (error) { return { ...base, status: 'invalid-model', error: error.message }; }
  }).sort((a, b) => a.id.localeCompare(b.id));
  return { readAt, warehouses, bins, derivedFrom: 'Ditto raw readings and current imported model attributes' };
}
