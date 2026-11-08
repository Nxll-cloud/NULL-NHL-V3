"""Process-local quote cache: 30 min healthy, 60s partial, 30–300s explicit negative cooldown.
No disk, secrets in keys/logs, background retries or provider requests beyond the existing fetch.
"""
from copy import deepcopy
from hashlib import sha256
import threading
import time
import pandas as pd
from odds_api_v45 import OddsFeedError, _items, _valid_price


class QuoteCache:
    def __init__(self, clock=time.monotonic):
        self.clock, self.entries, self.events, self.lock = clock, {}, {}, threading.RLock()

    def clear(self):
        with self.lock:
            self.entries.clear()
            self.events.clear()

    def get(self, fetch, key, regions, markets):
        ident = sha256(str(key).encode()).hexdigest(), regions, markets
        with self.lock:  # single-flight, including simultaneous sessions/reruns
            now = self.clock()
            old = self.entries.get(ident)
            if old and now < old['until']:
                return self._result(old, cached=True, now=now)
            try:
                frame, warnings = fetch(key, regions=regions, markets=markets,
                                        event_cache=lambda eid, load: self.event_get(ident, eid, load))
                status = dict(frame.attrs.get('feed_status') or {})
                state = status.get('state') or ('empty' if frame.empty else 'partial' if warnings else 'ok')
                if frame.empty and len(status.get('issues') or {}) == 1:
                    state = next(iter(status['issues']))
                status.update(state=state, quotes=len(frame))
                ttl = (1800 if state == 'ok' and not frame.empty else 60 if not frame.empty else
                       300 if state == 'auth' else 30 if state in ('timeout','network','malformed','unavailable') else 60)
                error = None
            except OddsFeedError as exc:
                frame, warnings = pd.DataFrame(), []
                state = exc.code
                status = dict(exc.status or {}, state=state, quotes=0)
                error = OddsFeedError(exc.safe_message, code=exc.code, status=status)
                ttl = 300 if state == 'auth' else 60 if state == 'quota' else 30
            now = self.clock()  # cooldown starts AFTER slow I/O, never expires during the request
            item = {'frame': frame.copy(deep=True), 'warnings': list(warnings), 'status': status,
                    'error': error, 'until': now + ttl, 'ttl': ttl}
            self.entries[ident] = item
            # Bound server memory; no credential material is stored in cache identities.
            if len(self.entries) > 64:
                for k in list(self.entries)[:-64]:
                    self.entries.pop(k, None)
            return self._result(item, cached=False, now=now)

    def event_get(self, ident, eid, load):
        """Keep healthy events 30 min during partial retries; failed/empty events have short cooldowns."""
        key = (*ident, str(eid))
        now = self.clock()
        hit = self.events.get(key)
        if hit and now < hit['until']:
            if hit['error']:
                raise hit['error']
            return deepcopy(hit['data'])
        try:
            data = load()
            if not isinstance(data, dict):
                raise OddsFeedError('Provider returned invalid event data.', code='malformed')
            usable = any(_valid_price(o.get('price')) and o.get('description') and o.get('name')
                         and (m.get('last_update') or b.get('last_update'))
                         for b in _items(data.get('bookmakers')) for m in _items(b.get('markets'))
                         for o in _items(m.get('outcomes')))
            error, ttl = None, 1800 if usable else 60
        except OddsFeedError as exc:
            data, error = None, OddsFeedError(exc.safe_message, code=exc.code)
            ttl = 300 if exc.code == 'auth' else 60 if exc.code == 'quota' else 30
        self.events[key] = {'data': deepcopy(data), 'error': error, 'until': self.clock() + ttl}
        if len(self.events) > 512:
            for k in list(self.events)[:-512]:
                self.events.pop(k, None)
        if error:
            raise error
        return deepcopy(data)

    @staticmethod
    def _result(item, cached, now):
        status = deepcopy(item['status'])
        status.update(cached=cached, retry_after_seconds=max(0, int(item['until'] - now)), cache_seconds=item['ttl'])
        if item['error']:
            e = item['error']
            raise OddsFeedError(e.safe_message, code=e.code, status=status)
        frame = item['frame'].copy(deep=True)
        frame.attrs['feed_status'] = status
        return frame, list(item['warnings'])
