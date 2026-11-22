"""t234: EdgeLab numerology overlay. Display/filter only: the anytime-goal % and order never change."""
from datetime import date
from pathlib import Path

import pytest

import numerology_overlay_v62 as nov
import scorer_patterns_v62 as sp
from numerology_v48 import gematria, universal_day

DAY = '2026-11-22'
GAMES = [{'Away': 'EDM', 'Home': 'STL', 'Venue': 'Enterprise Center', 'Start (UTC)': '2026-11-23T00:00:00Z'}]


def _name_with_root(root):
    for a in 'ABCDEFGHIJ':
        n = f'{a}l Smith'
        if gematria(n)['ordinal_root'] == root:
            return n
    raise AssertionError(root)


def _rows():
    ud = universal_day(DAY)
    miss = next(r for r in range(1, 10) if r != ud and r not in (1, 3, 4, 7))
    return [{'Player': _name_with_root(ud), 'Player ID': 1, 'Team': 'EDM', 'Jersey': 99, 'Birth date': '1990-01-01'},
            {'Player': _name_with_root(miss), 'Player ID': 2, 'Team': 'STL', 'Jersey': 99, 'Birth date': None}]


def test_matches_reuse_numbers_tab_logic_day_pattern_and_lifepath():
    m = nov.matches(_rows(), GAMES, DAY)
    assert set(m) == {'1', '2'}
    assert f'D {universal_day(DAY)}' in m['1']['gem']               # name digit == universal day (player_targets_v49)
    assert m['2']['gem'] == [] or all(not g.startswith('D ') for g in m['2']['gem'])
    assert m['2']['lp'] == [] and m['2']['lp_known'] is False       # no birthdate -> no Life Path, flagged
    assert m['1']['lp_known'] is True


def test_matches_never_raise_on_bad_input():
    assert nov.matches(None, GAMES, DAY) == {} and nov.matches(_rows(), [], DAY) == {} and nov.matches([{'x': 1}], GAMES, 'bad') == {}


def test_annotate_keeps_percent_order_and_engine_rank():
    preds = [{'pid': 2, 'name': 'B', 'p': .4}, {'pid': 1, 'name': 'A', 'p': .3}, {'pid': 3, 'name': 'C', 'p': .2}]
    nmap = {'1': {'gem': ['D 7'], 'pattern': [], 'lp': []}, '3': {'gem': [], 'pattern': ['Root 3'], 'lp': ['LP 5']}}
    full = nov.annotate(preds, nmap, ('gem',))
    assert [(r['pid'], r['p'], r['rank']) for r in full] == [(2, .4, 1), (1, .3, 2), (3, .2, 3)]
    assert [r['num'] for r in full] == [[], ['D 7'], []]
    tight = nov.annotate(preds, nmap, ('gem', 'lp'), tight=True)
    assert [(r['pid'], r['rank'], r['num']) for r in tight] == [(1, 2, ['D 7']), (3, 3, ['LP 5'])]
    assert nov.annotate(preds, nmap, (), tight=True) == [] and 'Pick at least one' in nov.empty_msg(())
    assert preds[0] == {'pid': 2, 'name': 'B', 'p': .4}   # input untouched


def _section(**kw):
    pat = {'status': 'ok', 'profile': {'nights': ['2026-11-20', '2026-11-21'], 'K': 200, 'N': 1500}, 'stats': []}
    row = {'pid': 1, 'name': 'A <b>', 'team': 'EDM', 'opp': 'STL', 'pos': 'C', 'phase': 'pre', 'p': .3, 'p_full': .3, 'mp': .28,
           'chips': ['Forward'], 'live': [], **kw.pop('row', {})}
    return sp.section_html(pat, kw.pop('preds', [row]), {}, {'eff': .04, 'k_sig': 5}, [], [], {'goals': 0}, DAY, **kw)


def test_section_html_unchanged_without_overlay_and_chips_with_it():
    base = _section()
    assert 'class="nu"' not in base and 'class="spn"' not in base
    on = _section(row={'num': ['D 7', 'LP <5>'], 'rank': 4}, num_head=nov.summary_html(1, 1, ('gem', 'lp'), True, 'Nov 22 pattern', 0))
    assert '<span class="nu">D 7</span>' in on and 'LP &lt;5&gt;' in on and '<span class="rk">4</span>' in on
    assert 'Numerology overlay ON' in on and 'tighter list shows only those' in on and 'stays out of the %' in on
    assert '30%' in on and 'A &lt;b&gt;' in on
    empty = _section(preds=[], empty_msg=nov.empty_msg(('gem',)))
    assert 'No engine pick still in play has a Gematria' in empty and 'No skaters left' not in empty


def test_overlay_is_default_off_and_wired_only_on_edgelab():
    src = Path('tabs/edgelab.py').read_text()
    assert "value=False, key=_ag_nov.TOGGLE_KEY" in src and "value=False, key=_ag_nov.TIGHT_KEY" in src
    assert 'numerology_overlay_v62' not in Path('tabs/numbers.py').read_text()
    assert 'numerology_overlay_v62' not in Path('tabs/predmodels.py').read_text()
    assert nov.DEFAULT_FAMILIES == ('gem',)


def test_files_small():
    for f in ('numerology_overlay_v62.py', 'scorer_patterns_v62.py', 'tabs/edgelab.py'):
        assert Path(f).stat().st_size < 100 * 1024
