"""t209/t210/t212: Life Path numbers (method, data join, overlay off-parity, union overlay, match table, no scoring)."""
from copy import deepcopy
import importlib.util
import subprocess
import sys
import pandas as pd
import pytest

import lifepath_v61 as lp
import daily_patterns_v60 as dp
import gem_match_v58 as gmx
import numboard_v56 as nb
import numbers_v58_ui as nv
import player_targets_v49 as pt
import precompute_slate as pre
import rankings

DAY = '2026-11-22'   # auto pattern: 1, 3, 4, 7, 10, 11, 21, 22, 43


@pytest.mark.parametrize('birth,chain', [
    ('1997-07-26', (41, 5)), ('1989-09-29', (47, 11)), ('2004-07-09', (22,)), ('1999-03-02', (33,)),
    ('1990-12-24', (28, 10, 1)), ('2000-01-01', (4,)), ('1987-08-07T00:00:00', (40, 4)),
])
def test_chain_keeps_every_step_and_stops_at_masters(birth, chain):
    assert lp.chain(birth) == chain and lp.number(birth) == chain[-1]
    assert lp.text(chain) == '/'.join(map(str, chain))


@pytest.mark.parametrize('bad', [None, '', 'nan', '1999-02-30', '19990302', True, 123, float('nan')])
def test_missing_birthdate_is_dash_and_never_matches(bad):
    assert lp.chain(bad) == () and lp.number(bad) is None and lp.text(lp.chain(bad)) == '—'
    assert lp.hits(lp.chain(bad), range(0, 100)) == []
    assert lp.reason({'life_path': lp.chain(bad)}, [dp.entry_for(DAY)]) is None


def test_today_numbers_and_attribution_on_any_step():
    e = dp.entry_for(DAY)
    assert e['numbers'] == (1, 3, 4, 7, 10, 11, 21, 22, 43)
    assert lp.reason({'life_path': (47, 11)}, [e]) == 'Life Path 11 · Nov 22 pattern (2026-11-22)'
    assert lp.reason({'life_path': (28, 10, 1)}, [e]) == 'Life Path 1 (also 10) · Nov 22 pattern (2026-11-22)'
    assert lp.reason({'life_path': (41, 5)}, [e]) is None
    assert lp.matched_values(43, e) == ['Universal Day 43/7'] and lp.matched_values(22, e) == ['Calendar Day 22/4']
    assert lp.matched_values(11, e) == ['Month 11']
    saved = {'date': DAY, 'label': 'S', 'numbers': (5,), 'breakdown': ()}
    assert lp.matched_values(5, saved) == ['pattern number 5']


class _R:
    def __init__(self, data, code=200):
        self.data, self.code = data, code

    def raise_for_status(self):
        if self.code != 200:
            raise RuntimeError(self.code)

    def json(self):
        return self.data


def _getter(calls):
    def get(url, timeout=None):
        calls.append(url)
        if '/roster/TOR/' in url:
            return _R({'forwards': [{'id': 1, 'birthDate': '1997-07-26'}, {'id': 2}], 'goalies': [{'id': 9, 'birthDate': 'bad'}]})
        if '/player/2/landing' in url:
            return _R({'birthDate': '1989-09-29'})
        return _R({}, 500)
    return get


def test_fetch_map_roster_then_landing_fallback_and_failures():
    calls = []
    m, errs = lp.fetch_map(['TOR', 'BOS'], _getter(calls), pids=['1', '2', '3'])
    assert m == {'1': '1997-07-26', '2': '1989-09-29'} and errs
    assert all(u.startswith('https://api-web.nhle.com/v1/') for u in calls)
    assert sum('/landing' in u for u in calls) == 2                          # only the still-missing ids
    assert lp.fetch_map(['TOR'], lambda *a, **k: (_ for _ in ()).throw(OSError()))[0] == {}
    capped = []
    assert lp.fetch_map([], _getter(capped), pids=[str(i) for i in range(500)], cap=5)[0] == {'2': '1989-09-29'}
    assert len(capped) == 5                                                    # landing calls are capped


