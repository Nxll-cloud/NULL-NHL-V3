"""Pooled retained-history accuracy: no forecast/settlement or existing nightly math changes."""
from copy import deepcopy
from pathlib import Path
from html.parser import HTMLParser
import pytest
import overall_accuracy_v60 as oa
import prediction_models_v59 as pm

TODAY='2026-11-07'


def entry(day, n, hits, np_hits=None):
    return {'day':day,'final':True,'players':[[p,f'Player {p}','T',.8-p*.01,p,p] for p in range(1,n+1)],
            'results':{'scorers':[[p,f'Player {p}','T',1] for p in range(1,hits+1)]},
            'summary':{'top_hits':hits,'top_n':n,'np_top_hits':hits if np_hits is None else np_hits,'np_top_n':n}}


def blend(day, ids=(1,2), scorers=(1,)):
    return {'day':day,'kind':'frozen','final':True,'top':[[p,'Player','T'] for p in ids],
            'model_top':list(ids),'np_top':list(ids),'results':{'scorers':list(scorers),'top_n':len(ids)}}


def indexed(**kwargs):
    return {r['key']:r for r in oa.aggregate(today=TODAY,model_top_ids=pm.model_top_ids,**kwargs)}


def test_pooled_not_nightly_average_and_variable_denominators():
    rs=[entry('2026-11-01',2,2),entry('2026-11-02',10,1)]
    rows=indexed(acc_entries=rs)
    assert rows['model']['correct']==3 and rows['model']['predictions']==12
    assert rows['model']['accuracy']==.25 # NOT average of 100% and 10% = 55%
    assert rows['np']['accuracy']==.25
    html=oa.section_html(list(rows.values()))
    assert '25.0% across 12 predictions' in html
    assert '55.0%' not in html


def test_all_history_not_trend_or_blend_union_and_current_graded_day():
    es=[entry(f'2026-10-{d:02}',2,1) for d in range(10,27)]
    es.append(entry(TODAY,2,2))
    rows=indexed(acc_entries=es)
    assert rows['model']['predictions']==36
    assert len(rows['model']['days'])==18
    assert TODAY in rows['model']['days']
    # No blend/books records required for an accuracy date to contribute.
    assert rows['blend']['accuracy'] is None


def test_missing_pending_void_unstarted_demo_and_future_excluded():
    es=[entry('2026-11-01',2,1)]
    for i in range(2,7):
        e=entry(f'2026-11-{i:02}',2,2)
        if i==2:e['results']=None
        if i==3:e['results']['status']='void'
        if i==4:e['final']=False
        if i==5:e['demo']=True
        if i==6:e['results']['complete']=False
        es.append(e)
    es.append(entry('2026-11-08',2,2))
    rows=indexed(acc_entries=es)
    assert rows['model']['correct']==1 and rows['model']['predictions']==2
    e=entry('2026-11-02',3,2)
    e['results']['statuses']={'1':'void','3':'pending'}
    # Only player 2 remains graded; missing NP identity summary cannot safely count filtered predictions.
    rows=indexed(acc_entries=[e])
    assert rows['model']['correct']==1 and rows['model']['predictions']==1
    assert rows['np']['accuracy'] is None


def test_duplicate_dates_players_and_fallback_sources_once():
    e=entry('2026-11-01',3,1)
    e['players'][1]=deepcopy(e['players'][0])
    e['results']['scorers'].append(deepcopy(e['results']['scorers'][0]))
    b=blend('2026-11-01',(1,2,3),(1,2,3))
    fallback=blend('2026-11-02',(4,4,5),(4,))
    rows=indexed(acc_entries=[e,e],blend_records=[b,b,fallback,fallback])
    assert rows['model']['predictions']==4 and rows['model']['correct']==2
    assert rows['blend']['predictions']==5 and rows['blend']['correct']==4
    assert rows['np']['predictions']==5 # 3 from authoritative stored summary + 2 unique fallback IDs
    assert len(rows['model']['days'])==2


def test_books_uses_own_frozen_top_and_actual_denominator():
    b=blend('2026-11-01',(1,1,2,3),(1,3))
    b['results']['statuses']={'3':'void'}
    b['results']['top_n']=999 # Never use inflated/mismatched summary denominator with recoverable IDs.
    rows=indexed(books_records=[b,b])
    assert rows['books']['correct']==1 and rows['books']['predictions']==2
    assert rows['model']['accuracy'] is None


