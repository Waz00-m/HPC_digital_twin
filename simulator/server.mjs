import http from 'node:http';
import net from 'node:net';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, dirname } from 'node:path';
import { once } from 'node:events';
import aedes from 'aedes';
import mqtt from 'mqtt';
import { makeBins, number, selectBins, applyChanges, advance, topicFor, payloadFor } from './engine.mjs';

const root = dirname(fileURLToPath(import.meta.url));
export async function createApplication({ port = 4318, mqttPort = null, brokerUrl = process.env.MQTT_BROKER_URL || 'mqtt://127.0.0.1:1884' } = {}) {
  // Embedded Aedes is isolated to tests that explicitly pass mqttPort (usually 0).
  const broker = mqttPort === null ? null : aedes();
  const brokerServer = broker ? net.createServer(broker.handle) : null;
  if (brokerServer) { brokerServer.listen(mqttPort, '127.0.0.1'); await once(brokerServer, 'listening'); }
  const localBrokerUrl = brokerServer ? `mqtt://127.0.0.1:${brokerServer.address().port}` : brokerUrl;
  let bins = makeBins(), client = null, running = false, lastStep = Date.now(), publishing = false;
  let config = { brokerUrl: localBrokerUrl, username: '', password: '', prefix: 'smartbin', format: 'number', intervalMs: 1000 };
  let connection = { status: 'disconnected', message: 'Connect to the local demo broker to publish readings.' };
  let sent = 0, failed = 0;
  const messages = [], streams = new Set();
  function snapshot() {
    return { bins, config: { ...config, password: undefined }, localBrokerUrl, running, connection, sent, failed, messages };
  }
  function broadcast() {
    const data = `data: ${JSON.stringify(snapshot())}\n\n`;
    for (const stream of streams) stream.write(data);
  }
  function event(message) { connection.message = message; broadcast(); }
  async function disconnect() {
    running = false;
    const previous = client;
    client = null;
    if (previous) { previous.removeAllListeners(); previous.on('error', () => {}); await previous.endAsync(true); }
    connection = { status: 'disconnected', message: 'MQTT disconnected. Simulation paused.' };
  }
  function validateConfig(input) {
    const next = { ...config, ...input };
    const u = new URL(next.brokerUrl);
    if (!['mqtt:', 'mqtts:'].includes(u.protocol) || !u.hostname || u.username || u.password || (u.pathname && u.pathname !== '/'))
      throw new Error('Use mqtt://host:port or mqtts://host:port. Enter credentials in their separate fields.');
    if (typeof next.prefix !== 'string' || !/^[a-zA-Z0-9_/-]{1,100}$/.test(next.prefix) || next.prefix.startsWith('/') || next.prefix.endsWith('/'))
      throw new Error('Topic prefix must use letters, numbers, /, - or _ without leading or trailing /.');
    if (!['number', 'json'].includes(next.format)) throw new Error('Choose numeric or JSON payloads.');
    number(next.intervalMs, 'Publish interval (milliseconds)', 250, 60000);
    if (typeof next.username !== 'string' || typeof next.password !== 'string') throw new Error('Credentials must be text.');
    return next;
  }
  async function connect(input) {
    const next = validateConfig(input);
    await disconnect();
    config = next;
    connection = { status: 'connecting', message: 'Connecting to MQTT broker…' };
    const c = mqtt.connect(config.brokerUrl, { protocolVersion: 4,
      clientId: `smartbin-simulator-${process.pid}-${Date.now()}`, username: config.username || undefined,
      password: config.password || undefined, reconnectPeriod: 2000, connectTimeout: 6000,
      clean: true, queueQoSZero: false });
    client = c;
    c.on('connect', () => { if (client !== c) return; connection = { status: 'connected', message: 'Connected. Ready to publish simulated readings.' }; broadcast(); });
    c.on('reconnect', () => { if (client !== c) return; connection.status = 'connecting'; event('Reconnecting to MQTT broker…'); });
    c.on('close', () => { if (client !== c) return; connection.status = 'disconnected'; event('Broker unavailable. No readings are being queued. Reconnecting…'); });
    c.on('error', error => { if (client === c) event(`MQTT: ${error.code || error.message}`); });
  }
  async function publish(selected) {
    if (!client?.connected) throw new Error('Connect to an MQTT broker before publishing.');
    if (publishing) throw new Error('A publish batch is still in progress. Try again shortly.');
    const active = selected.filter(b => b.online);
    if (!active.length) throw new Error('The selected bins are silent. Restore reporting first.');
    publishing = true;
    const c = client;
    try {
      await Promise.all(active.map(async bin => {
        const timestamp = new Date().toISOString(), topic = topicFor(bin, config.prefix), payload = payloadFor(bin, config.format, timestamp);
        try {
          await Promise.race([c.publishAsync(topic, payload, { qos: 1, retain: false }),
            new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('Broker acknowledgement timed out.')), 7000); timer.unref(); })]);
          if (c !== client) return;
          bin.lastPublishedAt = timestamp; bin.published++; sent++;
          messages.unshift({ timestamp, topic, payload, result: 'Broker acknowledged' });
        } catch (error) {
          failed++;
          messages.unshift({ timestamp, topic, payload, result: error.message });
        }
      }));
      messages.splice(60);
    } finally { publishing = false; broadcast(); }
  }
  let nextPublish = Date.now();
  const timer = setInterval(() => {
    const now = Date.now(), seconds = (now - lastStep) / 1000;
    lastStep = now;
    if (!running) return;
    bins.forEach(b => advance(b, seconds));
    if (now >= nextPublish) {
      nextPublish = now + config.intervalMs;
      if (client?.connected && !publishing && bins.some(b => b.online)) publish(bins).catch(error => event(error.message));
    }
    broadcast();
  }, 250);
  async function action(body) {
    switch (body.action) {
      case 'connect': await connect(body.config || {}); break;
      case 'disconnect': await disconnect(); break;
      case 'start':
        if (!client?.connected) throw new Error('Connect to an MQTT broker first.');
        running = true; lastStep = Date.now(); nextPublish = Date.now(); break;
      case 'pause': running = false; break;
      case 'generate':
        if (running || publishing) throw new Error('Pause and wait for publishing to finish before replacing bins.');
        bins = makeBins(body.count); break;
      case 'update': applyChanges(bins, body.selector, body.patch); break;
      case 'publish': await publish(selectBins(bins, body.selector)); break;
      case 'reset':
        running = false;
        bins.forEach(b => { b.weightKg = 0; b.mode = 'manual'; b.online = true; }); break;
      default: throw new Error('Unknown action.');
    }
    broadcast();
    return snapshot();
  }
  const assets = new Map([['/', ['index.html', 'text/html']], ['/app.js', ['app.js', 'text/javascript']], ['/styles.css', ['styles.css', 'text/css']]]);
  const server = http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'");
    try {
      const url = new URL(req.url, 'http://localhost');
      if (req.method === 'GET' && url.pathname === '/api/state') return json(res, 200, snapshot());
      if (req.method === 'GET' && url.pathname === '/api/events') {
        res.writeHead(200, { 'Content-Type': 'text/event-stream', Connection: 'keep-alive' });
        res.write(`data: ${JSON.stringify(snapshot())}\n\n`);
        streams.add(res); req.on('close', () => streams.delete(res)); return;
      }
      if (req.method === 'POST' && url.pathname === '/api/action') {
        if (req.headers.origin && req.headers.origin !== `http://${req.headers.host}`) return json(res, 403, { error: 'Open the control panel directly on localhost.' });
        if (!(req.headers['content-type'] || '').startsWith('application/json')) return json(res, 415, { error: 'Send JSON.' });
        let raw = '';
        for await (const chunk of req) { raw += chunk; if (raw.length > 32000) throw new Error('Request is too large.'); }
        return json(res, 200, await action(JSON.parse(raw)));
      }
      if (req.method === 'GET' && assets.has(url.pathname)) {
        const [name, type] = assets.get(url.pathname);
        const data = await readFile(resolve(root, 'public', name));
        res.writeHead(200, { 'Content-Type': `${type}; charset=utf-8` }); return res.end(data);
      }
      json(res, 404, { error: 'Not found.' });
    } catch (error) { json(res, 400, { error: error.message }); }
  });
  const bindHost = process.env.SMARTBIN_BIND_HOST || '127.0.0.1';
  if (!['127.0.0.1', '0.0.0.0'].includes(bindHost)) throw new Error('Use loopback or the explicit container bind host.');
  server.listen(port, bindHost);
  try { await once(server, 'listening'); } catch (error) { clearInterval(timer); brokerServer?.close(); broker?.close(); throw error; }
  return { url: `http://127.0.0.1:${server.address().port}`, localBrokerUrl, snapshot, action,
    async close() { clearInterval(timer); streams.forEach(s => s.end()); await disconnect(); await new Promise(r => server.close(r)); if (broker) await new Promise(r => broker.close(r)); if (brokerServer) await new Promise(r => brokerServer.close(r)); } };
}
function json(res, status, value) { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(value)); }
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  createApplication({ port: Number(process.env.PORT || 4318) }).then(app => {
    console.log(`SmartBin simulator: ${app.url}\nExternal demo MQTT broker: ${app.localBrokerUrl}`);
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => app.close().then(() => process.exit(0)));
  }).catch(error => { console.error(`Simulator could not start: ${error.message}`); process.exitCode = 1; });
}
