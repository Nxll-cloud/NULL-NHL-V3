import xml.etree.ElementTree as ET
from pathlib import Path

import ui_theme_v53 as ui

ASSETS = Path(__file__).resolve().parent / 'assets'


def test_brand_files_exist_and_svg_is_valid_xml():
    for name in ('logo.svg', 'logo_mark.svg', 'favicon.png', 'favicon_256.png', 'logo_1024.png', 'logo_mark_512.png'):
        assert (ASSETS / name).is_file() and (ASSETS / name).stat().st_size > 0
    for name in ('logo.svg', 'logo_mark.svg'):
        root = ET.parse(ASSETS / name).getroot()
        assert root.tag.endswith('svg') and root.get('viewBox')
    assert (ASSETS / 'favicon.png').read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'


def test_brand_helper_inlines_svg():
    html = ui.brand('full', 'lg')
    assert html.startswith('<img') and 'data:image/svg+xml;base64,' in html and 'np-brand-lg' in html
    assert 'np-brand-mark' in ui.brand('mark', 'sm')
    assert 'np-brand-md' in ui.brand('weird', 'huge')  # invalid args normalized


def test_fallbacks_when_assets_missing(tmp_path):
    html = ui.brand('full', base=str(tmp_path))
    assert 'np-brand-text' in html and 'PLAYBOOK' in html
    assert ui.logo_data_uri('mark', base=str(tmp_path)) is None
    assert ui.page_icon(base=str(tmp_path)) == '👑'
    (tmp_path / 'logo.svg').write_text('not an svg')
    assert ui.logo_data_uri('full', base=str(tmp_path)) is None
