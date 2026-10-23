"""V5.5 full-app AppTests (offline fixtures): designed Home fragment, themes, EdgeLab tab stamp flow."""
import pytest

from v54_testkit import run_app


@pytest.fixture(scope='module')
def mp():
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(scope='module')
def app(mp, tmp_path_factory):
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


def test_edgelab_tab_stamp_in_full_app(app):
    app.slider(key='edgelab_min_edge').set_value(1.0).run()
    keys = [b.key for b in app.button if b.key and b.key.startswith('edgelab_stamp_')]
    assert len(keys) >= 4
    app.button(key=keys[0]).click().run()
    assert not app.exception
    assert len(app.session_state['edgelab_stamped']) == 1
    assert any(b.key == 'edgelab_rm_' + app.session_state['edgelab_stamped'][0]['key'] for b in app.button)
    app.button(key='edgelab_clear').click().run()
    assert app.session_state['edgelab_stamped'] == []
