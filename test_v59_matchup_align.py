"""V5.9 Matchup Center goalie-threat rows: the % column lines up on every row and card (markup + CSS assertions)."""
import re
from pathlib import Path

import v56_ui as v56

ASSETS = Path(__file__).resolve().parent / 'assets'
V56 = (ASSETS / 'v56.css').read_text()
V55 = (ASSETS / 'v55.css').read_text()


def _rule(css, sel):
    m = re.search(re.escape(sel) + r'\{([^}]*)\}', css)
    assert m, sel
    return m.group(1)


def test_gtr_columns_are_fixed_so_pct_never_moves():
    cols = re.search(r'grid-template-columns:([^;]+)', _rule(V56, '.v55 .gtr')).group(1)
    tracks = cols.split()
    assert len(tracks) == 5 and 'auto' not in tracks          # an auto H2H track sized per row shifted the % column
    assert tracks[2] == 'minmax(0,1fr)' and tracks[3].endswith('px') and tracks[4].endswith('px')


def test_pct_box_not_shrunk_by_generic_mini_logo_rule():
    assert 'width:22px' in _rule(V55, '.v55 .mini')          # the logo rule that also matched "ngp mini"
    fix = _rule(V56, '.v55 .ngp.mini')
    assert 'width:auto' in fix and 'height:auto' in fix
    # v56.css is appended after v55.css, and .ngp.mini is more specific anyway
    src = (Path(__file__).resolve().parent / 'v55_ui.py').read_text()
    assert src.index("_asset_text('v55.css')") < src.index("_asset_text('v56.css')")


def test_h2h_text_wraps_in_two_chunks_inside_fixed_column():
    html = v56.h2h_text({'goals': 1, 'sog': 16, 'games': 3})
    assert html.count('<span>') == 2 and 'H2H 1 G / 16 SOG' in html and '· 3 gp' in html
    assert 'class="h2h hit"' in html
    assert v56.h2h_text(None) == '<small class="h2h none">no H2H shots</small>'
    assert 'white-space:nowrap' in _rule(V56, '.v55 .gtr .h2h span')


def test_goalie_threat_rows_keep_five_cells():
    g = {'name': 'Jake Allen', 'status': 'probable', 'sv': '.883', 'gaa': '3.15'}
    threats = [{'rank': 1, 'name': 'Artemi Panarin', 'p_next': 0.048, 'h2h': {'goals': 1, 'sog': 2, 'games': 1}},
               {'rank': 4, 'name': 'Arseny Gritsyuk', 'p_next': 0.04, 'h2h': None}]
    out = v56.goalie_threats(g, 'NJD', threats, '20262027', 'since 2024-25')
    assert out.count('<div class="gtr">') == 2
    assert out.count('<span class="ngp mini"><em>') == 2 and out.count('class="h2h') == 2
    assert '4.8%' in out and 'no H2H shots' in out
