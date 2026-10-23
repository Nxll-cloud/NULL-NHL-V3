"""V5.5 design system: st.html version guard, sanitizer safety, None-safety, live status from real data."""
import re
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import v55_state as vs
import v55_ui as v5
from v54_testkit import slate, club_rows


class _StNew:
    def __init__(self):
        self.calls = []

    def html(self, body, *, width='stretch', unsafe_allow_javascript=False):
        self.calls.append(('html', body, unsafe_allow_javascript))

    def markdown(self, body, unsafe_allow_html=False):
        self.calls.append(('markdown', body, unsafe_allow_html))


class _StOld:
    def __init__(self):
        self.calls = []

    def html(self, body):
        self.calls.append(('html', body, None))

    def markdown(self, body, unsafe_allow_html=False):
        self.calls.append(('markdown', body, unsafe_allow_html))


class _StAncient:
    def __init__(self):
        self.calls = []

    def markdown(self, body, unsafe_allow_html=False):
        self.calls.append(('markdown', body, unsafe_allow_html))


def test_version_guard_js_path():
    s = _StNew()
    assert v5.html_mode(s) == 'js' and v5.html_block(s, '<p>x</p>') == 'js'
    kind, body, js = s.calls[0]
    assert kind == 'html' and js is True and '<script>' in body and 'class="v55 v55-app' in body


def test_version_guard_static_and_markdown_paths():
    s = _StOld()
    assert v5.html_block(s, '<p>x</p>') == 'static'
    assert s.calls[0][0] == 'html' and '<script>' not in s.calls[0][1]
    a = _StAncient()
    assert v5.html_block(a, '<p>x</p>') == 'markdown'
    assert a.calls[0] == ('markdown', a.calls[0][1], True) and '<script>' not in a.calls[0][1]


def test_real_streamlit_supports_js():
    import streamlit as st
    assert v5.html_mode(st) == 'js'


@pytest.mark.parametrize('label,t', [('Night', 'dark'), ('Light', 'light'), ('High contrast', 'contrast'), (None, 'dark'), ('junk', 'dark')])
def test_themes_css_sanitizer_safe(label, t):
    assert v5.theme_from_label(label) == t
    css = v5.design_css(t)
    assert not re.search(r'<[/\w!]', css)
    assert '@font-face' in css and 'Barlow Condensed' in css and 'fonts.googleapis' not in css
    assert v5.page_style(t).startswith('<style>')
    assert not re.search(r'<[/\w!]', v5.js())


def test_sanitizer_check_rejects():
    with pytest.raises(ValueError):
        v5.check_sanitizer_safe('x', 'a{content:"</style>"}')


def test_no_global_google_fonts_import():
    import ui_theme_v53 as ui
    assert 'fonts.googleapis.com' not in ui.stylesheet()


NOW = datetime(2026, 10, 22, 22, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize('game,exp', [
    ({'status': 'LIVE', 'start': '2026-10-23T02:00:00Z'}, 'live'),            # status wins over time
    ({'status': 'CRIT', 'start': None}, 'live'),
    ({'status': 'FINAL', 'start': '2026-10-22T23:00:00Z'}, 'done'),
    ({'status': 'OFF'}, 'done'),
    ({'status': 'FUT', 'start': '2026-10-22T23:00:00Z'}, 'pre'),
    ({'status': 'FUT', 'start': '2026-10-22T21:30:00Z'}, 'starting'),         # past start, feed not yet live
    ({'start': '2026-10-22T21:30:00Z'}, 'live'),
    ({'start': '2026-10-22T17:00:00Z'}, 'done'),
    ({'start': None}, 'pre'), ({'start': 'garbage'}, 'pre'),
])
def test_game_state(game, exp):
    assert v5.game_state(game, NOW) == exp


def test_countdown_from_real_start():
    assert v5.until('2026-10-22T23:05:00Z', NOW) == '1h 05m'
    assert v5.until('2026-10-22T22:12:00Z', NOW) == '12m'
    assert v5.until(None, NOW) == '—'


def test_ring_and_spark_empty_states():
    assert 'none' in v5.ring(None, '7 day', 'no data')
    assert 'none' not in v5.ring(.5, '7 day', 'x')
    assert 'Game log unavailable' in v5.sparkline(None)
    assert '<svg' not in v5.sparkline([{'shots': 3, 'goals': 1}, {'shots': 1, 'goals': 0}])   # data-URI img only


def test_render_home_empty_is_safe():
    out = v5.render_home({}, NOW)
    assert 'v55' in out or out
    out2 = v5.render_home({'day': '2026-10-22', 'games': [], 'leaders': {}, 'picks': {}, 'track': None}, NOW)
    assert isinstance(out2, str)


def test_escaping():
    out = v5.tab_head('<k>', '<script>x</script>', '<b>', chips=[('<i>', 'muted')])
    assert '<script>x' not in out and '&lt;script&gt;' in out


# ---- v55_state with failing fetchers -----------------------------------------------------------------
def _boom(*a, **k):
    raise RuntimeError('offline')


def test_build_state_degrades_when_fetchers_fail():
    from home_leaders_v52 import all_targets, choose_leaders
    snap = slate()
    ranked = pd.DataFrame(snap['rankings'])
    day = snap.get('day', '2026-10-22')
    targets = all_targets(snap['games'], ranked, day)
    leaders = choose_leaders(ranked, targets, pd.DataFrame())
    st_ = vs.build_state(day=day, season='20262027', games=snap['games'], ranked=ranked, targets=targets, leaders=leaders,
                         goalie_rows=club_rows(), rosters_fn=_boom, logs_fn=_boom,
                         track=vs.track_summary([], lambda e, n=None: None))
    assert st_['fetch_errors']
    out = v5.render_home(st_, NOW)
    assert 'Game log unavailable' in out and 'class="hero' in out


def test_safe_many_never_raises():
    got, errs = vs.safe_many(lambda k: 1 / k, [1, 'x', 2, None])
    assert got == {1: 1.0, 2: 0.5} and len(errs) == 1


def test_track_summary_empty_and_demo():
    roll = lambda e, n=None: None
    t = vs.track_summary([], roll)
    assert t['r7'] is None and t['trend'] == [] and not t['demo']
    t2 = vs.track_summary([{'day': '2026-10-01', 'status': 'evaluated', 'hit_rate': .5, 'hits': [1], 'picks': 2, 'demo': True},
                           {'day': '2026-10-02', 'status': 'pending'}], roll)
    assert t2['demo'] and t2['pending'] == 1 and t2['trend'][0]['rate'] == .5
