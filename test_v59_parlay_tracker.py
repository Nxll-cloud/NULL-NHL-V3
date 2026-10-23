"""V5.9 live four-leg parlay tracker (parlay_tracker_v59): top-4-by-model legs locked at first puck drop, goal marking
from the SAME polled play-by-play, regulation-only rules (OT goal does not count, shootout ignored), running status,
celebration and busted states, fallback, and no new poll. All offline fixtures (TEST FIXTURES, never shown in the app)."""
import re
from pathlib import Path

import feature_flags_v58 as flags
import live_nextgoal_v56 as ng
import live_state_v56 as lstate
import parlay_v58 as parlay
import parlay_tracker_v59 as pt

HERE = Path(__file__).resolve().parent


def _row(pid, team, g_pg, s_pg, pos='C'):
    return {'Player ID': pid, 'Player': f'P{pid}', 'Team': team, 'Position': pos, 'Prior GP': 10, 'Goals/G Prior': g_pg, 'Shots/G L10': s_pg}


SLATE = [{'key': 'MTL@CHI', 'game_id': '2026020166', 'away': 'MTL', 'home': 'CHI', 'start': '2026-10-24T00:00:00Z', 'status': 'FUT'},
         {'key': 'TBL@COL', 'game_id': '2026020167', 'away': 'TBL', 'home': 'COL', 'start': '2026-10-24T01:00:00Z', 'status': 'FUT'}]
# MTL 1, 2 and COL 31 are the three strongest; TBL 21 fourth; one-per-team would take CHI 11 instead of MTL 2.
ROWS = ([_row(1, 'MTL', .6, 4.5), _row(2, 'MTL', .55, 4.2), _row(3, 'MTL', .1, 1.0)] + [_row(11, 'CHI', .3, 2.5), _row(12, 'CHI', .1, 1.0)]
        + [_row(21, 'TBL', .5, 4.0), _row(22, 'TBL', .1, 1.0)] + [_row(31, 'COL', .65, 4.8), _row(32, 'COL', .1, 1.0)])


def _ev(eid, pid, team, period, secs, kind='goal', ptype=None):
    return {'eid': eid, 'kind': kind, 'period': period, 'ptype': ptype or ('OT' if period == 4 else 'SO' if period == 5 else 'REG'), 'secs': secs,
            'shooter': pid, 'team': team, 'goalie': 99, 'strength': 'EV', 'shot_type': 'wrist', 'x': 70, 'y': 0, 'xg': .1, 'order': eid}


def _game(gid, away, home, events, period=2, ptype='REG', state='LIVE', secs_remaining=600):
    goals = [e for e in events if e['kind'] == 'goal' and e['ptype'] != 'SO']
    return {'game_id': gid, 'date': '2026-10-23', 'start': None, 'state': state, 'away': away, 'home': home,
            'away_score': sum(e['team'] == away for e in goals), 'home_score': sum(e['team'] == home for e in goals),
            'away_sog': 10, 'home_sog': 10, 'period': period, 'ptype': ptype, 'secs_remaining': secs_remaining, 'intermission': False,
            'situation': '1551', 'roster': {}, 'events': events}


def _results(pbp=None, scores=None):
    return lstate.slate_results(SLATE, ng.priors_from_rankings(ROWS), scores or {}, pbp or {}, {})


def _locked(pbp=None):
    store = {}
    pt.resolve(store, '2026-10-23', _results(), ROWS)                     # pregame pick
    res = _results(pbp)
    return pt.resolve(store, '2026-10-23', res, ROWS, now='2026-10-24T00:05:00+00:00'), res, store


def test_legs_are_exactly_top_four_by_model_chance_not_one_per_team():
    res = _results()
    legs = pt.top_by_model(res, ROWS)
    cands = parlay.candidates(res, ROWS)
    assert [l['pid'] for l in legs] == [c['pid'] for c in cands[:4]]
    assert {l['pid'] for l in legs} == {1, 2, 21, 31}
    old = parlay.build(res, ROWS)                                         # the V5.8 rule: one leg per team on 2 games
    assert old['per'] == 'team' and 11 in [l['pid'] for l in old['legs']] and 2 not in [l['pid'] for l in old['legs']]


