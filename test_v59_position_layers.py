"""V5.9 Position + gematria layers curiosity expander (Numbers tab)."""
import pathlib
import re

import position_layers_v59 as pl
import pos_tag_v59 as pt
from numerology_v48 import gematria

ROOT = pathlib.Path(__file__).resolve().parent


def _t(pid, name, team, day=(), arena=(), tm=(), form=0.0, eng=None):
    return {'player': name, 'player_id': pid, 'team': team, 'day': list(day), 'arena_matches': list(arena),
            'team_matches': list(tm), 'matches': len(day) + len(arena) + len(tm), 'form': form, 'form_known': True,
            'shot_rate': None, 'eng_total': eng if eng is not None else gematria(name)['ordinal']}


def _slate(arena, away, home):
    return [{'game': {'away': 'MTL', 'home': 'TOR', 'arena': arena}, 'away_targets': away, 'home_targets': home}]


def _pmap(**codes):
    return {'id': dict(codes), 'name': {}}


def _arena_with_root(r):
    for name in ('Bell Centre', 'Scotiabank Arena', 'TD Garden', 'Rogers Place', 'Ball Arena', 'UBS Arena', 'KeyBank Center',
                 'Canada Life Centre', 'Climate Pledge Arena', 'Amerant Bank Arena', 'PPG Paints Arena', 'Enterprise Center'):
        if gematria(name)['ordinal_root'] == r:
            return name
    raise AssertionError(r)


def test_position_layer_day_and_codes_vs_arena():
    assert 'Defenceman=day' in pl.position_hits('D', 7, None)          # any D on a day-7 slate
    assert pl.position_hits('D', 7, None) == ['Defenceman=day']           # Defenseman 5, Defense 4, D 4 do not fire
    assert pl.position_hits('C', None, 3) == ['C=arena']                  # C = 3
    assert pl.position_hits('LW', None, 3) == ['L=arena']                 # L = 12 -> 3
    assert pl.position_hits('LW', None, 6) == ['Left Wing=arena']         # Left Wing = 96 -> 6
    assert pl.position_hits('G', 7, 7) == ['G=day', 'G=arena']
    assert pl.position_hits(None, 7, 3) == [] and pl.position_hits('', 4, 4) == []
    for code, labels in pl.POS_LABELS.items():                            # every label digit comes from the shared cipher
        for lab in labels:
            text = dict(__import__('position_gematria_v59').LABELS)[lab]
            r = gematria(text)['ordinal_root']
            assert (f'{text}=day' in pl.position_hits(code, r, None))


def test_layer_counts_sort_and_no_hit_count():
    arena = _arena_with_root(3)
    away = [_t('1', 'Mike Matheson', 'MTL', day=['English']),                    # D: day + Defenceman=day -> 2
            _t('2', 'Nick Suzuki', 'MTL', arena=['English'], tm=['English']),    # C: arena + team + C=arena -> 3
            _t('3', 'Quiet Guy', 'MTL')]                                         # unknown position, no hits
    home = [_t('4', 'Some Winger', 'TOR'),                                       # LW: L=arena only -> 1
            _t('5', 'No Hits', 'TOR')]                                           # RW: R=9, RW=5, Right Wing=7 -> day 7 hits!
    rows, none = pl.rows(_slate(arena, away, home), 7, _pmap(**{'1': 'D', '2': 'C', '4': 'LW', '5': 'D'}))
    by = {r['player']: r for r in rows}
    assert by['Nick Suzuki']['layers'] == 3 and by['Nick Suzuki']['pos_hits'] == ['C=arena']
    assert by['Mike Matheson']['layers'] == 2 and by['Mike Matheson']['pos_hits'] == ['Defenceman=day']
    assert by['Some Winger']['layers'] == 1 and by['Some Winger']['pos_hits'] == ['L=arena']
    assert by['No Hits']['layers'] == 1                                          # D on day 7 -> position layer only
    assert 'Quiet Guy' not in by and none == 1
    assert [r['layers'] for r in rows] == sorted((r['layers'] for r in rows), reverse=True)
    assert rows[0]['player'] == 'Nick Suzuki'
    out = pl.table_html(rows, none, 7)
    assert out.count('<tr class="gm-r">') == 4 and '1 player with no layer hit' in out
    assert '<span class="pl-c">Defenceman=day</span>' in out and '<span class="pl-c">C=arena</span>' in out


