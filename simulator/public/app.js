const $ = id => document.getElementById(id);
let state, fleetKey = '', submitting = false, panelOnline = false, initializedSelection = false;
let entryUnit = 'kg', draftStatus = 'Current value', operation = '';

const names = { manual: 'Hold', filling: 'Filling', draining: 'Emptying', cycle: 'Fill / empty', noisy: 'Fluctuating' };
const formatNumber = value => Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 });
function selector() { return { warehouseId: $('warehouse').value, binId: $('bin').value }; }
function selection() {
  if (!state) return [];
  const scope = selector();
  return state.bins.filter(b => (!scope.warehouseId || b.warehouseId === scope.warehouseId) && (!scope.binId || b.id === scope.binId));
}
function message(value, error = false) { $('feedback').textContent = value; $('feedback').dataset.error = error; }
function text(tag, value, className = '') {
  const element = document.createElement(tag); element.textContent = value; element.className = className; return element;
}
function rangeText(values) {
  const min = Math.min(...values), max = Math.max(...values);
  return min === max ? formatNumber(min) : formatNumber(min) + '–' + formatNumber(max);
}
async function request(action, fields = {}) {
  const response = await fetch('/api/action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, ...fields }) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed. Try again.');
  render(result);
  return result;
}
async function act(action, fields = {}, success = '') {
  if (submitting) return;
  submitting = true; operation = action; renderControls();
  try {
    const result = await request(action, fields);
    if (action === 'generate' || action === 'reset') loadEditor();
    message(success || {
      connect: 'Connection requested. Wait for Ready to send.',
      start: 'Auto-send started for all reporting bins.',
      pause: 'Auto-send paused. You can still send a manual reading.',
      update: 'Selected bins updated.',
      publish: 'Current readings sent. Check MQTT activity for broker acknowledgements.',
      generate: 'New virtual fleet created. These bins have not been added to Ditto.',
      reset: 'All bins emptied locally and auto-send paused. No MQTT message was sent.',
      disconnect: 'Disconnected. Automatic publishing is paused.'
    }[action]);
    return result;
  } catch (error) {
    message(error.message, true);
  } finally { submitting = false; operation = ''; renderControls(); }
}
function binOptions() {
  const previous = $('bin').value;
  $('bin').replaceChildren(new Option('All bins in selection', ''));
  for (const bin of state.bins.filter(b => !$('warehouse').value || b.warehouseId === $('warehouse').value)) {
    $('bin').add(new Option(bin.id, bin.id));
  }
  if (Array.from($('bin').options).some(option => option.value === previous)) $('bin').value = previous;
}
function loadEditor() {
  const selected = selection(), first = selected[0];
  if (first) {
    $('capacity').value = first.capacityKg; $('mode').value = first.mode; $('rate').value = first.rateKgPerMinute;
    entryUnit = selected.length === 1 ? 'kg' : 'percent';
    $('unit').value = entryUnit;
    $('reading').value = selected.length === 1 ? +first.weightKg.toFixed(3) : 50;
    $('overload').checked = selected.length === 1 && first.weightKg > first.capacityKg;
  }
  draftStatus = selected.length === 1 ? 'Current value' : 'Draft — not sent';
  renderSelection(); renderDraft(); renderControls();
}
function renderSelection() {
  const selected = selection();
  $('selection-count').textContent = selected.length === 1
    ? selected[0].id + ' in ' + selected[0].warehouseId.replace('warehouse-', 'Warehouse ').toUpperCase()
    : selected.length + ' bins selected. Changes apply to this entire selection.';
  $('current-reading').textContent = selected.length ? rangeText(selected.map(b => b.weightKg)) + ' kg' : 'No bins selected';
  $('selected-capacity').textContent = selected.length ? rangeText(selected.map(b => b.capacityKg)) + ' kg' : '—';
}
function renderDraft() {
  const selected = selection(), value = $('reading').valueAsNumber;
  const single = selected.length === 1, isPercent = $('unit').value === 'percent';
  const slider = $('reading-slider'), max = $('overload').checked ? 200 : 100;
  slider.max = max;
  $('reading').max = isPercent ? 200 : 2000000;
  $('reading-label').textContent = isPercent ? 'Exact load (%)' : 'Exact weight (kg)';
  $('range-min').textContent = single && !isPercent ? '0 kg' : '0%';
  $('range-max').textContent = single && !isPercent ? formatNumber(selected[0].capacityKg * max / 100) + ' kg' : max + '%';
  $('draft-state').textContent = draftStatus;
  if (!selected.length || !Number.isFinite(value) || value < 0) {
    $('draft-value').textContent = '—';
    $('draft-details').textContent = selected.length ? 'Enter a valid nonnegative reading.' : 'Choose a warehouse or bin.';
    slider.setAttribute('aria-valuetext', 'No valid reading');
    return;
  }
  const weights = selected.map(b => isPercent ? b.capacityKg * value / 100 : value);
  const percent = isPercent ? value : single ? value / selected[0].capacityKg * 100 : 0;
  slider.value = Math.min(max, Math.max(0, percent));
  $('draft-value').textContent = single ? formatNumber(weights[0]) + ' kg' : isPercent ? formatNumber(value) + '%' : formatNumber(value) + ' kg each';
  $('draft-details').textContent = single
    ? formatNumber(percent) + '% of ' + formatNumber(selected[0].capacityKg) + ' kg capacity'
    : isPercent ? rangeText(weights) + ' kg per bin, according to each bin’s capacity.'
      : 'The same weight will be applied to all ' + selected.length + ' selected bins.';
  slider.setAttribute('aria-valuetext', single ? formatNumber(weights[0]) + ' kilograms, ' + formatNumber(percent) + ' percent of capacity' : isPercent ? formatNumber(value) + ' percent of each bin capacity' : 'Group slider is unavailable in kilogram mode');
  $('slider-help').textContent = !single && !isPercent
    ? 'Choose percentage units to use the group slider. Exact kilograms apply equally to every selected bin.'
    : percent > max
      ? 'This exact weight exceeds the slider scale. Extend to 200% or keep the typed value.'
      : 'Moving the slider previews a value. Send reading applies it and publishes once.';
}
function renderControls() {
  if (!state) return;
  const selected = selection(), connected = panelOnline && state.connection.status === 'connected';
  const reporting = selected.filter(b => b.online).length;
  for (const button of document.querySelectorAll('[data-action]')) button.disabled = submitting || !panelOnline;
  $('local-connect').disabled = submitting || !panelOnline || state.connection.status === 'connecting';
  $('local-connect').textContent = state.connection.status === 'connected' ? 'Reconnect local broker' : 'Connect local broker';
  $('start').disabled = submitting || !connected || state.running;
  $('pause').disabled = submitting || !panelOnline || !state.running;
  $('disconnect').disabled = submitting || !panelOnline || state.connection.status === 'disconnected';
  $('export').disabled = false;
  $('publish').disabled = submitting || !connected || !reporting;
  $('send-reading').disabled = submitting || !connected || !reporting;
  $('send-reading').textContent = operation === 'send' ? 'Sending…' : selected.length > 1 ? 'Send to ' + selected.length + ' bins' : 'Send reading';
  $('apply-reading').disabled = submitting || !panelOnline || !selected.length;
  $('reading-slider').disabled = submitting || !selected.length || (selected.length > 1 && $('unit').value === 'kg');
  $('reading').disabled = submitting || !selected.length;
  $('unit').disabled = submitting || !selected.length;
  for (const button of document.querySelectorAll('[data-percent]')) button.disabled = submitting || !selected.length;
  for (const id of ['hundred', 'reset']) $(id).disabled = submitting || !panelOnline || (id === 'hundred' && state.running);
  $('fleet-form').querySelector('[type=submit]').disabled = submitting || !panelOnline || state.running;
  for (const id of ['scenario-form', 'capacity-form']) $(id).querySelector('[type=submit]').disabled = submitting || !panelOnline || !selected.length;
  for (const id of ['silence', 'restore']) $(id).disabled = submitting || !panelOnline || !selected.length;
  $('send-help').textContent = !panelOnline ? 'Simulator connection lost. Wait for reconnection or reload.'
    : !connected ? 'Connect the broker above to send readings. You can preview values now.'
      : !selected.length ? 'Choose at least one bin.'
        : !reporting ? 'These bins are silent. Restore reporting in More bin controls before sending.'
          : selected.length > reporting ? reporting + ' reporting bins will send; silent bins will be skipped.'
            : 'Sends once to MQTT. Broker receipt appears in the activity log.';
}
function setDraftPercent(percent) {
  const selected = selection();
  if (!selected.length) return;
  if (selected.length === 1 && $('unit').value === 'kg') $('reading').value = +(selected[0].capacityKg * percent / 100).toFixed(3);
  else { $('unit').value = 'percent'; entryUnit = 'percent'; $('reading').value = percent; }
  draftStatus = 'Draft — not sent'; renderDraft(); renderControls();
}
async function sendReading(publish = true) {
  if (submitting) return;
  if (!$('reading-form').checkValidity()) { $('entry-options').open = true; $('reading-form').reportValidity(); return; }
  const scope = selector(), selected = selection();
  if (!selected.length) return message('Choose a bin or warehouse first.', true);
  if (publish && (!panelOnline || state.connection.status !== 'connected')) return message('Connect the broker before sending a reading.', true);
  if (publish && !selected.some(b => b.online)) return message('The selected bins are silent. Restore reporting before sending.', true);
  const patch = { mode: 'manual', [$('unit').value === 'kg' ? 'weightKg' : 'percent']: $('reading').valueAsNumber };
  submitting = true; operation = publish ? 'send' : 'update'; renderControls();
  let applied = false;
  try {
    await request('update', { selector: scope, patch }); applied = true;
    if (publish) await request('publish', { selector: scope });
    draftStatus = publish ? 'Sent to broker' : 'Applied locally';
    renderDraft();
    message(publish ? 'Reading sent for ' + selected.filter(b => b.online).length + ' reporting bin(s). Open the warehouse dashboard for the stored result.'
      : 'Reading applied locally. No immediate MQTT message was sent.');
  } catch (error) {
    draftStatus = applied ? 'Applied, not confirmed sent' : 'Draft — not sent';
    renderDraft();
    message((applied && publish ? 'The reading was applied locally, but sending failed: ' : '') + error.message, true);
  } finally { submitting = false; operation = ''; renderControls(); }
}
function render(next) {
  state = next;
  const key = next.bins.map(b => b.warehouseId + '/' + b.id).join(',');
  if (key !== fleetKey) {
    fleetKey = key; binOptions(); $('count').value = next.bins.length;
    if (!initializedSelection && next.bins.length) {
      $('warehouse').value = next.bins[0].warehouseId; binOptions(); $('bin').value = next.bins[0].id;
      initializedSelection = true; loadEditor();
    } else loadEditor();
  }
  $('connection').textContent = state.connection.status === 'connected' ? 'Ready to send' : 'MQTT ' + state.connection.status;
  $('connection').dataset.status = state.connection.status;
  $('connection-message').textContent = state.connection.message;
  $('run-status').textContent = state.running ? 'Automatic publishing is running for all reporting bins' : 'Automatic publishing paused';
  $('stats').textContent = state.bins.length + ' virtual bins · ' + state.bins.filter(b => b.online).length + ' reporting · ' + state.sent + ' broker acknowledgements · ' + state.failed + ' failed attempts';
  $('topic-example').textContent = state.config.prefix + '/warehouse-a/bin-001/weight';
  renderSelection(); renderDraft(); renderControls();
  const existing = new Map(Array.from($('bins').children, row => [row.dataset.binId, row])), visible = new Set();
  let rowIndex = 0;
  for (const b of state.bins.filter(b => !$('warehouse').value || b.warehouseId === $('warehouse').value)) {
    visible.add(b.id);
    let row = existing.get(b.id);
    if (!row) {
      row = document.createElement('tr'); row.dataset.binId = b.id;
      const identity = document.createElement('td');
      identity.append(text('p', b.id, 'font-semibold'), text('p', b.warehouseId.replace('warehouse-', 'Warehouse ').toUpperCase(), 'text-xs muted mt-1'));
      const weight = document.createElement('td');
      weight.append(text('p', '', 'tabular-nums'), text('p', '', 'text-xs muted mt-1'));
      const meter = text('div', '', 'bin-meter'); meter.setAttribute('aria-hidden', 'true'); meter.append(document.createElement('span')); weight.append(meter);
      const status = document.createElement('td'); status.append(text('p', ''), text('p', '', 'text-xs muted mt-1'));
      const control = document.createElement('td'), edit = text('button', 'Select', 'btn btn-sm');
      edit.setAttribute('aria-label', 'Control ' + b.id);
      edit.onclick = () => { $('bin').value = b.id; loadEditor(); render(state); $('reading-slider').focus(); if (window.matchMedia('(max-width: 1279px)').matches) $('controller').scrollIntoView({ block: 'start' }); };
      control.append(edit); row.append(identity, weight, status, control); $('bins').append(row);
    }
    if ($('bins').children[rowIndex] !== row) $('bins').insertBefore(row, $('bins').children[rowIndex] || null);
    rowIndex++;
    row.className = $('bin').value === b.id ? 'selected' : '';
    const weight = row.children[1], status = row.children[2], percent = b.weightKg / b.capacityKg * 100;
    weight.children[0].textContent = formatNumber(b.weightKg) + ' / ' + formatNumber(b.capacityKg) + ' kg';
    weight.children[1].textContent = percent.toFixed(1) + '% of capacity';
    const bar = weight.children[2].firstChild; bar.style.width = Math.min(100, percent) + '%'; bar.className = percent >= 85 ? 'high' : '';
    status.children[0].textContent = names[b.mode] + (b.online ? '' : ' / Silent');
    status.children[1].textContent = !b.online ? 'No messages sent' : b.lastPublishedAt ? 'Sent ' + new Date(b.lastPublishedAt).toLocaleTimeString() : 'Not sent yet';
  }
  for (const [id, row] of existing) if (!visible.has(id)) row.remove();
  $('empty-log').hidden = !!state.messages.length;
  const logs = document.createDocumentFragment();
  for (const item of state.messages) {
    const row = document.createElement('tr'), content = document.createElement('td');
    content.append(text('code', item.topic, 'block text-xs'), text('code', item.payload, 'block mt-1 text-xs'));
    row.append(text('td', new Date(item.timestamp).toLocaleTimeString(), 'tabular-nums whitespace-nowrap'), content, text('td', item.result)); logs.append(row);
  }
  $('messages').replaceChildren(logs);
}
const update = (patch, success) => act('update', { selector: selector(), patch }, success);
$('warehouse').onchange = () => { $('bin').value = ''; binOptions(); loadEditor(); render(state); };
$('bin').onchange = () => { loadEditor(); render(state); };
$('reading-slider').oninput = () => setDraftPercent(Number($('reading-slider').value));
$('reading').oninput = () => { draftStatus = 'Draft — not sent'; renderDraft(); };
$('unit').onchange = () => {
  const selected = selection(), nextUnit = $('unit').value, previous = $('reading').valueAsNumber;
  if (nextUnit === entryUnit) return;
  if (selected.length === 1 && Number.isFinite(previous)) $('reading').value = +(nextUnit === 'kg' ? previous * selected[0].capacityKg / 100 : previous / selected[0].capacityKg * 100).toFixed(3);
  else if (nextUnit !== entryUnit) { $('reading').value = nextUnit === 'percent' ? 50 : 0; draftStatus = 'Draft — not sent'; }
  entryUnit = nextUnit; renderDraft(); renderControls();
};
$('overload').onchange = () => { renderDraft(); renderControls(); };
for (const button of document.querySelectorAll('[data-percent]')) button.onclick = () => setDraftPercent(Number(button.dataset.percent));
$('reading-form').onsubmit = event => { event.preventDefault(); sendReading(); };
$('apply-reading').onclick = () => sendReading(false);
$('scenario-form').onsubmit = event => { event.preventDefault(); update({ mode: $('mode').value, rateKgPerMinute: Number($('rate').value) }, 'Scenario applied to the selection. Start auto-send to run it if paused.'); };
$('capacity-form').onsubmit = event => { event.preventDefault(); update({ capacityKg: Number($('capacity').value) }, 'Simulator capacity changed for the selection. Ontology and Ditto capacities were not changed.'); };
$('silence').onclick = () => update({ online: false }, 'Selected bins silenced. They will send no messages until reporting is restored.');
$('restore').onclick = () => update({ online: true }, 'Selected bins can report again.');
$('publish').onclick = () => act('publish', { selector: selector() });
$('start').onclick = () => act('start');
$('pause').onclick = () => act('pause');
$('disconnect').onclick = () => act('disconnect');
$('reset').onclick = () => act('reset');
$('fleet-form').onsubmit = event => { event.preventDefault(); act('generate', { count: Number($('count').value) }); };
$('hundred').onclick = () => act('generate', { count: 100 });
function connectionConfig(local = false) {
  return { brokerUrl: local ? state.localBrokerUrl : $('broker-url').value.trim(),
    username: local ? '' : $('username').value, password: local ? '' : $('password').value,
    prefix: $('prefix').value.trim(), format: $('format').value, intervalMs: Number($('interval').value) * 1000 };
}
$('local-connect').onclick = () => act('connect', { config: connectionConfig(true) });
$('broker-form').onsubmit = event => { event.preventDefault(); act('connect', { config: connectionConfig() }); };
$('export').onclick = () => {
  const blob = new Blob([JSON.stringify({ exportedAt: new Date().toISOString(), simulated: true, bins: state.bins }, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob), anchor = document.createElement('a');
  anchor.href = url; anchor.download = 'smartbin-fleet.json'; anchor.click(); URL.revokeObjectURL(url);
};
async function initialize() {
  for (const control of document.querySelectorAll('[data-action], [data-percent], #export, #send-reading, #reading-slider, #reading, #unit')) control.disabled = true;
  try {
    const result = await fetch('/api/state'); if (!result.ok) throw new Error('Simulator unavailable.');
    panelOnline = true; render(await result.json());
    $('broker-url').value = state.config.brokerUrl; $('prefix').value = state.config.prefix;
    $('interval').value = state.config.intervalMs / 1000; $('format').value = state.config.format;
    message(state.connection.status === 'connected' ? 'Ready. Choose a weight and send a reading.' : 'Connect the local broker, then choose a weight.');
    const stream = new EventSource('/api/events');
    stream.onmessage = event => { panelOnline = true; render(JSON.parse(event.data)); };
    stream.onerror = () => { panelOnline = false; message('Simulator connection lost. Reconnecting…', true); renderControls(); };
    stream.onopen = () => { panelOnline = true; renderControls(); if ($('feedback').dataset.error === 'true' && $('feedback').textContent.startsWith('Simulator connection')) message('Simulator reconnected.'); };
  } catch (error) { panelOnline = false; message(error.message + ' Start the simulator and reload this page.', true); if (state) renderControls(); }
}
initialize();
