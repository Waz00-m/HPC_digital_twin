import { readFile, writeFile } from 'node:fs/promises';
import { createDittoClient } from '../shared/ditto-client.mjs';

const client = createDittoClient();
const bins = (await client.readThings({ refresh: true })).filter(thing => thing.attributes?.type === 'SmartBin');
if (!bins.length) throw new Error('Import the ontology before configuring MQTT.');
const incomingScript = (await readFile(new URL('./incoming-mapping.js', import.meta.url), 'utf8')).replace('"__NAMESPACE__"', JSON.stringify(client.namespace));
const sourcesByWarehouse = new Map();
for (const bin of bins) {
  const a = bin.attributes, expected = 'smartbin/' + a.warehouseId + '/' + a.binId + '/weight';
  if (a.mqttTopic !== expected || bin.thingId !== client.namespace + ':' + a.binId || !/^[A-Za-z0-9_.-]+$/.test(a.binId)) throw new Error('Invalid imported MQTT identity for ' + bin.thingId);
  const subject = 'smartbin-mqtt:' + a.warehouseId;
  const policy = await client.request('/policies/' + encodeURIComponent(bin.policyId || bin.thingId));
  policy.entries.SMARTBIN_MQTT = { subjects: { [subject]: { type: 'Native MQTT load readings for ' + a.binId } },
    resources: { 'thing:/features/load': { grant: ['READ', 'WRITE'], revoke: [] } } };
  await client.request('/policies/' + encodeURIComponent(bin.policyId || bin.thingId), { method: 'PUT', body: policy });
  if (!sourcesByWarehouse.has(a.warehouseId)) sourcesByWarehouse.set(a.warehouseId, { addresses: [], consumerCount: 1, qos: 1,
    authorizationContext: [subject], payloadMapping: ['smartbin-weight'],
    enforcement: { input: '{{ source:address }}', filters: ['smartbin/' + a.warehouseId + '/{{ thing:name }}/weight'] } });
  sourcesByWarehouse.get(a.warehouseId).addresses.push(expected);
}
const connection = { id: 'smartbin-native-mqtt', name: 'SmartBin native MQTT', connectionType: 'mqtt', connectionStatus: 'open',
  uri: 'tcp://smartbin-mqtt:1883', clientCount: 1, failoverEnabled: true, sources: [...sourcesByWarehouse.values()], targets: [],
  specificConfig: { clientId: 'ditto-smartbin-native', cleanSession: 'false' },
  mappingDefinitions: { 'smartbin-weight': { mappingEngine: 'JavaScript', options: { incomingScript, outgoingScript: 'function mapFromDittoProtocolMsg() { return null; }' } } } };
await client.request('/connections/' + connection.id, { method: 'PUT', body: connection, admin: true });
await writeFile(new URL('./native-connection.json', import.meta.url), JSON.stringify(connection, null, 2) + '\n');
console.log('Configured Ditto native MQTT for ' + bins.length + ' bins with warehouse-scoped sources and topic-to-bin enforcement.');
console.log('Connection status: http://localhost:8090/api/2/connections/' + connection.id + '/status (DevOps authentication).');
