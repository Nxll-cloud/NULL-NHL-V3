"""Saved audit UI only: reviewed compact values, explicit limitations, no runtime backtest/API."""
from pathlib import Path
import hashlib
import number_pattern_backtest_v60 as audit


def test_reviewed_compact_summary_integrity_and_coverage():
    data=audit.load_summary()
    assert hashlib.sha256(audit.SUMMARY.read_bytes()).hexdigest()==SUMMARY_SHA256
    assert data['coverage']['games']==2624
    assert data['coverage']['skater_appearances']==94454
    assert set(data['coverage']['seasons'])=={'20242025','20252026'}
    assert all(s['games']==1312 for s in data['coverage']['seasons'].values())
    assert data['as_of']=='2026-11-07'
    assert audit.SUMMARY.stat().st_size<100000


def test_exact_saved_primary_rates_denominators_and_correct_ci_units():
    html=audit.section_html()
    for text in ('14.88%','15.15%','1,141','7,667','213 / 34','6.052','[5.784, 6.323]','0.6265'):
        assert text in html
    assert '95% date-cluster CI' in html
    assert '[-5.43, +4.36] pp' in html
    assert 'differences from controls, not confidence intervals around the raw hit rate' in html
    assert 'No reliable scoring or winning advantage found.' in html


def test_untested_new_overlay_mapping_and_undefined_literal_disclosed():
    html=audit.section_html()
    assert '4, 10, 0, 9, 3, 6' in html
    assert 'Possible date mapping: October 9th, 36.' in html
    assert 'not tested' in html and 'does not validate today’s optional player-row overlay' in html
    assert 'no meaning or year is inferred for 36' in html
    assert '2-21 is not split or expanded.' in html
    assert '50% wins is a tautology' in html
    assert 'only 1–9' in html and 'Zero core exposures (not 0% accuracy)' in html


def test_methods_controls_missing_controls_and_sources_no_promise():
    html=audit.section_html()
    for text in ('1,000','2,000','1,999','without replacement','season and calendar month','0.825','Not testable'):
        assert text in html
    for url in ('https://api.nhle.com/stats/rest/en/game','https://api.nhle.com/stats/rest/en/team/summary','https://api.nhle.com/stats/rest/en/skater/summary'):
        assert 'href="'+url+'"' in html
    assert 'not a prospective betting test' in html and 'no odds/ROI analysis' in html
    assert '<details><summary>Methods' in html
    assert 'overflow-x:auto' in html and 'max-width:100%' in html and '.npaudit table' in html


def test_separate_renderer_integration_below_panel_and_no_runtime_fetch(monkeypatch):
    import requests
    monkeypatch.setattr(requests,'get',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No API fetch allowed')))
    assert '2,624 final games' in audit.section_html()
    src=Path('tabs/numbers.py').read_text()
    assert src.index('numv58.reference_patterns_html()')<src.index('_num_audit.render(st)')<src.index('_games_num=np_snapshot')
    assert src.count('_num_audit.render(st)')==1
    module=Path('number_pattern_backtest_v60.py').read_text()
    assert 'import requests' not in module and 'import numbers_v58_ui' not in module
    assert 'from numbers_v58_ui' not in module and 'follow_pattern' not in module.lower()


def test_streamlit_saved_expander_renders_offline():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('''
import streamlit as st
import number_pattern_backtest_v60 as audit
audit.render(st)
''').run()
    assert not app.exception
    assert app.expander[0].label=='Historical number-pattern audit · 2024–25 & 2025–26'
    assert not app.button and not app.toggle


def test_missing_file_clear_unavailable_without_fabricated_results(monkeypatch,tmp_path):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(audit,'SUMMARY',tmp_path/'missing.json')
    app=AppTest.from_string('''
import streamlit as st
import number_pattern_backtest_v60 as audit
audit.render(st)
''').run()
    assert not app.exception
    assert 'Saved historical audit unavailable' in app.caption[0].value


SUMMARY_SHA256 = '6b4a62bd3ee745bfcf6c1f987b5971a4c529188a6a8aed906761f29e2f7cd9ef'
