// Executed INSIDE Ditto's native MQTT connection, not by a Node.js subscriber.
function mapToDittoProtocolMsg(headers, textPayload, bytePayload, contentType) {
  var namespace = "__NAMESPACE__";
  var topic = headers['mqtt.topic'] || headers.topic || '';
  var match = /^smartbin\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)\/weight$/.exec(topic);
  if (!match) return null;
  var raw = textPayload != null ? String(textPayload) : bytePayload != null ? Ditto.arrayBufferToString(bytePayload) : '';
  raw = raw.trim();
  if (!raw) return null;
  var weight;
  try {
    if (raw.charAt(0) === '{') {
      var data = JSON.parse(raw);
      if (data.binId !== match[2] || data.warehouseId !== match[1]) return null;
      weight = data.weightKg;
    } else {
      if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw)) return null;
      weight = Number(raw);
    }
  } catch (error) { return null; }
  if (typeof weight !== 'number' || !isFinite(weight) || weight < 0 || weight > 2000000) return null;
  return Ditto.buildDittoProtocolMsg(namespace, match[2], 'things', 'twin', 'commands', 'modify',
    '/features/load', { 'content-type': 'application/json', 'response-required': false }, {
      properties: { weightKg: weight, unit: 'kg', warehouseId: match[1],
        receivedAt: new Date().toISOString(), source: 'mqtt-native' }
    });
}
