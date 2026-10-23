"""Audit P1.4: a shots-share baseline next to every accuracy number + the pass/fail rule
(model log loss <= baseline log loss)."""
import math
import pandas as pd
import accuracy_v58 as acc
import backtesting as bt
import prediction_tracker_v54 as trk
from test_v58_accuracy import SNAP, SCORE, NOW, scored_entry, getter_for


def test_baseline_keeps_team_goal_totals_and_splits_by_shots():
    players = [[1, 'A', 'BOS', 0.30, 1, 1], [2, 'B', 'BOS', 0.10, 2, 2], [3, 'C', 'TOR', 0.20, 3, 3]]
    rows = [{'Player ID': 1, 'Team': 'BOS', 'Prior GP': 9, 'Shots/G L10': 1.0},
            {'Player ID': 2, 'Team': 'BOS', 'Prior GP': 9, 'Shots/G L10': 3.0},
            {'Player ID': 3, 'Team': 'TOR', 'Prior GP': 9, 'Shots/G L10': 2.0}]
    b = acc.shots_share_baseline(players, rows)
    lam = lambda ps: sum(-math.log(1 - p) for p in ps)
    assert abs(lam([b['1'], b['2']]) - lam([0.30, 0.10])) < 1e-3      # same team goal expectation as the model
    assert b['2'] > b['1']                                             # more shots -> bigger share
    assert abs(b['3'] - 0.20) < 1e-3                                   # lone skater keeps the whole team total


def test_entry_carries_baseline_and_summary_reports_pass_fail():
    e = scored_entry()
    assert e['baseline']['method'] == acc.BASELINE_TAG and len(e['baseline']['p']) == e['n_players']
    s = e['summary']
    assert s['baseline']['top_n'] == 10 and s['baseline']['calibration']['n'] == e['n_players']
    assert s['beats_baseline'] == (s['calibration']['log_loss'] <= s['baseline']['calibration']['log_loss'])
    assert acc.baseline_check({'log_loss': 0.5}, {'log_loss': 0.5}) is True
    assert acc.baseline_check({'log_loss': 0.51}, {'log_loss': 0.5}) is False
    assert acc.baseline_check(None, {'log_loss': 0.5}) is None


def test_old_entry_gets_baseline_from_its_snapshot_and_card_shows_it(tmp_path):
    e = scored_entry()
    old = {k: v for k, v in e.items() if k != 'baseline'}
    old['summary'] = {k: v for k, v in e['summary'].items() if k not in ('baseline', 'beats_baseline')}
    b = acc.attach_baseline(old, SNAP)
    assert b['baseline'] == e['baseline'] and b['summary']['baseline'] == e['summary']['baseline']
    assert acc.attach_baseline(dict(old, compacted=True), SNAP).get('baseline') is None   # compacted: cannot rebuild
    acc.save_entry(e, tmp_path / 'log')
    html = acc.card_html(acc.view(NOW, getter_for({}), tmp_path / 'log', tmp_path / 'snaps'))
    assert '(shots-share ' in html and 'shots-share baseline <b>' in html
    assert 'Shots-share baseline: night log loss' in html and ('PASS' in html or 'FAIL' in html)
    assert 'rule: model log loss ≤ baseline' in html


def test_card_without_baseline_says_na():
    assert 'n/a' in acc._baseline_line(None, None, {'night': {}, 'pooled': {}})


def test_trend_pools_baseline_only_where_both_are_scored():
    e1 = scored_entry()
    e2 = dict(scored_entry(), day='2026-10-21')
    e2['summary'] = {k: v for k, v in e2['summary'].items() if k != 'baseline'}
    t = acc.trend([e1, e2])
    assert t['baseline']['top_n'] == 10 and t['baseline']['calibration']['nights'] == 1
    assert t['baseline']['model_calibration']['n'] == e1['summary']['calibration']['n']


def test_research_backtest_adds_shots_baseline_row():
    scored = pd.DataFrame({'Player ID': [1, 2, 3], 'Baseline Form Index': [3, 2, 1], 'V3.2 Adjusted Index': [3, 2, 1],
                           bt.SHOTS_COL: [0.5, 4.0, 1.0], 'Scored': [0, 1, 0]})
    m = bt.top_k_metrics(scored, (1,))
    row = m[m['Model'] == bt.BASELINE_MODEL].iloc[0]
    assert row['Hit rate'] == 1 and m[m['Model'] == 'V3.2'].iloc[0]['Hit rate'] == 0
    assert bt.BASELINE_MODEL not in set(bt.top_k_metrics(scored.drop(columns=[bt.SHOTS_COL]), (1,))['Model'])


def test_tracker_baseline_is_graded_but_never_in_pick_rates():
    ranked = pd.DataFrame({'Player ID': [1, 2, 3], 'Player': ['A', 'B', 'C'], 'Team': ['BOS', 'BOS', 'TOR'],
                           'Statistical rank': [1, 2, 3], 'V3.2 Adjusted Index': [3, 2, 1], 'Shots/G L5': [0.5, 4.0, 1.0]})
    rows = trk.build_prediction_rows(ranked, cutoff=1, band=0, baseline_n=1)
    base = [r for r in rows if r['source'] == trk.BASELINE_SOURCE]
    assert [r['player_id'] for r in base] == ['2'] and base[0]['is_pick'] == 0
    conn = trk.connect(':memory:')
    trk.save_predictions(conn, '2026-10-22', rows, n_games=1)
    trk.record_game_results(conn, '2026-10-22', 'G1', [{'player': 'B', 'player_id': 2, 'team': 'BOS', 'goals': 1}], final=True)
    ev = trk.evaluate_slate(conn, '2026-10-22')
    assert ev['picks'] == 1 and not ev['hits']                    # the baseline hit is not a model hit
    assert ev['baseline'] == {'picks': 1, 'hits': 1, 'rate': 1.0}
    assert all(m['reason'] != 'baseline' for m in ev['near_misses'])
    assert trk.baseline_rollup([ev])['rate'] == 1.0 and trk.rolling([ev])['rate'] == 0.0
