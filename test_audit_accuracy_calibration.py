"""Audit fix (Phase 1 item 1): the accuracy log keeps every priced skater and reports Brier, log loss and reliability."""
import json
import math

import pytest

import accuracy_v58 as acc
from test_v58_accuracy import NOW, SCORE, SNAP, scored_entry


def test_calibration_math_by_hand():
    c = acc.calibration([(0.5, 1), (0.5, 0), (0.1, 0), (0.2, 1)])
    assert c['n'] == 4
    assert c['brier'] == pytest.approx(((0.5) ** 2 + 0.5 ** 2 + 0.01 + 0.64) / 4, abs=1e-5)
    ll = -(math.log(.5) + math.log(.5) + math.log(.9) + math.log(.2)) / 4
    assert c['log_loss'] == pytest.approx(ll, abs=1e-5)
    rel = {b['bucket']: b for b in c['reliability']}
    assert rel['40%+']['n'] == 2 and rel['40%+']['observed'] == 0.5
    assert rel['10-20%']['n'] == 1 and rel['20-30%']['observed'] == 1.0
    assert acc.calibration([]) is None


def test_log_loss_is_clipped_for_certain_predictions():
    c = acc.calibration([(0.0, 1), (1.0, 0)])
    assert math.isfinite(c['log_loss']) and c['log_loss'] == pytest.approx(-math.log(acc.P_EPS), rel=1e-3)


def test_scored_entry_keeps_every_player_and_has_calibration():
    e = scored_entry()
    assert len(e['players']) == e['n_players'] and not e.get('compacted')
    cal = e['summary']['calibration']
    assert cal['n'] == e['n_players'] and 0 < cal['brier'] < 1 and cal['log_loss'] > 0
    assert sum(b['n'] for b in cal['reliability']) == cal['n']
    scored = {s[0] for s in e['results']['scorers']}
    obs = sum(1 for p in e['players'] if p[0] in scored) / len(e['players'])
    assert obs == pytest.approx(sum(b['observed'] * b['n'] for b in cal['reliability']) / cal['n'], abs=1e-3)


def test_old_compacted_entries_still_load_and_render(tmp_path):
    old = acc.score(acc.predictions(SNAP, (), 'test', NOW), acc.results_from_score(SCORE), NOW, compact=True)
    old['summary'].pop('calibration', None)          # exactly what a pre-fix log file looks like
    acc.save_entry(old, tmp_path)
    back = acc.load_entry(old['day'], tmp_path)
    assert back and back['compacted'] and back['summary']['top_hits'] == 4
    t = acc.trend([back])
    assert t['calibration'] is None and t['nights'][0]['calibration'] is None
    rescored = acc.score(back, acc.results_from_score(SCORE), NOW)
    assert rescored['summary']['calibration'] is None   # incomplete list -> no misleading metric
    html = acc.card_html({'shown': back, 'trend': t, 'notes': []})
    assert 'n/a for this night' in html


def test_pooled_calibration_is_player_weighted():
    a = {'n': 10, 'brier': 0.1, 'log_loss': 0.3, 'reliability': [{'bucket': '0-10%', 'n': 10, 'mean_pred': .05, 'observed': .1}]}
    b = {'n': 30, 'brier': 0.2, 'log_loss': 0.5, 'reliability': [{'bucket': '0-10%', 'n': 30, 'mean_pred': .09, 'observed': .0}]}
    p = acc.pooled_calibration([{'calibration': a}, {'calibration': None}, {'calibration': b}])
    assert p['nights'] == 2 and p['n'] == 40
    assert p['brier'] == pytest.approx(0.175) and p['log_loss'] == pytest.approx(0.45)
    assert p['reliability'][0]['mean_pred'] == pytest.approx(0.08) and p['reliability'][0]['observed'] == pytest.approx(0.025)


def test_card_shows_brier_log_loss_and_reliability():
    e = scored_entry()
    html = acc.card_html({'shown': e, 'trend': acc.trend([e]), 'notes': []})
    assert 'Brier' in html and 'log loss' in html and 'Reliability table' in html


def test_full_slate_entry_stays_under_100kb():
    e = scored_entry()
    per_player = len(json.dumps(e['players'])) / len(e['players'])
    assert per_player * 16 * 2 * 22 < 100 * 1024   # 16-game slate x 2 teams x ~22 priced skaters
