"""t201: jersey numbers on the Numbers tab (join, fallback, null handling, overlay, threat additivity, schema)."""
from copy import deepcopy
import json
import pandas as pd
import pytest

import jersey_v61 as jy
import daily_patterns_v60 as dp
import numboard_v56 as nb
import numbers_v58_ui as nv
import player_targets_v49 as pt
import precompute_slate as pre
import rankings
import snapshot_store

DAY = '2026-11-17'   # auto pattern: 1, 2, 3, 8, 10, 11, 17, 21, 38


def ranked(rows):
    return pd.DataFrame([{'Player': n, 'Player ID': pid, 'Team': 'TOR', 'V3.2 Adjusted Index': 10, **extra}
                         for n, pid, extra in rows])


def test_norm_and_hit_raw_no_reduction_and_missing_never_matches():
    assert jy.norm(21) == 21 and jy.norm(21.0) == 21 and jy.norm('38') == 38
    for bad in (None, float('nan'), '', 'nan', True, False, 2.5, -1):
        assert jy.norm(bad) is None
    nums = dp.numbers_for(DAY)
    assert nums == (1, 2, 3, 8, 10, 11, 17, 21, 38)
    assert jy.hit(21, nums) and jy.hit(38, nums) and not jy.hit(39, nums)   # 39 -> 12 -> 3 is NOT reduced
    assert not jy.hit(None, nums) and not jy.hit(float('nan'), nums)
    assert not jy.hit(None, (0,)) and jy.hit(0, (0,)) and not jy.hit(0, nums)


def test_fill_records_joins_by_player_id_and_keeps_existing():
    recs = [{'Player ID': 8478402, 'Team': 'EDM'}, {'Player ID': '8477934.0', 'Team': 'EDM', 'Jersey': 29},
            {'Player ID': 1, 'Team': 'EDM', 'Jersey': None}]
    out = jy.fill_records(recs, {'8478402': 97, '8477934': 99})
    assert [r['Jersey'] for r in out] == [97, 29, None]
    assert 'Jersey' not in recs[0]   # no mutation
    assert jy.missing_teams(out) == ['EDM'] and jy.coverage(out) == (2, 3)


def test_fetch_map_failure_is_empty_never_raises():
    def boom(*a, **k):
        raise OSError('down')
    m, errors = jy.fetch_map(['TOR', 'BOS'], getter=boom)
    assert m == {} and len(errors) == 2


def test_fetch_map_reads_sweater_numbers():
    class R:
        def raise_for_status(self): pass
        def json(self): return {'forwards': [{'id': 5, 'sweaterNumber': 21}, {'id': 6}], 'goalies': [{'id': 7, 'sweaterNumber': 0}]}
    m, errors = jy.fetch_map(['TOR'], getter=lambda *a, **k: R())
    assert m == {'5': 21, '7': 0} and errors == []


def test_render_fallback_fills_frame_from_roster_map_and_is_safe():
    f = ranked([('A Player', 5, {}), ('B Player', 6, {})])
    out = jy.fill_frame(f, lambda teams: {'TOR': {'5': 21}})
    assert list(out['Jersey']) == [21, None] and 'Jersey' not in f.columns
    full = ranked([('A Player', 5, {'Jersey': 21})])
    assert jy.fill_frame(full, lambda t: (_ for _ in ()).throw(AssertionError('no fetch'))) is full
    def boom(t):
        raise RuntimeError('x')
    out = jy.fill_frame(f, boom)
    assert list(out['Jersey']) == [None, None]


def test_target_rows_threads_jersey_and_hit_without_changing_name_matches():
    f = ranked([('A Player', 5, {'Jersey': 21}), ('B Player', 6, {'Jersey': 39}), ('C Player', 7, {})])
    rows = {r['player_id']: r for r in pt.target_rows(f, 'TOR', 'Toronto Maple Leafs', 'Scotiabank Arena', DAY)}
    assert rows['5']['jersey'] == 21 and rows['5']['jersey_hit'] == ['Jersey #21']
    assert rows['6']['jersey'] == 39 and rows['6']['jersey_hit'] == []
    assert rows['7']['jersey'] is None and rows['7']['jersey_hit'] == []
    base = {r['player_id']: r for r in pt.target_rows(f.drop(columns=['Jersey']), 'TOR', 'Toronto Maple Leafs', 'Scotiabank Arena', DAY)}
    for k in rows:
        for fld in ('day', 'team_matches', 'arena_matches', 'matches', 'number', 'eng_total'):
            assert rows[k][fld] == base[k][fld]