def test_lock_at_first_puck_drop_and_snapshot_reuse():
    data, res, store = _locked()
    assert data['source'] == 'model'
    pre = [l['pid'] for l in data['legs']]
    live = _results({'2026020166': _game('2026020166', 'MTL', 'CHI', [_ev(1, 1, 'MTL', 1, 300)], period=1)})
    d1 = pt.resolve(store, '2026-10-23', live, ROWS, now='t')
    assert d1['locked'] and [l['pid'] for l in d1['legs']] == pre
    # the model changes a lot later: the locked legs do not reshuffle
    rows2 = [dict(r, **{'Goals/G Prior': .9}) if r['Player ID'] == 12 else r for r in ROWS]
    d2 = pt.resolve(store, '2026-10-23', lstate.slate_results(SLATE, ng.priors_from_rankings(rows2), {}, {}, {}), rows2)
    assert [l['pid'] for l in d2['legs']] == pre
    # a fresh session after puck drop reuses the frozen pre-game snapshot (accuracy log entry)
    entry = {'frozen_at': '2026-10-23T17:00:00+00:00', 'first_start': '2026-10-24T00:00:00+00:00',
             'players': [[31, 'P31', 'COL', .5, 1, 1], [12, 'P12', 'CHI', .45, 2, 2], [1, 'P1', 'MTL', .4, 3, 3], [21, 'P21', 'TBL', .3, 4, 4], [2, 'P2', 'MTL', .2, 5, 5]]}
    d3 = pt.resolve({}, '2026-10-23', live, ROWS, (), entry, now='t')
    assert d3['source'] == 'snapshot' and [l['pid'] for l in d3['legs']] == [31, 12, 1, 21] and d3['legs'][1]['p'] == .45
    late = dict(entry, frozen_at='2026-10-24T00:30:00+00:00')                # frozen after puck drop: not used
    d4 = pt.resolve({}, '2026-10-23', live, ROWS, (), late, now='t')
    assert d4['source'] == 'rebuilt' and len(d4['legs']) == 4
    assert pt.resolve(store, '2026-10-24', _results(), ROWS)['locked'] is False  # new slate date starts fresh


def test_leg_marked_scored_with_time_and_score():
    g = _game('2026020166', 'MTL', 'CHI', [_ev(1, 11, 'CHI', 1, 300), _ev(2, 3, 'MTL', 1, 900), _ev(3, 1, 'MTL', 2, 761)])
    data, res, _ = _locked({'2026020166': g})
    s = pt.states(data, {'2026020166': g}, res)
    assert s[1] == {'status': 'hit', 'goal': 'P2 12:41 · MTL 2-1', 'note': 'Regulation goal'}
    assert s[2]['status'] == 'live' and s[21]['status'] == 'pending'
    html = pt.section_html(data, s, {})
    assert '🚨 P2 12:41 · MTL 2-1' in html and 'npt-leg s-hit' in html and '✓ Scored' in html and '1 of 4 legs hit' in html


def test_ot_goal_not_counted_and_legs_dead_at_ot():
    g = _game('2026020166', 'MTL', 'CHI', [_ev(1, 11, 'CHI', 2, 100), _ev(2, 3, 'MTL', 3, 500), _ev(3, 1, 'MTL', 4, 120)],
              period=4, ptype='OT', state='OFF', secs_remaining=0)
    s1 = pt.leg_state({'pid': 1, 'team': 'MTL'}, g)
    assert s1['status'] == 'dead' and 'OT goal does not count' in s1['note'] and s1['goal'] is None
    in_ot = _game('2026020166', 'MTL', 'CHI', [_ev(1, 11, 'CHI', 2, 100), _ev(2, 3, 'MTL', 3, 500)], period=4, ptype='OT')
    s2 = pt.leg_state({'pid': 2, 'team': 'MTL'}, in_ot)
    assert s2['status'] == 'dead' and 'OT' in s2['note']
    # still in the 3rd period: alive
    p3 = _game('2026020166', 'MTL', 'CHI', [], period=3)
    assert pt.leg_state({'pid': 2, 'team': 'MTL'}, p3)['status'] == 'live'
    # final in regulation without a goal: dead; a regulation goal before OT still counts
    fin = _game('2026020166', 'MTL', 'CHI', [_ev(1, 11, 'CHI', 2, 100)], period=3, state='OFF', secs_remaining=0)
    assert pt.leg_state({'pid': 2, 'team': 'MTL'}, fin)['status'] == 'dead'
    reg_then_ot = _game('2026020166', 'MTL', 'CHI', [_ev(1, 2, 'MTL', 1, 61), _ev(2, 11, 'CHI', 3, 1000), _ev(3, 2, 'MTL', 4, 30)], period=4, ptype='OT', state='OFF')
    assert pt.leg_state({'pid': 2, 'team': 'MTL'}, reg_then_ot)['goal'] == 'P1 01:01 · MTL 1-0'


def test_shootout_goals_are_ignored():
    payload = {'id': 2026020166, 'gameState': 'OFF', 'awayTeam': {'id': 8, 'abbrev': 'MTL', 'score': 3}, 'homeTeam': {'id': 16, 'abbrev': 'CHI', 'score': 2},
               'periodDescriptor': {'number': 5, 'periodType': 'SO'}, 'clock': {},
               'rosterSpots': [{'playerId': 1, 'teamId': 8, 'positionCode': 'C', 'firstName': {'default': 'P'}, 'lastName': {'default': '1'}}],
               'plays': [{'eventId': 9, 'typeDescKey': 'goal', 'sortOrder': 9, 'timeInPeriod': '00:00',
                          'periodDescriptor': {'number': 5, 'periodType': 'SO'}, 'details': {'scoringPlayerId': 1, 'eventOwnerTeamId': 8}}]}
    g = ng.parse_pbp(payload)
    s = pt.leg_state({'pid': 1, 'team': 'MTL'}, g)
    assert s['status'] == 'dead' and s['goal'] is None
    # even if a SO goal event slipped through, it never counts
    g2 = _game('2026020166', 'MTL', 'CHI', [_ev(1, 1, 'MTL', 5, 0, ptype='SO')], period=5, ptype='SO', state='LIVE')
    assert pt.leg_state({'pid': 1, 'team': 'MTL'}, g2)['status'] == 'dead'


