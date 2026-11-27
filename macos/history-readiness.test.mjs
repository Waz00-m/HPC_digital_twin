import test from 'node:test';
import assert from 'node:assert/strict';
import { assertHistoryReady } from './history-readiness.mjs';

const now = Date.parse('2026-11-27T12:00:00Z');
const healthy = { connected: true, sample_seconds: 30, last_sample_error: null, last_sampled_at: '2026-11-27T11:59:45Z' };

test('readiness requires a connected collector and a fresh successful timed sample', () => {
  assert.doesNotThrow(() => assertHistoryReady({ collector: healthy }, now));
  assert.throws(() => assertHistoryReady({ collector: { ...healthy, last_sampled_at: null } }, now), /first successful timed/);
  assert.throws(() => assertHistoryReady({ collector: { ...healthy, last_sampled_at: '2026-11-27T11:50:00Z' } }, now), /stale/);
  assert.throws(() => assertHistoryReady({ collector: { ...healthy, last_sample_error: 'database is locked' } }, now), /database is locked/);
});

test('the underlying stream and sampling errors survive the startup check', () => {
  assert.throws(() => assertHistoryReady({ collector: { ...healthy, connected: false,
    last_error: 'Connection refused', last_sample_error: 'Ditto HTTP 401' } }, now), error =>
    error.message.includes('Connection refused') && error.message.includes('Ditto HTTP 401'));
  assert.throws(() => assertHistoryReady({ collector: null }, now), /collection is disabled/);
  assert.throws(() => assertHistoryReady({ collector: { connected: true } }, now), /predates timed sampling/);
});

test('a deliberately slow sampling interval has its own readiness age budget', () => {
  assert.doesNotThrow(() => assertHistoryReady({ collector: { ...healthy, sample_seconds: 3600,
    last_sampled_at: '2026-11-27T11:30:00Z' } }, now));
});
