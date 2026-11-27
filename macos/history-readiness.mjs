export function assertHistoryReady(health, now = Date.now()) {
  const collector = health.collector;
  if (!collector) throw new Error('History collection is disabled. Run bash macos/setup.sh to restore the configured history service.');
  if (!collector.connected) {
    const reason = collector.last_error || 'The Ditto event stream is still starting.';
    const sampling = collector.last_sample_error ? ` Timed sampling error: ${collector.last_sample_error}` : '';
    throw new Error(`History collector has not connected to Ditto: ${reason}${sampling}`);
  }
  if (collector.sample_seconds === undefined) {
    throw new Error('The installed history image predates timed sampling. Run bash macos/setup.sh to build the current image.');
  }
  if (collector.last_sample_error) throw new Error(`History timed sampling failed: ${collector.last_sample_error}`);
  const sampled = Date.parse(collector.last_sampled_at || '');
  if (!Number.isFinite(sampled)) throw new Error('Waiting for the first successful timed Ditto sample.');
  const maxAge = Math.max(90, Number(collector.sample_seconds) * 2 + 30) * 1000;
  if (now - sampled > maxAge) throw new Error(`History timed sampling is stale; last successful sample: ${collector.last_sampled_at}`);
}
