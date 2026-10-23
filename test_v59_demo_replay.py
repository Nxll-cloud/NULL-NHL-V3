"""V5.9 Live Next Goal DEMO replay fixes, offline on the recorded fixtures:
state (pulse only while autoplay steps; paused = static REPLAY tag with the score; end = 'Final a–h'), Show-filter gating
(the replay is a fallback shown only when no real game matches), one clock convention (time LEFT in the period) and
real strength per replayed event (situationCode, no hardcoded 5v5), plus the demo-scoped spacing hook (.ngp-demo)."""
import json
import re

import pytest

import live_feed_v56 as lf
import live_nextgoal_v56 as ng
import v56_ui as v56
from v54_testkit import HERE, run_app

F = HERE / 'test_fixtures_v56'
TAB = '⏱ Live Next Goal'
EXTRA = json.loads((F / 'slate_extra_2026020164.json').read_text())['games']
LIVE_PBP = {'score.json': F / 'score_20261022_live.json', '2026020164.json': F / 'pbp_live_2026020164.json',
            '2026020154.json': F / 'pbp_2026020154.json'}


def _demo():
    return ng.parse_pbp(lf.load_demo())


def _md(at):
    tab = next(t for t in at.tabs if t.label == TAB)
    return ' '.join([m.value for m in tab.markdown] + [h.value for h in tab.get('html')]), ' '.join(c.value for c in tab.caption)


def _demo_sec(src):
    m = re.search(r'<section class="sec ngp-wrap ngp-demo">.*?</section>', src, re.S)
    return m.group(0) if m else None


# ---------------------------------------------------------------- 1) state badge
def _res(game):
    r = ng.model(game, {})
    ng.rerank(r['players'], None)
    return r


def test_paused_replay_never_pulses_and_shows_score():
    g = _demo()
    t = ng.truncate(g, 40)
    h = v56.nextgoal_panel(_res(t), '20262027', 'P1 01:28', demo=True, replay='paused')
    assert 'class="pulse"' not in h and 'REPLAY · P1 01:28 · 0–2' in h and 'LIVE P1' not in h
    assert '<section class="sec ngp-wrap ngp-demo">' in h and 'DEMO' in h


def test_playing_replay_pulses():
    h = v56.nextgoal_panel(_res(ng.truncate(_demo(), 40)), '20262027', 'P1 01:28', demo=True, replay='playing')
    assert 'class="pulse"' in h and 'REPLAYING · P1 01:28 · 0–2' in h


def test_last_step_is_final_with_score():
    g = _demo()
    full = ng.truncate(g, len(g['events']))
    assert ng.phase(full) == 'final'
    h = v56.nextgoal_panel(_res(full), '20262027', 'Final', demo=True, replay='paused')
    assert 'Final 1–2' in h and 'class="pulse"' not in h


def test_real_live_panels_unchanged():
    g = ng.truncate(_demo(), 40)
    h = v56.nextgoal_panel(_res(g), '20262027', 'P1 01:28')
    assert h.startswith('<section class="sec ngp-wrap">') and 'ngp-demo' not in h and 'ngst' not in h
    assert '<span class="live"><i class="pulse"></i>LIVE P1 01:28</span>' in h
    assert v56.state_badge('live', 'P2 10:00') == '<span class="live"><i class="pulse"></i>LIVE P2 10:00</span>'


# ---------------------------------------------------------------- 4) strength
def test_truncate_uses_each_events_situation_code():
    g = _demo()
    raw = {p['eventId']: str(p.get('situationCode') or '') for p in lf.load_demo()['plays']}
    codes = set()
    for k in range(1, len(g['events'])):
        e = g['events'][k - 1]
        assert e['sit'] == raw[e['eid']]
        assert ng.truncate(g, k)['situation'] == e['sit']
        codes.add(e['sit'])
    assert codes - {'1551'}, 'the fixture has power-play / empty-net moments'
    pp = next(k for k in range(1, len(g['events'])) if g['events'][k - 1]['strength'] == 'PP')
    t = ng.truncate(g, pp)
    assert t['situation'] != '1551'
    assert ng.situation_mult(t['situation'], True) != 1.0 or ng.situation_mult(t['situation'], False) != 1.0


def test_truncate_unknown_situation_is_neutral_not_even_strength():
    g = _demo()
    g = dict(g, events=[dict(e, sit='') for e in g['events']])
    assert ng.truncate(g, 5)['situation'] == ''
    assert ng.situation_mult('', True) == 1.0


