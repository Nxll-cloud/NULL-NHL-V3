"""V5.6 next-goal model, poller and live-state tests (pure; no network)."""
import json
import math
from pathlib import Path

import pytest

import live_feed_v56 as lf
import live_nextgoal_v56 as ng
import live_state_v56 as lstate

F = Path(__file__).resolve().parent / 'test_fixtures_v56'


def play(eid, kind, period=1, t='05:00', shooter=11, team_id=1, goalie=91, x=80, y=0, sit='1551', side='right', stype='wrist', ptype='REG'):
    d = {'eventOwnerTeamId': team_id, 'goalieInNetId': goalie, 'xCoord': x, 'yCoord': y, 'shotType': stype, 'zoneCode': 'O'}
    d['scoringPlayerId' if kind == 'goal' else 'shootingPlayerId'] = shooter
    if goalie is None:
        d.pop('goalieInNetId')
    if x is None:
        d.pop('xCoord'), d.pop('yCoord')
    return {'eventId': eid, 'typeDescKey': kind, 'periodDescriptor': {'number': period, 'periodType': ptype}, 'timeInPeriod': t,
            'situationCode': sit, 'homeTeamDefendingSide': side, 'sortOrder': eid, 'details': d}


def payload(plays, state='LIVE', period=1, ptype='REG', remaining=900):
    spot = lambda pid, tid, pos, fn: {'playerId': pid, 'teamId': tid, 'positionCode': pos, 'firstName': {'default': fn}, 'lastName': {'default': 'X'}}
    return {'id': 1, 'gameDate': '2026-10-22', 'gameState': state, 'awayTeam': {'id': 1, 'abbrev': 'AAA', 'score': 0, 'sog': 0},
            'homeTeam': {'id': 2, 'abbrev': 'HHH', 'score': 0, 'sog': 0}, 'periodDescriptor': {'number': period, 'periodType': ptype},
            'clock': {'secondsRemaining': remaining, 'timeRemaining': f'{remaining // 60:02d}:{remaining % 60:02d}', 'inIntermission': False},
            'rosterSpots': [spot(11, 1, 'C', 'A1'), spot(12, 1, 'D', 'A2'), spot(21, 2, 'L', 'H1'), spot(91, 2, 'G', 'HG'), spot(92, 1, 'G', 'AG')],
            'plays': plays}


PRIORS = {11: {'name': 'A1 X', 'team': 'AAA', 'pos': 'C', 'gp': 10, 'goals': 5, 'sog': 30, 'form': 80, 'source': 'season'},
          21: {'name': 'H1 X', 'team': 'HHH', 'pos': 'L', 'gp': 10, 'goals': 1, 'sog': 15, 'form': 20, 'source': 'season'}}


# ---------------------------------------------------------------- xG
def test_xg_closer_and_central_is_higher():
    assert ng.shot_xg(85, 0, 89) > ng.shot_xg(50, 0, 89) > ng.shot_xg(50, 35, 89)


def test_xg_shot_type_strength_and_bounds():
    base = ng.shot_xg(70, 5, 89, 'wrist', 'EV')
    assert ng.shot_xg(70, 5, 89, 'tip-in', 'EV') > base
    assert ng.shot_xg(70, 5, 89, 'wrist', 'PP') > base > ng.shot_xg(70, 5, 89, 'wrist', 'SH')
    assert ng.XG_MIN <= ng.shot_xg(-80, 40, 89) <= ng.XG_MAX
    assert ng.shot_xg(0, 0, 89, 'wrist', 'EN') <= ng.XG_MAX_EN


def test_xg_missing_coordinates_default():
    assert ng.shot_xg(None, None, 89) == ng.XG_DEFAULT


# ---------------------------------------------------------------- shrinkage / priors / blend
def test_shrinkage_k50():
    assert ng.shrunk_sh(0, 0) == pytest.approx(ng.LEAGUE_SH)
    assert ng.shrunk_sh(5, 10) == pytest.approx((5 + 50 * 0.10) / 60)
    assert ng.shrunk_sh(50, 100) < 0.5


def test_pace_weight_moves_to_in_game():
    assert ng.pace_weight(0) == 0 and ng.pace_weight(30) == pytest.approx(0.5) and ng.pace_weight(600) > 0.9


