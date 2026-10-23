"""V5.5 EdgeLab pure functions kept in V5.8 (price math, validation, stamp/SQLite helpers).
V5.8 removed the bankroll / Kelly / DEMO / manual-probability UI and its tests; the read-only view is tested in test_v58_edgelab.py."""
import math
import sqlite3
from datetime import datetime, timezone

import pytest

import edgelab_v55 as el


# ---- the pasted prototype's logic, verbatim semantics (reference implementation) -----------------
def ref_implied(o):
    return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)


@pytest.mark.parametrize('o,exp', [(-140, 140 / 240), (145, 100 / 245), (100, .5), (-100, .5), (-115, 115 / 215)])
def test_implied(o, exp):
    assert el.american_to_implied(o) == pytest.approx(exp)


@pytest.mark.parametrize('bad', [0, 50, -99, 99.5, float('nan'), float('inf'), None, 'abc', True])
def test_invalid_odds_rejected(bad):
    with pytest.raises(el.EdgeLabError):
        el.validate_odds(bad)


@pytest.mark.parametrize('bad', [0, 1, -0.1, 1.2, float('nan'), None, '0.5'])
def test_invalid_probability_rejected(bad):
    with pytest.raises(el.EdgeLabError):
        el.validate_probability(bad)


def test_rounding_half_up():
    assert el.round_half_up(2.675, 2) == 2.68 and el.round_half_up(1.005, 2) == 1.01 and el.round_half_up(-1.005, 2) == -1.01


BETS = [{'game': 'EDM @ CGY', 'pick': 'EDM ML', 'odds': -140, 'model_p': 0.61, 'book': 'DraftKings', 'team': 'EDM', 'edge': 2.67, 'stake': 0.0},
        {'game': 'TOR @ BOS', 'pick': 'BOS ML', 'odds': -155, 'model_p': 0.64, 'book': 'BetMGM', 'team': 'BOS', 'edge': 3.22, 'stake': 0.0},
        {'player': 'A. Matthews', 'pick': 'Over 0.5 Goals', 'odds': 100, 'model_p': 0.51, 'book': 'FanDuel', 'team': 'TOR', 'edge': 1.0, 'stake': 0.0}]


def test_edge_sign_and_format():
    assert el.edge_pct(.5, 150) > 0 and el.edge_pct(.5, -200) < 0      # overpriced favourite: negative, not abs()
    assert el.fmt_edge(-3.456) == '-3.46%' and el.fmt_odds(145) == '+145'
    assert [r['pick'] for r in el.all_edges([{**b, 'model_p': .5} for b in BETS[:2]])] == ['EDM ML', 'BOS ML']


def test_keys_stable_and_unique():
    keys = [el.bet_key('game', b) for b in BETS[:2]] + [el.bet_key('prop', BETS[2])]
    assert len(set(keys)) == len(keys)
    b = dict(BETS[0]); b2 = {**b, 'odds': -150, 'model_p': .7}
    assert el.bet_key('game', b) == el.bet_key('game', b2)   # price edits keep the key
    assert all(k == k.lower() and ' ' not in k for k in keys)


def test_stamp_eastern_time_dedupe_remove():
    kept = BETS[:2]   # stored stamps keep their V5.5 fields (stake/bankroll) so nothing already saved is lost
    now = datetime(2026, 10, 23, 1, 30, tzinfo=timezone.utc)        # 9:30 PM ET on Oct 22
    s = el.make_stamp('game', kept[0], 2500, now=now)
    assert s['stamped_at'] == '2026-10-22T21:30:00-04:00' and s['stamped_label'].endswith('ET')
    stamps, added = el.add_stamp([], s)
    stamps, again = el.add_stamp(stamps, el.make_stamp('game', kept[0], 2500, now=now))
    assert added and not again and len(stamps) == 1
    s2 = el.make_stamp('game', kept[1], 2500, now=now)
    stamps, _ = el.add_stamp(stamps, s2)
    assert [x['key'] for x in el.scorecard_rows(stamps)] == [s2['key'], s['key']]   # newest first
    assert el.remove_stamp(stamps, s['key']) == [s2]
    t = el.scorecard_totals(stamps)
    assert t['count'] == 2 and t['staked'] == el.round_half_up(s['stake'] + s2['stake'])
    csv = el.stamps_csv(stamps)
    assert csv.splitlines()[0].startswith('stamped_at,kind') and len(csv.splitlines()) == 3


def test_sqlite_roundtrip():
    conn = sqlite3.connect(':memory:')
    kept = BETS[2:]
    s = el.make_stamp('prop', kept[0], 2500)
    el.db_save(conn, s); el.db_save(conn, s)
    assert el.db_load(conn) == [s]
    el.db_delete(conn, s['key']); assert el.db_load(conn) == []
    el.db_save(conn, s); el.db_clear(conn); assert el.db_load(conn) == []


def test_disclaimer_wording():
    assert el.DISCLAIMER == 'Mobile research prototype. Not betting advice.'
    assert 'Kelly' not in el.RESEARCH_NOTE and not hasattr(el, 'DEMO_PROPS') and not hasattr(el, 'kelly')


