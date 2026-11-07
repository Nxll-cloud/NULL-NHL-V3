from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import pytest
import strict_card_v60 as sc
import strict_card_ui_v60 as ui
import strict_ledger_v60 as lg
import situational_v58 as sit

NOW = datetime(2026, 11, 7, 14, tzinfo=timezone.utc)
START = (NOW + timedelta(hours=10)).isoformat()


def pool():
    cs, gs, starters, quotes = [], [], {}, []
    for i in range(1, 5):
        a, h, gid = f'A{i}', f'H{i}', str(2026020000+i)
        starters[gid] = {}
        for j, (t, o, home) in enumerate(((a,h,False),(h,a,True))):
            pid, gpid = i*10+j, str(i*100+j)
            cs.append({'pid':pid,'name':f'Player {pid}', 'team':t,'opp':o, 'home':home,'game_id':gid,'game':gid,
                       'start': START,'phase':'pregame','p':.50-i*.02-j*.01,'position':'C'})
            gs.append({'Team':o,'Goalie':f'Goalie {gpid}','Player ID':gpid,'SA':400,'Saves':330,'GP':14})
            starters[gid][o] = {'team':o,'goalie':f'Goalie {gpid}','goalie_id':gpid,'status':'probable','game_id':gid,'source':'test NHL','fetched_at':NOW.isoformat()}
            quotes.append({'pid':str(pid),'player':f'Player {pid}','team':t,'game':f'{a} @ {h}',
                           'books':{'DraftKings' if i%2 else 'FanDuel':200},'updated':NOW.isoformat()})
    return cs, sit.context(goalies=gs,starters=starters), {'day':'2026-11-07','demo':False,'source':sc.odds.SOURCE_API,'fetched_at':NOW.isoformat(),'rows':quotes}


def card():
    return sc.build('2026-11-07',*pool(),NOW)


def evidence(rec, status='won'):
    return {c['game_id']:{'final':True,'verified':True,'scorers':[c['pid']] if status=='won' else [],'total':8,
                           'team_goals':{c['team']:4,c['opp']:4},'starters':{c['opp']:c['goalie']['goalie_id']}} for c in rec['legs']}


def test_strict_distinct_ids_not_opposing_teams_and_shared_optimizer(monkeypatch):
    orig = sc.parlay.choose
    seen=[]
    def choose(cs,k,per):
        seen.append(per);return orig(cs,k,per)
    monkeypatch.setattr(sc.parlay,'choose',choose)
    rec=card()
    assert len(rec['legs'])==3 and len({c['game_id'] for c in rec['legs']})==3
    assert seen==['game_id']
    cs,ctx,q=pool()
    cs=[c for c in cs if c['game_id'] in {cs[0]['game_id'],cs[2]['game_id']}]
    assert not sc.build('2026-11-07',cs,ctx,q,NOW)['legs']
    assert 'No qualifying 3-game card' in ui.section_html(sc.build('2026-11-07',cs,ctx,q,NOW))


@pytest.mark.parametrize('change',[ 'small_gp','small_sa','unknown','strong','missing_gp','wrong_game'])
def test_goalie_eligibility(change):
    cs,ctx,q=pool(); c=cs[0]
    if change=='small_gp':ctx['goalies'][0]['GP']=2
    if change=='small_sa':ctx['goalies'][0]['SA']=90;ctx['goalies'][0]['Saves']=70
    if change=='missing_gp':ctx['goalies'][0].pop('GP')
    if change=='strong':ctx['goalies'][0]['Saves']=390
    if change=='unknown':ctx['starters'][tuple(sorted((c['team'],c['opp'])))][c['opp']]['status']='unknown'
    if change=='wrong_game':ctx['starters'][tuple(sorted((c['team'],c['opp'])))][c['opp']]['game_id']='999'
    assert sc.goalie_evidence(c,ctx)[1]


@pytest.mark.parametrize('change',['demo','source','pid','team','game','missing_price','future','stale','started','no_fetched'])
def test_only_real_quotes_with_safe_matching(change):
    cs,ctx,q=pool();c=cs[0]
    if change=='demo':q['demo']=True
    if change=='source':q['source']='Edge Flags demo'
    if change in ('pid','team','game'):q['rows'][0][change]='wrong'
    if change=='missing_price':q['rows'][0]['books']={}
    if change=='future':q['fetched_at']=(NOW+timedelta(hours=1)).isoformat()
    if change=='stale':q['fetched_at']=(NOW-timedelta(hours=3)).isoformat()
    if change=='started':c['start']=NOW.isoformat()
    if change=='no_fetched':q.pop('fetched_at')
    assert sc.quoted(c,q,NOW) is None


