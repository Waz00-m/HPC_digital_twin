import { writeFile } from 'node:fs/promises';
import { createDittoClient } from '../shared/ditto-client.mjs';
import { normalizeFleet } from '../shared/fleet.mjs';
import { assertHistoryReady } from './history-readiness.mjs';
const client = createDittoClient();
const seedMissing = process.argv.includes('--seed-missing');
const report = process.argv.includes('--report');
async function retry(action, description, seconds = 120) {
  const deadline = Date.now() + seconds * 1000;
  let last;
  while (Date.now() < deadline) {
    try { return await action(); } catch (error) { last = error; await new Promise(resolve => setTimeout(resolve, 1500)); }
  }
  throw new Error(description + ': ' + last?.message);
}
async function api(origin, path, body) {
  const response = await fetch(origin + path, { signal: AbortSignal.timeout(20000), ...(body ? { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) } : {}) });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || ('HTTP ' + response.status));
  return value;
}
async function waitNative() {
  await retry(async () => {
    const status = await client.request('/connections/smartbin-native-mqtt/status', { admin: true });
    if (status.liveStatus !== 'open' || !status.clientStatus?.some(item => item.status === 'open') ||
        !status.sourceStatus?.length || !status.sourceStatus.every(item => item.status === 'open')) throw new Error('Waiting for Ditto native MQTT to subscribe.');
  }, 'Native MQTT readiness');
}
if (process.argv.includes('--check-provisioned')) {
  const things = await client.readThings({ refresh: true });
  if (things.filter(t => t.attributes?.type === 'SmartBin').length !== 9 || things.filter(t => t.attributes?.type === 'Warehouse').length !== 3) throw new Error('Stored model setup is missing and needs repair.');
  await waitNative();
  console.log('Existing nine-bin model and native MQTT connection are ready.');
  process.exit(0);
}
if (process.argv.includes('--configure')) {
  await retry(async () => {
    const things = await client.readThings({ refresh: true });
    if (things.filter(t => t.attributes?.type === 'SmartBin').length !== 9 || things.filter(t => t.attributes?.type === 'Warehouse').length !== 3) throw new Error('Waiting for the twelve imported Things to appear in search.');
  }, 'Ontology indexing');
  await import('../mqtt/configure-ditto.mjs');
  await waitNative();
  process.exit(0);
}
const simulator = 'http://127.0.0.1:4318', history = 'http://127.0.0.1:4322';
if (process.argv.includes('--status')) {
  const values = await Promise.allSettled([api(simulator, '/api/state'), api('http://127.0.0.1:4321', '/api/fleet'), api(history, '/api/metrics')]);
  console.log(JSON.stringify({ simulator: values[0].status === 'fulfilled' ? { connected: values[0].value.connection.status, automaticPublishing: values[0].value.running } : { error: values[0].reason.message },
    dashboard: values[1].status === 'fulfilled' ? { bins: values[1].value.bins.length, warehouses: values[1].value.warehouses.length } : { error: values[1].reason.message },
    history: values[2].status === 'fulfilled' ? values[2].value : { error: values[2].reason.message } }, null, 2));
  process.exit(values.every(value => value.status === 'fulfilled') ? 0 : 1);
}
await retry(async () => { await api(simulator, '/api/state'); await api('http://127.0.0.1:4321', '/api/fleet'); }, 'App startup');
const fleet = normalizeFleet(await client.readThings({ refresh: true }));
if (fleet.bins.length !== 9 || fleet.warehouses.length !== 3) throw new Error('Expected nine bins and three warehouses. Run Install-Mac.command to import the starter model.');
await waitNative();
let state = await api(simulator, '/api/state');
if (!state.running) {
  if (state.bins.length !== 9) throw new Error('The simulator fleet differs from the nine-bin model. Restore the nine-bin demo before continuing.');
  for (const bin of fleet.bins) {
    const index = Number(bin.id.split('-').at(-1)) - 1;
    const weight = bin.hasReading ? bin.weightKg : bin.capacityKg * (index < 3 ? .4 : index < 6 ? .85 : 1.1);
    await api(simulator, '/api/action', { action: 'update', selector: { binId: bin.id }, patch: { weightKg: weight, capacityKg: bin.capacityKg } });
  }
}
if (state.connection.status !== 'connected') state = await api(simulator, '/api/action', { action: 'connect' });
await retry(async () => {
  if ((await api(simulator, '/api/state')).connection.status !== 'connected') throw new Error('Waiting for the spoofer broker connection.');
}, 'Spoofer broker readiness', 30);
if (seedMissing) {
  for (const bin of fleet.bins.filter(bin => !bin.hasReading)) await api(simulator, '/api/action', { action: 'publish', selector: { binId: bin.id } });
}
const stored = await retry(async () => {
  const health = await api(history, '/health');
  assertHistoryReady(health);
  const latest = await api(history, '/api/latest');
  const valid = latest.rows.filter(row => row.model_type === 'SmartBin' && row.quality === 'valid');
  if (valid.length !== 9) throw new Error('Waiting for nine valid bin snapshots. On first setup run Install-Mac.command; otherwise send the missing readings.');
  return latest;
}, 'Thing-history readiness', 180);
let run;
if (report) run = await api(history, '/api/model-runs', { model: 'pipeline-check' });
const result = { checkedAt: new Date().toISOString(), thingsStored: stored.count, bins: 9, warehouses: 3,
  mqtt: 'native Ditto connectivity', history: 'stored post-Ditto Things', modelRunId: run?.run_id ?? null,
  bossModelConnected: false, prediction: false, dashboard: 'http://127.0.0.1:4321/', simulator: 'http://127.0.0.1:4318/', historyApi: 'http://127.0.0.1:4322/api/metrics' };
if (report) await writeFile('/artifacts/setup-report.json', JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result, null, 2));