def test_form_multiplier_bounded_and_optional():
    assert ng.form_mult(None) == 1.0 and ng.form_mult(0) == 0.9 and ng.form_mult(100) == pytest.approx(1.1)
    assert ng.form_mult(500) == pytest.approx(1.1) and ng.form_mult(-3) == 0.9


def test_priors_from_rankings():
    rows = [{'Player ID': '8478402', 'Player': 'C McDavid', 'Team': 'edm', 'Position': 'C', 'Prior GP': 8, 'Goals/G Prior': 0.5,
             'Shots/G L10': 3.5, 'Form %': 70}, {'Player ID': None}]
    p = ng.priors_from_rankings(rows)
    assert list(p) == [8478402] and p[8478402]['goals'] == 4 and p[8478402]['sog'] == 28 and p[8478402]['team'] == 'EDM'


# ---------------------------------------------------------------- model
def _sum_p(res):
    return sum(p['p_next'] for p in res['players'])


def test_competing_risk_sums_to_at_most_one():
    g = ng.parse_pbp(payload([play(1, 'shot-on-goal'), play(2, 'shot-on-goal', shooter=21, team_id=2, goalie=92, x=-80)]))
    res = ng.model(g, PRIORS)
    assert 0 < _sum_p(res) <= 1 and _sum_p(res) == pytest.approx(res['p_any'])
    assert res['p_any'] + res['p_none'] == pytest.approx(1)
    for t in ('AAA', 'HHH'):
        assert sum(p['p_next'] for p in res['players'] if p['team'] == t) == pytest.approx(res['p_team'][t])


def test_zero_shots_live_uses_prior():
    res = ng.model(ng.parse_pbp(payload([])), PRIORS)
    assert res['phase'] == 'live' and res['p_any'] > 0
    assert res['players'][0]['pid'] == 11          # better prior shooter ranks first


def test_no_season_data_falls_back_to_league_prior():
    res = ng.model(ng.parse_pbp(payload([play(1, 'shot-on-goal')])), {})
    assert res['players'] and all(p['p_next'] >= 0 for p in res['players']) and _sum_p(res) <= 1


def test_goalies_never_listed_as_shooters():
    res = ng.model(ng.parse_pbp(payload([play(1, 'shot-on-goal')])), PRIORS)
    assert not {91, 92} & {p['pid'] for p in res['players']}


def test_empty_net_raises_opponent_rate():
    base = ng.parse_pbp(payload([play(1, 'shot-on-goal', sit='1551')]))
    en = ng.parse_pbp(payload([play(1, 'shot-on-goal', sit='1560')]))   # home goalie pulled
    rb, re_ = ng.model(base, PRIORS), ng.model(en, PRIORS)
    assert re_['p_team']['AAA'] > rb['p_team']['AAA']


def test_empty_net_shot_without_goalie_is_parsed():
    g = ng.parse_pbp(payload([play(1, 'goal', goalie=None, sit='1560')]))
    assert g['events'][0]['goalie'] is None and g['events'][0]['strength'] == 'EN'


def test_missing_coordinates_event_kept():
    g = ng.parse_pbp(payload([play(1, 'shot-on-goal', x=None)]))
    assert g['events'][0]['xg'] == ng.XG_DEFAULT


def test_overtime_horizon_and_multiplier():
    g = ng.parse_pbp(payload([play(1, 'shot-on-goal', period=4, ptype='OT')], period=4, ptype='OT', remaining=120))
    el, rem = ng.elapsed_remaining(g)
    assert rem == pytest.approx(2.0) and el == pytest.approx(63.0)
    assert ng.model(g, PRIORS)['team_mult']['AAA'] == pytest.approx(ng.OT_RATE_MULT)


def test_shootout_excluded():
    pl = [play(1, 'shot-on-goal'), play(2, 'goal', period=5, ptype='SO')]
    g = ng.parse_pbp(payload(pl, period=5, ptype='SO'))
    assert len(g['events']) == 1 and ng.phase(g) == 'shootout'
    assert ng.model(g, PRIORS)['p_any'] == 0