def test_two_of_four_status_and_busted_state():
    g1 = _game('2026020166', 'MTL', 'CHI', [_ev(1, 1, 'MTL', 1, 200)], period=2)
    g2 = _game('2026020167', 'TBL', 'COL', [_ev(1, 31, 'COL', 1, 400)], period=2)
    pbp = {'2026020166': g1, '2026020167': g2}
    data, res, _ = _locked(pbp)
    s = pt.states(data, pbp, res)
    sm = pt.summary(s)
    assert (sm['hit'], sm['pending'], sm['dead'], sm['overall'], sm['text']) == (2, 2, 0, 'live', '2 of 4 legs hit')
    html = pt.section_html(data, s, {})
    assert '2 of 4 legs hit' in html and '2 pending' in html and '0 dead' in html and 'Regulation only' in html and 'Some sportsbooks count' in html
    g2f = _game('2026020167', 'TBL', 'COL', [_ev(1, 31, 'COL', 1, 400)], period=3, state='OFF', secs_remaining=0)
    s2 = pt.states(data, {'2026020166': g1, '2026020167': g2f}, res)
    sm2 = pt.summary(s2)
    assert sm2['overall'] == 'busted' and sm2['dead'] == 1
    html2 = pt.section_html(data, s2, {})
    assert 'Parlay busted' in html2 and 'npt-leg s-dead' in html2 and 'P21: Final · no regulation goal' in html2


def test_all_four_hit_celebration():
    g1 = _game('2026020166', 'MTL', 'CHI', [_ev(1, 1, 'MTL', 1, 200), _ev(2, 2, 'MTL', 3, 100)], period=3)
    g2 = _game('2026020167', 'TBL', 'COL', [_ev(1, 31, 'COL', 1, 400), _ev(2, 21, 'TBL', 2, 50)], period=2)
    pbp = {'2026020166': g1, '2026020167': g2}
    data, res, _ = _locked(pbp)
    s = pt.states(data, pbp, res)
    assert pt.summary(s)['overall'] == 'won'
    html = pt.section_html(data, s, {})
    assert 'pt-won' in html and 'npt-win' in html and 'All 4 legs hit' in html and '4 of 4 legs hit' in html
    css = (HERE / 'assets' / 'v58.css').read_text()
    assert '@keyframes nptShine' in css and re.search(r'prefers-reduced-motion:reduce\)\{\.v55 \.npt-win\{animation:none', css)
    assert not re.search(r'url\(', css.split('V5.9 live parlay tracker')[1])                # CSS only, no new assets


def test_fallback_to_top_four_next_goal_targets():
    res = [{'slate': SLATE[0], 'score': {}, 'result': {'phase': 'pregame', 'players': [
        {'pid': i, 'name': f'N{i}', 'team': 'MTL' if i % 2 else 'CHI', 'lam_game': 0, 'p_next': i / 100, 'goals': 0} for i in range(1, 7)]}}]
    assert pt.top_by_model(res) == []
    d = pt.resolve({}, '2026-10-23', res, None, out_ids={6})
    assert d['source'] == 'fallback' and [l['pid'] for l in d['legs']] == [5, 4, 3, 2]
    assert 'Fallback: top 4 live next-goal targets' in pt.section_html(d, {}, {})
    assert 'No parlay pick yet' in pt.section_html(pt.resolve({}, '2026-10-23', [], None), {}, {})


def test_uses_existing_poll_no_new_interval():
    src = (HERE / 'parlay_tracker_v59.py').read_text()
    code = src.split('"""', 2)[2]
    for banned in ('st.fragment', 'run_every', 'st_autorefresh', 'import requests', 'urlopen', 'time.sleep', 'setInterval', 'fetch_pbp', 'Poller(', 'import streamlit'):
        assert banned not in code, banned
    home = (HERE / 'tabs' / 'home.py').read_text()
    assert 'ptrack.states(_pl_data,_v56_pbp,_v56_results)' in home
    found = sorted(m for p in [HERE / 'app.py', *(HERE / 'tabs').glob('*.py')] for m in re.findall(r"run_every=\(?'[^']+'", p.read_text()))
    # the tracker adds no timer: this is exactly the set already on main (1.5s = Next Goal DEMO replay, offline only)
    assert found == ["run_every='1.5s'", "run_every='10s'", "run_every='30s'", "run_every=('3s'", "run_every=('45s'"]
    assert (HERE / 'app.py').read_text().count('st_autorefresh(') == 1
    app = (HERE / 'app.py').read_text()
    watch = app[app.index('def np_scorer_watch'):app.index('with _np_scorer_slot')]
    assert 'ptrack.phase_signature(_pbp)' in watch and 'v56_collect(False)' in watch


def test_flag_default_on():
    assert flags.show_parlay_tracker(secrets={}, environ={}) is True
    assert flags.show_parlay_tracker(secrets={}, environ={'FEATURE_PARLAY_TRACKER': '0'}) is False
