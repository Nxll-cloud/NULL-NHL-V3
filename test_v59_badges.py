"""V5.9: scored-tonight badges on Storylines, Live Next Goal, Edge Flags, parlay legs, long shot and Research Top 10 lists
(display only), plus the Storylines multiselect tap-target CSS. Offline."""
import json

import pandas as pd

import longshot_v58 as ls
import parlay_v58 as parlay
import scorers_tonight_v58 as sctn
import storylines_v58 as sl
from v54_testkit import HERE, run_app

F = HERE / 'test_fixtures_v56'
EXTRA = json.loads((F / 'slate_extra_2026020164.json').read_text())['games']
PBP = {'score.json': F / 'score_20261022_live.json', '2026020164.json': F / 'pbp_live_2026020164.json',
       '2026020154.json': F / 'pbp_2026020154.json'}

REC = {'day': '2026-10-22', 'demo': False, 'names': {'scorer guy': 8471}, 'players': {
    8471: {'player_id': 8471, 'name': 'Scorer Guy', 'team': 'BOS', 'game': 'BOS @ NSH', 'game_id': '1', 'goals': 2,
           'events': [{'time': 'P1 05:00', 'strength': 'PP', 'ppg': True, 'eng': False, 'shg': False},
                      {'time': 'P2 10:00', 'strength': 'EV', 'ppg': False, 'eng': False, 'shg': False}]}}}


def _c(pid, name, p=.2):
    return {'pid': pid, 'name': name, 'team': 'BOS', 'opp': 'NSH', 'home': False, 'game': 'g1', 'game_id': '1', 'start': None,
            'phase': 'live', 'p': p, 'p_next': None, 'np_rank': None, 'form': None, 'model_rank': 1, 'why': ['gematria'], 'signals': []}


def _tab(at, label):
    return next(t for t in at.tabs if t.label == label)


def _html(block):
    return ' '.join([m.value for m in block.markdown] + [h.value for h in block.get('html')])


# ------------------------------------------------------------------------------------------------ helpers
def test_badge_for_by_pid_and_name():
    assert 'class="npsc' in sctn.badge_for(REC, pid=8471) and '2G' in sctn.badge_for(REC, pid='8471')
    assert 'class="npsc' in sctn.badge_for(REC, name='Scorer Guy')
    assert sctn.badge_for(REC, pid=999) == '' and sctn.badge_for(None, pid=8471) == ''
    assert sctn.badge_for({'players': {}}, pid=8471) == ''
    assert 'demo' in sctn.badge_for(dict(REC, demo=True), pid=8471)


def test_mark_frame_by_id_adds_tonight_column_and_drops_id():
    df = pd.DataFrame({'Player': ['Scorer Guy', 'Other Guy'], 'Player ID': [8471, 1]})
    out = sctn.mark_frame_by_id(df, REC, 'Player ID')
    assert sctn.COL in out.columns and 'Player ID' not in out.columns
    assert out[sctn.COL].tolist()[0].startswith('🚨') and out[sctn.COL].tolist()[1] == ''
    plain = sctn.mark_frame_by_id(df, None, 'Player ID')
    assert 'Player ID' not in plain.columns and sctn.COL not in plain.columns


# ------------------------------------------------------------------------------------------------ html parts
def test_parlay_leg_badge_only_for_scorer():
    legs = [_c(8471, 'Scorer Guy'), _c(2, 'Quiet Guy')]
    html = parlay.section_html({'legs': legs, 'joint': .04, 'per': 'game'}, {}, {}, scored=REC)
    assert html.count('class="npsc') == 1 and 'Scorer Guy<span class="npsc' in html
    assert 'class="npsc' not in parlay.section_html({'legs': legs, 'joint': .04, 'per': 'game'}, {}, {})


def test_long_shot_badge_only_for_scorer():
    assert 'Scorer Guy<span class="npsc' in ls.section_html(_c(8471, 'Scorer Guy'), record=REC)
    assert 'class="npsc' not in ls.section_html(_c(2, 'Quiet Guy'), record=REC)


def test_storylines_row_badge_and_no_double_badge():
    r = {'tag': 'REVENGE GAMES', 'player': 'Scorer Guy', 'pid': 8471, 'team': 'BOS', 'opp': 'NSH', 'story': 'x', 'detail': 'd',
         'source': 'NHL', 'link': ''}
    row = sl.row_html(r, ('Top pick',), '50%', sctn.badge_for(REC, r['pid'], r['player']))
    assert row.count('class="npsc') == 1 and '<b>Scorer Guy<span class="npsc' in row
    assert sctn.mark_html(row, REC).count('class="npsc') == 1           # auto-marker never doubles an explicit badge
    assert 'class="npsc' not in sl.row_html(dict(r, pid=2, player='Quiet Guy'), (), '—', sctn.badge_for(REC, 2, 'Quiet Guy'))


# ------------------------------------------------------------------------------------------------ app (fixture slate)
def test_badges_in_live_next_goal_edge_flags_and_research_top10(monkeypatch, tmp_path):
    at = run_app(monkeypatch, tmp_path, extra_games=EXTRA, pbp_files=PBP)
    assert not at.exception
    for label in ('⏱ Live Next Goal', '🚩 Edge Flags'):
        html = _html(_tab(at, label))
        assert 'class="npsc' in html, label
        assert '</span><span class="npsc' not in html.replace('class="npsc demo', 'class="npsc'), label   # no double badge
    frames = [d.value for d in _tab(at, '📊 Research').dataframe]
    assert any(sctn.COL in f.columns and f[sctn.COL].astype(str).str.startswith('🚨').any() for f in frames)
    assert not any('Player ID' in f.columns for f in frames if sctn.COL in f.columns)
    ef = [d.value for d in _tab(at, '🚩 Edge Flags').dataframe]
    assert not any('pid' in f.columns for f in ef)


# ------------------------------------------------------------------------------------------------ CSS
def test_multiselect_inner_targets_44px_on_mobile():
    mob = (HERE / 'assets' / 'mobile.css').read_text()
    assert '[data-testid="stMultiSelect"] input[role="combobox"]{min-height:44px!important;min-width:44px!important' in mob
    assert '[data-testid="stMultiSelect"] [role="group"][data-rac] > button{min-width:44px!important;min-height:44px!important' in mob
