"""V5.7: brand assets are the owner's raster logo (webp + png/jpg fallbacks); the old shield/Ø SVGs are gone."""
import shutil
from pathlib import Path

from PIL import Image

import ui_theme_v53 as ui
import v55_ui as v5

ASSETS = Path(__file__).resolve().parent / 'assets'
BRAND_FILES = {  # name: (width, height)
    'logo_full.webp': (640, 640), 'logo_full.jpg': (512, 512), 'logo_full_360.webp': (360, 360),
    'logo_mark.webp': (256, 256), 'logo_mark.png': (256, 256), 'logo_mark_128.webp': (128, 128),
    'favicon.png': (64, 64), 'favicon_256.png': (256, 256),
}


def test_brand_files_exist_are_images_and_small():
    for name, size in BRAND_FILES.items():
        path = ASSETS / name
        assert path.is_file() and 0 < path.stat().st_size < 100_000, name
        with Image.open(path) as im:
            assert im.size == size, name
    assert (ASSETS / 'favicon.png').read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'


def test_old_logo_files_removed():
    for name in ('logo.svg', 'logo_mark.svg', 'logo_1024.png', 'logo_mark_512.png'):
        assert not (ASSETS / name).exists(), name
    assert 'svg' not in ' '.join(ui.LOGO_FILES.values()) + ' '.join(ui.LOGO_FALLBACKS.values())
    assert 'Ø' not in ui.brand('mark', base='/nonexistent')


def test_brand_helper_inlines_raster():
    html = ui.brand('full', 'lg')
    assert html.startswith('<img') and 'data:image/webp;base64,' in html and 'np-brand-lg' in html
    assert 'np-brand-mark' in ui.brand('mark', 'sm') and 'data:image/webp' in ui.brand('mark', 'sm')
    assert 'np-brand-md' in ui.brand('weird', 'huge')  # invalid args normalized
    assert len(ui.logo_data_uri('full')) < len(ui.logo_data_uri('full', hires=True))


def test_mime_sniffing():
    assert ui._image_mime(b'RIFF\x00\x00\x00\x00WEBPVP8 ') == 'image/webp'
    assert ui._image_mime(b'\x89PNG\r\n\x1a\n....') == 'image/png'
    assert ui._image_mime(b'\xff\xd8\xff\xe0') == 'image/jpeg'
    assert ui._image_mime(b'not an image') is None and ui._image_mime(None) is None


def test_fallbacks_when_assets_missing(tmp_path):
    html = ui.brand('full', base=str(tmp_path))
    assert 'np-brand-text' in html and 'PLAYBOOK' in html
    assert ui.logo_data_uri('mark', base=str(tmp_path)) is None
    assert ui.page_icon(base=str(tmp_path)) == '👑'
    (tmp_path / 'logo_full_360.webp').write_text('not an image')
    assert ui.logo_data_uri('full', base=str(tmp_path)) is None
    alt = tmp_path / 'alt'; alt.mkdir()  # fresh base (asset bytes are cached per base)
    (alt / 'logo_full_360.webp').write_text('not an image')
    shutil.copy(ASSETS / 'logo_full.jpg', alt / 'logo_full.jpg')  # corrupt webp -> jpg fallback
    assert ui.logo_data_uri('full', base=str(alt)).startswith('data:image/jpeg;base64,')


def test_logo_paths_and_page_icon():
    assert ui.logo_path('mark', fallback=True).endswith('logo_mark.png')
    assert ui.logo_path('full').endswith('logo_full.webp')
    assert getattr(ui.page_icon(), 'size', None) == (64, 64)


def test_logo_in_tab_heads_and_home_hero():
    assert 'v55-mark' in v5.tab_head('K', 'T') and 'data:image/webp' in v5.tab_head('K', 'T')
    assert 'hero-brand' in v5.hero({'day': '2026-10-22'}, None) and 'data:image/webp' in v5.hero({'day': '2026-10-22'}, None)