def test_quote_is_offered_not_fair():
    rec=card();q=rec['legs'][0]['quote']
    assert q['american']==200 and q['decimal']==3 and q['market']=='player_goal_scorer_anytime'
    assert rec['legs'][0]['goalie']['status']=='probable'


def test_duplicate_and_unknown_game_rejected():
    cs,ctx,q=pool(); cs.append(cs[0]);cs[1]['game_id']=''
    rec=sc.build('2026-11-07',cs,ctx,q,NOW)
    assert len({c['pid'] for c in rec['legs']})==3
    assert 'invalid/duplicate candidate' in rec['reasons']


def test_freeze_immutable_and_no_late_rebuild(tmp_path,monkeypatch):
    rec=card();sc.save(rec,tmp_path)
    moved=deepcopy(rec);moved['legs'][0]['quote']['american']=400;moved['id']=sc.digest(moved)
    assert sc.save(moved,tmp_path)==rec
    monkeypatch.setattr(sc,'ROOT',tmp_path)
    assert ui.resolve({},rec['day'],[],[],None,None,NOW)==rec
    late=[{'slate':{'start':START},'result':{'phase':'final'}}]
    monkeypatch.setattr(sc,'ROOT',tmp_path/'absent')
    assert not ui.resolve({},rec['day'],late,[],None,None,NOW)['legs']
    assert not sc.build(rec['day'],*pool(),NOW+timedelta(days=1))['legs']


def test_final_only_grading_and_notes():
    rec=card();games=evidence(rec)
    games[rec['legs'][0]['game_id']]['final']=False
    pending=sc.settle(rec,games,NOW)
    assert pending['results']['card']=='pending'
    assert pending['results']['legs'][str(rec['legs'][0]['pid'])]=='pending'
    graded=sc.settle(rec,evidence(rec),NOW)
    assert graded['results']['card']=='won' and 'matched' in graded['results']['notes']
    assert sc.settle(graded,evidence(rec,'lost'),NOW)['results']['card']=='won'
    assert sc.grade_note({'kind':'starter','game_id':'1','team':'X','goalie_id':'2'},{'1':{'final':True,'verified':True}})=='unknown'
    assert sc.grade_note({'kind':'fade','game_id':'1','team':'X','threshold':2},{'1':{'final':True,'verified':True,'team_goals':{'X':1}}})=='won'
    assert sc.grade_note({'kind':'environment','game_id':'1','threshold':7},{'1':{'final':True,'verified':True,'total':6}})=='lost'
    assert sc.grade_note({'kind':'environment','game_id':'1','threshold':7},{'1':{'final':True,'verified':False,'total':9}})=='unknown'


@pytest.mark.parametrize('a,d',[(200,3),(-125,1.8),(100,2),(-100,2)])
def test_us_odds(a,d):
    assert lg.decimal(a)==d
    assert lg.financial('won',d,10)['pnl']==round((d-1)*10,2)
    assert lg.financial('lost',d,10)['pnl']==-10
    assert lg.financial('push',d,10)['pnl']==0
    assert lg.financial('void',d,10)['pnl']==0
    assert lg.financial('pending',d,10)['pnl'] is None
    assert lg.financial('won',d,None)['pnl'] is None
    assert lg.financial('won',d,0)['pnl']==0


def test_ledger_distinguishes_card_single_and_realized():
    rec=card()
    entries=lg.add([],rec,'card',10,now=NOW)
    assert lg.add(entries,rec,'card',99,now=NOW)==entries
    entries=lg.add(entries,rec,str(rec['legs'][0]['pid']),5,-125,'DraftKings',True,NOW)
    graded=sc.settle(rec,evidence(rec),NOW)
    out=lg.grade(entries,{rec['id']:graded})
    assert len(out)==2 and sum(e['stake'] for e in out)==15
    assert out[0]['outcome']['pnl']==260 and out[0]['outcome']['realized_pnl'] is None
    assert 'Mixed-book' in out[0]['outcome']['payout_basis']
    assert out[1]['outcome']['pnl']==4 and out[1]['outcome']['realized_pnl'] is None
    assert lg.grade(out,{rec['id']:sc.settle(rec,evidence(rec,'lost'),NOW)})==out
    assert lg.restore(lg.export(out))==out
    with pytest.raises(ValueError):lg.add([],rec,'card',10,None,'DK',True,NOW)
    with pytest.raises(ValueError):lg.add([],rec,'card',10,now=NOW+timedelta(days=1))
    with pytest.raises(ValueError):lg.financial('won',3,-1)


