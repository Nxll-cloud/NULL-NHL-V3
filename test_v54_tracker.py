import json

import pandas as pd
import pytest

import prediction_tracker_v54 as trk
from live_scoring_future import GoalEvent
from v54_testkit import slate

DAY = '2026-10-22'


@pytest.fixture
def conn(tmp_path):
    c = trk.connect(tmp_path / 't.sqlite')
    yield c
    c.close()


def ranked():
    return pd.DataFrame(slate()['rankings'])


def seed(conn, day=DAY, n_games=3):
    rows = trk.build_prediction_rows(ranked(), games=slate()['games'])
    trk.save_predictions(conn, day, rows, n_games=n_games)
    return rows


def test_build_rows_cutoff_band_and_game_ids():
    rows = trk.build_prediction_rows(ranked(), games=slate()['games'])
    stats = [r for r in rows if r['source'] == 'Stats']
    assert sum(r['is_pick'] for r in stats) == trk.PICK_CUTOFF and len(stats) == trk.PICK_CUTOFF + trk.WATCH_BAND
    assert all(r['game_id'] for r in stats)


def test_leader_row_dedupes_with_top_n():
    r = ranked()
    top = r.sort_values('Statistical rank').iloc[0]
    leaders = {'statistical': {'player_id': top['Player ID'], 'player': top['Player'], 'team': top['Team'], 'form': 1}}
    rows = trk.build_prediction_rows(r, leaders=leaders, games=slate()['games'])
    mine = [x for x in rows if x['player_key'] == 'id:' + str(top['Player ID']) and x['source'] == 'Stats']
    assert len(mine) == 1 and mine[0]['rank'] == 0


def test_round_trip_idempotent_and_lock_never_overwritten(conn):
    rows = seed(conn)
    n = len(trk.predictions(conn, DAY))
    seed(conn)
    assert len(trk.predictions(conn, DAY)) == n == len(rows)
    assert trk.lock_slate(conn, DAY) is True and trk.lock_slate(conn, DAY) is False
    res = trk.save_predictions(conn, DAY, rows[:2])
    assert res['status'] == 'locked' and len(trk.predictions(conn, DAY)) == n
    with pytest.raises(trk.TrackerError):
        trk.lock_slate(conn, '2001-01-01')
    assert trk.save_predictions(conn, '2026-10-23', [])['status'] == 'empty'


def test_pending_until_final_and_excluded_from_rates(conn):
    seed(conn)
    ev = trk.evaluate_slate(conn, DAY)
    assert ev['status'] == 'pending' and trk.rolling([ev])['picks'] == 0


def test_hits_misses_unpredicted_and_near_misses(conn):
    rows = seed(conn, n_games=3)
    picks = [r for r in rows if r['is_pick']]
    watch = [r for r in rows if not r['is_pick']]
    hit, assist_only = picks[0], picks[1]
    w = watch[0]
    for gid in {r['game_id'] for r in rows}:
        sc = []
        if gid == hit['game_id']:
            sc.append({'player': hit['player'], 'player_id': hit['player_id'], 'team': hit['team'], 'goals': 1})
        if gid == assist_only['game_id']:
            sc.append({'player': assist_only['player'], 'player_id': assist_only['player_id'], 'team': assist_only['team'], 'goals': 0, 'assists': 2})
        if gid == w['game_id']:
            sc.append({'player': w['player'], 'player_id': w['player_id'], 'team': w['team'], 'goals': 1})
            sc.append({'player': 'Totally Unranked', 'team': w['team'], 'goals': 2})
        trk.record_game_results(conn, DAY, gid, sc)
    ev = trk.evaluate_slate(conn, DAY)
    assert ev['status'] == 'evaluated' and ev['picks'] == trk.PICK_CUTOFF
    assert [h['player'] for h in ev['hits']] == [hit['player']]
    reasons = {n['player']: n['reason'] for n in ev['near_misses']}
    assert 'assist' in reasons[assist_only['player']] and 'just outside' in reasons[w['player']]
    assert {u['player'] for u in ev['unpredicted']} >= {'Totally Unranked', w['player']}
    assert ev['by_source']['Stats']['hits'] == 1
    assert trk.rolling([ev])['rate'] == pytest.approx(1 / trk.PICK_CUTOFF)


def test_partial_slate_only_scores_final_games(conn):
    rows = seed(conn, n_games=3)
    gid = rows[0]['game_id']
    trk.record_game_results(conn, DAY, gid, [])
    ev = trk.evaluate_slate(conn, DAY)
    assert ev['picks'] == sum(1 for r in rows if r['is_pick'] and r['game_id'] == gid)


def test_record_merges_duplicates_and_name_only(conn):
    n = trk.record_game_results(conn, DAY, '2026020154', [{'player': 'Ann Lee', 'goals': 1}, {'player': 'ann  lee', 'goals': 1},
                                                          {'player': '', 'goals': 1}, {'player_id': '8470001', 'player': 'X', 'goals': 1, 'assists': 1}])
    a = trk.actuals(conn, DAY)
    assert n == 2 and a[a['player'] == 'Ann Lee']['goals'].iloc[0] == 2
    with pytest.raises(trk.TrackerError):
        trk.record_game_results(conn, DAY, '', [])


