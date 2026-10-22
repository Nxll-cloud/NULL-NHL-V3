import pandas as pd

import player_intelligence_v54 as pi
from signals import build_signals
from storylines_v36 import build_storylines, combined_table
from storyline_v38 import merge_history
from history_v386 import merge_multi_history
from ranking_integrity_v3871 import validate_statistical_ranks
from storyline_v37 import select_storyline_watch
from storyline_v387 import separate_leaders
from v54_testkit import slate

DAY = '2026-10-22'


def ranked():
    return pd.DataFrame(slate()['rankings'])


def legacy_research(r, day, metadata=None):
    """The V5.2 Research pipeline exactly as it was inlined in app.py."""
    signals = build_signals(r, day, metadata)
    storylines = build_storylines(r, metadata if metadata is not None else pd.DataFrame(), day)
    combined = combined_table(r, signals, storylines)
    combined = merge_history(combined, None)
    combined = merge_multi_history(combined, None)
    validate_statistical_ranks(combined)
    return separate_leaders(combined)


def test_research_output_unchanged_vs_legacy_pipeline():
    r = ranked()
    res = pi.build_intelligence(r, DAY)
    legacy = legacy_research(r, DAY)
    assert pi.pick_identity(pi.four_picks(res)) == pi.pick_identity(pi.four_picks({'v387': legacy}))
    assert res['v387']['leaders'].keys() == legacy['leaders'].keys()


def test_home_and_research_share_one_function():
    r = ranked()
    state = {'signals_ranked': r, 'signals_day': DAY}
    home, _ = pi.intelligence_from_state(state, DAY)
    research, _ = pi.intelligence_from_state(dict(state), DAY)
    assert pi.pick_identity(pi.four_picks(home)) == pi.pick_identity(pi.four_picks(research))
    assert [k for k, _ in pi.LEADER_LABELS] == ['statistical', 'storyline', 'overlap', 'longshots']


def test_missing_inputs():
    assert pi.intelligence_from_state({}, DAY) == (None, [])
    assert pi.intelligence_from_state({'signals_ranked': ranked(), 'signals_day': '2000-01-01'}, DAY)[0] is None
    assert pi.build_intelligence(pd.DataFrame(), DAY) is None
    assert set(pi.four_picks(None).values()) == {None}


def test_bad_metadata_upload_warns():
    import io
    _, warn = pi.read_uploaded_metadata(io.StringIO('a,b\n1,2\n'))
    assert 'Player ID' in warn


def test_intel_row_solo_keeps_one_card_per_grid():
    import ui_theme_v53 as ui
    assert ui.intel_row(['<i>a</i>']) == '<div class="np-intel-row"><i>a</i></div>'
    assert 'np-intel-solo' in ui.intel_row(['<i>a</i>'], solo=True)
    import pathlib
    assert '.np-intel-row.np-intel-solo{grid-template-columns:1fr' in pathlib.Path(ui.__file__).read_text()