def _t(day=0, arena=0, team=0, jersey=None):
    return {'day': ['English'] * day, 'arena_matches': ['English'] * arena, 'team_matches': ['English'] * team,
            'jersey': jersey, 'jersey_hit': [f'Jersey #{jersey}'] if jersey is not None else []}


def test_threat_additive_and_identical_without_jersey():
    for d in (0, 1):
        for a in (0, 1):
            for t in (0, 1):
                old = 3 * d + 2 * a + t
                assert nb.threat_raw(_t(d, a, t)) == old and nb.threat_score(_t(d, a, t)) == round(100 * old / 6)
                assert nb.threat_raw(_t(d, a, t, jersey=21)) == old + 2
                assert nb.threat_score(_t(d, a, t, jersey=21)) == min(100, round(100 * (old + 2) / 6))
    no_key = {'day': ['English'], 'arena_matches': [], 'team_matches': []}
    assert nb.threat_raw(no_key) == 3


def test_jersey_hit_moves_player_up_board():
    a = {**_t(1), 'player': 'A', 'matches': 1, 'form': 50, 'eng_total': 100}
    b = {**_t(0, 0, 1, jersey=21), 'player': 'B', 'matches': 1, 'form': 10, 'eng_total': 90}
    c = {**_t(1, 0, 0, jersey=38), 'player': 'C', 'matches': 1, 'form': 1, 'eng_total': 80}
    order = [p['player'] for p in nb.game_board({}, [a, b, c], [])['players']]
    assert order == ['C', 'A', 'B']


def test_overlay_union_includes_jersey_attribution():
    e = dp.entry_for(DAY)
    p = {'values': {'ordinal_root': 5, 'ordinal': 140}, 'jersey': 21}
    assert dp.reason(p, [e]) == 'Jersey #21 · Nov 17 pattern (2026-11-17)'
    p2 = {'values': {'ordinal_root': 2, 'ordinal': 140}, 'jersey': 38}
    assert dp.reason(p2, [e]) == 'English root = 2 & Jersey #38 · Nov 17 pattern (2026-11-17)'
    for j in (None, float('nan'), 39, True):
        assert dp.reason({'values': {'ordinal_root': 5, 'ordinal': 140}, 'jersey': j}, [e]) is None
    zero = {'date': '2026-01-01', 'label': 'Z', 'numbers': (0,)}
    assert dp.reason({'values': {}, 'jersey': 0}, [zero]) == 'Jersey #0 · Z (2026-01-01)'
    assert dp.reason({'values': {}, 'jersey': None}, [zero]) is None


def _player(pid, root, jersey, hit):
    p = {'player_id': str(pid), 'player': f'J{pid}', 'team': 'TOR',
         'values': {'ordinal_root': root, 'reduction_root': root, 'reverse_root': 9 - root, 'ordinal': 140},
         'day': [], 'arena_matches': [], 'team_matches': [], 'matches': 0, 'form': 30, 'eng_total': 140, 'shot_rate': 2,
         'jersey': jersey, 'jersey_hit': [f'Jersey #{jersey}'] if hit else []}
    raw = nb.threat_raw(p)
    tier, colour = nb.tier(raw)
    return {**p, 'threat_raw': raw, 'threat': nb.threat_score(p), 'tier': tier, 'colour': colour}


def _board():
    ps = [_player(1, 5, 21, True), _player(2, 5, 39, False), _player(3, 5, None, False)]
    return {'game': {'away': 'TOR', 'home': 'BOS', 'arena': '', 'start': ''}, 'players': ps, 'all_players': ps,
            'badge': 1, 'arena_hit': False, 'arena_players': [], 'arena_root': None}


def test_board_marker_legend_note_and_off_parity():
    b = [_board()]; before = deepcopy(b)
    html = nv.boards_html(b, 2)
    assert '#21 ✓' in html and 'JERSEY' in html and '#39' in html and '#39 ✓' not in html
    assert 'not part of the historical Numbers backtest' in html
    for off in (False, [], ()):
        assert nv.boards_html(b, 2, overlay=off) == html
    on = nv.boards_html(b, 2, overlay=[dp.entry_for(DAY)])
    assert 'Overlay match · Jersey #21' in on and 'J2' not in on and 'J3' not in on
    assert nv.overlay_counts(b, patterns=[dp.entry_for(DAY)]) == (3, 1)
    assert b == before


