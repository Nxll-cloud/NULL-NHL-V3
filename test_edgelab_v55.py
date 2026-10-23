"""V5.5 EdgeLab: pure functions, the pasted prototype as a reference, bug fixes, and an AppTest stamp flow."""
import math
import sqlite3
from datetime import datetime, timezone

import pytest

import edgelab_v55 as el


# ---- the pasted prototype's logic, verbatim semantics (reference implementation) -----------------
def ref_implied(o):
    return 100 / (o + 100) if o > 0 else abs(o) / (abs(o) + 100)


def ref_kelly(p, o, bankroll):
    b = o / 100 if o > 0 else 100 / abs(o)
    k = (b * p - (1 - p)) / b
    return max(0, round(k * .25 * bankroll, 2))


def ref_process(rows, bankroll, min_edge):
    out = []
    for r in rows:
        imp = ref_implied(r['odds'])
        edge = (r['model_p'] - imp) * 100
        if edge >= min_edge:
            out.append({**r, 'edge': edge, 'stake': ref_kelly(r['model_p'], r['odds'], bankroll)})
    return sorted(out, key=lambda x: x['edge'], reverse=True)


@pytest.mark.parametrize('o,exp', [(-140, 140 / 240), (145, 100 / 245), (100, .5), (-100, .5), (-115, 115 / 215)])
def test_implied(o, exp):
    assert el.american_to_implied(o) == pytest.approx(exp)


def test_kelly_matches_reference_and_bounds():
    for p, o in [(.61, -140), (.56, -115), (.64, -155), (.42, 145), (.62, -130), (.51, 100), (.58, -105)]:
        assert el.kelly(p, o, 2500) == pytest.approx(ref_kelly(p, o, 2500), abs=0.011)
    assert el.kelly(.3, -200, 2500) == 0.0              # negative edge -> no stake
    assert el.kelly(.999, 10000, 1000) <= 1000           # never above bankroll
    assert 0 <= el.kelly(.99, 10000, 1000, fraction=1) <= 1000
    with pytest.raises(el.EdgeLabError):
        el.kelly(.6, -110, 1000, fraction=1.5)


@pytest.mark.parametrize('min_edge', [1.0, 2.0, 4.0, 6.5, 12.0])
@pytest.mark.parametrize('bankroll', [500, 2500, 50000])
def test_process_matches_reference_on_demo(min_edge, bankroll):
    for rows in (el.DEMO_GAMES, el.DEMO_PROPS):
        got, skipped = el.process(rows, bankroll, min_edge)
        ref = ref_process(rows, bankroll, min_edge)
        assert not skipped
        assert [r['pick'] for r in got] == [r['pick'] for r in ref]
        for g, r in zip(got, ref):
            assert g['edge'] == pytest.approx(r['edge'], abs=0.005)
            assert g['stake'] == pytest.approx(r['stake'], abs=0.011)
            assert 0 <= g['stake'] <= bankroll


def test_edge_sign_and_sorting():
    rows = [{'game': 'A', 'pick': 'x', 'odds': -200, 'model_p': .5, 'book': 'b'},
            {'game': 'A', 'pick': 'y', 'odds': 150, 'model_p': .5, 'book': 'b'}]
    kept, _ = el.process(rows, 1000, -100)
    assert kept[0]['pick'] == 'y' and kept[0]['edge'] > 0
    assert kept[1]['edge'] < 0                       # overpriced favourite: negative edge, not abs()
    assert el.fmt_edge(-3.456) == '-3.46%' and el.fmt_odds(145) == '+145'


@pytest.mark.parametrize('bad', [0, 50, -99, 99.5, float('nan'), float('inf'), None, 'abc', True])
def test_invalid_odds_rejected(bad):
    with pytest.raises(el.EdgeLabError):
        el.validate_odds(bad)


@pytest.mark.parametrize('bad', [0, 1, -0.1, 1.2, float('nan'), None, '0.5'])
def test_invalid_probability_rejected(bad):
    with pytest.raises(el.EdgeLabError):
        el.validate_probability(bad)


def test_process_skips_invalid_rows():
    rows = [{'game': 'A', 'pick': 'x', 'odds': 50, 'model_p': .5, 'book': 'b'},
            {'game': 'A', 'pick': 'y', 'odds': 150, 'model_p': float('nan'), 'book': 'b'}]
    kept, skipped = el.process(rows, 1000, 0)
    assert kept == [] and len(skipped) == 2


def test_rounding_half_up():
    assert el.round_half_up(2.675, 2) == 2.68 and el.round_half_up(1.005, 2) == 1.01 and el.round_half_up(-1.005, 2) == -1.01


