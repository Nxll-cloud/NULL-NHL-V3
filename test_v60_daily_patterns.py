"""Daily pattern registry + union filter (display only; no scoring/rank changes)."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import numbers_v58_ui as nv
import daily_patterns_v60 as dp
from test_v60_number_overlay import board, player, BASELINE_HASH


def entries():
    es, warn = dp.load()
    assert not warn
    return {e['date']: e for e in es}


def test_registry_seed_entries_literal():
    es = entries()
    assert list(es) == ['2026-11-07', '2026-11-09']
    a, b = es['2026-11-07'], es['2026-11-09']
    assert a['numbers'] == (4, 10, 0, 9, 3, 6) and a['note'] == 'Possible date mapping: October 9th, 36.' and a['breakdown'] == ()
    assert b['numbers'] == (1, 3, 9, 10, 11, 21, 30) and b['note'] is None
    assert b['breakdown'] == (('Universal Day', '30/3'), ('Universal Month', '21/3'), ('Calendar Day', '9'),
                              ('Universal Year', '10/1'), ('Month', '11'))
    assert dp.REGISTRY.stat().st_size < 100_000


def test_validation_skips_bad_entries_with_warnings_never_raises():
    good = {'date': '2026-11-10', 'label': 'X', 'numbers': [0, 5]}
    raw = [good, dict(good), {'date': '2026-13-01', 'label': 'X', 'numbers': [1]}, {'date': '11/10/2026', 'label': 'X', 'numbers': [1]},
           {'date': '2026-11-11', 'label': '', 'numbers': [1]}, {'date': '2026-11-12', 'label': 'X', 'numbers': [True]},
           {'date': '2026-11-13', 'label': 'X', 'numbers': [1.5]}, {'date': '2026-11-14', 'label': 'X', 'numbers': []},
           {'date': '2026-11-15', 'label': 'X', 'numbers': [2, 2]}, {'date': '2026-11-16', 'label': 'X', 'numbers': [1], 'breakdown': [['A']]},
           {'date': '2026-11-17', 'label': 'X', 'numbers': [1], 'note': 5}, 'junk']
    es, warn = dp.validate(raw)
    assert [e['date'] for e in es] == ['2026-11-10'] and es[0]['numbers'] == (0, 5)
    assert len(warn) == 11 and any('duplicate date' in w for w in warn) and any('repeated number' in w for w in warn)
    assert dp.validate({'x': 1})[0] == [] and dp.load('/nonexistent/x.json')[0] == []


def test_new_entry_via_data_only_shows_in_panel_and_toggle(tmp_path):
    raw = json.loads(dp.REGISTRY.read_text())
    raw.append({'date': '2026-11-10', 'label': 'Nov 10 pattern', 'numbers': [2, 20], 'breakdown': [['Month', '11']]})
    f = tmp_path / 'r.json'; f.write_text(json.dumps(raw))
    es, warn = dp.load(f)
    assert not warn and es[-1]['date'] == '2026-11-10'
    html = nv.daily_patterns_html(es)
    assert 'Nov 10 pattern · 2026-11-10' in html and '<dt>Month</dt><dd>11</dd>' in html


def test_panel_shows_literal_breakdown_note_and_honest_matchability():
    html = nv.daily_patterns_html(list(entries().values()))
    assert '1, 3, 9, 10, 11, 21, 30' in html and '4, 10, 0, 9, 3, 6' in html
    for a, b in (('Universal Day', '30/3'), ('Universal Month', '21/3'), ('Calendar Day', '9'), ('Universal Year', '10/1'), ('Month', '11')):
        assert f'<dt>{a}</dt><dd>{b}</dd>' in html
    assert 'Possible date mapping: October 9th, 36.' in html
    assert 'Can match a 1–9 English root: 1, 3, 9 · full-total only: 10, 11, 21, 30' in html
    assert 'not backtested' in html and 'not a forecast' in html
    # 11-07 entry has no breakdown list
    seg = html.split('Nov 7 pattern')[1].split('ndp-item')[0]
    assert '<dl' not in seg


def test_off_parity_byte_identical():
    b = [board()]; before = deepcopy(b)
    for off in (False, [], ()):
        html = nv.boards_html(b, 9, overlay=off)
        assert hashlib.sha256(html.encode()).hexdigest() == BASELINE_HASH
    assert b == before and nv.overlay_counts(b, patterns=[]) == (4, 0)


def test_root_or_full_total_attribution_and_zero_handling():
    es = entries(); e7, e9 = es['2026-11-07'], es['2026-11-09']
    p = {'values': {'ordinal_root': 3, 'ordinal': 21}}
    assert dp.reason(p, [e9]) == 'English root = 3 & English total = 21 · Nov 9 pattern (2026-11-09)'
    assert dp.reason(p, [e7]) == 'English root = 3 · Nov 7 pattern (2026-11-07)'
    assert dp.reason({'values': {'ordinal_root': 2, 'ordinal': 30}}, [e9]) == 'English total = 30 · Nov 9 pattern (2026-11-09)'
    assert dp.reason({'values': {'ordinal_root': 2, 'ordinal': 10}}, [e7, e9]) == \
        'English total = 10 · Nov 7 pattern (2026-11-07); English total = 10 · Nov 9 pattern (2026-11-09)'
    assert dp.reason({'values': {'ordinal_root': 0}}, [e7]) == 'English root = 0 · Nov 7 pattern (2026-11-07)'
    for v in (None, '', float('nan'), True, 'x', 2.5):
        assert dp.reason({'values': {'ordinal_root': v, 'ordinal': v}}, [e7, e9]) is None
    assert dp.reason({'values': {'ordinal_root': 2}, 'eng_total': 11}, [e9]) == 'English total = 11 · Nov 9 pattern (2026-11-09)'
    assert dp.reason({'values': {'reverse_root': 3}}, [e9]) is None  # Reverse never counts


def _slate():
    b = board()
    roots_totals = [(2, 47), (4, 31), (6, 10), (5, 21), (7, 70), (9, 63)]
    for p, (r, t) in zip(b['all_players'], roots_totals):
        p['values']['ordinal_root'] = r; p['values']['ordinal'] = t; p['eng_total'] = t
    return b


def test_single_multi_union_no_backfill_no_rerank():
    es = entries(); e7, e9 = es['2026-11-07'], es['2026-11-09']
    b = _slate()
    assert nv.overlay_counts([b], patterns=[e7]) == (4, 1)          # P2 root 4
    assert nv.overlay_counts([b], patterns=[e9]) == (4, 1)          # P4 total 21
    assert nv.overlay_counts([b], patterns=[e7, e9]) == (4, 2)      # union
    html = nv.boards_html([b], 9, overlay=[e7, e9])
    assert 'OverlayPlayer2' in html and 'OverlayPlayer4' in html
    assert 'OverlayPlayer1' not in html and 'OverlayPlayer3' not in html and 'OverlayPlayer6' not in html  # no backfill
    assert 'English total = 21 · Nov 9 pattern (2026-11-09)' in html and 'English root = 4 · Nov 7 pattern (2026-11-07)' in html
    assert 'Overlay ON · 2 of 4 current selections shown' in html and '⚑ 6 threats' in html


def test_no_match_zero_state():
    b = _slate()
    nothing = {'date': '2026-01-01', 'label': 'none', 'numbers': (99,), 'note': None, 'breakdown': ()}
    assert nv.overlay_counts([b], patterns=[nothing]) == (4, 0)
    assert '0 overlay matches in the current selection.' in nv.boards_html([b], 9, overlay=[nothing])


def test_integration_panel_placement_toggle_keys_scoped_per_slate_and_entry():
    src = Path('tabs/numbers.py').read_text()
    assert src.index('_num_audit.render(st)') < src.index('numv58.daily_patterns_html(_num_daily,_num_daily_warn)') < src.index('_games_num=np_snapshot')
    assert dp.toggle_key('2026-11-09', '2026-11-07') != dp.toggle_key('2026-11-10', '2026-11-07')
    assert dp.toggle_key('2026-11-09', '2026-11-07') != dp.toggle_key('2026-11-09', '2026-11-09')


def test_apptest_independent_toggles_union_and_slate_reset():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import streamlit as st
import numbers_v58_ui as nv, daily_patterns_v60 as dp
from test_v60_daily_patterns import _slate
es,_=dp.load()
slate=st.selectbox('Slate',['2026-11-09','2026-11-10'])
sel=[e for e in es if st.toggle(e['label'],value=False,key=dp.toggle_key(slate,e['date']))]
base,m=nv.overlay_counts([_slate()],patterns=sel)
st.caption(f'baseline {base} matching {m}')
st.markdown(nv.boards_html([_slate()],9,overlay=sel) if sel else nv.boards_html([_slate()],9),unsafe_allow_html=True)
''').run()
    assert not app.exception and [t.value for t in app.toggle] == [False, False]
    baseline = app.markdown[0].value
    app.toggle[1].set_value(True).run()
    assert 'matching 1' in app.caption[0].value and 'OverlayPlayer4' in app.markdown[0].value and 'OverlayPlayer2' not in app.markdown[0].value
    app.toggle[0].set_value(True).run()
    assert 'matching 2' in app.caption[0].value
    app.toggle[0].set_value(False).run(); app.toggle[1].set_value(False).run()
    assert app.markdown[0].value == baseline
    app.toggle[1].set_value(True).run()
    app.selectbox[0].set_value('2026-11-10').run()
    assert [t.value for t in app.toggle] == [False, False] and app.markdown[0].value == baseline
