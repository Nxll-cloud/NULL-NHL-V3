"""Audit D1 (MODEL_D_ATTEMPTS): a defenceman's in-game shot pace also counts his missed and blocked attempts, capped at
D_ATT_CAP per game. Forwards and pregame are unchanged; flag off = the old SOG-only pace exactly."""
import json
from pathlib import Path

import pytest

import backtest_next_goal as bt
import feature_flags_v58 as ff
import live_nextgoal_v56 as ng
from test_v58_situational import AWAY, HOME, live_game, priors

ROOT = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.setattr(ng, 'D_ATTEMPTS', None)
    monkeypatch.delenv('MODEL_D_ATTEMPTS', raising=False)


def ev(eid, kind, shooter, team, secs):
    return {'eid': eid, 'kind': kind, 'period': 2, 'ptype': 'REG', 'secs': secs, 'shooter': shooter, 'team': team,
            'goalie': 88 if team == HOME else 99, 'strength': 'EV', 'shot_type': 'slap', 'x': 50, 'y': 10, 'xg': 0.03,
            'order': 10 + eid}


def d_game(misses=3, blocks=2, d_sog=1):
    g = live_game()
    extra = [ev(100 + i, 'miss', 4, HOME, 300 + i) for i in range(misses)] + \
            [ev(200 + i, 'block', 4, HOME, 400 + i) for i in range(blocks)] + \
            [ev(300 + i, 'sog', 4, HOME, 500 + i) for i in range(d_sog)] + \
            [ev(400, 'miss', 3, HOME, 520), ev(401, 'block', 2, AWAY, 530)]          # forwards' misses/blocks
    g['events'] = g['events'] + extra
    return g


def rec(res, pid):
    return next(r for r in res['players'] if r['pid'] == pid)


def test_flag_default_on_and_switches():
    assert ff.MODEL_D_ATTEMPTS is True and ff.model_d_attempts(environ={}) is True
    assert ff.model_d_attempts(environ={'MODEL_D_ATTEMPTS': '0'}) is False
    assert ff.model_d_attempts(secrets={'MODEL_D_ATTEMPTS': 'false'}, environ={}) is False
    assert ff.model_d_attempts(secrets={'MODEL_D_ATTEMPTS': 'false'}, environ={'MODEL_D_ATTEMPTS': 'on'}) is True


def test_switch_precedence(monkeypatch):
    assert ng.d_attempts_enabled() is True
    monkeypatch.setenv('MODEL_D_ATTEMPTS', 'off')
    assert ng.d_attempts_enabled() is False
    monkeypatch.setattr(ng, 'D_ATTEMPTS', True)          # app override (from secrets) wins over env
    assert ng.d_attempts_enabled() is True
    assert ng.d_attempts_enabled(False) is False         # explicit argument wins over everything
    assert ng.model(d_game(), priors())['d_attempts'] is True
    assert ng.model(d_game(), priors(), d_attempts=False)['d_attempts'] is False


def test_count_formula_and_cap():
    w, spa, cap = ng.D_ATT_WEIGHT, ng.D_SOG_PER_ATT, ng.D_ATT_CAP
    assert (w, spa, cap) == (0.5, 0.41, 6)
    assert ng.d_in_game_count(2, 5) == pytest.approx((1 - w) * 2 + w * spa * (2 + 3))
    assert ng.d_in_game_count(0, 0) == 0
    assert ng.d_in_game_count(1, 1 + cap + 20) == ng.d_in_game_count(1, 1 + cap)    # capped
    assert ng.d_in_game_count(3, 2) == ng.d_in_game_count(3, 3)                      # att < sog never negative
    assert ng.d_in_game_count(2, 9) > ng.d_in_game_count(2, 2)


def test_d_misses_and_blocks_raise_d_pace_forwards_unchanged():
    g = d_game()
    off, on = ng.model(g, priors(), d_attempts=False), ng.model(g, priors(), d_attempts=True)
    assert rec(on, 4)['att'] == 6 and rec(on, 4)['sog'] == 1
    assert rec(on, 4)['shot_rate'] > rec(off, 4)['shot_rate']
    assert rec(on, 4)['p_next'] / on['p_team'][HOME] > rec(off, 4)['p_next'] / off['p_team'][HOME]
    for pid in (1, 2, 3):                                # forwards: identical pace and rate (their misses don't count)
        assert rec(on, pid)['shot_rate'] == pytest.approx(rec(off, pid)['shot_rate'])
        assert rec(on, pid)['rate'] == pytest.approx(rec(off, pid)['rate'])
    elapsed = on['elapsed']
    expect = ng.pace_weight(elapsed) * ng.d_in_game_count(1, 6) / elapsed + (1 - ng.pace_weight(elapsed)) * rec(on, 4)['prior_pg'] / 60
    assert rec(on, 4)['shot_rate'] == pytest.approx(expect, rel=1e-3)


def test_one_blowout_is_capped():
    a = ng.model(d_game(misses=ng.D_ATT_CAP, blocks=0), priors(), d_attempts=True)
    b = ng.model(d_game(misses=ng.D_ATT_CAP + 10, blocks=5), priors(), d_attempts=True)
    assert rec(a, 4)['shot_rate'] == pytest.approx(rec(b, 4)['shot_rate'])


def test_flag_off_is_the_old_sog_only_pace():
    g = d_game()
    off = ng.model(g, priors(), d_attempts=False)
    e = off['elapsed']
    r = rec(off, 4)
    assert r['shot_rate'] == pytest.approx(ng.pace_weight(e) * r['sog'] / e + (1 - ng.pace_weight(e)) * r['prior_pg'] / 60, rel=1e-3)


def test_pregame_is_unchanged():
    g = ng.pregame_game(1, AWAY, HOME)
    a, b = ng.model(g, priors(), d_attempts=False), ng.model(g, priors(), d_attempts=True)
    assert [(p['pid'], p['lam_game'], p['p_next']) for p in a['players']] == [(p['pid'], p['lam_game'], p['p_next']) for p in b['players']]


def test_backtest_defaults_off_and_results_written_beside_the_baseline():
    import inspect
    assert inspect.signature(bt.run_backtest).parameters['d_attempts'].default is False
    assert inspect.signature(bt.replay_game).parameters['d_attempts'].default is False
    doc = json.loads((ROOT / 'backtests' / 'audit_d_attempts_2026-04-04.json').read_text())
    runs = {k: v['headline'] for k, v in doc['runs'].items()}
    base = json.loads((ROOT / 'backtests' / 'baseline_v56.json').read_text())['headline']
    assert runs['plain_off']['log_loss'] == base['log_loss']          # D1 off reproduces the stored baseline
    assert runs['app_D1']['log_loss'] <= runs['app_off']['log_loss']    # the ON default's justification
    assert runs['plain_D1']['log_loss'] <= runs['plain_off']['log_loss']
    assert all(r['log_loss_sog_share'] == base['log_loss_sog_share'] for r in runs.values())


def test_phase2_note_for_e2_and_app_wiring():
    card = (ROOT / 'MODEL_CARD.md').read_text()
    assert 'MODEL_D_ATTEMPTS' in card and 'E2' in card and 'Phase 2' in card
    assert 'ng.D_ATTEMPTS=np_flags.model_d_attempts(st.secrets)' in (ROOT / 'tabs' / 'live.py').read_text()