def test_fill_frame_render_fallback_and_identity_when_complete():
    f = pd.DataFrame([{'Player': 'A', 'Player ID': 1.0, 'Team': 'TOR'}, {'Player': 'B', 'Player ID': 2, 'Team': 'TOR'}])
    out = lp.fill_frame(f, lambda t, p: {'1': '1997-07-26'})
    assert list(out[lp.COLUMN]) == ['1997-07-26', None] and lp.COLUMN not in f
    done = out.assign(**{lp.COLUMN: ['1997-07-26', '1989-09-29']})
    assert lp.fill_frame(done, lambda t, p: 1 / 0) is done
    assert list(lp.fill_frame(f, lambda t, p: 1 / 0)[lp.COLUMN]) == [None, None]


def test_rankings_roster_precompute_carry_birthdate():
    row = {'Player': 'A', 'id': 5, 'Team': 'TOR', 'Position': 'C', 'GP': 10, 'GP L5': 5, 'GP L10': 10, 'Shots L5': 10,
           'Shots L10': 20, 'Goals': 2, 'Goals L5': 1, 'Data status': 'ok', 'Birth date': '1997-07-26'}
    assert rankings.rank_players([row])[0]['Birth date'] == '1997-07-26'
    assert rankings.rank_players([{k: v for k, v in row.items() if k != 'Birth date'}])[0]['Birth date'] is None
    errs = []
    out = pre.fill_birthdates([{'Player ID': 5, 'Team': 'TOR'}, {'Player ID': 6, 'Team': 'TOR', 'Birth date': '2000-01-01'}], errs,
                              fetch=lambda teams, pids: ({'5': '1997-07-26'}, ['x']))
    assert [r['Birth date'] for r in out] == ['1997-07-26', '2000-01-01'] and errs == ['x']
    errs = []
    out = pre.fill_birthdates([{'Player ID': 5, 'Team': 'TOR'}], errs, fetch=lambda *a, **k: 1 / 0)
    assert out[0]['Birth date'] is None and errs == ['Birthdates: ZeroDivisionError']


def test_nhl_roster_reads_birthdate(monkeypatch):
    import nhl_data
    monkeypatch.setattr(nhl_data, 'fetch_json', lambda path: {'forwards': [{'id': 1, 'firstName': {'default': 'A'}, 'lastName': {'default': 'B'},
                                                                       'positionCode': 'C', 'sweaterNumber': 9, 'birthDate': '1997-07-26'}]})
    assert nhl_data.get_roster('TOR')[0]['Birth date'] == '1997-07-26'


def _ranked():
    return pd.DataFrame([{'Player': 'Alpha One', 'Player ID': 1, 'Team': 'TOR', 'V3.2 Adjusted Index': 10, 'Jersey': 21, 'Birth date': '1989-09-29'},
                         {'Player': 'Beta Two', 'Player ID': 2, 'Team': 'TOR', 'V3.2 Adjusted Index': 20, 'Jersey': 5, 'Birth date': '1997-07-26'},
                         {'Player': 'Gamma Three', 'Player ID': 3, 'Team': 'TOR', 'V3.2 Adjusted Index': 30, 'Jersey': None, 'Birth date': None}])


def test_targets_carry_life_path_without_changing_matches_or_threat():
    with_lp = pt.target_rows(_ranked(), 'TOR', 'Toronto Maple Leafs', 'Scotiabank Arena', DAY)
    without = pt.target_rows(_ranked().drop(columns=['Birth date']), 'TOR', 'Toronto Maple Leafs', 'Scotiabank Arena', DAY)
    strip = lambda rows: [{k: v for k, v in r.items() if k not in ('life_path', 'birth_date')} for r in rows]
    assert strip(with_lp) == strip(without)
    assert [(r['player'], r['life_path']) for r in with_lp] == [(r, c) for r, c in
            [(x['player'], lp.chain(x['birth_date'])) for x in with_lp]]
    assert {r['player']: r['life_path'] for r in with_lp}['Alpha One'] == (47, 11)
    for a, b in zip(with_lp, without):
        assert nb.threat_raw(a) == nb.threat_raw(b) and nb.threat_score(a) == nb.threat_score(b)
    assert (nb.W_DAY, nb.W_ARENA, nb.W_TEAM, nb.W_JERSEY) == (3, 2, 1, 2)


