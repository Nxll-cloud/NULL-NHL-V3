"""V5.6 offline AppTests: pregame prior, live (real captured PBP), final, DEMO replay, Matchup Center goalies,
Numbers 'By Game' and Edge Flags. Every HTTP call is faked; the live feeds come from real captured fixtures."""
import json

import pytest

from v54_testkit import HERE, run_app, markdown

F = HERE / 'test_fixtures_v56'
TABS = {'home': '🏠 Home', 'mc': '🎯 Matchup Center', 'numbers': '🔮 Numbers', 'nextgoal': '⏱ Live Next Goal', 'edgeflags': '🚩 Edge Flags'}
EXTRA = json.loads((F / 'slate_extra_2026020164.json').read_text())['games']


def _tab(at, key):
    return next(t for t in at.tabs if t.label == TABS[key])   # at.tabs also lists nested tabs, so match by label


def _md(block):
    return ' '.join([m.value for m in block.markdown] + [h.value for h in block.get('html')])


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(scope='module')
def pregame(mp, tmp_path_factory):
    return run_app(mp, tmp_path_factory.mktemp('pre'))


@pytest.fixture(scope='module')
def live(mp, tmp_path_factory):
    return run_app(mp, tmp_path_factory.mktemp('live'), extra_games=EXTRA,
                   pbp_files={'score.json': F / 'score_20261022_live.json', '2026020164.json': F / 'pbp_live_2026020164.json',
                              '2026020154.json': F / 'pbp_2026020154.json'})


def test_pregame_prior(pregame):
    assert not pregame.exception
    ng = _md(_tab(pregame, 'nextgoal'))
    assert 'PREGAME PRIOR' in ng and 'NSH @ BOS' in ng
    assert 'ngp-wrap' in ng and 'pregame prior' in ng.lower()


def test_demo_replay_labelled_and_steps(pregame):
    # V5.9: the replay is a fallback; with every real game pregame it shows under the (empty) Live filter
    pregame.session_state['v56_ng_filter'] = 'Live'
    pregame.run()
    ng = _md(_tab(pregame, 'nextgoal'))
    assert 'DEMO replay' in ng and 'MIN @ CGY' in ng and '2026020162' in ng
    step = pregame.session_state['v56_demo_step']
    pregame.button(key='v56_demo_next').click().run()
    assert not pregame.exception
    assert pregame.session_state['v56_demo_step'] == step + 1
    assert 'vs previous replay step' in _md(_tab(pregame, 'nextgoal'))
    pregame.button(key='v56_demo_first').click().run()
    assert pregame.session_state['v56_demo_step'] == 0
    pregame.session_state['v56_ng_filter'] = 'All'
    pregame.run()


def test_live_game_from_real_pbp(live):
    assert not live.exception
    ng = _md(_tab(live, 'nextgoal'))
    assert 'UTA' in ng and 'SEA' in ng and 'LIVE' in ng and 'P2' in ng
    assert 'vs pregame prior' in ng          # first sight of a live game compares with the pregame prior
    home = _md(_tab(live, 'home'))
    assert 'lstrip' in home                  # Home live strip


def test_final_game(live):
    ng = _md(_tab(live, 'nextgoal'))
    assert 'Final' in ng and 'no further goal is possible' in ng
    home = _md(_tab(live, 'home'))
    assert 'class="scr"' in home             # board tiles carry scores


def test_matchup_center_goalies_threats_and_toggle(live):
    mcx = _md(_tab(live, 'mc'))
    assert 'Goalies: Goals Allowed' in mcx and 'Goalies vs tonight' in mcx
    assert 'gtgrid' in mcx and 'since 20' in mcx
    assert live.toggle(key='v56_mc_sort_flag') is not None
    live.toggle(key='v56_mc_sort_flag').set_value(True).run()
    assert not live.exception


def test_numbers_by_game_default_and_old_views_intact(pregame):
    nums = _md(_tab(pregame, 'numbers'))
    assert 'nbgrid' in nums and 'nleg' in nums
    pregame.radio(key='v48_view').set_value('Games').run()
    assert not pregame.exception and 'np-num-match' in _md(_tab(pregame, 'numbers'))


def test_edge_flags_demo_without_key(pregame):
    ef = _md(_tab(pregame, 'edgeflags'))
    assert 'efgrid' in ef and 'DEMO opening lines' in ef


def test_home_hero_uses_official_game_state(live):
    import re
    home = _md(_tab(live, 'home'))
    hero = re.search(r'<section class="hero.*?</section>', home, re.S)
    assert hero and 'when done' in hero.group(0) and 'Live now' not in hero.group(0)   # featured game is FINAL in the score fixture
