"""V5.9 Numbers TOP PICK tie-break regression (real 2026-10-23 slate, real data path).

Bug: tabs/numbers.py built the tie-break lookup from ranking rows ({'Player ID', ...}, no 'pid' / 'lam_game'), so it
was {'None': 0.0} and every tie inside equal gematria points fell to alphabetical order (e.g. Newhook over Anderson).
Fix: numbers_v58_ui.model_p_from_results reads the next-goal model's player records (lstate.slate_results ->
result['players'] with pid + lam_game), the same records Home's parlay / Long Shot use. Model P is a tie-break only."""
import json
from pathlib import Path

import pandas as pd

import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import matchup_center_v54 as mc
import numboard_v56 as nb
import numbers_v58_ui as numv58
from numerology_v48 import analyze_game, universal_day
from player_targets_v49 import slate_targets

FIX = json.loads((Path(__file__).parent / 'test_fixtures_v59' / 'numbers_2026-10-23.json').read_text())
DAY = FIX['day']
TEAM_NAMES = {'MTL': 'Montreal Canadiens', 'CHI': 'Chicago Blackhawks', 'TBL': 'Tampa Bay Lightning', 'COL': 'Colorado Avalanche'}
NAZAR, DEL_MASTRO, ANDERSON, NEWHOOK = '8483493', '8482807', '8476981', '8481618'


def _rows():
    return pd.DataFrame(FIX['rankings']).to_dict('records')


def _results():
    """Exactly the live tab's path: ranking rows -> priors -> slate games -> slate_results (pregame, no feeds)."""
    return lstate.slate_results(mc.slate_games(FIX['games']), ng.priors_from_rankings(_rows()), {}, {}, {})


def _boards():
    an = [analyze_game(g, DAY, TEAM_NAMES) for g in FIX['games']]
    return nb.slate_boards(slate_targets(an, pd.DataFrame(FIX['rankings']), DAY))


def test_ranking_rows_have_no_model_keys_so_old_lookup_was_empty():
    rows = _rows()
    assert rows and all('pid' not in r and 'lam_game' not in r for r in rows)
    old = {str(r.get('pid')): ng.p_anytime(r.get('lam_game', 0)) for r in rows}   # the pre-fix expression
    assert set(old) == {'None'}


def test_model_p_lookup_is_built_from_next_goal_records():
    mp = numv58.model_p_from_results(_results())
    ids = {str(int(r['Player ID'])) for r in _rows()}
    assert len(mp) >= 60 and 'None' not in mp and set(mp) <= ids
    assert all(0.0 < p < 1.0 for p in mp.values())
    assert mp[NAZAR] > mp[DEL_MASTRO] and mp[ANDERSON] > mp[NEWHOOK]
    assert numv58.model_p_from_results(None) == {} and numv58.model_p_from_results([{'result': {}}]) == {}


def test_ties_inside_equal_points_go_to_higher_model_chance():
    mp = numv58.model_p_from_results(_results())
    boards = _boards()
    picks = numv58.top_picks_per_team([b['all_players'] for b in boards], mp)
    assert set(picks) == {'MTL', 'CHI', 'TBL', 'COL'}
    allp = [p for b in boards for p in b['all_players']]
    for team, ps in picks.items():
        top = ps[0]
        tied = [p for p in allp if p['team'] == team and p['threat_raw'] == top['threat_raw']]
        assert all(p['threat_raw'] <= top['threat_raw'] for p in allp if p['team'] == team)
        assert mp[str(top['player_id'])] == max(mp.get(str(p['player_id']), -1) for p in tied)
    # Anderson and Newhook both match the day (English 7) with equal points: the higher model chance wins, not the name.
    by = {str(p['player_id']): p for p in allp}
    assert by[ANDERSON]['threat_raw'] == by[NEWHOOK]['threat_raw'] and by[ANDERSON]['day'] == by[NEWHOOK]['day'] == ['English']
    assert numv58.pick_order(by[ANDERSON], mp) < numv58.pick_order(by[NEWHOOK], mp)
    assert numv58.pick_order(by[ANDERSON], {}) > numv58.pick_order(by[NEWHOOK], {})   # without model P: alphabetical
    # Nazar vs Del Mastro, constructed at equal points (their real points differ now that Reverse no longer counts).
    tie = [{**by[DEL_MASTRO], 'threat_raw': 3}, {**by[NAZAR], 'threat_raw': 3}]
    assert sorted(tie, key=lambda p: numv58.pick_order(p, mp))[0]['player_id'] == by[NAZAR]['player_id']


def test_model_p_never_changes_points_or_tiers():
    boards = _boards()
    before = [(p['player'], p['threat_raw'], p['threat'], p['tier']) for b in boards for p in b['all_players']]
    html = numv58.boards_html(boards, universal_day(DAY), numv58.model_p_from_results(_results()))
    after = [(p['player'], p['threat_raw'], p['threat'], p['tier']) for b in boards for p in b['all_players']]
    assert before == after == [(p['player'], p['threat_raw'], p['threat'], p['tier']) for b in _boards() for p in b['all_players']]
    assert all(t == round(100 * r / 6) for _, r, t, _ in after)
    assert html.count('TOP PICK') >= 4


def test_float_and_int_ids_hit_the_same_key():
    mp = {'8477935': 0.24}
    for pid in (8477935, '8477935', 8477935.0, '8477935.0'):
        assert numv58.pick_order({'player_id': pid, 'threat_raw': 3, 'player': 'X'}, mp)[1] == -0.24
    assert numv58.model_p_from_results([{'result': {'players': [{'pid': 8477935.0, 'lam_game': 0.3}]}}]) == {'8477935': ng.p_anytime(0.3)}