def test_final_has_no_next_goal_and_pregame_has_full_horizon():
    assert ng.model(ng.parse_pbp(payload([play(1, 'goal')], state='OFF')), PRIORS)['p_any'] == 0
    pre = ng.model(ng.pregame_game(1, 'AAA', 'HHH'), PRIORS)
    assert pre['phase'] == 'pregame' and pre['remaining'] == 60 and 0 < pre['p_any'] < 1


def test_use_form_changes_only_when_enabled():
    g = ng.parse_pbp(payload([play(1, 'shot-on-goal')]))
    a, b = ng.model(g, PRIORS), ng.model(g, PRIORS, use_form=True)
    pa = {p['pid']: p['p_next'] for p in a['players']}
    pb = {p['pid']: p['p_next'] for p in b['players']}
    assert pa != pb and _sum_p(b) <= 1


# ---------------------------------------------------------------- rerank / dedupe / truncate
def test_rerank_deltas():
    ps = [{'pid': 1}, {'pid': 2}, {'pid': 3}]
    assert ng.rerank(ps, None) == {1: 1, 2: 2, 3: 3} and all(p['delta'] == 0 for p in ps)
    ps2 = [{'pid': 3}, {'pid': 1}, {'pid': 4}]
    ng.rerank(ps2, {1: 1, 2: 2, 3: 3})
    assert [p['delta'] for p in ps2] == [2, -1, None]
    assert [ng.arrow(p['delta']) for p in ps2] == ['up', 'down', 'new'] and ng.arrow(0) == 'same'


def test_dedupe_by_event_id():
    g = ng.parse_pbp(payload([play(1, 'shot-on-goal'), play(1, 'shot-on-goal'), play(2, 'shot-on-goal')]))
    assert len(g['events']) == 2
    merged, added = ng.merge_events({e['eid']: e for e in g['events']}, g['events'] + [dict(g['events'][0], eid=3)])
    assert len(merged) == 3 and added == 1


def test_truncate_rebuilds_score_and_clock():
    pl = [play(1, 'shot-on-goal'), play(2, 'goal', t='10:00'), play(3, 'shot-on-goal', period=2, t='02:00')]
    g = ng.parse_pbp(payload(pl, state='OFF'))
    t = ng.truncate(g, 2)
    assert t['state'] == 'LIVE' and t['away_score'] == 1 and t['secs_remaining'] == 600 and len(t['events']) == 2
    assert ng.truncate(g, 99)['state'] == 'OFF'


