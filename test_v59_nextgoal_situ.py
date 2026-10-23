"""V5.9: the Live Next Goal tab (live panels + DEMO replay) uses the SAME situational layer (situational_v58, gated by
MODEL_SITUATIONAL) as Home and Matchup Center, so all three show identical next-goal % for the same game.
Offline AppTests on the recorded V5.6 fixtures; the situational stats feed is replaced by a fixed goalie context."""
import html
import re

import pytest

import matchup_center_v54 as mc
import situational_v58 as sit
from v54_testkit import HERE, run_app

F = HERE / 'test_fixtures_v56'
TABS = {'home': '🏠 Home', 'mc': '🎯 Matchup Center', 'nextgoal': '⏱ Live Next Goal'}
LIVE_GAME = {'Away': 'UTA', 'Home': 'SEA', 'Start (UTC)': '2026-10-23T02:00:00Z'}
PBP = {'score.json': F / 'score_20261022_live.json', '2026020164.json': F / 'pbp_live_2026020164.json',
       '2026020154.json': F / 'pbp_2026020154.json'}
# Very different goalies per team, so the goalie adjustment visibly moves every shooter's next-goal %.
SV = {'SEA': 0.860, 'UTA': 0.935, 'MIN': 0.940, 'CGY': 0.860, 'BOS': 0.870, 'NSH': 0.930}


def _fake_context(day, season, getter=None, starters=None, parts=sit.PARTS):
    goalies = [{'Team': t, 'Goalie': f'{t} Test Goalie', 'Player ID': str(900 + i), 'SA': 1000, 'Saves': round(sv * 1000)}
               for i, (t, sv) in enumerate(SV.items())]
    return sit.context(goalies=goalies, starters=starters, parts=parts)


def _run(tmp_path_factory, name, on):
    import json
    m = pytest.MonkeyPatch()
    m.setattr(sit, 'fetch_context', _fake_context)
    m.setenv('MODEL_SITUATIONAL', '1' if on else '0')
    m.setenv('MODEL_XG', '0')   # no MoneyPuck download in tests
    extra = json.loads((F / 'slate_extra_2026020164.json').read_text())['games']
    key = mc.game_key(extra[0])
    at = run_app(m, tmp_path_factory.mktemp(name), extra_games=extra, pbp_files=PBP, session={'v54_mc_game': key, 'v54_mc_select': key})
    return at, m


@pytest.fixture(scope='module')
def on(tmp_path_factory):
    at, m = _run(tmp_path_factory, 'situ_on', True)
    yield at
    m.undo()


@pytest.fixture(scope='module')
def off(tmp_path_factory):
    at, m = _run(tmp_path_factory, 'situ_off', False)
    yield at
    m.undo()


def _html(at, key):
    tab = next(t for t in at.tabs if t.label == TABS[key])
    return ' '.join([x.value for x in tab.markdown] + [h.value for h in tab.get('html')])


ROW = re.compile(r'<div class="ngn"><b>(.*?)(?:<span[^>]*>.*?</span>)?</b><small>([A-Z]{3}) .*?<span class="ngp"><em>([^<]+)</em>', re.S)


def panel(at, key, title):
    """{(player, team): next-goal % text} from the panel titled ``title`` (e.g. 'UTA @ SEA') on tab ``key``."""
    src = _html(at, key)
    for sec in re.findall(r'<section class="sec ngp-wrap(?: ngp-demo)?">.*?</section>', src, re.S):
        h3 = re.search(r'<h3>(.*?)</h3>', sec, re.S).group(1)
        if html.unescape(h3).strip() == title:
            return {(html.unescape(n), t): p for n, t, p in ROW.findall(sec)}
    return None


def test_apps_run(on, off):
    assert not on.exception and not off.exception


def test_next_goal_tab_matches_matchup_center_with_layer_on(on):
    tab, mcx = panel(on, 'nextgoal', 'UTA @ SEA'), panel(on, 'mc', 'Live Next Goal')
    assert tab and mcx and len(mcx) >= 5
    assert {k: tab[k] for k in mcx} == mcx   # MC shows the top 8; every one is identical on the Next Goal tab


def test_home_strip_leader_matches_next_goal_tab(on):
    home = _html(on, 'home')
    lead = re.search(r'<div class="ls live">.*?<small>next: (\S+) ([\d.]+%)</small>', home, re.S)
    assert lead, 'Home live strip shows the live game leader'
    (name, team), p = next(iter(panel(on, 'nextgoal', 'UTA @ SEA').items()))
    assert name.split(' ')[-1] == html.unescape(lead.group(1))
    # same number at two display precisions (tab 1 dp, strip 0 dp): compare within rounding, not round(round(x))
    assert abs(float(p.rstrip('%')) - float(lead.group(2).rstrip('%'))) <= 0.55


def test_layer_actually_changes_the_numbers(on, off):
    a, b = panel(on, 'nextgoal', 'UTA @ SEA'), panel(off, 'nextgoal', 'UTA @ SEA')
    assert a and b and a != b
    # off: Next Goal tab and Matchup Center still agree (the V5.6 model exactly)
    mco = panel(off, 'mc', 'Live Next Goal')
    assert {k: b[k] for k in mco} == mco


def _run_empty(tmp_path_factory, name, on):
    m = pytest.MonkeyPatch()
    m.setattr(sit, 'fetch_context', _fake_context)
    m.setenv('MODEL_SITUATIONAL', '1' if on else '0')
    m.setenv('MODEL_XG', '0')
    return run_app(m, tmp_path_factory.mktemp(name), games=['NSH@BOS'], session={'v56_ng_filter': 'Live'}), m


def test_demo_replay_uses_the_layer(tmp_path_factory):
    # V5.9: the DEMO replay is a fallback shown only when no real game matches the Show filter -> Live on a pregame slate
    (a_at, m1), (b_at, m2) = _run_empty(tmp_path_factory, 'demo_on', True), _run_empty(tmp_path_factory, 'demo_off', False)
    try:
        t = 'DEMO · MIN @ CGY · fallback replay'
        a, b = panel(a_at, 'nextgoal', t), panel(b_at, 'nextgoal', t)
        assert a and b and a != b
    finally:
        m2.undo(); m1.undo()


def test_tab_has_no_private_model_path():
    src = (HERE / 'tabs' / 'nextgoal.py').read_text(encoding='utf-8')
    assert 'lstate.slate_results(' not in src and 'ng.model(' not in src   # only the shared helpers from tabs/live.py
    live = (HERE / 'tabs' / 'live.py').read_text(encoding='utf-8')
    assert 'situ=_v56_situ' in live and '_v56_results=v56_slate_results()' in live
