"""V5.8: Research shows everything down to 'Top 10 Statistical Sleepers'; the rest is display-gated by FEATURE_RESEARCH_EXTRAS."""
import ast

import pytest

import feature_flags_v58 as flags
from v54_testkit import HERE, run_app

VISIBLE = ['Top 10 Statistical', 'Top 10 Storylines', 'Top 10 Overlap', 'Top 10 Statistical Sleepers',
           '🥅 First Goal Intelligence']   # V6.0: always-visible first-goal board follows Sleepers
HIDDEN = ['Full NHL Slate', 'Player Statistics Explorer', 'V3.2 Goal-Scorer Rankings', 'V3.3 Historical Backtesting',
          'V3.5 Auto Storyline, Numerology & Gematria', 'V3.8 Opponent History & Season Milestone Evidence',
          'V3.8.2 Data Integrity Audit', 'V3.8.2 Opponent, Milestone & Birthday Diagnostics',
          'V3.8.4 Official Schedule & Player Assignment Audit', 'V3.8.5 Roster & Historical Schedule Verification',
          'V3.8.6 Multi-Season Opponent Storylines', 'V3.8.2 Combined Statistical + Experimental Explorer']


def _research(at):
    return next(t for t in at.tabs if t.label == '📊 Research')


def _heads(block):
    return [s.value for s in block.subheader]


def _text(block):
    return ' '.join([m.value for m in block.markdown] + [c.value for c in block.caption])


@pytest.mark.parametrize('env,secrets,want', [(None, {}, False), ('1', {}, True), ('off', {'FEATURE_RESEARCH_EXTRAS': 'true'}, False),
                                              (None, {'FEATURE_RESEARCH_EXTRAS': 'on'}, True), ('junk', {}, False)])
def test_research_flag_resolution(env, secrets, want):
    environ = {} if env is None else {'FEATURE_RESEARCH_EXTRAS': env}
    assert flags.show_research_extras(secrets, environ) is want


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(scope='module')
def research_off(mp, tmp_path_factory):
    mp.delenv('FEATURE_RESEARCH_EXTRAS', raising=False)
    return run_app(mp, tmp_path_factory.mktemp('rx_off'))


def test_sleepers_is_the_last_research_section_by_default(research_off):
    at = research_off
    assert not at.exception
    tab = _research(at)
    heads = _heads(tab)
    assert heads == VISIBLE, heads                         # Sleepers, then only the V6.0 First Goal board
    assert not set(HIDDEN) & set(heads)
    text = _text(tab)
    assert 'Player Intelligence' in text and 'Historical Data Coverage' in text
    for gone in ('🏒 Matchup Center', 'Data updated:', 'Goalies: Goals Allowed now lives', 'Scheduled 30-minute snapshots',
                 'Universal day (YYYYMMDD', 'players evaluated. Pattern overlap'):
        assert gone not in text, gone
    assert not [d for d in tab.get('divider')] and not tab.get('file_uploader') and not tab.slider
    labels = [b.label for b in tab.get('download_button')]
    assert labels and set(labels) <= {f'Download {h} CSV' for h in VISIBLE}, labels   # no hidden-section downloads
    assert not [b for b in tab.button if b.label in ('↻ Refresh now', 'Fetch NHL player biographies and arenas')]


def test_everything_returns_with_flag_on(monkeypatch, tmp_path, research_off):
    monkeypatch.setenv('FEATURE_RESEARCH_EXTRAS', '1')
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    heads = _heads(_research(at))
    for h in VISIBLE + HIDDEN:
        assert h in heads, h
    assert heads.index('Top 10 Statistical Sleepers') < heads.index('Full NHL Slate')   # the top container renders first
    assert 'Universal day (YYYYMMDD' in _text(_research(at))
    # display-only: Home and the shared ranking state are identical either way
    off_home = next(t for t in research_off.tabs if t.label == '🏠 Home')
    on_home = next(t for t in at.tabs if t.label == '🏠 Home')
    assert _heads(off_home) == _heads(on_home)
    assert research_off.session_state['signals_ranked'].equals(at.session_state['signals_ranked'])


def test_ranking_state_writes_are_never_gated():
    """The live-ranking pipeline (Home's source when no snapshot exists) and the history job must run with the flag off."""
    tree = ast.parse((HERE / 'tabs' / 'research.py').read_text(encoding='utf-8'))
    parents = {}
    for node in ast.walk(tree):
        for ch in ast.iter_child_nodes(node):
            parents[ch] = node
    targets = {"st.session_state['signals_ranked']", "st.session_state['signals_day']", "st.session_state['v42_last_rank']",
               "st.session_state['v43_history_job']", 'ranked', '(_intel, _intel_warnings)'}
    calls = {'rank_players', 'intel_from_state', 'assign_statistical_ranks'}
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        tgt = ast.unparse(node.targets[0])
        fn = [n.func.id for n in ast.walk(node.value) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        hit = ({tgt} & targets) | (set(fn) & calls)
        if not hit:
            continue
        found |= hit
        p = parents.get(node)
        while p is not None:
            if isinstance(p, (ast.If, ast.IfExp)):
                assert '_rx' not in ast.unparse(p.test), (ast.unparse(node), ast.unparse(p.test))
            p = parents.get(p)
    critical = targets | calls
    assert found == set(critical), found