def test_void_partial_pending_and_unknown_stake():
    rec=card();e=lg.add([],rec,'card',10,now=NOW)[0]
    states={str(c['pid']):'won' for c in rec['legs']}
    rec['results']={'legs':states}
    states[str(rec['legs'][0]['pid'])]='void'
    assert lg.evaluate(e,rec)['pnl']==80
    for p in states:states[p]='void'
    assert lg.evaluate(e,rec)['pnl']==0
    states[str(rec['legs'][0]['pid'])]='pending'
    assert lg.evaluate(e,rec)['pnl'] is None
    states[str(rec['legs'][0]['pid'])]='lost'
    assert lg.evaluate(e,rec)['pnl']==-10
    e['stake']=None
    assert lg.evaluate(e,rec)['pnl'] is None


def test_actual_card_price_and_postvoid_no_invention():
    rec=card();e=lg.add([],rec,'card',10,900,'DraftKings',True,NOW)[0]
    rec=sc.settle(rec,evidence(rec),NOW)
    assert lg.evaluate(e,rec)['pnl']==90 and lg.evaluate(e,rec)['realized_pnl'] is None
    rec['results']['legs'][str(rec['legs'][0]['pid'])]='void'
    assert lg.evaluate(e,rec)['pnl'] is None


def test_pbp_requires_complete_final_excludes_so():
    pbp={'1':{'state':'LIVE','away_score':1,'home_score':0,'events':[{'kind':'goal','shooter':1,'team':'A','ptype':'REG'}],'away':'A','home':'H'}}
    assert not ui.games_from_pbp(pbp)['1']['verified']
    pbp['1']['state']='FINAL'
    assert ui.games_from_pbp(pbp)['1']['verified']
    pbp['1']['home_score']=2
    assert not ui.games_from_pbp(pbp)['1']['verified']
    pbp['1']['home_score']=1;pbp['1']['ptype']='SO'
    assert ui.games_from_pbp(pbp)['1']['verified']


def test_public_save_rejects_private_and_settlement_mutation(tmp_path):
    rec=card();private=deepcopy(rec);private['stake']=10;private['id']=sc.digest(private)
    with pytest.raises(ValueError):sc.save(private,tmp_path)
    rec=sc.settle(rec,evidence(rec),NOW);sc.save(rec,tmp_path)
    changed=deepcopy(rec);changed['results']['legs'][str(rec['legs'][0]['pid'])]='lost'
    with pytest.raises(ValueError):sc.save(changed,tmp_path)
    assert 'private_ledgers/' in Path('.gitignore').read_text()
    assert 'strict_ledger' not in Path('.github/workflows/precompute.yml').read_text()


def test_scoped_html_and_integration_no_home_change():
    html=ui.section_html(card())
    assert '<table>' in html and html.count('<th scope="col">')==7 and html.count('<tr>')==4
    assert 'overflow-x:auto' in html and 'max-width:100%' in html and '@media(max-width:420px)' in html
    assert '.sc60 table' in html and 'probable' in html
    assert 'strict_card_ui_v60' in Path('tabs/predmodels.py').read_text()
    assert 'strict_card' not in Path('parlay_tracker_v59.py').read_text()


def test_bridge_no_network_reuses_model_pool_and_books(tmp_path):
    import matchup_center_v54 as mc
    cs,ctx,q=pool()
    snap={'games':[{'Game ID':str(2026020000+i),'Away':f'A{i}','Home':f'H{i}','Start (UTC)':START} for i in range(1,5)]}
    ent={'day':'2026-11-07','frozen_at':NOW.isoformat(),'first_start':START,'players':[[c['pid'],c['name'],c['team'],c['p'],1,None] for c in cs]}
    sc.capture_inputs(snap,ent,sit.Situ(ctx),tmp_path)
    inp=json.loads((tmp_path/'2026-11-07.json').read_text())
    book={'day':'2026-11-07','demo':False,'source':q['source'],'frozen_at':NOW.isoformat(),'odds_updated':NOW.isoformat(),
          'top':[[c['pid'],c['name'],c['team'],'C',.2,1,'DK',200,q['rows'][i]['books']] for i,c in enumerate(cs)]}
    rec=sc.from_inputs(inp,book,NOW)
    assert len(rec['legs'])==3
    assert sc.from_inputs(inp,book,NOW+timedelta(days=1)) is None
    assert (tmp_path/'2026-11-07.json').stat().st_size<100000


