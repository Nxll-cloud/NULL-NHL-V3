"""Audit win% fix (MODEL_WINPROB_V2): 18 dressed skaters, team GF/GA normalisation, home ice, real tie / OT-SO rates,
range; flag default and V5.9 path unchanged; team/summary parsed into the situational context."""
import json
from pathlib import Path

import feature_flags_v58 as flags
import situational_v58 as sit
import winprob_v59 as wp

ROOT = Path(__file__).resolve().parent


def _p(pid, team, lam, pos='C', prior=2.0):
    return {'pid': pid, 'team': team, 'lam_game': lam, 'pos': pos, 'prior_pg': prior, 'gp': 10, 'name': f'P{pid}'}


def _res(players, pool='roster', phase='pregame', **game):
    g = {'away': 'MTL', 'home': 'CHI', 'away_score': None, 'home_score': None, 'period': None, 'ptype': None} | game
    return {'phase': phase, 'pool': pool, 'players': players, 'game': g, 'team_rate': {}, 'team_mult': {}, 'remaining': 60.0}


EVEN = [_p(i, 'MTL', 0.15) for i in range(18)] + [_p(100 + i, 'CHI', 0.15) for i in range(18)]


def test_league_constants_documented_values():
    assert abs(wp.REG_TIE_RATE - 0.2205) < 1e-3 and abs(wp.OT_HOME - 0.5253) < 1e-3
    assert 1.03 < wp.HOME_MULT < 1.045 and abs(wp.HOME_MULT * wp.LEAGUE_GPG - wp.LEAGUE_HOME_GPG) < 1e-9
    # tie inflation reproduces the real tie rate at league-average scoring
    _, t, _ = wp.regulation_probs(wp.LEAGUE_AWAY_GPG, wp.LEAGUE_HOME_GPG)
    assert abs(t * wp.TIE_INFLATE - wp.REG_TIE_RATE) < 1e-9 and wp.TIE_INFLATE > 1


def test_win_prob_v2_sums_to_one_and_home_gets_ot_edge():
    pa, ph = wp.win_prob_v2(3.0, 3.0)
    assert abs(pa + ph - 1) < 1e-12 and ph > pa      # equal teams: the home OT/SO share tips it
    pa1, _ = wp.win_prob(3.0, 3.0)
    assert abs(pa1 - 0.5) < 1e-12                     # V5.9 path unchanged (50/50)
    # live with no time left: no tie inflation, a lead is a lead
    assert wp.win_prob_v2(1e-9, 1e-9, lead=1, tie_scale=0.0)[0] > 0.999


def test_home_ice_applied_pregame():
    e = wp.expected_goals_v2(_res(EVEN))
    assert e['lam']['CHI'] > e['lam']['MTL'] and abs(e['lam']['CHI'] / e['lam']['MTL'] - wp.HOME_MULT / wp.AWAY_MULT) < 1e-9
    f = wp.favorite_v2({'result': _res(EVEN), 'slate': {'key': 'MTL@CHI'}})
    assert f['team'] == 'CHI' and f['p_away'] + f['p_home'] == 100 and f['v2'] is True


def test_dressed_top_12f_6d_by_toi_when_no_roster():
    ps = [_p(i, 'MTL', 0.2, 'C') for i in range(16)] + [_p(50 + i, 'MTL', 0.1, 'D') for i in range(9)] + \
         [_p(100 + i, 'CHI', 0.15) for i in range(12)] + [_p(150 + i, 'CHI', 0.1, 'D') for i in range(6)]
    toi = {i: {'ev_toi_pg': 900 - i} for i in range(16)} | {50 + i: {'ev_toi_pg': 1200 - i} for i in range(9)}
    d = wp.dressed(ps, 'priors', toi)
    mtl = [p['pid'] for p in d if p['team'] == 'MTL']
    assert len(mtl) == 18 and sorted(mtl) == list(range(12)) + list(range(50, 56))
    assert len(wp.dressed(ps, 'roster', toi)) == len(ps)   # real roster: everyone dressed counts
    # no TOI -> shots/g prior proxy
    ps2 = [_p(i, 'MTL', 0.2, 'C', prior=float(i)) for i in range(14)]
    assert sorted(p['pid'] for p in wp.dressed(ps2, 'priors', {})) == list(range(2, 14))
    e = wp.expected_goals_v2(_res(ps, pool='priors'), {'skaters': toi})
    assert e['n'] == {'MTL': 18, 'CHI': 18}