def _boards():
    rows = pt.target_rows(_ranked(), 'TOR', 'Toronto Maple Leafs', 'Scotiabank Arena', DAY)
    return nb.slate_boards([{'game': {'away': 'TOR', 'home': 'BOS', 'arena': 'TD Garden', 'start': '2026-11-23T00:00:00Z'},
                             'away_targets': rows, 'home_targets': []}])


def _old(module):
    """The committed (pre-Life Path) version of a module, loaded side by side for byte-parity checks."""
    try:   # 84ad7b7 = main just before the Life Path layer (skipped on shallow CI checkouts)
        src = subprocess.run(['git', 'show', f'84ad7b7:{module}.py'], capture_output=True, text=True, check=True).stdout
    except Exception:
        pytest.skip('git history unavailable')
    spec = importlib.util.spec_from_loader(f'_old_{module}', loader=None)
    m = importlib.util.module_from_spec(spec)
    exec(compile(src, f'old_{module}.py', 'exec'), m.__dict__)
    return m


def test_overlay_off_is_byte_identical_to_previous_release():
    old = _old('numbers_v58_ui')
    b = _boards(); before = deepcopy(b)
    e = dp.entry_for(DAY)
    for kw in ({}, {'overlay': False}, {'overlay': []}, {'overlay': [e]}, {'overlay': True}):
        assert nv.boards_html(b, 4, **kw) == old.boards_html(b, 4, **kw)
        assert nv.boards_html(b, 4, lifepath=None, **kw) == old.boards_html(b, 4, **kw)
        assert nv.boards_html(b, 4, lifepath=[], **kw) == old.boards_html(b, 4, **kw)
    assert nv.overlay_counts(b, patterns=[e]) == old.overlay_counts(b, patterns=[e])
    assert 'LP ' not in nv.boards_html(b, 4) and b == before
    og = _old('gem_match_v58')
    rows, miss = gmx.match_table([{'game': {'away': 'TOR', 'home': 'BOS', 'arena': 'TD Garden'}, 'away_targets': b[0]['all_players'], 'home_targets': []}], 4)
    assert gmx.table_html(rows, miss, 4) == og.table_html(rows, miss, 4)


def test_lifepath_overlay_filters_rows_with_attribution_and_union():
    b = _boards(); e = dp.entry_for(DAY)
    on = nv.boards_html(b, 4, lifepath=[e])
    assert 'Overlay match · Life Path 11 · Nov 22 pattern (2026-11-22)' in on and 'LP 47/11' in on
    assert 'Beta Two' not in on and 'Gamma Three' not in on and 'Overlay ON · 1 of 3' in on
    assert nv.overlay_counts(b, lifepath=[e]) == (3, 1)
    other = {'date': '2026-11-20', 'label': 'X', 'numbers': (21, 5), 'breakdown': ()}   # Beta: LP 41/5; Alpha jersey 21
    both = nv.boards_html(b, 4, overlay=[other], lifepath=[e, other])
    assert 'Beta Two' in both and 'Life Path 5 · X (2026-11-20)' in both and 'Jersey #21 · X (2026-11-20)' in both
    assert 'Gamma Three' not in both                                                    # no birthdate: never matches
    assert nv.overlay_counts(b, patterns=[other], lifepath=[e, other]) == (3, 2)


def test_match_table_overlay_tags_rows_display_only():
    b = _boards(); e = dp.entry_for(DAY)
    st = [{'game': {'away': 'TOR', 'home': 'BOS', 'arena': 'TD Garden'}, 'away_targets': b[0]['all_players'], 'home_targets': []}]
    rows, miss = gmx.match_table(st, 4)
    off, on = gmx.table_html(rows, miss, 4), gmx.table_html(rows, miss, 4, lifepath=[e])
    assert off.count('<tr class="gm-r">') == on.count('<tr class="gm-r">')               # same rows: overlay never adds/removes
    if rows:
        assert 'LP ' in on and 'Life Path overlay ON' in on and 'LP ' not in off