def test_streamlit_render_and_private_entry(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(sc,'load',lambda *a,**k:card())
    app=AppTest.from_string('''
import streamlit as st
import strict_card_ui_v60 as ui
ui.render(st,'2026-11-07',[],[],None,None)
''').run()
    assert not app.exception
    assert len(app.selectbox)==1
    assert app.selectbox[0].value=='card'
    app.text_input[0].set_value('10')
    next(b for b in app.button if b.label=='Log privately — no bet placed').click().run()
    assert not app.exception
    assert app.session_state['sc60_private_ledger'][0]['stake']==10
    assert not app.session_state['sc60_private_ledger'][0]['placed']
    assert app.session_state['sc60_private_ledger'][0]['outcome']['realized_pnl'] is None


def test_existing_score_feed_evidence_verified_and_starter_no_extra_fetch():
    import accuracy_v58 as acc
    game={'id':1,'gameState':'FINAL','awayTeam':{'abbrev':'A','score':1},'homeTeam':{'abbrev':'H','score':0},
          'goals':[{'playerId':10,'teamAbbrev':'A'}]}
    calls=[]
    def box(gid):
        calls.append(gid)
        return {'id':1,'homeTeam':{'abbrev':'H'},'awayTeam':{'abbrev':'A'},'playerByGameStats':{
            'homeTeam':{'goalies':[{'starter':True,'playerId':100}]},'awayTeam':{'goalies':[]}}}
    res=acc.results_from_score({'games':[game]},box_fn=box)
    assert calls==[1] and res['strict_games']['1']['verified']
    assert res['strict_games']['1']['starters']=={'H':'100'}
    game['awayTeam']['score']=2
    res=acc.results_from_score({'games':[game]},box_fn=box)
    assert not res['strict_games']['1']['verified']


def test_workflow_update_freeze_and_grade_idempotent(tmp_path,monkeypatch):
    import books_picks_v59 as bp
    import accuracy_v58 as acc
    rec=card()
    monkeypatch.setattr(sc,'from_inputs',lambda *args:rec)
    monkeypatch.setattr(bp,'load',lambda *args:{'test':'book'})
    inp=tmp_path/'inputs';inp.mkdir();(inp/'2026-11-07.json').write_text('{}')
    root=tmp_path/'cards'
    monkeypatch.setattr(acc,'load_entry',lambda *args:None)
    sc.update(NOW,root,inp)
    assert sc.load(rec['day'],root)==rec
    moved=deepcopy(rec);moved['legs'][0]['pid']=999;moved['id']=sc.digest(moved)
    monkeypatch.setattr(sc,'from_inputs',lambda *args:moved)
    sc.update(NOW,root,inp)
    assert sc.load(rec['day'],root)==rec
    ent={'final':True,'games':[c['game_id'] for c in rec['legs']], 'results':{'n_games':3,'strict_games':evidence(rec)}}
    monkeypatch.setattr(acc,'load_entry',lambda *args:ent)
    sc.update(NOW+timedelta(days=1),root,inp)
    assert sc.load(rec['day'],root)['results']['card']=='won'
    ent['results']['strict_games']=evidence(rec,'lost')
    sc.update(NOW+timedelta(days=1),root,inp)
    assert sc.load(rec['day'],root)['results']['card']=='won'


def test_book_confirmation_void_and_actual_pnl_audit():
    rec=card()
    entries=lg.add([],rec,'card',10,900,'DraftKings',True,NOW)
    with pytest.raises(ValueError):lg.confirm_settlement(entries,entries[0]['id'],{},'book',rec)
    final=sc.settle(rec,evidence(rec),NOW)
    entries=lg.grade(entries,{rec['id']:final})
    states={str(c['pid']):'won' for c in rec['legs']}
    states[str(rec['legs'][0]['pid'])]='void'
    entries=lg.confirm_settlement(entries,entries[0]['id'],states,'Book voided DNP, repriced at +500',final,500,NOW+timedelta(days=1))
    assert entries[0]['outcome']['realized_pnl']==50
    assert entries[0]['calculated_outcome']['pnl']==90
    assert lg.restore(lg.export(entries))==entries
    with pytest.raises(ValueError):lg.confirm_settlement(entries,entries[0]['id'],states,'again',final)


def test_session_quote_never_replaced_by_new_workflow_pick(monkeypatch):
    rec=card();other=deepcopy(rec)
    other['legs'][0]['quote']['american']=400;other['id']=sc.digest(other)
    monkeypatch.setattr(sc,'load',lambda *args:other)
    store={'sc60_quote:'+rec['day']:rec}
    assert ui.resolve(store,rec['day'],[],[],None,None,NOW)==rec


def test_slate_day_and_incomplete_pbp_ids():
    cs,ctx,q=pool();q['day']='2026-11-06'
    assert not sc.build('2026-11-07',cs,ctx,q,NOW)['legs']
    pbp={'1':{'state':'FINAL','away_score':1,'home_score':0,'away':'A','home':'H',
              'events':[{'kind':'goal','team':'A','ptype':'REG'}]}}
    assert not ui.games_from_pbp(pbp)['1']['verified']