def test_tie_break_uses_pick_order():
    import numbers_v58_ui as nv
    arena = _arena_with_root(5)
    a = [_t('10', 'Alpha One', 'MTL', day=['English'], form=1.0), _t('11', 'Beta Two', 'MTL', day=['English'], form=9.0),
         _t('12', 'Gamma Three', 'MTL', tm=['English'], form=50.0)]
    rows, _ = pl.rows(_slate(arena, a, []), 1, None)
    assert [r['layers'] for r in rows] == [1, 1, 1]
    assert [r['player'] for r in rows] == [p['player'] for p in sorted(rows, key=lambda p: nv.pick_order(p))]
    assert [r['player'] for r in rows][:2] == ['Beta Two', 'Alpha One']            # day (3 pts) before team, form breaks tie
    mp = {'10': 0.9, '11': 0.1}
    rows, _ = pl.rows(_slate(arena, a, []), 1, None, model_p=mp)
    assert [r['player'] for r in rows][:2] == ['Alpha One', 'Beta Two']


def test_unknown_position_blank_and_no_pos_layer():
    rows, _ = pl.rows(_slate(_arena_with_root(3), [_t('1', 'Mike Matheson', 'MTL', day=['English'])], []), 7, None)
    assert rows[0]['pos'] == '' and rows[0]['pos_hits'] == [] and rows[0]['layers'] == 1
    assert '<td class="pl-pos"></td>' in pl.table_html(rows, 0, 7)


def test_scored_column_and_demo_label():
    rec = {'day': '2026-10-24', 'demo': False, 'players': {1: {'name': 'Mike Matheson', 'goals': 1, 'game': 'MTL@TOR', 'events': []},
                                                            2: {'name': 'Nick Suzuki', 'goals': 2, 'game': 'MTL@TOR', 'events': []}},
           'names': {}}
    rows, _ = pl.rows(_slate(_arena_with_root(3), [_t('1', 'Mike Matheson', 'MTL', day=['English']),
                                                   _t('2', 'Nick Suzuki', 'MTL', tm=['English']),
                                                   _t('3', 'Jake Evans', 'MTL', tm=['English'])], []), 7, None, rec)
    by = {r['player']: r['scored'] for r in rows}
    assert by == {'Mike Matheson': '1G', 'Nick Suzuki': '2G', 'Jake Evans': ''}
    out = pl.table_html(rows, 0, 7)
    assert '>1G</span>' in out and '>2G</span>' in out and 'DEMO' not in out
    demo = pl.table_html(rows, 0, 7, demo=True)
    assert '(DEMO replay data)' in demo and '1G demo' in demo
    assert pl.scored(None, '1', 'Mike Matheson') == ''


def test_not_loaded_and_empty():
    assert 'once this slate’s rankings are loaded' in pl.table_html([], 0, 7, loaded=False)
    assert 'No player hits any layer tonight' in pl.table_html([], 3, 7)


def test_not_imported_by_scoring_modules():
    hits = [f.name for f in ROOT.rglob('*.py')
            if not f.name.startswith('test_') and f.name not in ('position_layers_v59.py', 'all_layers_v59.py', 'prediction_models_v59.py') and f.parent.name != 'tabs'
            and re.search(r'position_layers_v59', f.read_text(errors='ignore'))]
    assert hits == []


def test_renders_once_in_expander_under_position_gematria():
    src = (ROOT / 'tabs' / 'numbers.py').read_text()
    i = src.index("st.expander('Position gematria · curiosity layer')")
    j = src.index("st.expander('Position + gematria layers · curiosity layer')")
    assert i < j and src.count("st.expander('Position + gematria layers · curiosity layer')") == 1
    between = src[i:j]
    # order at the end of the tab: Position gematria -> All-layer matches -> Position + gematria layers
    assert between.count('st.expander(') == 2 and between.count('_posgem.table_html()') == 1
    assert "st.expander('All-layer matches · curiosity layer')" in between
    assert src.count('_poslay.table_html(') == 1 and src.count('_poslay.rows(') == 1
    assert 'expanded=True' not in src[j:]


def test_css_present_and_safe():
    css = (ROOT / 'assets' / 'v58.css').read_text() + (ROOT / 'assets' / 'mobile.css').read_text()
    assert '.v59-pl' in css and '<' not in css
