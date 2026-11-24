import test from 'node:test';
import assert from 'node:assert/strict';
import mqtt from 'mqtt';
import { once } from 'node:events';
import { makeBins, applyChanges, advance, topicFor } from './engine.mjs';
import { createApplication } from './server.mjs';


test('warehouse selection uses each capacity; invalid batch is atomic; silence freezes scenarios', () => {
  const bins = makeBins();
  assert.equal(new Set(bins.map(b => b.id)).size, 9);
  for (const id of ['warehouse-a', 'warehouse-b', 'warehouse-c']) assert.equal(bins.filter(b => b.warehouseId === id).length, 3);
  applyChanges(bins, {}, { percent: 85 });
  assert.deepEqual(bins.slice(0, 3).map(b => b.weightKg), [8.5, 42.5, 85]);
  const before = structuredClone(bins);
  assert.throws(() => applyChanges(bins, {}, { percent: -1, mode: 'filling' }));
  assert.deepEqual(bins, before);
  applyChanges(bins, { binId: 'bin-001' }, { mode: 'filling', weightKg: 2, rateKgPerMinute: 6 });
  advance(bins[0], 30); assert.equal(bins[0].weightKg, 5);
  advance(bins[0], 100); assert.equal(bins[0].weightKg, 10);
  applyChanges(bins, { binId: 'bin-001' }, { online: false });
  advance(bins[0], 1); assert.equal(bins[0].weightKg, 10);
  applyChanges(bins, { binId: 'bin-002' }, { mode: 'filling', weightKg: 0, rateKgPerMinute: 0.01 });
  for (let i = 0; i < 240; i++) advance(bins[1], 0.25);
  assert.ok(Math.abs(bins[1].weightKg - 0.01) < 1e-10, 'small fill increments must accumulate');
});

test('real MQTT subscriber receives correct identities, numeric and JSON payloads, and 100-bin fleet', { timeout: 20000 }, async () => {
  const app = await createApplication({ port: 0, mqttPort: 0 });
  const receiver = mqtt.connect(app.localBrokerUrl, { reconnectPeriod: 0 });
  const received = [];
  try {
    await once(receiver, 'connect');
    receiver.on('message', (topic, payload) => received.push({ topic, payload: payload.toString() }));
    await receiver.subscribeAsync('smartbin/#');
    await app.action({ action: 'connect' });
    const deadline = Date.now() + 4000;
    while (app.snapshot().connection.status !== 'connected' && Date.now() < deadline) await new Promise(r => setTimeout(r, 20));
    assert.equal(app.snapshot().connection.status, 'connected');
    await app.action({ action: 'update', selector: { binId: 'bin-001' }, patch: { weightKg: 7.2 } });
    await app.action({ action: 'publish', selector: { binId: 'bin-001' } });
    await new Promise(r => setTimeout(r, 80));
    assert.deepEqual(received[0], { topic: 'smartbin/warehouse-a/bin-001/weight', payload: '7.2' });
    await app.action({ action: 'update', selector: { binId: 'bin-001' }, patch: { online: false } });
    await assert.rejects(app.action({ action: 'publish', selector: { binId: 'bin-001' } }), /silent/);
    await app.action({ action: 'generate', count: 100 });
    received.length = 0;
    await app.action({ action: 'publish' });
    await new Promise(r => setTimeout(r, 100));
    assert.equal(new Set(received.map(m => m.topic)).size, 100);
    assert.equal(app.snapshot().bins.length, 100);
    await app.action({ action: 'connect', config: { format: 'json' } });
    const deadline2 = Date.now() + 4000;
    while (app.snapshot().connection.status !== 'connected' && Date.now() < deadline2) await new Promise(r => setTimeout(r, 20));
    received.length = 0;
    await app.action({ action: 'publish', selector: { binId: 'bin-100' } });
    await new Promise(r => setTimeout(r, 80));
    const payload = JSON.parse(received[0].payload);
    assert.equal(payload.binId, 'bin-100'); assert.equal(payload.simulated, true);
    assert.equal(received[0].topic, topicFor(app.snapshot().bins[99], 'smartbin'));
    await app.action({ action: 'start' });
    await assert.rejects(app.action({ action: 'generate', count: 9 }), /Pause/);
    await app.action({ action: 'pause' });
    const result = await fetch(`${app.url}/api/action`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action: 'update', patch: { capacityKg: 0 } }) });
    assert.equal(result.status, 400);
    assert.match((await result.json()).error, /Capacity/);
    const forbidden = await fetch(`${app.url}/api/action`, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: 'https://example.com' }, body: '{}' });
    assert.equal(forbidden.status, 403);
    assert.equal((await fetch(app.url)).status, 200);
    assert.ok(!('password' in JSON.parse(JSON.stringify(app.snapshot())).config));
  } finally { await receiver.endAsync(true); await app.close(); }
});
