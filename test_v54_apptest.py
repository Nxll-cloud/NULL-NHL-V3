"""Offline AppTests of the full app (trimmed real slate fixture; all HTTP faked; sockets blocked)."""
import pytest

import player_intelligence_v54 as pi
import ui_theme_v53 as ui
from v54_testkit import run_app, state_dict


def _md(block):
    return ' '.join(m.value for m in block.markdown)


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(scope='module')
def overview(mp, tmp_path_factory):
    return run_app(mp, tmp_path_factory.mktemp('ov'))


def test_all_tabs_render_without_exceptions(overview):
    assert not overview.exception
    labels = [t.label for t in overview.tabs][:6]
    assert labels == ['🏠 Home', '🎯 Matchup Center', '⚡ Odds', '📊 Research', '🔮 Numbers', '📈 Track Record']


def test_home_has_no_historical_coverage_and_shows_form_pct(overview):
    home = _md(overview.tabs[0])
    assert 'historical coverage' not in home.lower()
    assert 'np-intel-row' in home and 'FORM %' in home and 'Form score' not in home


def test_home_featured_row_equals_research_picks(overview):
    state = state_dict(overview)
    res, _ = pi.intelligence_from_state(state, state['signals_day'])
    picks = pi.four_picks(res)
    home, research = _md(overview.tabs[0]), _md(overview.tabs[3])
    named = [p for p in picks.values() if p]
    assert named, 'fixture slate should produce at least one pick'
    for p in named:
        name = ui.esc(str(p['Player']))
        assert name in home and name in research


def test_research_goalie_section(overview):
    research = _md(overview.tabs[3])
    assert 'Goalies: Goals Allowed' in research and 'np-gk-grid' in research and 'np-gk-legend' in research
    assert 'Swayman' in research or 'Saros' in research


def test_track_record_tab_and_lock_button(overview):
    track = _md(overview.tabs[5])
    assert 'track record' in track.lower()
    assert any(b.key == 'v54_lock' for b in overview.button)


def test_matchup_center_overview(overview):
    assert 'np-intel' in _md(overview.tabs[1])
    keys = {b.key for b in overview.button}
    assert {'v54_mc_open_statistical', 'v54_mc_open_storyline'} <= keys


def test_selected_matchup_confirmed_starters(mp, tmp_path_factory):
    at = run_app(mp, tmp_path_factory.mktemp('mc'), session={'v54_mc_game': '2026020154'})
    assert not at.exception
    mcx = _md(at.tabs[1])
    assert 'Player targets by matchup' in mcx
    assert 'Confirmed starter' in mcx and 'Michael DiPietro' in mcx  # ESPN fixture: BOS confirmed
    assert 'Probable starter' in mcx and 'Saros' in mcx  # ESPN 'expected' -> Probable
    assert any(b.key == 'v54_mc_back' for b in at.button)


def test_selected_matchup_unknown_starters(mp, tmp_path_factory):
    at = run_app(mp, tmp_path_factory.mktemp('unk'), espn='empty', session={'v54_mc_game': '2026020154'})
    assert not at.exception
    mcx = _md(at.tabs[1])
    assert 'Confirmed starter' not in mcx and 'Probable starter' not in mcx
    assert 'starter not yet announced' in mcx


def test_card_click_opens_matchup_and_back(mp, tmp_path_factory):
    at = run_app(mp, tmp_path_factory.mktemp('click'))
    next(b for b in at.button if b.key == 'v54_mc_open_statistical').click().run()
    assert not at.exception
    assert at.session_state['v54_mc_game'] and 'Player targets by matchup' in _md(at.tabs[1])
    next(b for b in at.button if b.key == 'v54_mc_back').click().run()
    assert 'Player targets by matchup' not in _md(at.tabs[1])


def test_missing_game_shows_back_button(mp, tmp_path_factory):
    at = run_app(mp, tmp_path_factory.mktemp('miss'), session={'v54_mc_game': '9999999999'})
    assert not at.exception and any(b.key == 'v54_mc_back_missing' for b in at.button)