# ---------------------------------------------------------------- poller
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_poller_cadence_backoff_last_good_and_stop():
    clock, calls = Clock(), []
    live = payload([play(1, 'shot-on-goal')])
    responses = [live, ConnectionError('down'), dict(live, plays=live['plays'] + [play(2, 'shot-on-goal')]), dict(live, gameState='OFF')]

    def fetch(gid):
        calls.append(gid)
        r = responses[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    p = ng.Poller(1, fetch, clock=clock, rand=lambda: 1.0)
    g1 = p.poll()
    assert len(g1['events']) == 1 and p.next_due == 1030
    assert p.poll() is g1 and len(calls) == 1          # not due: no fetch
    clock.t = 1030
    assert p.poll() is g1 and p.failures == 1 and p.next_due == 1030 + 30   # error keeps last good, backs off
    clock.t = 1060
    assert len(p.poll()['events']) == 2 and p.new_events == 1 and p.failures == 0
    clock.t = 1090
    assert ng.phase(p.poll()) == 'final' and not p.due() and p.next_due == float('inf')


def test_backoff_exponential_with_jitter_and_cap():
    assert ng.backoff(0, rand=lambda: 0.0) == 15 and ng.backoff(2, rand=lambda: 1.0) == 120
    assert ng.backoff(20, rand=lambda: 1.0) == 600


def test_cadence():
    assert ng.cadence('live') == 30 and ng.cadence('final') is None
    assert ng.cadence('pregame', 10) == 120 and ng.cadence('pregame', 300) == 600


# ---------------------------------------------------------------- real fixtures
def test_demo_fixture_real_and_small():
    raw = lf.load_demo()
    g = ng.parse_pbp(raw)
    assert g['away'] == 'MIN' and g['home'] == 'CGY' and ng.phase(g) == 'final' and len(g['events']) > 50
    for f in F.glob('*.json'):
        assert f.stat().st_size < 100 * 1024, f


def test_live_fixture_model_runs():
    g = ng.parse_pbp(json.loads((F / 'pbp_live_2026020164.json').read_text()))
    res = ng.model(g)
    assert res['phase'] == 'live' and 0 < _sum_p(res) <= 1 + 1e-9


def test_trim_payload_preserves_parse():
    raw = json.loads((F / 'pbp_2026020154.json').read_text())
    assert ng.parse_pbp(ng.trim_payload(raw)) == ng.parse_pbp(raw)


def test_p_anytime():
    assert ng.p_anytime(0) == 0 and ng.p_anytime(-1) == 0 and ng.p_anytime(1) == pytest.approx(1 - math.exp(-1))


# ---------------------------------------------------------------- live feed / live state
def test_parse_scores_fixture():
    s = lf.parse_scores(json.loads((F / 'score_20261022_live.json').read_text()))
    assert s['2026020162']['label'] == 'Final' and s['2026020164']['state'] == 'LIVE'
    assert s['2026020159']['label'] == 'Final/OT' and s['2026020165']['label'] == 'P2 INT'


def test_period_label():
    assert lf.period_label(2, 'REG', {'timeRemaining': '04:45'}) == 'P2 04:45'
    assert lf.period_label(2, 'REG', {'inIntermission': True}) == 'P2 INT'
    assert lf.period_label(5, 'SO', {}) == 'SO' and lf.period_label(4, 'OT', {}).startswith('OT')


def test_fetch_never_hits_network_in_tests():
    def boom(*a, **k):
        raise ConnectionError('offline')
    with pytest.raises(Exception):
        lf.fetch_pbp(1, boom)


def test_needs_pbp():
    assert lstate.needs_pbp('LIVE') and lstate.needs_pbp('CRIT') and lstate.needs_pbp('OFF') and lstate.needs_pbp('FINAL')
    assert not lstate.needs_pbp('FUT') and not lstate.needs_pbp(None)


def _slate(gid='1'):
    return [{'game_id': gid, 'key': 'k' + gid, 'away': 'AAA', 'home': 'HHH', 'start': '2026-10-22T23:00:00Z', 'status': 'FUT'}]


def test_slate_results_arrow_bases_and_missing_pbp_note():
    mem = {}
    pre = lstate.slate_results(_slate(), PRIORS, {}, {}, mem)
    assert pre[0]['result']['rank_basis'] == 'pregame prior' and all(p['delta'] == 0 for p in pre[0]['result']['players'])
    g = ng.parse_pbp(payload([play(1, 'shot-on-goal', shooter=21, team_id=2, goalie=92, x=-85)]))
    mem2 = {}
    live = lstate.slate_results(_slate(), PRIORS, {'1': {'state': 'LIVE'}}, {'1': g}, mem2)
    assert live[0]['result']['rank_basis'] == 'vs pregame prior'
    g2 = ng.parse_pbp(payload([play(1, 'shot-on-goal', shooter=21, team_id=2, goalie=92, x=-85), play(2, 'shot-on-goal')]))
    live2 = lstate.slate_results(_slate(), PRIORS, {'1': {'state': 'LIVE'}}, {'1': g2}, mem2)
    assert live2[0]['result']['rank_basis'] == 'vs previous update'
    miss = lstate.slate_results(_slate(), PRIORS, {'1': {'state': 'LIVE'}}, {}, {})
    assert 'unavailable' in miss[0]['note']


def test_strip_and_tile_scores():
    g = ng.parse_pbp(payload([play(1, 'goal')]))
    res = lstate.slate_results(_slate('2') + _slate('1'), PRIORS, {'1': {'state': 'LIVE'}}, {'1': g}, {})
    items = lstate.strip_items(res)
    assert [i['phase'] for i in items] == ['live', 'pregame'] and items[0]['leader'] is not None and items[1]['label'] == 'Pregame'
    tiles = lstate.tile_scores(res)
    assert set(tiles) == {'k1'} and tiles['k1']['phase'] == 'live'
