"""V5.9 Position gematria curiosity table (Numbers tab)."""
import pathlib
import re

import position_gematria_v59 as pg
from numerology_v48 import gematria

ROOT = pathlib.Path(__file__).resolve().parent


def _by_label():
    return {r['label']: r for r in pg.rows()}


def test_order_and_labels():
    assert [label for label, _ in pg.LABELS] == [
        'Center', 'Left Wing', 'Right Wing', 'Defenseman (US)', 'Defenceman (Canadian)', 'Defense', 'Forward',
        'Goalie', 'Goaltender', 'C', 'L', 'R', 'D', 'G', 'LW', 'RW']


def test_values_computed_from_shared_cipher():
    rows = _by_label()
    assert rows['Center']['english'] == (65, 2) and rows['Center']['reduced'] == (29, 2) and rows['Center']['reverse'] == (97, 7)
    assert rows['Defenseman (US)']['english'] == (86, 5)
    assert rows['Defenceman (Canadian)']['english'] == (70, 7)
    assert rows['G']['english'] == (7, 7) and rows['G']['reverse'] == (20, 2)
    assert rows['LW']['english'] == (35, 8) and rows['LW']['reverse'] == (19, 1)
    for r in pg.rows():
        v = gematria(r['text'])
        assert r['english'] == (v['ordinal'], v['ordinal_root'])
        assert r['reduced'] == (v['reduction'], v['reduction_root'])
        assert r['reverse'] == (v['reverse'], v['reverse_root'])


def test_values_not_hardcoded_in_module():
    src = (ROOT / 'position_gematria_v59.py').read_text()
    assert '86' not in src and '→ 5' not in src


def test_html_has_both_spellings_and_curiosity_note():
    out = pg.table_html()
    assert '<b>Defenseman</b><small class="pg-sp">(US)</small>' in out
    assert '<b>Defenceman</b><small class="pg-sp">(Canadian)</small>' in out
    assert 'Curiosity layer — not used in any score, rank, tier, TOP PICK or match table.' in out
    assert 'Position gematria' in out
    assert out.count('<tr class="gm-r">') == 16
    assert '65 → 2' in out and '200 → 2' in out


def test_numbers_tab_renders_it_once_in_expander():
    src = (ROOT / 'tabs' / 'numbers.py').read_text()
    assert src.count('_posgem.table_html()') == 1
    assert "st.expander('Position gematria · curiosity layer')" in src


def test_not_imported_by_scoring_modules():
    hits = []
    for f in ROOT.rglob('*.py'):
        if f.name.startswith('test_') or f.name in ('position_gematria_v59.py', 'position_layers_v59.py') or f.parent.name == 'tabs':
            continue
        if re.search(r'position_gematria_v59', f.read_text(errors='ignore')):
            hits.append(f.name)
    assert hits == []
