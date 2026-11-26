from __future__ import annotations

import threading
import time

from .ditto import bounded_lines, sse_messages
from .store import utc_now


class Collector:
    def __init__(self, store, client, reconcile_seconds=30, sample_seconds=30):
        if not 1 <= reconcile_seconds <= 3600:
            raise ValueError("Reconciliation interval must be 1–3,600 seconds.")
        self.store, self.client = store, client
        store.bind_source(client.origin, client.namespace)
        self.reconcile_seconds = reconcile_seconds
        if not isinstance(sample_seconds, int) or isinstance(sample_seconds, bool) or not 1 <= sample_seconds <= 3600:
            raise ValueError("Sample interval must be 1–3,600 whole seconds.")
        self.sample_seconds = sample_seconds
        self._lock = threading.Lock()
        self._state = {"connected": False, "last_event_at": None, "last_reconciled_at": None, "last_error": None,
                       "sample_seconds": sample_seconds, "last_sampled_at": None, "last_sample_error": None,
                       "capture": "Ditto SSE revisions plus independently timed HTTP samples, including unchanged values. reading_at remains the original reading time; gaps are not backfilled."}

    def status(self):
        with self._lock:
            return dict(self._state)

    def _set(self, **changes):
        with self._lock:
            self._state.update(changes)

    def reconcile(self):
        things = self.client.things()
        inserted = sum(self.store.insert_snapshot(thing)["inserted"] for thing in things)
        self._set(last_reconciled_at=utc_now())
        return {"read": len(things), "inserted": inserted}

    def handle(self, event):
        thing_id = event.get("thingId")
        if not isinstance(thing_id, str) or not thing_id.startswith(self.client.namespace + ":"):
            raise ValueError("Notification is outside the configured Thing namespace.")
        self.store.insert_event(event)
        context = event.get("_context") or {}
        if context.get("path") in ("", "/") and context.get("topic", "").endswith("/deleted"):
            raw_revision = event.get("_revision") or context.get("headers", {}).get("entity-revision")
            revision = int(raw_revision) if str(raw_revision).isdigit() else None
            self.store.mark_deleted(thing_id, revision)
        else:
            # A notification may contain only a changed property. Always GET a complete
            # version; preserve the original notification separately to avoid claiming
            # that this later HTTP observation is the exact state at the event revision.
            thing = self.client.thing(thing_id)
            self.store.insert_snapshot(thing)
        self._set(last_event_at=utc_now(), last_error=None)

    def sample_once(self):
        # Fetch from Ditto now; never relabel a locally cached value as a new GET.
        result = self.store.record_samples(self.client.things())
        self._set(last_sampled_at=result["sampled_at"], last_sample_error=None)
        return result

    def _sample_loop(self, stop):
        while not stop.is_set():
            started = time.monotonic()
            try:
                self.sample_once()
            except Exception as error:
                self._set(last_sample_error=str(error))
                try:
                    self.store.log("sample-gap", {"error": str(error), "sample_seconds": self.sample_seconds,
                        "meaning": "No timed samples were fabricated for this failed Ditto GET. Stored revision history remains available."})
                except Exception as log_error:
                    self._set(last_sample_error=str(error) + "; could not save gap notice: " + str(log_error))
            # Never overlap polls or fabricate missed intervals when a GET is slow.
            stop.wait(max(0.1, self.sample_seconds - (time.monotonic() - started)))

    def run(self, stop):
        sampling_stop = threading.Event()
        sampling = threading.Thread(target=self._sample_loop, args=(sampling_stop,), daemon=True)
        sampling.start()
        try:
            self._run_stream(stop)
        finally:
            sampling_stop.set()
            sampling.join()

    def _run_stream(self, stop):
        retry = 1
        while not stop.is_set():
            try:
                # Subscribe before reading baseline so notifications buffer during GETs.
                with self.client.stream() as response:
                    self._set(connected=True, last_error=None)
                    self.store.log("stream-connected", {"source": "ditto-sse", "origin": self.client.origin})
                    self.reconcile()
                    next_reconcile = time.monotonic() + self.reconcile_seconds
                    retry = 1
                    for event in sse_messages(bounded_lines(response)):
                        if stop.is_set():
                            break
                        if event is not None:
                            self.handle(event)
                        if time.monotonic() >= next_reconcile:
                            self.reconcile()
                            next_reconcile = time.monotonic() + self.reconcile_seconds
                    if not stop.is_set():
                        raise ConnectionError("Ditto change stream ended.")
            except Exception as error:
                self._set(connected=False, last_error=str(error))
                self.store.log("stream-gap", {"error": str(error), "reconcile_on_reconnect": True,
                    "history_note": "Notifications during an outage cannot be assumed recoverable; reconnect reads current Things."})
                stop.wait(retry)
                retry = min(30, retry * 2)
        self._set(connected=False)
