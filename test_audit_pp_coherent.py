"""Audit P1.3: the live power play is priced once (team SITUATION_MULT['PP']) under MODEL_PP_COHERENT: the player's PP
split is pregame-only, live it is a neutral share ratio; PP shots count at EV xG. Flag off = the old stacking exactly."""
import pytest

import feature_flags_v58 as ff
import live_nextgoal_v56 as ng
import situational_v58 as sit
from test_v58_situational import AWAY, HOME, TEAMS, live_game, priors, sk


def ctx(coherent):
    c = sit.context(skaters={1: sk(), 2: sk(goals=8, shots=80, ppg=0, pps=0, pp_min=0.0)}, teams=TEAMS, parts=('pp',))
    return dict(c, pp_coherent=coherent)


def run(c, game):
    return ng.model(game, priors(), situ=sit.Situ(c))


def rec(res, pid):
    return next(r for r in res['players'] if r['pid'] == pid)


def pp_game(situation='1541'):   # away 5 v home 4: AWAY on the power play
    return dict(live_game(), situation=situation)


def test_flag_default_and_switches():
    assert ff.MODEL_PP_COHERENT is True and ff.model_pp_coherent(environ={}) is True
    assert ff.model_pp_coherent(environ={'MODEL_PP_COHERENT': '0'}) is False
    assert ff.model_pp_coherent(secrets={'MODEL_PP_COHERENT': 'false'}, environ={}) is False
    assert sit.layer(sit.context(), {}, False).pp_coherent is False and sit.layer(sit.context(), {}, True).pp_coherent


def test_pregame_is_unchanged_by_the_flag():
    g = ng.pregame_game(1, AWAY, HOME)
    a, b = run(ctx(False), g), run(ctx(True), g)
    assert [(p['pid'], p['lam_game'], p['p_next']) for p in a['players']] == [(p['pid'], p['lam_game'], p['p_next']) for p in b['players']]
    assert 'pp' in rec(a, 1)['situ']['applied'] and rec(a, 1)['situ'].get('pp_share') is None   # pregame: the PP split


def test_live_pp_does_not_re_add_pp_scoring_to_the_team():
    old, new = run(ctx(False), pp_game()), run(ctx(True), pp_game())
    # the share only re-splits the team: team rate == plain rates x the ratio WITHOUT the share (ratio_neutral)
    plain = {r['pid']: r['rate'] for r in ng.model(pp_game(), priors())['players']}
    expect = sum(plain[r['pid']] * (r['situ'].get('ratio_neutral') or r['situ']['ratio']) for r in new['players'] if r['team'] == AWAY)
    assert new['team_rate'][AWAY] == pytest.approx(expect)
    assert new['team_rate'][AWAY] == pytest.approx(sum(r['rate'] for r in new['players'] if r['team'] == AWAY))
    assert new['team_rate'][HOME] == pytest.approx(old['team_rate'][HOME])   # no PP split data on HOME
    bd = rec(new, 1)['situ']
    assert bd['pp_mode'] == 'live share' and bd['opp_factor'] is None
    ev, pp = bd['ev'], bd['pp']
    assert bd['pp_share'] == pytest.approx((pp / (ev + pp)) / sit.PP_GOAL_FRAC)
    assert rec(new, 2)['situ'].get('pp_share') in (None, 0.0) or rec(new, 2)['situ']['ratio'] == sit.RATIO_MIN
    # on the PP the PP specialist gets the bigger share of his team
    assert rec(new, 1)['p_next'] / new['p_team'][AWAY] > rec(old, 1)['p_next'] / old['p_team'][AWAY] - 1e-9


def test_live_even_strength_share_is_near_neutral():
    bd = rec(run(ctx(True), pp_game('1551')), 1)['situ']
    assert bd['pp_share'] == pytest.approx((bd['ev'] / (bd['ev'] + bd['pp'])) / (1 - sit.PP_GOAL_FRAC))
    assert 0.8 < bd['pp_share'] < 1.2
    assert rec(run(ctx(True), pp_game('1451')), 1)['situ']['pp_share'] == 1.0   # shorthanded -> 1


def test_pp_shot_xg_bonus_not_stacked_under_flag():
    g = pp_game()
    g['events'] = g['events'] + [{'eid': 9, 'kind': 'sog', 'period': 2, 'ptype': 'REG', 'secs': 250, 'shooter': 1, 'team': AWAY,
                                  'goalie': 99, 'strength': 'PP', 'shot_type': 'wrist', 'x': 75, 'y': 3,
                                  'xg': ng.shot_xg(75, 3, 89, 'wrist', 'PP'), 'xg_ev': ng.shot_xg(75, 3, 89, 'wrist', 'EV'), 'order': 9}]
    assert g['events'][-1]['xg'] > g['events'][-1]['xg_ev']
    old, new = rec(run(ctx(False), g), 1), rec(run(ctx(True), g), 1)
    assert new['xg_sog'] == pytest.approx(old['xg_sog'] - g['events'][-1]['xg'] + g['events'][-1]['xg_ev'])


def test_no_situ_is_the_v56_model_exactly():
    g = pp_game()
    assert ng.model(g, priors())['p_team'] == ng.model(g, priors(), situ=None)['p_team']


def test_backtest_result_recorded_alongside_baseline():
    import json
    from pathlib import Path
    d = json.loads((Path(__file__).parent / 'backtests' / 'audit_pp_2026-04-04.json').read_text())
    assert d['decision']['regression'] is False and d['decision']['flag_default'] == 'ON'
    assert d['decision']['log_loss_on'] <= d['decision']['log_loss_off']