def test_keys_stable_and_unique():
    keys = [el.bet_key('game', b) for b in el.DEMO_GAMES] + [el.bet_key('prop', b) for b in el.DEMO_PROPS]
    assert len(set(keys)) == len(keys)
    b = dict(el.DEMO_GAMES[0]); b2 = {**b, 'odds': -150, 'model_p': .7}
    assert el.bet_key('game', b) == el.bet_key('game', b2)   # price edits keep the key
    assert all(k == k.lower() and ' ' not in k for k in keys)


def test_stamp_eastern_time_dedupe_remove():
    kept, _ = el.process(el.DEMO_GAMES, 2500, 1.0)
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
    kept, _ = el.process(el.DEMO_PROPS, 2500, 1.0)
    s = el.make_stamp('prop', kept[0], 2500)
    el.db_save(conn, s); el.db_save(conn, s)
    assert el.db_load(conn) == [s]
    el.db_delete(conn, s['key']); assert el.db_load(conn) == []
    el.db_save(conn, s); el.db_clear(conn); assert el.db_load(conn) == []


def test_real_price_needs_user_probability():
    import pandas as pd
    q = pd.DataFrame([{'player': 'Real Player', 'selection': 'Yes', 'market': 'Anytime goal', 'american_odds': 250, 'sportsbook': 'DK', 'team': 'EDM'},
                      {'player': 'Bad Price', 'selection': 'Yes', 'market': 'Anytime goal', 'american_odds': 20, 'sportsbook': 'DK', 'team': 'EDM'}])
    opts = el.quote_options(q)
    assert len(opts) == 1 and 'model_p' not in opts[0]
    with pytest.raises(el.EdgeLabError):
        el.score_real(opts[0], None, 2500)
    with pytest.raises(el.EdgeLabError):
        el.score_real(opts[0], 0, 2500)
    b = el.score_real(opts[0], 35, 2500)
    assert b['edge'] == pytest.approx((0.35 - 100 / 350) * 100, abs=0.005)
    assert el.quote_options(None) == [] and el.quote_options(pd.DataFrame()) == []


def test_disclaimer_wording():
    assert el.DISCLAIMER == 'Mobile research prototype. Not betting advice.'
    assert 'DEMO DATA' in el.DEMO_BADGE


# ---- AppTest: standalone render + stamp click ----------------------------------------------------
APP = '''
import sqlite3, os
from datetime import datetime, timezone
import edgelab_v55 as el
DB = os.environ.get('EDGELAB_TEST_DB', ':memory:')
el.render_edgelab(quotes=None, now_fn=lambda: datetime(2026, 10, 23, 1, 30, tzinfo=timezone.utc),
                  conn_factory=lambda: sqlite3.connect(DB))
'''


def _texts(at):
    return ' '.join([m.value for m in at.markdown] + [c.value for c in at.caption])


def test_apptest_render_and_stamp(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('EDGELAB_TEST_DB', str(tmp_path / 'e.sqlite'))
    at = AppTest.from_string(APP, default_timeout=30)
    at.run()
    assert not at.exception
    assert [t.label for t in at.tabs] == ['Games', 'Props', 'Scorecard (0)']
    txt = _texts(at)
    assert 'DEMO DATA — not live prices' in txt and 'Not betting advice' in txt
    assert at.number_input(key='edgelab_bankroll').value == 2500 and at.slider(key='edgelab_min_edge').value == 4.0
    at.slider(key='edgelab_min_edge').set_value(1.0).run()
    stamp_keys = [b.key for b in at.button if b.key and b.key.startswith('edgelab_stamp_')]
    assert len(stamp_keys) >= 4
    at.button(key=stamp_keys[0]).click().run()
    assert not at.exception
    st_ = at.session_state['edgelab_stamped']
    assert len(st_) == 1 and st_[0]['stamped_at'].endswith('-04:00')
    assert at.button(key=stamp_keys[0]).disabled                       # no duplicate stamps
    assert [t.label for t in at.tabs][2] == 'Scorecard (1)'
    # persistence on mid-session saves the existing stamp
    at.toggle(key='edgelab_persist').set_value(True).run()
    assert len(el.db_load(sqlite3.connect(str(tmp_path / 'e.sqlite')))) == 1
    at.button(key='edgelab_rm_' + st_[0]['key']).click().run()
    assert at.session_state['edgelab_stamped'] == []
    assert el.db_load(sqlite3.connect(str(tmp_path / 'e.sqlite'))) == []
