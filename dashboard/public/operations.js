(() => {
  const settings = new Map();
  let currentFleet, lastResult, busy = false, formKey = '', initialized = false;
  const selectedBins = () => currentFleet?.bins.filter(bin => !$('scenario-warehouse').value || bin.warehouseId === $('scenario-warehouse').value) || [];
  function message(text, error = false) { $('scenario-feedback').textContent = text; $('scenario-feedback').dataset.error = error; }
  function stale() { if (lastResult) $('result-stale').hidden = false; }
  function remember() {
    for (const row of $('bin-configs').children) {
      const value = settings.get(row.dataset.bin);
      for (const input of row.querySelectorAll('[data-field]')) value[input.dataset.field] = input.tagName === 'SELECT' ? input.value : input.valueAsNumber;
    }
  }
  function inputField(bin, key, title, options = null) {
    const label = el('label', title, 'field');
    const control = document.createElement(options ? 'select' : 'input');
    control.className = options ? 'select' : 'input'; control.dataset.field = key;
    control.id = 'setting-' + bin.id + '-' + key;
    if (options) for (const [value, text] of options) control.append(new Option(text, value));
    else {
      control.type = 'number'; control.required = true;
      control.min = key === 'rateKgPerMinute' ? '0' : key === 'serviceMinutes' ? '0.25' : '1';
      control.max = key === 'rateKgPerMinute' ? '10000' : key === 'serviceMinutes' ? '60' : '99';
      control.step = key === 'alertPercent' ? '1' : key === 'serviceMinutes' ? '0.25' : '0.001';
    }
    control.value = settings.get(bin.id)[key]; label.append(control);
    control.setAttribute('aria-label', bin.id + ' ' + title);
    if (key === 'mode') control.onchange = () => {
      const row = control.closest('[data-bin]'); row.querySelector('[data-field="alertPercent"]').value = control.value === 'inventory' ? 20 : (bin.alertThresholdPercent || 85);
      remember(); stale();
    };
    return label;
  }
  function renderSettings(force = false) {
    const bins = selectedBins(), key = bins.map(b => b.id).join('|');
    if (!force && key === formKey) return;
    remember(); formKey = key;
    $('bin-config-count').textContent = '· ' + bins.length;
    $('bin-configs').replaceChildren(...bins.map(bin => {
      const row = el('fieldset', '', 'bin-assumption'); row.dataset.bin = bin.id;
      row.append(el('legend', bin.id + ' · ' + warehouseName(bin.warehouseId) + ' · ' + number(bin.capacityKg) + ' kg'));
      const grid = el('div', '', 'bin-assumption-fields');
      grid.append(inputField(bin, 'mode', 'Purpose', [['collection', 'Collection'], ['inventory', 'Inventory']]),
        inputField(bin, 'rateKgPerMinute', 'Demand (kg/min)'), inputField(bin, 'alertPercent', 'Alert (%)'), inputField(bin, 'serviceMinutes', 'Service (min)'));
      row.append(grid); return row;
    }));
    $('preview').disabled = !bins.length || busy; $('save-draft').disabled = !bins.length || busy;
  }
  window.syncScenarioFleet = value => {
    currentFleet = value;
    value.bins.forEach((bin, index) => {
      if (!settings.has(bin.id)) settings.set(bin.id, { id: bin.id, mode: index % 2 ? 'inventory' : 'collection',
        rateKgPerMinute: Number(((bin.capacityKg || 10) * [0.015, 0.012, 0.018, 0.02, 0.01][index % 5]).toFixed(3)),
        alertPercent: index % 2 ? 20 : (bin.alertThresholdPercent || 85), serviceMinutes: 2 });
    });
    renderSettings();
    if (!initialized && !busy) { message(value.bins.length ? 'Ready. Review the demo assumptions, then compare strategies. No live bins will change.' : 'Import the nine-bin ontology into Ditto, then refresh.'); initialized = true; }
  };
  function config() {
    remember();
    return { kind: 'operations', name: $('scenario-name').value, warehouseId: $('scenario-warehouse').value || null,
      horizonMinutes: $('scenario-horizon').valueAsNumber, delayMinutes: $('scenario-delay').valueAsNumber,
      travelMinutes: $('scenario-travel').valueAsNumber, localTravelMinutes: $('scenario-local').valueAsNumber,
      variabilityPercent: $('scenario-variation').valueAsNumber, runs: $('scenario-runs').valueAsNumber, seed: $('scenario-seed').valueAsNumber,
      burst: $('scenario-pattern').value === 'burst' ? { startMinute: $('burst-start').valueAsNumber, durationMinutes: $('burst-duration').valueAsNumber, multiplier: 2 } : null,
      bins: selectedBins().map(bin => ({ ...settings.get(bin.id) })) };
  }
  function fillDraft(draft) {
    if (!currentFleet) return message('Wait for Ditto to load before opening a draft.', true);
    remember();
    const value = draft.config;
    $('scenario-name').value = value.name; $('scenario-warehouse').value = value.warehouseId || '';
    if ($('scenario-warehouse').value !== (value.warehouseId || '')) return message('This draft’s warehouse is absent. Import its model before loading it.', true);
    if (value.kind === 'operations') {
      const map = { horizon: 'horizonMinutes', delay: 'delayMinutes', travel: 'travelMinutes', local: 'localTravelMinutes', variation: 'variabilityPercent', runs: 'runs', seed: 'seed' };
      for (const [id, key] of Object.entries(map)) $('scenario-' + id).value = value[key];
      $('scenario-pattern').value = value.burst ? 'burst' : 'steady';
      $('burst-start').value = value.burst?.startMinute ?? 20; $('burst-duration').value = value.burst?.durationMinutes ?? 10;
      for (const bin of value.bins) settings.set(bin.id, { ...bin });
      message('Loaded “' + value.name + '”. Compare to use a fresh Ditto snapshot.');
    } else {
      // Keep old drafts usable, but make the change of model explicit.
      $('scenario-horizon').value = Math.max(5, Math.min(240, value.horizonMinutes));
      for (const bin of selectedBins()) settings.set(bin.id, { id: bin.id, mode: value.rateKgPerMinute < 0 ? 'inventory' : 'collection',
        rateKgPerMinute: Math.abs(value.rateKgPerMinute), alertPercent: value.rateKgPerMinute < 0 ? 20 : (bin.alertThresholdPercent || 85), serviceMinutes: 2 });
      $('scenario-pattern').value = 'steady';
      message('Converted the old linear draft to team simulation assumptions. Review purposes and rates; its single emptying event is replaced by team service.');
    }
    // The form currently shows previous values: rebuild without remembering them again.
    $('bin-configs').replaceChildren(); formKey = ''; renderSettings(true); updatePattern(); stale();
  }
  async function loadDrafts() {
    try {
      const result = await api('/api/scenarios');
      $('saved-drafts').replaceChildren(...(result.scenarios.length ? result.scenarios.map(draft => {
        const button = el('button', '', 'draft-button'); button.type = 'button';
        button.append(el('p', draft.config.name, 'font-semibold text-sm'), el('p', number(draft.config.horizonMinutes) + ' min · ' + (draft.config.kind === 'operations' ? 'Team simulation' : 'Legacy linear draft'), 'text-sm muted mt-1'));
        button.onclick = () => { if (!busy) fillDraft(draft); }; return button;
      }) : [el('p', 'No drafts saved yet.', 'text-sm muted')]));
    } catch (error) { $('saved-drafts').replaceChildren(el('p', error.message, 'text-sm')); }
  }
  function svgNode(tag, attributes, text = '') {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    node.textContent = text; return node;
  }
  function drawChart() {
    if (!lastResult || $('scenario-page').hidden) return;
    const series = lastResult.comparisons, maximum = Math.max(1, ...series.flatMap(p => p.baseline.samples.map(s => s.overflowKg + s.unmetKg)));
    const width = Math.max(180, $('forecast-chart').clientWidth), height = 280, left = 48, right = 14, top = 15, bottom = 45;
    const x = t => left + t / lastResult.scenario.horizonMinutes * (width - left - right), y = n => height - bottom - n / maximum * (height - top - bottom);
    const svg = svgNode('svg', { viewBox: '0 0 ' + width + ' ' + height, role: 'img', 'aria-label': 'Cumulative lost kilograms by strategy. Exact totals are in the comparison table.' });
    for (let i = 0; i <= 4; i++) {
      const n = maximum * i / 4, t = lastResult.scenario.horizonMinutes * i / 4;
      svg.append(svgNode('line', { x1: left, x2: width - right, y1: y(n), y2: y(n), stroke: 'var(--color-base-300)' }),
        svgNode('text', { x: left - 8, y: y(n) + 5, 'text-anchor': 'end', 'font-size': 14, fill: 'currentColor' }, new Intl.NumberFormat(undefined, { maximumFractionDigits: 1, notation: 'compact' }).format(n)),
        svgNode('text', { x: x(t), y: height - 20, 'text-anchor': 'middle', 'font-size': 14, fill: 'currentColor' }, number(t)));
    }
    svg.append(svgNode('text', { x: width / 2, y: height - 1, 'text-anchor': 'middle', 'font-size': 14, fill: 'currentColor' }, 'Minutes from snapshot'));
    const palette = ['var(--color-neutral)', 'var(--color-secondary)', 'var(--color-primary)'];
    const legend = series.map((item, index) => {
      svg.append(svgNode('path', { d: item.baseline.samples.map((s, i) => (i ? 'L' : 'M') + x(s.minute).toFixed(2) + ',' + y(s.overflowKg + s.unmetKg).toFixed(2)).join(' '), fill: 'none', stroke: palette[index], 'stroke-width': 2.5, 'stroke-dasharray': index === 0 ? '6 3' : index === 1 ? '2 3' : 'none' }));
      const span = el('span'), swatch = el('span', '', 'chart-key'); swatch.style.background = palette[index];
      span.append(swatch, document.createTextNode(item.name)); return span;
    });
    $('forecast-chart').replaceChildren(svg); $('chart-legend').replaceChildren(...legend);
  }
  function tableRow(values) { const row = el('tr'); values.forEach((value, i) => row.append(el(i ? 'td' : 'th', value))); return row; }
  function renderSchedule() {
    if (!lastResult) return;
    const run = lastResult.comparisons.find(p => p.id === $('result-policy').value).baseline;
    const list = el('ol');
    for (const job of run.jobs) {
      const item = el('li'), action = job.mode === 'collection' ? 'Empty' : 'Replenish';
      item.append(el('strong', number(job.departAt) + '–' + number(Math.min(job.completeAt, lastResult.scenario.horizonMinutes)) + ' min · ' + action + ' ' + job.binId),
        el('p', warehouseName(job.warehouseId) + ' · ' + number(job.travelMinutes) + ' min travel + ' + number(job.serviceMinutes) + ' min service · ' + (job.completed ? 'Completed at ' + number(job.completeAt) + ' min' : 'Still in progress at scenario end'), 'text-sm muted mt-1'));
      list.append(item);
    }
    $('team-schedule').replaceChildren(run.jobs.length ? list : el('p', 'No service was dispatched within this duration.', 'text-sm muted'));
    $('forecast-rows').replaceChildren(...run.bins.map(bin => {
      const initial = lastResult.model.find(b => b.id === bin.id);
      return tableRow([bin.id + ' · ' + bin.mode, number(initial.initialWeightKg) + ' → ' + number(bin.weightKg) + ' kg', bin.firstLossAt === null ? 'None in this run' : number(bin.firstLossAt) + ' min', number(bin.overflowKg + bin.unmetKg), String(bin.services)]);
    }));
  }
  function renderResult(result) {
    lastResult = result; $('preview-empty').hidden = true; $('preview-output').hidden = false; $('result-stale').hidden = true;
    $('preview-context').textContent = result.model.length + ' bins · ' + number(result.scenario.horizonMinutes) + ' minutes · Ditto snapshot ' + new Date(result.startingReadAt).toLocaleString();
    const job = result.recommendation;
    if (job) {
      $('next-decision').replaceChildren(el('p', (job.mode === 'collection' ? 'Empty ' : 'Replenish ') + job.binId + ' in ' + warehouseName(job.warehouseId), 'decision-title'),
        el('p', 'Dispatch at ' + number(job.departAt) + ' min · arrive ' + number(job.arriveAt) + ' min · finish ' + number(job.completeAt) + ' min.', 'text-sm mt-2'),
        el('p', 'At dispatch: ' + number(job.percent) + '% of capacity, ' + number(job.rateKgPerMinute) + ' kg/min ' + (job.mode === 'collection' ? 'arriving' : 'being consumed') + '. ' + (job.deadlineIn === null ? 'No current demand deadline.' : 'Full/empty in ' + number(job.deadlineIn) + ' min at that rate; travel + service needs ' + number(job.completionIn) + ' min. Safety margin: ' + number(job.slackMinutes) + ' min. Negative means the team cannot finish before loss begins.'), 'text-sm muted mt-3'));
    } else $('next-decision').replaceChildren(el('p', 'No service is due within this scenario. Increase demand or duration to test the queue.', 'mt-3'));
    if (job) {
      const margins = result.ranking.filter(bin => bin.useful && bin.slackMinutes !== null).slice(0, 3);
      $('next-decision').append(el('p', 'The rule selects the smallest safety margin among eligible bins. Snapshot margins: ' + margins.map(bin => bin.binId + ' ' + number(bin.slackMinutes) + ' min').join('; ') + '.', 'text-sm mt-3'));
      if (!job.completed) $('next-decision').append(el('p', 'This job finishes after the scenario ends; no completed service is counted for it.', 'text-sm mt-2'));
    }
    const base = result.comparisons.find(p => p.id === 'deadline').baseline, delayed = result.delayed;
    const delta = result.delayImpact.lossKg;
    $('delay-result').replaceChildren(el('p', 'Start the same rule ' + number(result.scenario.delayMinutes) + ' minutes later: ' + number(delayed.lossKg) + ' kg lost, compared with ' + number(base.lossKg) + ' kg starting immediately.', 'mt-3'),
      el('p', (Math.abs(delta) < 0.005 ? 'No material change in total lost kg.' : number(Math.abs(delta)) + ' kg ' + (delta > 0 ? 'more' : 'less') + ' lost in the delayed run.') + ' Collection overflow: ' + number(delayed.overflowKg) + ' kg; unmet inventory demand: ' + number(delayed.unmetKg) + ' kg. This re-runs the whole queue with identical nominal demand.', 'text-sm muted mt-2'));
    $('comparison-rows').replaceChildren(...result.comparisons.map(p => tableRow([p.name, number(p.baseline.overflowKg) + ' kg', number(p.baseline.unmetKg) + ' kg', String(p.baseline.binsWithLoss), String(p.baseline.completedServices), number(p.baseline.busyPercent) + '%'])));
    const best = Math.min(...result.comparisons.map(p => p.baseline.lossKg));
    $('comparison-insight').textContent = 'Lowest total lost kg in this nominal run: ' + result.comparisons.filter(p => Math.abs(p.baseline.lossKg - best) < 0.005).map(p => p.name).join(' / ') + '. No strategy is guaranteed to win every workload.';
    $('trial-context').textContent = result.scenario.runs + ' synthetic trials, seed ' + result.scenario.seed + ', demand varies ±' + number(result.scenario.variabilityPercent) + '% each minute. Same workload per strategy per trial. Counts are demo outcomes, not real-world failure probabilities.';
    $('trial-rows').replaceChildren(...result.comparisons.map(p => tableRow([p.name, p.trials.withLoss + ' / ' + p.trials.count, number(p.trials.meanLossKg) + ' kg', number(p.trials.p90LossKg) + ' kg'])));
    const assumptions = [...result.assumptions];
    if (result.initialExcessKg > 0) assumptions.unshift('The snapshot already exceeds rated capacity by ' + number(result.initialExcessKg) + ' kg. That pre-existing excess is removed before this run; it is not counted as new overflow.');
    $('preview-assumptions').replaceChildren(...assumptions.map(text => el('li', text)));
    if (result.initialExcessKg > 0) $('preview-context').textContent += ' · ' + number(result.initialExcessKg) + ' kg pre-existing excess removed (see assumptions)';
    renderSchedule(); drawChart(); $('view-results').hidden = false;
  }
  async function action(save) {
    if (busy || !$('scenario-form').reportValidity()) return;
    busy = true; const input = config();
    const controls = [...$('scenario-form').querySelectorAll('input, select, button')]; controls.forEach(c => c.disabled = true);
    $('preview').textContent = save ? 'Compare strategies' : 'Comparing…';
    message(save ? 'Saving local assumptions…' : 'Comparing three strategies and synthetic trials from a Ditto snapshot…');
    try {
      const result = await api(save ? '/api/scenarios' : '/api/simulation/preview', input);
      if (save) { message('Draft saved locally.'); await loadDrafts(); }
      else { renderResult(result); message('Comparison ready. No MQTT sent; live Ditto Things unchanged.'); if (innerWidth <= 800) showResults(); }
    } catch (error) {
      message(error.message, true);
      if (/burst/i.test(error.message)) $('scenario-pattern').closest('details').open = true;
      if (/bin-/.test(error.message)) $('bin-configs').closest('details').open = true;
    }
    finally { busy = false; controls.forEach(c => c.disabled = false); $('preview').textContent = 'Compare strategies'; updatePattern(); }
  }
  function updatePattern() { $('burst-start').disabled = $('burst-duration').disabled = $('scenario-pattern').value === 'steady'; }
  function showResults() { $('forecast-title').scrollIntoView({ block: 'start' }); $('forecast-title').focus({ preventScroll: true }); }
  $('scenario-form').addEventListener('input', stale);
  $('scenario-form').addEventListener('invalid', event => { let parent = event.target.parentElement; while (parent) { if (parent.tagName === 'DETAILS') parent.open = true; parent = parent.parentElement; } }, true);
  $('scenario-warehouse').onchange = () => { renderSettings(); stale(); };
  $('scenario-pattern').onchange = updatePattern;
  $('scenario-form').onsubmit = event => { event.preventDefault(); void action(false); };
  $('save-draft').onclick = () => action(true);
  $('result-policy').onchange = renderSchedule;
  $('view-results').onclick = showResults;
  window.addEventListener('resize', drawChart);
  window.initializeScenarios = () => { void loadDrafts(); drawChart(); };
  $('preview').disabled = $('save-draft').disabled = true;
  if (fleet) window.syncScenarioFleet(fleet);
  if (location.hash === '#scenarios') window.initializeScenarios();
})();
