"""V5.5 full-app AppTests (offline fixtures): designed Home fragment, themes, EdgeLab tab (read-only since V5.8)."""
import pytest

from v54_testkit import run_app


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(scope='module')
def app(mp, tmp_path_factory):
    mp.setenv('FEATURE_TRACK_RECORD', '1')   # V5.8: Track Record hidden by default; V5.5 tab-order checks run with the flag ON
    return run_app(mp, tmp_path_factory.mktemp('v55'))


def _html(at):
    return [h for h in at.get('html')]


def test_home_fragment_is_st_html_with_js(app):
    assert not app.exception
    hs = _html(app)
    assert hs, 'Home must render through st.html'
    home = hs[0]
    assert home.proto.unsafe_allow_javascript
    body = home.value
    for needle in ('class="v55 v55-app', 'class="hero', 'np-intel-row', 'Tonight’s board', '<script>'):
        assert needle in body, needle
    assert 'PREVIEW' not in body and 'role="tab"' not in body      # no fake HTML tabs, no preview chip


def test_nine_native_tabs(app):
    labels = [t.label for t in app.tabs]   # at.tabs also lists EdgeLab's nested tabs (depth-first)
    top = ['🏠 Home', '🎯 Matchup Center', '⚡ Odds', '📊 Research', '🔮 Numbers', '📈 Track Record', '🧪 EdgeLab', '⏱ Live Next Goal', '🚩 Edge Flags']
    assert [x for x in labels if x in top] == top


@pytest.mark.parametrize('label,flag', [('Light', 'data-theme="light"'), ('High contrast', 'data-theme="contrast"')])
def test_theme_switch(app, label, flag):
    seg = [x for x in app.get('button_group') if getattr(x, 'key', None) == 'v55_theme']
    if seg:
        seg[0].set_value(label).run()
    else:
        app.radio(key='v55_theme').set_value(label).run()
    assert not app.exception
    md = ' '.join(m.value for m in app.markdown)
    assert flag in md
    assert flag in _html(app)[0].value


def test_edgelab_tab_is_read_only_in_full_app(app):
    # V5.8: EdgeLab is a read-only view (no bankroll / Min Edge / Stamp / Scorecard); see test_v58_edgelab.py
    assert not app.exception
    keys = {getattr(w, 'key', None) for w in list(app.button) + list(app.slider) + list(app.number_input)}
    assert not any(k and k.startswith('edgelab_') for k in keys)
    assert not any(t.label.startswith('Scorecard') or t.label in ('Games', 'Props') for t in app.tabs)
