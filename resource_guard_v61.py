"""V6.1 resource guard: keep Streamlit Community Cloud CPU/memory low without changing any output.

* ``freeze_imports()`` - Streamlit runs ``gc.collect(2)`` after EVERY script and fragment run (runner.postScriptGC).
  The ~100k objects created by importing pandas/numpy/streamlit and the project modules never become garbage, so
  they are moved once per process to the permanent generation (``gc.freeze``) and every later full collection skips
  them. Reference counting still frees anything normally; only the cyclic GC stops rescanning them.
* ``thaw()`` - undo it before the stale-module guard drops project modules, so the old module objects can be
  collected; the next ``freeze_imports()`` re-freezes the freshly imported set.
* ``BoundedTTL`` - small thread-safe TTL map with eviction of expired entries on write and a hard size cap
  (used by storylines_v58 for process-wide NHL/ESPN payloads).
"""
import gc
import sys
import threading
import time
import types

_STATE = '_np_gc_state'


def _state():
    s = sys.modules.get(_STATE)
    if s is None:
        s = sys.modules[_STATE] = types.ModuleType(_STATE)
        s.frozen = False
    return s


def freeze_imports():
    """Freeze the currently tracked objects once per process (or once after each ``thaw``). Returns True if it froze."""
    s = _state()
    if s.frozen:
        return False
    gc.collect()          # do not freeze import-time garbage
    gc.freeze()
    s.frozen = True
    return True


def thaw():
    s = _state()
    if s.frozen:
        gc.unfreeze()
        s.frozen = False


def compact(record, keep):
    """Copy of a dict with only the keys in ``keep`` that are present (absent keys stay absent; values unchanged)."""
    return {k: record[k] for k in keep if k in record}


class BoundedTTL:
    """Thread-safe {key: (stored_at, value)} with per-kind TTL. Expired entries are dropped on write (at most once a
    ``sweep`` seconds) and the map never exceeds ``cap`` entries (oldest first)."""

    def __init__(self, ttl, cap, sweep=60, clock=None):
        self.ttl, self.cap, self.sweep = dict(ttl), int(cap), sweep
        self.clock = clock or (lambda: time.time())   # looked up per call (patchable, like the old time.time())
        self.data, self.lock, self._swept = {}, threading.Lock(), 0.0

    def get(self, kind, key):
        now = self.clock()
        with self.lock:
            hit = self.data.get((kind, key))
            if hit and now - hit[0] < self.ttl[kind]:
                return True, hit[1]
        return False, None

    def put(self, kind, key, value, now=None):
        now = self.clock() if now is None else now
        with self.lock:
            self.data[(kind, key)] = (now, value)
            if now - self._swept >= self.sweep or len(self.data) > self.cap:
                self._swept = now
                for k in [k for k, v in self.data.items() if now - v[0] >= self.ttl[k[0]]]:
                    self.data.pop(k, None)
            if len(self.data) > self.cap:
                for k in sorted(self.data, key=lambda k: self.data[k][0])[:len(self.data) - self.cap]:
                    self.data.pop(k, None)
        return value

    def __len__(self):
        return len(self.data)