def test_resolve_names_unique_only():
    roster = [{'player': 'Élias Pettersson'}, {'player': 'Elias Pettersson'}, {'player': 'Nick Suzuki'}]
    m, u = trk.resolve_names(['nick suzuki', 'Elias Pettersson', 'Nobody', ' '], roster)
    assert [x['player'] for x in m] == ['Nick Suzuki'] and u == ['Elias Pettersson', 'Nobody']


def test_ingest_goal_events_dedupes():
    import sqlite3  # noqa: F401
    ev = GoalEvent(game_id='5', period=1, time='01:00', team='BOS', scorer='A B', scorer_id='1', assists=(('C D', '2'),), event_id='9')
    by_game = trk.events_to_scorers([ev, ev, {'game_id': '5', 'period': 2, 'time': '02:00', 'team': 'BOS', 'scorer': 'A B', 'scorer_id': '1'}, 'junk'])
    rec = {s['player']: s for s in by_game['5']}
    assert rec['A B']['goals'] == 2 and rec['C D']['assists'] == 1


def test_ingest_into_store(conn):
    ev = GoalEvent(game_id='5', period=1, time='01:00', team='BOS', scorer='A B', scorer_id='1')
    assert trk.ingest_goal_events(conn, DAY, [ev], final=True) == 1 and trk.final_games(conn, DAY) == {'5'}


def test_parse_landing_goals():
    payload = {'id': 7, 'gameState': 'OFF', 'summary': {'scoring': [{'periodDescriptor': {'number': 1}, 'goals': [
        {'firstName': {'default': 'A'}, 'lastName': {'default': 'B'}, 'playerId': 1, 'timeInPeriod': '03:00', 'teamAbbrev': {'default': 'BOS'},
         'eventId': 55, 'assists': [{'firstName': {'default': 'C'}, 'lastName': {'default': 'D'}, 'playerId': 2}]}, 'junk']}]}}
    events, final = trk.parse_landing_goals(payload)
    assert final and events[0].scorer == 'A B' and events[0].assists == (('C D', '2'),) and events[0].game_id == '7'
    with pytest.raises(trk.TrackerError):
        trk.parse_landing_goals('x')
    with pytest.raises(trk.TrackerError):
        trk.fetch_final_goals('1', fetch=lambda p: (_ for _ in ()).throw(ConnectionError()))


def test_shrinkage_bounds_and_badges():
    p0 = trk.PRIOR_RATE
    assert trk.adjustment(1, 2, p0) == 0.0  # below MIN_SAMPLE
    for k, n in [(0, 50), (50, 50), (3, 3), (0, 3)]:
        assert -trk.ADJ_CAP <= trk.adjustment(k, n, p0) <= trk.ADJ_CAP
    assert trk.shrunk_rate(0, 0, p0) == p0
    assert trk.badge_for(3, 4, p0) == 'Hot when predicted' and trk.badge_for(0, 5, p0) == 'Keeps missing'
    assert trk.badge_for(1, 4, p0) is None and trk.badge_for(2, 2, p0) is None
    assert trk.pooled_rate([]) == p0


def test_toggle_off_returns_same_object_and_on_is_bounded():
    r = ranked()
    recs = pd.DataFrame([{'player_key': 'id:' + str(r.iloc[0]['Player ID']), 'Adjustment': -0.05}])
    assert trk.apply_track_record(r, recs, enabled=False) is r
    on = trk.apply_track_record(r, recs, enabled=True)
    assert on is not r and on['Track adj'].between(-0.05, 0.05).all() and len(on) == len(r)
    assert 'Track adj' not in r.columns


def test_player_records_trade_uses_latest_team():
    evals = [{'status': 'evaluated', 'day': '1', 'hits': [{'player': 'P', 'player_key': 'id:1', 'team': 'AAA'}], 'misses': [], 'picks': 1, 'by_source': {}},
             {'status': 'evaluated', 'day': '2', 'hits': [], 'misses': [{'player': 'P', 'player_key': 'id:1', 'team': 'BBB'}], 'picks': 1, 'by_source': {}}]
    recs = trk.player_records(evals)
    assert recs.iloc[0]['Team'] == 'BBB' and recs.iloc[0]['Picks'] == 2


def test_export_import_whitelist_and_locked_skip(conn, tmp_path):
    seed(conn)
    text = trk.export_json(conn)
    other = trk.connect(tmp_path / 'o.sqlite')
    trk.save_predictions(other, DAY, seed(other)[:1])
    trk.lock_slate(other, DAY)
    data = json.loads(text)
    data['predictions'][0]['evil); DROP TABLE slates;--'] = 1
    trk.import_json(other, json.dumps(data))
    assert len(trk.predictions(other, DAY)) == 1  # locked slate kept as is
    assert trk.slate_info(other, DAY)['locked']
    with pytest.raises(trk.TrackerError):
        trk.import_json(other, json.dumps({'schema': 'other'}))
    other.close()


def test_db_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv('PLAYBOOK_TRACKER_DB', str(tmp_path / 'x.sqlite'))
    assert str(trk.db_path()) == str(tmp_path / 'x.sqlite')
