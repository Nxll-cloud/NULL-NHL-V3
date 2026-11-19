"""V6.1 deploy diagnostics: runtime odds-key lookup (location only, never the value) and the build commit stamp."""
import os
import pytest
import deploy_info_v61 as di

K = 'k_TEST_VALUE_DO_NOT_LEAK'


@pytest.mark.parametrize('secrets,where', [
    ({'ODDS_API_KEY': K}, 'secrets: top-level ODDS_API_KEY'),
    ({'ODDS_API_KEY': f'  {K}  '}, 'secrets: top-level ODDS_API_KEY'),
    ({'odds_api_key': K}, 'secrets: top-level odds_api_key'),
    ({'THE_ODDS_API_KEY': K}, 'secrets: top-level THE_ODDS_API_KEY'),
    ({'odds': {'api_key': K}}, 'secrets: [odds] api_key'),
    ({'the_odds_api': {'key': K}}, 'secrets: [the_odds_api] key'),
    ({'api': {'ODDS_API_KEY': K}}, 'secrets: [api] ODDS_API_KEY'),
])
def test_key_found_and_location_named(secrets, where):
    assert di.find_odds_key(secrets, environ={}) == (K, where)


def test_top_level_wins_and_keeps_configuration_semantics():
    assert di.find_odds_key({'ODDS_API_KEY': K, 'odds': {'api_key': 'other'}}, environ={})[0] == K
    for bad in (False, 123, {'nested': 'x'}):   # existing behaviour: a non-string top-level key = configuration error
        assert di.find_odds_key({'ODDS_API_KEY': bad}, environ={})[0] == bad


def test_unrelated_sections_and_empty_values_ignored_then_env_then_missing():
    assert di.find_odds_key({'db': {'api_key': 'no'}, 'ODDS_KEY': '  '}, environ={}) == ('', None)
    assert di.find_odds_key({}, environ={'ODDS_API_KEY': K}) == (K, 'environment: ODDS_API_KEY')
    assert di.find_odds_key(None, environ={}) == ('', None)

    class Raises:   # st.secrets with no secrets file
        def items(self):
            raise FileNotFoundError('no secrets')
    assert di.find_odds_key(Raises(), environ={}) == ('', None)


def test_caption_never_contains_the_value():
    v, where = di.find_odds_key({'odds': {'api_key': K}}, environ={})
    cap = di.sidebar_caption({'commit': 'abc123def456', 'branch': 'main'}, where)
    assert K not in cap and 'Odds key: found (secrets: [odds] api_key)' in cap and 'Build abc123def456 (main)' in cap
    assert 'not found' in di.sidebar_caption({'commit': 'unknown'}, None)


def _git(tmp_path, head, refs=None, packed=''):
    g = tmp_path / '.git'
    g.mkdir()
    (g / 'HEAD').write_text(head)
    for ref, sha in (refs or {}).items():
        p = g.joinpath(*ref.split('/'))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(sha + '\n')
    if packed:
        (g / 'packed-refs').write_text(packed)
    return tmp_path


SHA = '774fb8dac8acec011cb5ed697fbede97ca92f5c0'


def test_build_stamp_from_ref_packed_detached_env_unknown(tmp_path):
    (tmp_path / 'a').mkdir()
    a = _git(tmp_path / 'a', 'ref: refs/heads/main\n', {'refs/heads/main': SHA})
    assert di.build_stamp(a, environ={}) == {'commit': SHA[:12], 'source': 'git', 'branch': 'main'}
    (tmp_path / 'b').mkdir()
    b = _git(tmp_path / 'b', 'ref: refs/heads/main\n', packed=f'# pack-refs\n{SHA} refs/heads/main\n')
    assert di.build_stamp(b, environ={})['commit'] == SHA[:12]
    (tmp_path / 'c').mkdir()
    c = _git(tmp_path / 'c', SHA + '\n')
    assert di.build_stamp(c, environ={})['commit'] == SHA[:12]
    (tmp_path / 'd').mkdir()
    assert di.build_stamp(tmp_path / 'd', environ={'GITHUB_SHA': SHA}) == {'commit': SHA[:12], 'source': 'env', 'branch': ''}
    assert di.build_stamp(tmp_path / 'd', environ={})['commit'] == 'unknown'


def test_real_checkout_stamp_matches_git_head():
    s = di.build_stamp()
    if os.path.isdir(os.path.join(di.HERE, '.git')):
        assert s['source'] == 'git' and len(s['commit']) == 12


def test_app_reads_key_at_runtime_not_import_time():
    src = open('app.py').read()
    fn = src[src.index('def np_api_key'):src.index('_np_live_quotes=pd.DataFrame()')]
    assert 'find_odds_key(st.secrets)' in fn and 'v61_odds_key_where' in fn
    assert src.index('_np_key=np_api_key()') > src.index('def np_api_key')
    assert "st.secrets.get('ODDS_API_KEY'" not in src   # single lookup path


def test_sectioned_key_reaches_the_shared_loader():
    """A key stored as [odds] api_key now feeds the same loader (offline fake provider); no missing-key state, no leak."""
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    from test_v60_edgelab import app_source, KEY
    st.cache_resource.clear()
    app = AppTest.from_string(app_source(), default_timeout=30)
    app.session_state['case'] = 'valid'
    app.secrets['odds'] = {'api_key': KEY}
    app.run()
    assert not app.exception
    html = ' '.join(m.value for m in app.markdown) + ' ' + ' '.join(h.value for h in app.get('html'))
    assert 'No provider key:' not in html and KEY not in html
    assert app.session_state['v61_odds_key_where'] == 'secrets: [odds] api_key'
