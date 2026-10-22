"""Shared offline fixtures for the V5.4 tests (not a test module)."""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
FIX = HERE / 'test_fixtures_v54'
APP = str(HERE / 'app.py')


def load(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


def slate():
    return load('slate_trimmed_20261022.json')


def club_rows():
    import goalies_v54 as gk
    rows = []
    for team, payload in load('nhl_club_stats_goalies_20261022.json').items():
        rows += gk.parse_club_goalies(payload, team)
    return rows


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status

    def json(self):
        return self._p

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))


def run_app(monkeypatch, tmp_path, espn='fixture', session=None, timeout=180):
    """AppTest of app.py on the trimmed real slate with every HTTP call faked (offline)."""
    import requests
    import streamlit as st
    import snapshot_store
    from streamlit.testing.v1 import AppTest
    snap = slate()
    club = load('nhl_club_stats_goalies_20261022.json')
    espn_payload = load('espn_scoreboard_20261022.json')
    if espn == 'empty':  # feed reachable but no probables listed -> unknown state
        for ev in espn_payload.get('events', []):
            for c in ev['competitions'][0]['competitors']:
                c.pop('probables', None)

    def fake_get(url, params=None, timeout=None, headers=None, **kw):
        if 'club-stats/' in url:
            return _Resp(club.get(url.split('club-stats/')[1].split('/')[0], {'goalies': []}))
        if 'site.api.espn.com' in url:
            return _Resp(espn_payload)
        raise requests.ConnectionError('offline test')

    monkeypatch.setenv('PLAYBOOK_TRACKER_DB', str(tmp_path / 'tracker.sqlite'))
    monkeypatch.setattr(requests, 'get', fake_get)
    monkeypatch.setattr(snapshot_store, 'load_snapshot', lambda day, root=None: {**snap, 'day': day})
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=timeout)
    for k, v in (session or {}).items():
        at.session_state[k] = v
    at.run()
    return at


def markdown(at):
    return ' '.join(m.value for m in at.markdown)


def state_dict(at):
    keys = ['signals_ranked', 'signals_day', 'signal_meta', 'auto_signal_metadata', 'auto_signal_day',
            'history_v38', 'history_v38_day', 'history_v386', 'history_v386_day']
    out = {}
    for k in keys:
        try:
            out[k] = at.session_state[k]
        except KeyError:
            pass
    return out