def test_live_path_situation_unchanged():
    payload = json.loads((F / 'pbp_live_2026020164.json').read_text())
    g = ng.parse_pbp(payload)
    last = [p for p in payload['plays'] if p.get('situationCode')][-1]['situationCode']
    assert g['situation'] == last
    assert ng.truncate(g, len(g['events']) + 5)['situation'] == g['situation']   # full game passes through untouched


# ---------------------------------------------------------------- 2) filter gating + 3) clock + autoplay (AppTest)
@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    m.setenv('MODEL_XG', '0')
    yield m
    m.undo()


@pytest.fixture(scope='module')
def live(mp, tmp_path_factory):
    return run_app(mp, tmp_path_factory.mktemp('demo_live'), extra_games=EXTRA, pbp_files=LIVE_PBP)


@pytest.fixture(scope='module')
def pregame(mp, tmp_path_factory):
    return run_app(mp, tmp_path_factory.mktemp('demo_pre'))


def _show(at, filt):
    at.session_state['v56_ng_filter'] = filt
    at.run()
    assert not at.exception
    return _md(at)


@pytest.mark.parametrize('filt', ['All', 'Live', 'Pregame', 'Final'])
def test_demo_hidden_when_a_real_game_matches(live, filt):
    src, cap = _show(live, filt)
    assert _demo_sec(src) is None and 'DEMO · MIN @ CGY' not in src
    assert 'DEMO replay hidden' in cap


def test_demo_hidden_under_all_on_pregame_slate(pregame):
    src, cap = _show(pregame, 'All')
    assert _demo_sec(src) is None and 'DEMO replay hidden' in cap


@pytest.mark.parametrize('filt', ['Live', 'Final'])
def test_demo_is_a_labelled_fallback_when_nothing_matches(pregame, filt):
    src, cap = _show(pregame, filt)
    sec = _demo_sec(src)
    assert sec and 'fallback replay' in sec and 'DEMO' in sec
    assert f'no real {filt.lower()} game on this slate' in src
    assert 'class="pulse"' not in sec and 'LIVE P' not in sec   # never a pulsing LIVE card under a filter


def test_note_clock_is_time_left(pregame):
    pregame.session_state['v56_demo_step'] = 40
    src, _ = _show(pregame, 'Live')
    sec = _demo_sec(src)
    assert 'Event 40/108 · P1 01:28 left' in sec and 'REPLAY · P1 01:28 · 0–2' in sec
    assert 'P1 18:32' not in sec   # elapsed clock gone


def test_autoplay_pulses_only_while_playing_and_manual_step_pauses(pregame):
    _show(pregame, 'Live')
    pregame.button(key='v59_demo_play_btn').click().run()
    assert not pregame.exception and pregame.session_state['v59_demo_play'] is True
    sec = _demo_sec(_md(pregame)[0])
    assert 'class="pulse"' in sec and 'REPLAYING' in sec
    step = pregame.session_state['v56_demo_step']
    pregame.button(key='v56_demo_next').click().run()   # manual step = pause
    assert pregame.session_state['v59_demo_play'] is False and pregame.session_state['v56_demo_step'] == step + 1
    sec = _demo_sec(_md(pregame)[0])
    assert 'class="pulse"' not in sec and 'REPLAY · ' in sec


def test_last_button_shows_final_score(pregame):
    _show(pregame, 'Final')
    pregame.button(key='v56_demo_last').click().run()
    sec = _demo_sec(_md(pregame)[0])
    assert 'Final 1–2' in sec and 'class="pulse"' not in sec and 'Event 108/108' in sec
    pregame.session_state['v56_ng_filter'] = 'All'
    pregame.run()


def test_demo_spacing_css_is_scoped():
    css = (HERE / 'assets' / 'v58.css').read_text()
    rules = [r for r in re.findall(r'([^{}]+)\{', css) if 'ngp-demo' in r or 'v59_demo_ctrl' in r]
    assert rules and all(('.ngp-demo' in r) or ('.st-key-v59_demo_ctrl' in r) for r in rules)
    mob = (HERE / 'assets' / 'mobile.css').read_text()
    assert '.v55 .ngp-demo .ngr{grid-template-columns' in mob and '.st-key-v59_demo_ctrl [data-testid="stColumn"]' in mob
