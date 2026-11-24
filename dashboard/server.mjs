import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { once } from 'node:events';
import { createDittoClient } from '../shared/ditto-client.mjs';
import { normalizeFleet } from '../shared/fleet.mjs';
import { previewScenario } from '../simulation/engine.mjs';
import { createScenarioStore } from '../simulation/store.mjs';
const root = dirname(fileURLToPath(import.meta.url));
export async function createDashboard({ port = 4321, client = createDittoClient(), storePath = resolve(root, '.data/scenarios.json') } = {}) {
  const store = createScenarioStore(storePath);
  let cached, pending;
  async function fleet() {
    if (cached?.expires > Date.now()) return cached.value;
    if (pending) return pending;
    pending = (async () => {
      const [things, connection] = await Promise.allSettled([client.readThings(), client.request('/connections/smartbin-native-mqtt/status', { admin: true })]);
      if (things.status === 'rejected') throw things.reason;
      const value = { ...normalizeFleet(things.value), transport: connection.status === 'fulfilled'
        ? { available: true, status: connection.value } : { available: false, error: connection.reason.message } };
      cached = { expires: Date.now() + 1500, value }; return value;
    })();
    try { return await pending; } finally { pending = null; }
  }
  const assets = new Map([['/', ['index.html', 'text/html']], ['/app.js', ['app.js', 'text/javascript']], ['/operations.js', ['operations.js', 'text/javascript']], ['/styles.css', ['styles.css', 'text/css']]]);
  function json(res, status, body) { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); }
  const server = http.createServer(async (req, res) => {
    res.setHeader('cache-control', 'no-store'); res.setHeader('x-content-type-options', 'nosniff');
    res.setHeader('content-security-policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'");
    const url = new URL(req.url, 'http://localhost');
    try {
      if (req.method === 'GET' && url.pathname === '/api/fleet') return json(res, 200, await fleet());
      if (req.method === 'GET' && url.pathname === '/api/scenarios') return json(res, 200, { scenarios: await store.list() });
      if (req.method === 'POST' && ['/api/scenarios', '/api/simulation/preview'].includes(url.pathname)) {
        if (req.headers.origin && req.headers.origin !== 'http://' + req.headers.host) return json(res, 403, { error: 'Open this dashboard directly on localhost.' });
        if (!(req.headers['content-type'] || '').startsWith('application/json')) return json(res, 415, { error: 'Send JSON.' });
        let body = ''; for await (const chunk of req) { body += chunk; if (body.length > 16000) throw new Error('Scenario is too large.'); }
        const input = JSON.parse(body);
        if (url.pathname === '/api/scenarios') return json(res, 201, await store.save(input));
        return json(res, 200, previewScenario(await fleet(), input));
      }
      if (req.method === 'GET' && assets.has(url.pathname)) {
        const [name, type] = assets.get(url.pathname); const bytes = await readFile(resolve(root, 'public', name));
        res.writeHead(200, { 'content-type': type + '; charset=utf-8' }); return res.end(bytes);
      }
      return json(res, 404, { error: 'Not found.' });
    } catch (error) { json(res, url.pathname === '/api/fleet' ? 503 : 400, { error: error.message }); }
  });
  server.listen(port, '127.0.0.1'); await once(server, 'listening');
  return { url: 'http://127.0.0.1:' + server.address().port, close: () => new Promise(resolveClose => server.close(resolveClose)) };
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  createDashboard({ port: Number(process.env.DASHBOARD_PORT || 4321) }).then(app => {
    console.log('SmartBin twin dashboard: ' + app.url);
    for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => app.close().then(() => process.exit(0)));
  }).catch(error => { console.error(error.message); process.exitCode = 1; });
}
