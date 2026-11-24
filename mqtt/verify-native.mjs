import assert from 'node:assert/strict';
import net from 'node:net';
import { createRequire } from 'node:module';
import { writeFile } from 'node:fs/promises';
import { createDittoClient } from '../shared/ditto-client.mjs';
import { normalizeFleet } from '../shared/fleet.mjs';
const require = createRequire(new URL('../simulator/package.json', import.meta.url));
const mqtt = require('mqtt');
const client = createDittoClient();
const oldBridgeListening = await new Promise(resolve => {
  const socket = net.connect({ host: '127.0.0.1', port: 4320 });
  socket.once('connect', () => { socket.destroy(); resolve(true); });
  socket.once('error', () => resolve(false)); socket.setTimeout(1500, () => { socket.destroy(); resolve(false); });
});
assert.equal(oldBridgeListening, false, 'Stop the removed bridge before verifying the native path.');
const initial = (await client.readThings({ refresh: true })).filter(t => t.attributes.type === 'SmartBin');
assert.equal(initial.length, 9, 'This verification deliberately updates the original nine demo bins.');
const connection = await client.request('/connections/smartbin-native-mqtt/status', { admin: true });
assert.equal(connection.liveStatus, 'open'); assert.ok(connection.sourceStatus.every(source => source.status === 'open'));
const publisher = await mqtt.connectAsync('mqtt://127.0.0.1:1884', { reconnectPeriod: 0, connectTimeout: 6000 });
const phases = [];
async function verify(name, percentFor, json = false) {
  const before = new Map((await client.readThings()).map(t => [t.thingId, t._revision]));
  const expected = new Map();
  for (const thing of initial) {
    const a = thing.attributes, weightKg = a.capacityKg * percentFor(a.binId) / 100;
    expected.set(thing.thingId, weightKg);
    const payload = json ? JSON.stringify({ binId: a.binId, warehouseId: a.warehouseId, weightKg, simulated: true }) : String(weightKg);
    await publisher.publishAsync(a.mqttTopic, payload, { qos: 1 });
  }
  let things, done = false;
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    things = (await client.readThings()).filter(t => expected.has(t.thingId));
    done = things.length === 9 && things.every(t => t._revision > before.get(t.thingId) &&
      t.features?.load?.properties?.source === 'mqtt-native' &&
      Math.abs(t.features.load.properties.weightKg - expected.get(t.thingId)) < 0.000001);
    if (done) break;
    await new Promise(resolve => setTimeout(resolve, 350));
  }
  assert.ok(done, name + ': every bin must be updated by the native Ditto connection');
  for (const thing of things) {
    const original = initial.find(t => t.thingId === thing.thingId);
    assert.deepEqual(thing.attributes, original.attributes); assert.equal(thing.policyId, original.policyId);
    assert.ok(!('weightPercent' in thing.features.load.properties), 'raw twin stores telemetry; model calculations are read-side');
  }
  const fleet = normalizeFleet(things);
  for (const bin of fleet.bins) {
    const percent = percentFor(bin.id);
    assert.ok(Math.abs(bin.weightPercent - percent) < 0.000001);
    assert.equal(bin.status, percent > 100 ? 'over-capacity' : percent >= bin.alertThresholdPercent ? 'attention' : 'normal');
  }
  phases.push({ name, bins: fleet.bins }); console.log(name + ': all nine native MQTT updates verified in Ditto.');
}
try {
  await verify('Below threshold', () => 84.9);
  await verify('At threshold, JSON payload', () => 85, true);
  await verify('Over capacity', () => 110);
  await verify('Alert cleared', () => 40);
  const beforeInvalid = await client.request('/things/smartbin%3Abin-002?fields=thingId,features/load,_revision');
  assert.ok(Number.isFinite(beforeInvalid._revision));
  for (const payload of ['-1', '{"binId":"bin-999","warehouseId":"warehouse-b","weightKg":1}', '{"topic":"other/commands","value":{}}'])
    await publisher.publishAsync('smartbin/warehouse-b/bin-002/weight', payload, { qos: 1 });
  await publisher.publishAsync('smartbin/warehouse-a/bin-002/weight', '99', { qos: 1 });
  await new Promise(resolve => setTimeout(resolve, 1500));
  const afterInvalid = await client.request('/things/smartbin%3Abin-002?fields=thingId,features/load,_revision');
  assert.equal(afterInvalid._revision, beforeInvalid._revision, 'invalid inputs must not change a twin');
  console.log('Invalid payloads and wrong-warehouse topic: no twin changes.');
  await verify('Mixed warehouse demo', id => Number(id.slice(-3)) <= 3 ? 40 : Number(id.slice(-3)) <= 6 ? 85 : 110);
  await writeFile(new URL('./native-demo-results.json', import.meta.url), JSON.stringify({
    verifiedAt: new Date().toISOString(), oldBridgeListening, connection: 'smartbin-native-mqtt', phases
  }, null, 2) + '\n');
  console.table(phases.at(-1).bins.map(b => ({ bin: b.id, warehouse: b.warehouseId, kg: b.weightKg,
    capacity: b.capacityKg, percent: +b.weightPercent.toFixed(3), status: b.status, source: b.source })));
} finally { await publisher.endAsync(true); }