def test_firstgoal_favourites_not_global_topten_and_empty_no_zero():
    r={'day':'2026-11-01','final':True,'favs':{'A @ B':[1],'C @ D':[2],'E @ F':[3],'G @ H':[4]},
       'top':[[99]],'results':{'firsts':{'A @ B':1,'C @ D':88,'E @ F':3},'top_hits':999,'fav_hits':999,
                             'games':999,'voided_games':['E @ F']}}
    rows=indexed(firstgoal_records=[r,r])
    assert rows['firstgoal']['correct']==1 and rows['firstgoal']['predictions']==2
    assert rows['firstgoal']['accuracy']==.5
    assert indexed()['firstgoal']['accuracy'] is None
    assert 'Not tracked yet' in oa.section_html([indexed()['firstgoal']])
    # Explicit completed no-goal result is a miss under firstgoal_v60.score; absent game is unknown.
    r['results']['firsts']['C @ D']=None
    assert indexed(firstgoal_records=[r])['firstgoal']['predictions']==2


def test_gematria_existing_matched_scored_schema_no_layer_doublecount():
    r={'day':'2026-11-01','games':[{'game':'A@B'}], 'matched':[
        {'pid':1,'game':'A@B','match':{'date':['a'],'team':['b']}},
        {'pid':1,'game':'A@B','match':{'arena':['c']}},
        {'pid':2,'game':'A@B','match':{'date':['a']}},
        {'pid':3,'game':'C@D','match':{'date':['a']}},
        {'pid':4,'game':'A@B','match':{'date':['a']}},
        {'pid':5,'game':'A@B','match':{'date':['a']}}],
       'results':{'complete':True,'postponed':['C@D'],'scored':{'1':2,'2':0,'3':1,'4':None,'5':float('nan')}}}
    row=indexed(gematria_records=[r,r])['gematria']
    assert row['correct']==1 and row['predictions']==2
    r['results']['complete']=False
    assert indexed(gematria_records=[r])['gematria']['accuracy'] is None


def test_np_preserves_existing_summary_metric_for_old_compacted_entry():
    e=entry('2026-11-01',3,1,np_hits=2)
    e['compacted']=True
    rows=indexed(acc_entries=[e])
    assert rows['np']['correct']==2 and rows['np']['predictions']==3


def test_untracked_models_do_not_borrow_static_examples_or_offline_backtests():
    rows=indexed()
    for k in ('nextgoal','winprob','storyline','overlap','sleepers','thelist','firstgoal'):
        assert rows[k]['accuracy'] is None and rows[k]['predictions']==0
    html=oa.section_html(list(rows.values()))
    assert '5/7' not in html and '0.0%' not in html
    assert len(rows)==len(set(r['label'] for r in rows.values()))
    assert 'Goal Threat Index' not in html # Not an independent named model in this app.
    assert 'not lifetime accuracy' in html and '90 days' in html and '60 days' in html


def test_placement_preserves_original_nightly_table_and_both_visible():
    src=Path('tabs/predmodels.py').read_text()
    assert src.index('pmv.nights_table(_pm_ns)') < src.index('oav.section_html(oav.aggregate(')
    assert 'f\'Top-10 hits for each system over the last {pmv.TREND_N} nights\'' in src
    assert '_oa_firstgoal, _oa_gematria, pmv.acc.eastern_today().isoformat()' in src
    block=src[src.index('# Cumulative companion'):src.index("st.caption('🧪 '")]
    assert 'st.tabs' not in block and 'checkbox' not in block and 'st.expander' not in block
    html=oa.section_html(list(indexed(acc_entries=[entry('2026-11-01',2,1)]).values()))
    assert '.oa60 table' in html and 'overflow-x:auto' in html and 'max-width:100%' in html
    assert '<th scope="row">Model' in html and '50.0% across 2 predictions' in html
    assert '<details>' in html # Only explanatory scope text is collapsed, never either accuracy view.


def test_real_existing_readers_and_log_signature(tmp_path,monkeypatch):
    import gematria_log_v59 as gem
    import firstgoal_v60 as fg
    g=tmp_path/'gem';g.mkdir();f=tmp_path/'first';f.mkdir()
    monkeypatch.setattr(gem,'ROOT',g);monkeypatch.setattr(fg,'ROOT',f)
    assert oa.gematria_records()==[] and oa.log_signature()==()
    p=g/'2026-11-01.json';p.write_text('{}')
    monkeypatch.setattr(gem,'load',lambda day,root:{'day':day,'results':{}})
    assert oa.gematria_records()[0]['day']=='2026-11-01'
    assert len(oa.log_signature())==1


def test_streamlit_section_render_no_network():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_string('''
import streamlit as st
import overall_accuracy_v60 as oa
import prediction_models_v59 as pm
st.markdown('<section aria-label="Night by night">Existing nightly table</section>',unsafe_allow_html=True)
st.markdown(oa.section_html(oa.aggregate(today='2026-11-07', model_top_ids=pm.model_top_ids)),unsafe_allow_html=True)
''').run()
    assert not app.exception
    assert 'Night by night' in app.markdown[0].value
    assert 'Overall model accuracy' in app.markdown[1].value
    assert 'Not tracked yet' in app.markdown[1].value
