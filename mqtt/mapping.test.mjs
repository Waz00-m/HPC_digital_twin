import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
const script = (await readFile(new URL('./incoming-mapping.js', import.meta.url), 'utf8')).replace('"__NAMESPACE__"', '"smartbin"');
function mapper() {
  const sandbox = { Ditto: {
    buildDittoProtocolMsg: (namespace, name, group, channel, criterion, action, path, headers, value) => ({ namespace, name, action, path, headers, value }),
    arrayBufferToString: bytes => Buffer.from(bytes).toString()
  } };
  vm.createContext(sandbox); vm.runInContext(script, sandbox); return sandbox.mapToDittoProtocolMsg;
}
test('native mapper accepts numeric/JSON/binary weights and targets only the topic bin load feature', () => {
  const map = mapper(), headers = { 'mqtt.topic': 'smartbin/warehouse-b/bin-002/weight' };
  for (const [text, bytes] of [['20.125', null], [null, Buffer.from('20.125')], ['{"binId":"bin-002","warehouseId":"warehouse-b","weightKg":20.125}', null]]) {
    const result = map(headers, text, bytes, null);
    assert.equal(result.namespace, 'smartbin'); assert.equal(result.name, 'bin-002');
    assert.equal(result.path, '/features/load'); assert.equal(result.action, 'modify');
    assert.equal(result.value.properties.weightKg, 20.125); assert.equal(result.value.properties.source, 'mqtt-native');
    assert.ok(!('weightPercent' in result.value.properties), 'derived values belong to the read-side model calculation');
  }
});
test('native mapper drops invalid values, identity changes and injected protocol commands', () => {
  const map = mapper(), header = { 'mqtt.topic': 'smartbin/warehouse-b/bin-002/weight' };
  for (const value of ['', '-1', 'NaN', 'Infinity', '2000001', '{}',
    '{"binId":"bin-003","warehouseId":"warehouse-b","weightKg":20}',
    '{"binId":"bin-002","warehouseId":"warehouse-a","weightKg":20}',
    '{"topic":"smartbin/bin-999/things/twin/commands/modify","path":"/attributes","value":{}}']) assert.equal(map(header, value, null, null), null);
  assert.equal(map({ 'mqtt.topic': 'other/warehouse-b/bin-002/weight' }, '20', null, null), null);
});
