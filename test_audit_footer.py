"""Audit P1.7d: one shared footer on every tab (21+/1-800-GAMBLER, data sources + MoneyPuck terms,
not affiliated with the NHL, not betting advice, model card link)."""
import re
from pathlib import Path

import pytest

import app_footer
from v54_testkit import run_app

ROOT = Path(__file__).resolve().parent


def test_footer_text_has_every_required_part():
    md = app_footer.footer_md()
    assert '21+' in md and '1-800-GAMBLER' in md
    for name in ('NHL API', 'ESPN', 'MoneyPuck', 'The Odds API'):
        assert f'[{name}](' in md
    assert 'MoneyPuck data used under its terms' in md and 'non-commercial' in md
    assert 'Not affiliated with or endorsed by the NHL' in md
    assert 'not betting advice' in md
    assert '[Model card](https://github.com/Nxll-cloud/NULL-NHL-V3/blob/main/MODEL_CARD.md)' in md
    assert (ROOT / 'MODEL_CARD.md').exists()
    assert '<' not in md   # plain markdown: no HTML/JS


def test_render_draws_one_caption():
    calls = []

    class Fake:
        def caption(self, text):
            calls.append(('caption', text))

    app_footer.render(Fake())
    assert calls == [('caption', app_footer.footer_md())]


def test_app_renders_footer_after_every_tab_body():
    src = (ROOT / 'app.py').read_text()
    # V6.1: each tab is np_run_tab(name, label) = run_tab inside safe_section, then the shared footer (its own section)
    helper = src[src.index('def np_run_tab('):]
    helper = helper[:helper.index('\n\n\n')]
    assert re.search(r"np_run_section\(name, [^)]*\)\n\s+with safe_section\([^)]*\):\n\s+app_footer\.render\(st\)", helper)
    all_runs = re.findall(r"np_run_tab\('(\w+)', '[^']+'\)", src)
    assert len(all_runs) == len(set(all_runs))
    assert set(all_runs) == {p.stem for p in (ROOT / 'tabs').glob('*.py')} - {'__init__', 'live'}
    assert "np_run_section('live'" in src
    assert src.index('def _np_drop_stale_modules') < src.index('import app_footer')   # crash guard stays first


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


def test_every_tab_shows_footer_in_apptest(mp, tmp_path_factory):
    mp.setenv('FEATURE_TRACK_RECORD', '1')
    at = run_app(mp, tmp_path_factory.mktemp('footer'))
    assert not at.exception
    assert len(at.tabs) == 11   # V5.9: + Prediction Models
    for tab in at.tabs:
        caps = [c.value for c in tab.caption]
        assert caps.count(app_footer.footer_md()) == 1, tab.label
