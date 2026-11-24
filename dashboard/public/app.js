const $ = id => document.getElementById(id);
const number = value => Number.isFinite(value) ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
const labels = { normal: 'Normal', attention: 'Needs attention', 'over-capacity': 'Over capacity',
  unconfigured: 'No alert configured', 'awaiting-reading': 'Awaiting reading', 'invalid-model': 'Check model', 'identity-mismatch': 'Check identity' };
const colors = { normal: 'badge-success', attention: 'badge-warning', 'over-capacity': 'badge-error' };
let fleet, selectedWarehouse = '', selectedBin = null, boardKey = '', filterKey = '', refreshing = false;

function el(tag, text = '', className = '') {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
}
function setText(node, text) { if (node.textContent !== text) node.textContent = text; }
function time(value) { return value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleTimeString() : 'No reading yet'; }
function warehouseName(id) { return fleet?.warehouses.find(w => w.id === id)?.name || id; }
function matchesStatus(bin) {
  const status = $('status-filter').value;
  return !status || (status === 'other' ? !['normal', 'attention', 'over-capacity', 'awaiting-reading'].includes(bin.status) : bin.status === status);
}
async function api(path, body) {
  const response = await fetch(path, { signal: AbortSignal.timeout(35000), ...(body ? {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
  } : {}) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The dashboard could not complete the request.');
  return result;
}
function renderFilters() {
  const key = fleet.warehouses.map(w => w.id + w.name).join(',');
  if (filterKey !== key) {
    filterKey = key;
    const items = [{ id: '', name: 'All warehouses' }, ...fleet.warehouses];
    $('warehouse-filters').replaceChildren(...items.map(item => {
      const button = el('button', '', 'warehouse-filter'); button.type = 'button'; button.dataset.warehouse = item.id;
      button.append(el('span', item.name), el('span', '', 'tabular-nums text-sm'));
      button.onclick = () => { selectedWarehouse = item.id; renderOverview(); };
      return button;
    }));
    const previous = $('scenario-warehouse').value;
    $('scenario-warehouse').replaceChildren(new Option('All warehouses', ''), ...fleet.warehouses.map(w => new Option(w.name, w.id)));
    $('scenario-warehouse').value = previous;
    $('warehouse-select').replaceChildren(new Option('All warehouses', ''), ...fleet.warehouses.map(w => new Option(w.name, w.id)));
  }
  $('warehouse-select').value = selectedWarehouse;
  for (const button of $('warehouse-filters').children) {
    button.setAttribute('aria-pressed', String(button.dataset.warehouse === selectedWarehouse));
    setText(button.children[1], String(fleet.bins.filter(b => !button.dataset.warehouse || b.warehouseId === button.dataset.warehouse).length));
  }
}
function renderOverview() {
  if (!fleet) return;
  renderFilters();
  const readings = fleet.bins.filter(b => b.hasReading).length;
  const counts = ['normal', 'attention', 'over-capacity'].map(status => fleet.bins.filter(b => b.status === status).length);
  const summary = [readings + ' / ' + fleet.bins.length + ' readings received', counts[0] + ' normal', counts[1] + ' need attention', counts[2] + ' over capacity'];
  const issues = fleet.bins.length - counts.reduce((a, b) => a + b, 0);
  if (issues) summary.push(issues + ' awaiting reading or configuration');
  const summaryText = summary.join(' · ');
  if ($('fleet-summary').dataset.summary !== summaryText) {
    $('fleet-summary').replaceChildren(...summary.map(item => el('span', item))); $('fleet-summary').dataset.summary = summaryText;
  }
  const transport = fleet.transport;
  const status = transport?.status;
  const connected = transport?.available && status.liveStatus === 'open' &&
    status.clientStatus?.some(client => client.status === 'open') && status.sourceStatus?.every(source => source.status === 'open');
  $('transport-status').textContent = connected ? 'Native MQTT connected' : transport?.available ? 'Native MQTT ' + (status.liveStatus || status.connectionStatus || 'unknown') : 'MQTT status unavailable';
  $('read-time').textContent = 'Read from Ditto ' + time(fleet.readAt);
  const groups = fleet.warehouses.filter(w => !selectedWarehouse || w.id === selectedWarehouse).map(w => ({
    ...w, bins: fleet.bins.filter(b => b.warehouseId === w.id && matchesStatus(b))
  })).filter(w => w.bins.length);
  if (selectedBin && !groups.some(w => w.bins.some(bin => bin.id === selectedBin))) selectedBin = null;
  const key = groups.map(w => w.id + ':' + w.bins.map(b => b.id).join(',')).join('|');
  if (key !== boardKey || !$('warehouse-board').children.length) {
    boardKey = key;
    $('warehouse-board').replaceChildren(...groups.map(w => {
      const section = el('section', '', 'warehouse-section'); section.dataset.warehouse = w.id;
      const heading = el('div', '', 'warehouse-heading'); const title = el('h2', w.name); title.id = 'heading-' + w.id; section.setAttribute('aria-labelledby', title.id);
      heading.append(title, el('p', '', 'muted tabular-nums')); section.append(heading);
      const grid = el('div', '', 'bin-grid');
      for (const bin of w.bins) {
        const button = el('button', '', 'bin-record'); button.type = 'button'; button.dataset.bin = bin.id; button.setAttribute('aria-controls', 'bin-detail');
        const top = el('div', '', 'bin-top'); top.append(el('strong', bin.id), el('span', '', 'badge'));
        const weight = el('p', '', 'bin-weight');
        const meter = el('div', '', 'capacity-meter'); meter.setAttribute('aria-hidden', 'true'); meter.append(el('div', '', 'fill'), el('span', '', 'threshold'));
        button.append(top, weight, meter, el('p', '', 'text-sm'), el('p', '', 'bin-receipt muted'));
        button.onclick = () => { selectedBin = bin.id; renderOverview(); $('bin-detail').scrollIntoView({ block: 'nearest', behavior: 'smooth' }); $('close-detail').focus({ preventScroll: true }); };
        grid.append(button);
      }
      section.append(grid); return section;
    }));
  }
  for (const group of groups) {
    const section = [...$('warehouse-board').children].find(node => node.dataset.warehouse === group.id);
    const all = fleet.bins.filter(b => b.warehouseId === group.id), valid = all.filter(b => b.hasReading);
    const total = valid.reduce((sum, b) => sum + b.weightKg, 0), capacity = all.reduce((sum, b) => sum + (Number.isFinite(b.capacityKg) ? b.capacityKg : 0), 0);
    section.querySelector('.warehouse-heading p').textContent = valid.length === all.length ? number(total) + ' / ' + number(capacity) + ' kg total' : valid.length + ' / ' + all.length + ' readings available';
    for (const button of section.querySelectorAll('.bin-record')) {
      const bin = group.bins.find(b => b.id === button.dataset.bin);
      button.dataset.status = bin.status; button.setAttribute('aria-expanded', String(selectedBin === bin.id));
      button.setAttribute('aria-label', 'Inspect ' + bin.id + ', ' + (bin.hasReading ? number(bin.weightKg) + ' kilograms, ' : '') + labels[bin.status]);
      const badge = button.querySelector('.badge'); badge.textContent = labels[bin.status] || 'Unknown'; badge.className = 'badge ' + (colors[bin.status] || 'badge-ghost');
      const weight = button.querySelector('.bin-weight');
      weight.replaceChildren(document.createTextNode(bin.hasReading ? number(bin.weightKg) + ' ' : '— '), el('small', ' / ' + number(bin.capacityKg) + ' kg'));
      button.querySelector('.fill').style.width = (bin.hasReading ? Math.max(0, Math.min(100, bin.weightPercent)) : 0) + '%';
      const tick = button.querySelector('.threshold'); tick.hidden = !Number.isFinite(bin.alertThresholdPercent); tick.style.left = (bin.alertThresholdPercent || 0) + '%';
      button.children[3].textContent = bin.hasReading ? number(bin.weightPercent) + '% of rated weight' : bin.error || 'Send an initial reading';
      button.children[4].textContent = 'Last received ' + time(bin.receivedAt);
    }
  }
  $('empty-state').hidden = groups.length > 0;
  $('empty-state').textContent = fleet.bins.length ? 'No bins match these filters.' : 'No SmartBin records found in Ditto. Import the ontology to get started.';
  renderDetail();
}
function renderDetail() {
  const bin = fleet?.bins.find(b => b.id === selectedBin);
  $('bin-detail').hidden = !bin;
  if (!bin) return;
  $('detail-title').textContent = bin.id + ' · ' + warehouseName(bin.warehouseId);
  const entries = [
    ['Current received weight', bin.hasReading ? number(bin.weightKg) + ' kg' : 'Awaiting valid reading'],
    ['Weight status', labels[bin.status] || bin.status],
    ['Model capacity', number(bin.capacityKg) + ' kg'],
    ['Alert threshold', Number.isFinite(bin.alertThresholdPercent) ? number(bin.capacityKg * bin.alertThresholdPercent / 100) + ' kg (' + number(bin.alertThresholdPercent) + '%)' : 'Not configured'],
    ['Last reading received', bin.receivedAt ? new Date(bin.receivedAt).toLocaleString() : 'None'],
    ['Reading source', bin.source || 'None'],
    ['Ditto Thing ID', bin.thingId], ['MQTT topic', bin.mqttTopic || 'Not configured'],
    ['Ontology individual', bin.ontologyIndividualIri || 'Not mapped'],
    ['Calculation', 'Current raw weight ÷ imported capacity × 100. Status uses the current imported threshold.']
  ];
  const list = el('dl', '', 'detail-list');
  for (const [label, value] of entries) { const group = el('div'); group.append(el('dt', label), el('dd', value)); list.append(group); }
  $('detail-body').replaceChildren(list);
}
async function refresh() {
  if (refreshing) return; refreshing = true; $('refresh').disabled = true;
  try {
    fleet = await api('/api/fleet'); $('connection-error').hidden = true; renderOverview(); window.syncScenarioFleet?.(fleet);
  } catch (error) {
    $('connection-error').hidden = false;
    $('connection-error').textContent = (fleet ? 'Connection lost. Showing last known values. ' : 'Ditto is unavailable. ') + error.message;
    $('transport-status').textContent = 'Readback unavailable';
  } finally { refreshing = false; $('refresh').disabled = false; }
}
$('refresh').onclick = refresh;
$('status-filter').onchange = renderOverview;
$('warehouse-select').onchange = () => { selectedWarehouse = $('warehouse-select').value; renderOverview(); };
$('close-detail').onclick = () => {
  const previous = selectedBin; selectedBin = null; renderOverview();
  [...document.querySelectorAll('.bin-record')].find(button => button.dataset.bin === previous)?.focus();
};
function route() {
  const scenario = location.hash === '#scenarios';
  $('scenario-page').hidden = !scenario; $('overview-page').hidden = scenario;
  $('overview-link').toggleAttribute('aria-current', !scenario); $('scenario-link').toggleAttribute('aria-current', scenario);
  if (scenario) { $('scenario-link').setAttribute('aria-current', 'page'); window.initializeScenarios?.(); }
  else $('overview-link').setAttribute('aria-current', 'page');
}
window.addEventListener('hashchange', route);
route(); void refresh();
setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
