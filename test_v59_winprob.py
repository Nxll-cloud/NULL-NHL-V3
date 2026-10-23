"""V5.9 favorite / model win estimate on Tonight's Board (winprob_v59): favorite chosen correctly, the pair sums to 100,
missing-data fallback, rendered inline on the board tile. Offline, through the real slate_results/model path."""
from datetime import datetime, timezone

import feature_flags_v58 as flags
import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import v55_ui as v5
import winprob_v59 as wp

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


def _row(pid, team, g_pg, s_pg, pos='C'):
    return {'Player ID': pid, 'Player': f'P{pid}', 'Team': team, 'Position': pos, 'Prior GP': 10, 'Goals/G Prior': g_pg, 'Shots/G L10': s_pg}


SLATE = [{'key': 'MTL@CHI', 'game_id': '2026020166', 'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T00:30:00Z', 'status': 'FUT'},
         {'key': 'TBL@COL', 'game_id': '2026020167', 'away': 'TBL', 'home': 'COL', 'start': '2026-10-24T02:00:00Z', 'status': 'FUT'}]


def _results(rows):
    return lstate.slate_results(SLATE, ng.priors_from_rankings(rows), {}, {}, {})


STRONG_MTL = [_row(i, 'MTL', 0.5, 4.0) for i in range(1, 7)] + [_row(10 + i, 'CHI', 0.2, 2.0) for i in range(6)] + \
             [_row(20 + i, 'TBL', 0.3, 3.0) for i in range(6)] + [_row(30 + i, 'COL', 0.3, 3.0) for i in range(6)]


def test_poisson_math_sums_to_one_and_is_symmetric():
    w, t, l = wp.regulation_probs(3.0, 3.0)
    assert abs(w + t + l - 1) < 1e-9 and abs(w - l) < 1e-9 and 0.1 < t < 0.2
    assert all(abs(x - 0.5) < 1e-9 for x in wp.win_prob(3.0, 3.0))
    pa, ph = wp.win_prob(3.6, 2.4)
    assert abs(pa + ph - 1) < 1e-12 and pa > 0.6
    # a live 2-goal lead with little time left is near-certain
    assert wp.win_prob(0.1, 0.1, lead=2)[0] > 0.98


def test_favorite_chosen_correctly_and_pair_sums_to_100():
    fav = wp.by_key(_results(STRONG_MTL))
    f = fav['MTL@CHI']
    assert f['team'] == 'MTL' and f['pct'] == f['p_away'] > 50 and f['p_away'] + f['p_home'] == 100
    assert f['xg_away'] > f['xg_home'] > 0
    g = fav['TBL@COL']   # identical rosters: coin flip, pair still 100
    assert g['p_away'] + g['p_home'] == 100 and g['pct'] == 50
    # flip the strengths: CHI becomes the favorite at the complementary number
    flipped = [dict(r, Team={'MTL': 'CHI', 'CHI': 'MTL'}.get(r['Team'], r['Team'])) for r in STRONG_MTL]
    h = wp.by_key(_results(flipped))['MTL@CHI']
    assert h['team'] == 'CHI' and h['pct'] == f['pct'] and h['p_home'] == f['p_away']


def test_missing_inputs_show_nothing():
    only_one_side = [r for r in STRONG_MTL if r['Team'] != 'CHI']
    fav = wp.by_key(_results(only_one_side))
    assert 'MTL@CHI' not in fav and 'TBL@COL' in fav
    assert wp.by_key([]) == {} and wp.pill(None) == '' and wp.legend({}) == ''
    res = _results(STRONG_MTL)[0]
    final = {'slate': res['slate'], 'result': dict(res['result'], phase='final')}
    ot = {'slate': res['slate'], 'result': dict(res['result'], phase='live', game=dict(res['result']['game'], period=4, ptype='OT', away_score=2, home_score=2))}
    nolive = {'slate': res['slate'], 'result': dict(res['result'], phase='live', game=dict(res['result']['game'], period=2, away_score=None, home_score=1))}
    assert wp.favorite(final) is None and wp.favorite(ot) is None and wp.favorite(nolive) is None


def test_live_uses_score_and_remaining_rates():
    res = _results(STRONG_MTL)[1]['result']
    live = dict(res, phase='live', remaining=5.0, team_rate={'TBL': 0.05, 'COL': 0.05}, team_mult={'TBL': 1.0, 'COL': 1.0},
                game=dict(res['game'], period=3, ptype='REG', away_score=1, home_score=3))
    f = wp.favorite({'slate': SLATE[1], 'result': live})
    assert f['team'] == 'COL' and f['pct'] >= 95 and f['phase'] == 'live' and f['xg_away'] == 0.25


def test_pill_renders_inline_on_board_tile():
    fav = wp.by_key(_results(STRONG_MTL))
    games = [dict(g) for g in SLATE]
    html = v5.scoreboard({'games': games, 'winprob': fav, 'starters': {}}, NOW)
    tiles = html.split('<div class="tile')[1:]
    assert len(tiles) == 2
    m = fav['MTL@CHI']
    assert f'<b>MTL {m["pct"]}%</b>' in tiles[0] and 'class="wpf"' in tiles[1]
    assert 'Model estimate, not odds' in tiles[0] and 'model win estimate' in html
    # inside the tile, after both team rows (not a separate section)
    assert tiles[0].index('class="wpf"') > tiles[0].rindex('class="row"')
    bare = v5.scoreboard({'games': games, 'winprob': {'TBL@COL': fav['TBL@COL']}, 'starters': {}}, NOW).split('<div class="tile')[1:]
    assert 'wpf' not in bare[0] and 'class="wpf"' in bare[1]
    assert 'wpf' not in v5.scoreboard({'games': games, 'starters': {}}, NOW)
    assert flags.show_win_prob(secrets={}, environ={}) is True
    assert flags.show_win_prob(secrets={'FEATURE_WIN_PROB': 'false'}, environ={}) is False
