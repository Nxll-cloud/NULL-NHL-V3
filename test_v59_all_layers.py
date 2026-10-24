"""V5.9 All-layer matches curiosity expander (Numbers tab)."""
import pathlib
import re

import all_layers_v59 as al
from numerology_v48 import gematria

ROOT = pathlib.Path(__file__).resolve().parent


def _t(pid, name, team, day=False, arena=False, form=0.0):
    v = gematria(name)
    return {'player': name, 'player_id': pid, 'team': team, 'day': ['English'] if day else [],
            'arena_matches': ['English'] if arena else [], 'team_matches': [], 'matches': int(day) + int(arena),
            'form': form, 'form_known': True, 'shot_rate': None, 'eng_total': v['ordinal'], 'values': v}


def _arena(root):
    for name in ('Bell Centre', 'Scotiabank Arena', 'TD Garden', 'Rogers Place', 'Ball Arena', 'UBS Arena', 'KeyBank Center',
                 'Canada Life Centre', 'Climate Pledge Arena', 'Amerant Bank Arena', 'PPG Paints Arena', 'Enterprise Center',
                 'United Center', 'Little Caesars Arena', 'Crypto.com Arena', 'SAP Center', 'Honda Center', 'Xcel Energy Center'):
        if gematria(name)['ordinal_root'] == root:
            return name
    raise AssertionError(root)


def _slate(arena, players):
    return [{'game': {'away': 'MTL', 'home': 'TOR', 'arena': arena}, 'away_targets': players, 'home_targets': []}]


PM = lambda **c: {'id': dict(c), 'name': {}}

# Day 2 and arena number 2: Center has English 2 (and Reverse 7); Goaltender English 2. For Reverse on target 2 we need a
# label with Reverse digit 2: G (English 7 -> Reverse 2), Goalie (English 4 -> Reverse 5)... so a goalie G hits via Reverse.


def test_each_criterion():
    ar = _arena(2)
    ev = al.evaluate(_t('1', 'X', 'MTL', day=True, arena=True), 'G', 2, 2)
    assert ev['met'] == {'day': True, 'position': True, 'arena': True, 'reverse': True, 'english': True}
    assert 'Day Eng' in ev['hits'] and 'Arena Eng' in ev['hits'] and 'G=day Rev' in ev['hits'] and 'Goaltender=day Eng' in ev['hits']
    assert al.evaluate(_t('1', 'X', 'MTL', day=False, arena=True), 'G', 2, 2)['met']['day'] is False
    assert al.evaluate(_t('1', 'X', 'MTL', day=True, arena=False), 'G', 2, 2)['met']['arena'] is False
    nopos = al.evaluate(_t('1', 'X', 'MTL', day=True, arena=True), None, 2, 2)['met']
    assert nopos['position'] is False and nopos['reverse'] is False                 # name Rev = 9 - 2 = 7: no Reverse hit
    c = al.evaluate(_t('1', 'X', 'MTL', day=True, arena=True), 'C', 2, 2)            # Center Eng 2 = day/arena, no Rev 2
    assert c['met']['position'] and not c['met']['reverse'] and 'Center=day Eng' in c['hits']
    eng = al.evaluate(_t('1', 'X', 'MTL'), 'RW', 2, 2)['met']                        # Right Wing Rev 2 only -> no English
    assert eng['reverse'] and not eng['english']
    # labels come from the shared cipher
    for code, labels in al._pl.POS_LABELS.items():
        for lab in labels:
            g = gematria(al._pl._TEXT[lab])
            assert f'{al._pl._TEXT[lab]}=day Rev' in al.evaluate(_t('1', 'X', 'MTL'), code, g['reverse_root'], None)['hits']


def test_name_reverse_hit_counts():
    v = gematria('Mike Matheson')
    ev = al.evaluate(_t('1', 'Mike Matheson', 'MTL'), None, None, v['reverse_root'])
    assert ev['hits'] == ['Arena Rev'] and ev['met']['reverse'] and not ev['met']['arena']


def test_and_and_sort_and_closest():
    ar = _arena(2)
    ps = [_t('1', 'All Five', 'MTL', True, True, form=1.0), _t('2', 'Also Five', 'MTL', True, True, form=9.0),
          _t('3', 'No Arena', 'MTL', True, False), _t('4', 'No Rev', 'MTL', True, True), _t('5', 'Nothing', 'MTL')]
    full, close = al.rows(_slate(ar, ps), 2, PM(**{'1': 'G', '2': 'G', '3': 'G', '4': 'C', '5': 'G'}))
    assert [p['player'] for p in full] == ['Also Five', 'All Five']                  # pick_order: equal points -> form
    assert {p['player']: p['missed'] for p in close} == {'No Arena': ['arena'], 'No Rev': ['reverse']}
    out = al.table_html(full, close, 2)
    assert out.count('<tr class="gm-r">') == 2 and '2 players match all five layers' in out and 'No player matches' not in out
    assert '<span class="pl-c rv">G=day Rev</span>' in out


def test_empty_state_and_closest_list():
    ar = _arena(2)
    full, close = al.rows(_slate(ar, [_t('3', 'No Arena', 'MTL', True, False), _t('5', 'Nothing', 'MTL')]), 2, PM(**{'3': 'G'}))
    assert full == [] and [p['player'] for p in close] == ['No Arena']
    out = al.table_html(full, close, 2)
    assert 'No player matches all layers today.' in out and 'Closest (4 of 5)' in out and 'missed Arena' in out
    many = [dict(close[0], player=f'P{i}') for i in range(12)]
    assert 'showing 8 of 12' in al.table_html([], many, 2) and al.table_html([], many, 2).count('<li>') == 8
    assert 'No player hits 4 of the 5 layers either' in al.table_html([], [], 2)
    assert 'rankings are loaded' in al.table_html([], [], 2, loaded=False)


def test_scored_column_and_caption():
    ar = _arena(2)
    rec = {'day': 'd', 'demo': True, 'players': {1: {'name': 'All Five', 'goals': 1, 'game': '', 'events': []}}, 'names': {}}
    full, _ = al.rows(_slate(ar, [_t('1', 'All Five', 'MTL', True, True)]), 2, PM(**{'1': 'G'}), rec)
    assert full[0]['scored'] == '1G'
    out = al.table_html(full, [], 2, demo=True)
    assert '1G demo' in out and 'DEMO replay data' in out
    assert 'Curiosity layer — not used in any score' in out


def test_not_imported_by_scoring_modules():
    hits = [f.name for f in ROOT.rglob('*.py')
            if not f.name.startswith('test_') and f.name not in ('all_layers_v59.py', 'prediction_models_v59.py') and f.parent.name != 'tabs'
            and re.search(r'all_layers_v59', f.read_text(errors='ignore'))]
    assert hits == []


def test_collapsed_expander_between_position_sections():
    src = (ROOT / 'tabs' / 'numbers.py').read_text()
    i = src.index("\nwith st.expander('Position gematria · curiosity layer'):\n")
    j = src.index("\nwith st.expander('All-layer matches · curiosity layer'):\n")
    k = src.index("\nwith st.expander('Position + gematria layers · curiosity layer'):\n")
    assert i < j < k and src.count('_alllay.table_html(') == 1 and src.count('_alllay.rows(') == 1
    assert 'expanded=True' not in src[i:]


def test_css():
    css = (ROOT / 'assets' / 'v58.css').read_text()
    assert '.v59-al' in css and '<' not in css