def test_legend_unchanged_when_no_jersey_data():
    assert nv.legend() == nv.legend(False) and 'JERSEY' not in nv.legend()


def test_rank_players_and_roster_carry_jersey():
    row = {'Player': 'A', 'id': 5, 'Team': 'TOR', 'Position': 'C', 'GP': 10, 'GP L5': 5, 'GP L10': 10, 'Shots L5': 10,
           'Shots L10': 20, 'Goals': 2, 'Goals L5': 1, 'Data status': 'ok', 'Jersey': 21}
    assert rankings.rank_players([row])[0]['Jersey'] == 21
    assert rankings.rank_players([{**row, 'Jersey': None}])[0]['Jersey'] is None
    assert rankings.rank_players([{k: v for k, v in row.items() if k != 'Jersey'}])[0]['Jersey'] is None


def test_precompute_fill_jersey_and_failure_leaves_null():
    errors = []
    out = pre.fill_jersey([{'Player ID': 5, 'Team': 'TOR', 'Jersey': None}, {'Player ID': 6, 'Team': 'TOR', 'Jersey': 9}],
                          errors, fetch=lambda teams: ({'5': 21}, []))
    assert [r['Jersey'] for r in out] == [21, 9] and errors == []
    def boom(teams):
        raise RuntimeError('down')
    errors = []
    out = pre.fill_jersey([{'Player ID': 5, 'Team': 'TOR'}], errors, fetch=boom)
    assert out[0]['Jersey'] is None and errors == ['Jersey: RuntimeError']


def test_snapshot_schema_round_trip_with_jersey(tmp_path):
    rows = [{'Player': 'A', 'Player ID': 5, 'Team': 'TOR', 'Jersey': 21}, {'Player': 'B', 'Player ID': 6, 'Team': 'TOR', 'Jersey': None}]
    snapshot_store.save_snapshot(DAY, [{'Away': 'TOR', 'Home': 'BOS'}], rows, root=tmp_path)
    data = snapshot_store.load_snapshot(DAY, root=tmp_path)
    assert [r['Jersey'] for r in data['rankings']] == [21, None]
    assert json.loads((tmp_path / f'{DAY}.json').read_text())['schema'] == snapshot_store.SCHEMA


def test_display_tag_text_and_legacy_rows():
    assert jy.text(21) == '#21' and jy.text(None) == '—' and jy.text(0) == '#0'
    assert '#21' in jy.tag({'jersey': 21}) and '—' in jy.tag({'jersey': None}) and jy.tag({}) == ''


def test_board_rows_show_jersey_or_dash_next_to_name():
    html = nv.boards_html([_board()], 2)
    assert 'npr-name">J1</b><span class="npr-jn" title="Jersey number">#21</span>' in html
    assert 'npr-name">J3</b><span class="npr-jn none"' in html and '>—</span>' in html


def test_gem_match_table_shows_jersey_display_only():
    import gem_match_v58 as gmx
    f = ranked([('A Player', 5, {'Jersey': 21}), ('A Playerr', 6, {})])
    targets = pt.slate_targets([{'away': 'TOR', 'home': 'BOS', 'away_name': 'Toronto Maple Leafs', 'home_name': 'Boston Bruins',
                                 'arena': 'TD Garden', 'start': ''}], f, DAY)
    rows, _ = gmx.match_table(targets, 6)
    base, _ = gmx.match_table(pt.slate_targets([{'away': 'TOR', 'home': 'BOS', 'away_name': 'Toronto Maple Leafs', 'home_name': 'Boston Bruins',
                                                 'arena': 'TD Garden', 'start': ''}], f.drop(columns=['Jersey']), DAY), 6)
    assert [(r['Player'], r['Match type']) for r in rows] == [(r['Player'], r['Match type']) for r in base]
    assert {r['Player'] for r in rows} == {'A Player', 'A Playerr'}
    html = gmx.table_html(rows, [], 6)
    assert '<b>A Player</b><span class="npr-jn" title="Jersey number">#21</span>' in html
    assert '<b>A Playerr</b><span class="npr-jn none"' in html