def test_team_gf_ga_normalisation_and_range():
    ctx = {'teams': {'MTL': {'gf_pg': 3.8, 'ga_pg': 2.4, 'team_gp': 70}, 'CHI': {'gf_pg': 2.4, 'ga_pg': 3.8, 'team_gp': 70}}}
    e = wp.expected_goals_v2(_res(EVEN), ctx)
    assert e['team_norm'] and e['lam']['MTL'] > e['lam']['CHI']   # strong road team overturns home ice
    tr = wp.team_rates('MTL', 'CHI', ctx['teams'])
    k = sum(tr) / (0.15 * 18 * 2)
    assert abs(e['lam']['MTL'] - (wp.TEAM_W * tr[0] + (1 - wp.TEAM_W) * k * 2.7) * wp.AWAY_MULT) < 1e-9
    f = wp.favorite_v2({'result': _res(EVEN), 'slate': {'key': 'MTL@CHI'}}, ctx)
    assert f['team'] == 'MTL' and f['lo'] <= f['pct'] <= f['hi'] and f['lo'] < f['hi']
    assert 'range' in wp.pill(f) and '52.5% home' in wp.pill(f)
    assert wp.team_rates('MTL', 'XXX', ctx['teams']) is None


def test_live_and_ot_and_by_key_flag():
    live = _res(EVEN, phase='live', away_score=1, home_score=1, period=3, ptype='REG')
    live.update(team_rate={'MTL': 0.05, 'CHI': 0.05}, team_mult={'MTL': 1.0, 'CHI': 1.0}, remaining=10.0)
    f = wp.favorite_v2({'result': live, 'slate': {'key': 'MTL@CHI'}})
    assert f['phase'] == 'live' and f['team'] == 'CHI'
    ot = _res(EVEN, phase='live', away_score=1, home_score=1, period=4, ptype='OT')
    assert wp.expected_goals_v2(ot) is None
    rows = [{'result': _res(EVEN), 'slate': {'key': 'MTL@CHI'}}]
    assert 'v2' not in wp.by_key(rows)['MTL@CHI'] and wp.by_key(rows, True)['MTL@CHI']['v2']


def test_flag_default_follows_backtest_rule():
    bt = json.loads((ROOT / 'backtests' / 'audit_winprob_2026-04-04.json').read_text())
    assert flags.MODEL_WINPROB_V2 is (not bt['decision']['regression'])
    assert flags.model_winprob_v2(environ={'MODEL_WINPROB_V2': '1'}) is True
    assert flags.model_winprob_v2(environ={'MODEL_WINPROB_V2': '0'}) is False


def test_team_summary_parsed_into_context():
    t = sit.parse_teams([], [], [{'id': 8, 'triCode': 'MTL'}],
                        [{'teamId': 8, 'goalsForPerGame': 3.1, 'goalsAgainstPerGame': 2.9, 'gamesPlayed': 40}])
    assert t['MTL'] == {'gf_pg': 3.1, 'ga_pg': 2.9, 'team_gp': 40.0}
    seen = []

    def getter(url, params=None):
        seen.append(url)
        if url.endswith('/team'):
            return {'data': [{'id': 8, 'triCode': 'MTL'}]}
        if url.endswith('team/summary'):
            return {'data': [{'teamId': 8, 'goalsForPerGame': 3.0, 'goalsAgainstPerGame': 3.2, 'gamesPlayed': 5}]}
        return {'data': []}
    ctx = sit.fetch_context('2026-10-23', '20262027', getter=getter)
    assert any(u.endswith('team/summary') for u in seen) and ctx['teams']['MTL']['gf_pg'] == 3.0
    assert sit.opp_factor('MTL', 'CHI', ctx['teams']) is None   # GF/GA alone never feeds the next-goal model
