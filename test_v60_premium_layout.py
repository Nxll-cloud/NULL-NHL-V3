"""V6.0 premium polish: render/structure guards (CSS + markup only, no data)."""
import re
from pathlib import Path

import v55_ui as v5
import prediction_models_v59 as pmv

ROOT = Path(__file__).resolve().parent


def test_premium_layers_load_last_and_are_small():
    dark, light = v5.design_css('dark'), v5.design_css('light')
    prem = (ROOT / 'assets' / 'v60_premium.css').read_text(encoding='utf-8')
    darkonly = (ROOT / 'assets' / 'v60_premium_dark.css').read_text(encoding='utf-8')
    assert dark.rstrip().endswith(darkonly.rstrip()) and prem in dark and prem in light and darkonly not in light
    assert dark.index(prem) > dark.index('.v58-num .npr{')  # after v58 + mobile layers
    for f in ('v60_premium.css', 'v60_premium_dark.css'):
        assert (ROOT / 'assets' / f).stat().st_size < 100 * 1024
        assert not re.search(r'<[A-Za-z/!]', (ROOT / 'assets' / f).read_text(encoding='utf-8'))


def test_section_subheader_not_squeezed_by_logo_rule():
    css = v5.design_css('dark')
    assert '.v55 .mini{width:22px;height:22px' in css           # the logo rule still exists...
    assert '.v55 .sh.mini{width:auto;height:auto' in css         # ...but sec_head is released from it
    assert css.index('.v55 .sh.mini{width:auto;height:auto') > css.index('.v55 .mini{width:22px;height:22px')
    assert 'class="sh mini"' in v5.sec_head('Night by night', 'sub')


def test_tab_bar_and_banner_selectors_present():
    css = v5.design_css('dark')
    assert '[data-testid="stTabs"] [role="tab"][aria-selected="true"]' in css
    assert '.v55 .th::before' in css and '.v55 .hero::after' in css


def test_prediction_models_structure():
    t = {s: {'source': 'test', 'rows': [{'rank': 1, 'pid': 1, 'name': 'A Player', 'team': 'TOR', 'pos': '', 'stat': '10.0%',
                                         'layers': '1 layer' if s == 'blend' else ''}]} for s in pmv.SYSTEMS}
    html = pmv.page_html(t, [], ())
    assert html.count('class="pmc"') == 4 and html.count('class="pmacc"') == 4 and html.count('<h3>') == 4
    assert '<div class="pm">' in html and html.count('class="pmr') == 4 and 'class="pmx"' in html
    css = v5.design_css('dark')
    for sel in ('.v55 .pm .pmc{', '.v55 .pm .pmc .pmacc{margin-top:auto', '.v55 section.pms{'):
        assert sel in css
