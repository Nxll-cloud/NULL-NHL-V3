"""Number reference display: literal notation, accessible key underline, no scoring changes."""
from html.parser import HTMLParser
from pathlib import Path
import ast
import numbers_v58_ui as nv


class ReferenceParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.in_u=False; self.underlined=[];self.current=[];self.sections=[];self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag=='u':self.in_u=True;self.current=[]
        if tag=='section':self.sections.append(dict(attrs))
    def handle_endtag(self,tag):
        if tag=='u':self.underlined.append(''.join(self.current));self.in_u=False
    def handle_data(self,data):
        self.text.append(data)
        if self.in_u:self.current.append(data)


def test_exact_primary_and_only_key_sequence_underlined():
    html=nv.reference_patterns_html()
    parser=ReferenceParser();parser.feed(html)
    assert '<p>9, <u>91</u>, <u>92</u>, <u>93</u>, <u>19</u></p>' in html
    assert parser.underlined==['91','92','93','19']
    assert '<u>9</u>' not in html
    assert 'underlined numbers mark the key sequence' in html
    assert parser.sections==[{'class':'sec num-pattern-ref','aria-label':'Number patterns reference'}]


def test_secondary_groups_literal_not_range_and_honorary_separate():
    html=nv.reference_patterns_html()
    assert '<h4>Secondary patterns</h4><ul><li>2-21, 22, 20</li><li>7, 27, 37, 17</li><li>4, 43, 44, 49</li></ul>' in html
    assert '<h4>Honorary numbers</h4><p>81, 18, 11, 13</p>' in html
    assert '2–21' not in html and '2, 3, 4' not in html
    assert '<h4>Primary pattern</h4>' in html and 'nprf-primary' in html
    assert 'Display reference only' in html and 'unchanged' in html


def test_mobile_scoped_theme_and_no_widgets_or_forecast_inputs():
    html=nv.reference_patterns_html()
    assert '.num-pattern-ref .nprf-grid' in html
    assert 'max-width:100%' in html and 'min-width:0' in html and 'box-sizing:border-box' in html
    assert '@media(max-width:600px)' in html and 'grid-template-columns:1fr' in html
    assert 'rgba(155,92,255' in html and 'rgba(0,229,255' in html
    assert 'text-decoration-line:underline' in html
    source=Path('numbers_v58_ui.py').read_text()
    fn=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='reference_patterns_html')
    calls=[n for n in ast.walk(fn) if isinstance(n,ast.Call)]
    assert not calls # Static markup only: no models, ciphers, filters or APIs invoked.


def test_reference_is_unconditional_near_header_before_existing_numbers_strip():
    src=Path('tabs/numbers.py').read_text()
    assert src.count('numv58.reference_patterns_html()')==1
    caption=src.index("st.caption('Symbolic patterns for entertainment only.")
    reference=src.index('numv58.reference_patterns_html()')
    schedule=src.index('_games_num=np_snapshot')
    tonight=src.index('numv58.tonight_strip(')
    assert caption<reference<schedule<tonight
    # Integration adds no controls and does not modify the existing scoring/sort calls.
    assert 'numboard.slate_boards(num_slate_targets(_analyses,_nb_ranked,np_day)' in src
    assert '_nb_boards=sorted(_nb_boards,key=lambda b:-b[\'badge\'])' in src
    assert "_mode=='Statistics'" in src and "_mode=='Overlap'" in src


def test_existing_cipher_day_and_row_legend_unchanged():
    assert nv.day_digits('2026-11-07')==([2,0,2,6,1,1,0,7],19)
    legend=nv.legend()
    assert 'the day match uses the English digit only' in legend
    assert 'each counts once (0 or 1)' in legend
    assert 'ties: score, then model chance, form, shot rate, English name total' in legend
    assert '<u>' not in legend # Reference emphasis does not leak into hot markers/tiers.


def test_streamlit_reference_renders_without_data_or_widget_changes():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('''
import streamlit as st
import numbers_v58_ui as nv
st.markdown(nv.reference_patterns_html(),unsafe_allow_html=True)
''').run()
    assert not app.exception
    assert 'Number patterns' in app.markdown[0].value
    assert '2-21, 22, 20' in app.markdown[0].value
    assert not app.button and not app.selectbox and not app.radio
