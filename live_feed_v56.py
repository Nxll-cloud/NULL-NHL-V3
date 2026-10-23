"""V5.6 live feed helpers: NHL official score + play-by-play endpoints (network only through an injected getter).

* ``score/{YYYY-MM-DD}``: one request for every game's state, score, SOG, period and clock -> board tiles and the
  Home live strip.
* ``gamecenter/{id}/play-by-play``: shot events for the next-goal model (``live_nextgoal_v56.parse_pbp``).

The app wraps these in ``st.cache_data`` (TTL 25 s live / 5 min otherwise) and a per-game ``Poller`` (backoff with
jitter, last good state kept, events deduped by eventId). Tests inject fakes; nothing here runs at import.
"""
from __future__ import annotations

import json
from pathlib import Path

import venue_v58

API = 'https://api-web.nhle.com/v1/'
HERE = Path(__file__).resolve().parent
DEMO_FIXTURE = HERE / 'test_fixtures_v56' / 'pbp_2026020162.json'
DEMO_LABEL = 'DEMO replay · real NHL play-by-play of MIN @ CGY, 2026-10-22 (game 2026020162), stepped event by event'


def fetch_json(getter, path, timeout=10):
    r = getter(API + path, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_pbp(game_id, getter, timeout=10):
    return fetch_json(getter, f'gamecenter/{int(game_id)}/play-by-play', timeout)


def fetch_scores(day, getter, timeout=10):
    return parse_scores(fetch_json(getter, f'score/{day}', timeout))


def period_label(period, ptype, clock=None):
    if ptype == 'SO':
        return 'SO'
    if ptype == 'OT' or (period or 0) > 3:
        lab = 'OT'
    else:
        lab = f'P{int(period or 1)}'
    if clock and clock.get('inIntermission'):
        return f'{lab} INT'
    t = (clock or {}).get('timeRemaining')
    return f'{lab} {t}' if t else lab


def parse_scores(payload):
    """score payload -> {game_id(str): {'state','away','home','away_score','home_score','away_sog','home_sog','label','venue'}}."""
    out = {}
    for g in (payload or {}).get('games') or []:
        gid = g.get('id')
        if gid is None:
            continue
        a, h = g.get('awayTeam') or {}, g.get('homeTeam') or {}
        pd_ = g.get('periodDescriptor') or {}
        state = str(g.get('gameState', ''))
        label = ('Final' + ('/' + pd_.get('periodType') if pd_.get('periodType') in ('OT', 'SO') else '')) if state in ('OFF', 'FINAL') \
            else period_label(pd_.get('number', g.get('period')), pd_.get('periodType'), g.get('clock')) if state in ('LIVE', 'CRIT') else ''
        out[str(gid)] = {'state': state, 'away': a.get('abbrev'), 'home': h.get('abbrev'), 'away_score': a.get('score'),
                         'home_score': h.get('score'), 'away_sog': a.get('sog'), 'home_sog': h.get('sog'), 'label': label,
                         'venue': venue_v58.from_api(g)}   # V5.8: arena (score endpoint games[].venue.default)
    return out


def load_demo(path=None):
    return json.loads(Path(path or DEMO_FIXTURE).read_text(encoding='utf-8'))