def _slate(rows):
    return [{'game': {'away': 'TOR', 'home': 'BOS'}, 'away_targets': rows, 'home_targets': []}]


def test_today_table_all_matches_labels_and_empty_states():
    e = dp.entry_for(DAY)
    ts = [{'player': f'P{i}', 'player_id': str(i), 'team': 'TOR', 'jersey': i, 'life_path': lp.chain(d), 'birth_date': d,
           'values': {'ordinal': 100 + i, 'ordinal_root': 1}} for i, d in enumerate(
           ['1989-09-29', '1997-07-26', None, '1989-07-18', '2004-07-09', '1990-12-24'] * 10)]
    rows, n, miss = lp.table_rows(_slate(ts), e)
    assert n == 60 and miss == 10 and len(rows) == 40                                   # no top-N cut
    r = {x['player']: x for x in rows}
    assert r['P0']['matched'] == ['Month 11'] and r['P3']['matched'] == ['Universal Day 43/7']
    assert r['P4']['matched'] == ['Calendar Day 22/4'] and r['P5']['matched'] == ['Universal Year 10/1']
    html = lp.table_html(rows, e, n, miss)
    assert html.count('<tr><td>') == 40 and '47/11' in html and 'Month 11' in html and '#0' in html and 'Eng 100' in html
    assert '10 without a birthdate (never match)' in html and '50 of 60 players have a birthdate' in html
    assert 'P1<' not in html and 'P2<' not in html
    none = lp.table_html([], e, 3, 0)
    assert 'No player’s Life Path matches today’s numbers.' in none
    nob = lp.table_html(*lp.table_rows(_slate([dict(ts[2], player_id='x')]), e)[:1], e, 1, 1)
    assert 'No birthdates are available for this slate yet' in nob
    assert 'appear once this slate’s rankings are loaded' in lp.table_html([], e, 0, 0, loaded=False)
    assert '<script' not in lp.table_html([dict(rows[0], player='<script>x</script>')], e, 1, 0)


def test_tags_and_mobile_css():
    assert lp.tag({'life_path': (47, 11), 'birth_date': '1989-09-29'}).endswith('>LP 47/11</span>')
    assert 'LP —' in lp.tag({'life_path': ()}) and lp.tag({}) == ''
    assert '@media(max-width:600px)' in lp.TABLE_STYLE and 'overflow-x:hidden' in lp.TABLE_STYLE


def test_numbers_tab_wiring():
    src = open('tabs/numbers.py', encoding='utf-8').read()
    assert "value=False,key=_num_lp.toggle_key(np_day)" in src                      # default off, own key
    assert "_num_lp.table_html(" in src and "entry_for(np_day,_num_daily)" in src
    assert "numv58.boards_html(_nb_boards,_day_num,_nb_mp,pmap=_num_pmap))" in src      # off path unchanged


def test_apptest_numbers_tab_table_and_overlay_toggle(monkeypatch, tmp_path):
    """Offline AppTest: always-visible Life Path table, default-off toggle, By Game overlay on, no exception."""
    import streamlit as st
    from v54_testkit import run_app
    st.cache_data.clear()
    monkeypatch.setattr(lp, 'fetch_map', lambda teams, getter=None, pids=(), cap=80: ({str(p): '1989-09-29' for p in pids}, []))
    at = run_app(monkeypatch, tmp_path)
    assert not at.exception
    tab = next(t for t in at.tabs if t.label == '🔮 Numbers')
    html = lambda: ' '.join([m.value for m in tab.markdown] + [h.value for h in tab.get('html')])
    base = html()
    assert 'Life Path matches' in base and 'players have a birthdate' in base and 'Overlay match · Life Path' not in base
    tg = next(t for t in at.get('toggle') if str(t.key).startswith('v61_lifepath_overlay:'))
    assert tg.value is False
    tg.set_value(True).run()
    assert not at.exception
    tab = next(t for t in at.tabs if t.label == '🔮 Numbers')
    on = ' '.join([m.value for m in tab.markdown] + [h.value for h in tab.get('html')]) + ' '.join(c.value for c in tab.caption)
    assert 'Overlay ON (Life Path' in on
