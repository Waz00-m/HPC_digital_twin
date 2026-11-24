export function createDittoClient({
  origin = process.env.DITTO_URL || 'http://127.0.0.1:8090',
  username = process.env.DITTO_USERNAME || 'ditto', password = process.env.DITTO_PASSWORD || 'ditto',
  devopsUsername = process.env.DITTO_DEVOPS_USERNAME || 'devops', devopsPassword = process.env.DITTO_DEVOPS_PASSWORD || 'foobar',
  namespace = process.env.DITTO_NAMESPACE || 'smartbin'
} = {}) {
  const url = new URL(origin);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
      (url.protocol === 'http:' && !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname))) throw new Error('Use a local HTTP or remote HTTPS Ditto origin without credentials or a path.');
  if (!/^[A-Za-z0-9_.-]+$/.test(namespace)) throw new Error('Invalid Ditto namespace.');
  async function request(path, { method = 'GET', body, admin = false, headers = {} } = {}) {
    const authorization = 'Basic ' + Buffer.from(admin ? devopsUsername + ':' + devopsPassword : username + ':' + password).toString('base64');
    const response = await fetch(url.origin + '/api/2' + path, { method, signal: AbortSignal.timeout(15000),
      headers: { authorization, ...(body !== undefined ? { 'content-type': 'application/json' } : {}), ...headers },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      const error = new Error('Ditto returned HTTP ' + response.status + ' for ' + path.split('?')[0] + '. ' + (detail.message || '') + ' ' + (detail.description || ''));
      error.status = response.status; throw error;
    }
    const raw = await response.text();
    return raw ? JSON.parse(raw) : null;
  }
  let discovery;
  async function discover({ refresh = false } = {}) {
    if (!refresh && discovery?.expires > Date.now()) return discovery.ids;
    const query = new URLSearchParams({ namespaces: namespace,
      filter: 'or(eq(attributes/type,"SmartBin"),eq(attributes/type,"Warehouse"))', fields: 'thingId', option: 'size(200)' });
    const result = await request('/search/things?' + query);
    if (result.cursor || result.nextPage) throw new Error('This dashboard supports up to 200 imported records. Narrow the namespace before continuing.');
    const ids = result.items.map(thing => thing.thingId);
    discovery = { ids, expires: Date.now() + 60000 };
    return ids;
  }
  async function readThings(options) {
    const ids = await discover(options), things = [];
    for (let i = 0; i < ids.length; i += 50) {
      const query = new URLSearchParams({ ids: ids.slice(i, i + 50).join(','), fields: 'thingId,policyId,attributes,features/load/properties,_revision,_modified' });
      things.push(...await request('/things?' + query));
    }
    return things;
  }
  return { request, readThings, namespace };
}
