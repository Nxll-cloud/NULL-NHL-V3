"""EdgeLab-only regressions. Sanitized provider transport, no production keys/network."""
from copy import deepcopy
from pathlib import Path
import ast
import json
import pandas as pd
import pytest
import requests
import odds_api_v45 as api
import edgelab_v58 as el
import edgelab_prices_v60 as scope
from odds_feed_cache_v60 import QuoteCache

DAY='2026-11-07'
TIME='2026-11-07T23:00:00Z'
KEY='SANITIZED_NOT_A_REAL_KEY'


def player(name='Connor McDavid',pid=1,team='EDM'):
    return {'name':name,'pid':pid,'team':team,'lam_game':.4,'rate':.01,'goals':0,'rank':1}


def result(players=None,game='2026020001',away='EDM',home='COL',start=TIME,phase='pregame'):
    return {'slate':{'game_id':game,'away':away,'home':home,'start':start},
            'result':{'players':players if players is not None else [player()], 'phase':phase,'remaining':30 if phase=='live' else 60}}


def quote(**kw):
    return {'player':'Connor McDavid','market':'player_goal_scorer_anytime','selection':'Yes',
            'american_odds':220,'sportsbook':'Audit Book','updated_at':'2026-11-07T22:55:00Z',
            'event_id':'opaque-provider-id','home_team':'Colorado Avalanche','away_team':'Edmonton Oilers',
            'commence_time':TIME,**kw}


def prepared(rows=None,results=None,source='Automatic API'):
    return scope.prepare(pd.DataFrame(rows if rows is not None else [quote()]), results or [result()], DAY, source)


def test_valid_provider_and_negative_odds_are_not_repriced_or_hidden():
    for a in (220,-120,10000):
        prices,rep=prepared([quote(american_odds=a)])
        priced,unpriced=el.model_rows([result()],prices)
        assert rep['accepted']==1 and len(priced)==1 and not unpriced
        assert priced[0]['american']==a and priced[0]['price_source']=='provider'
        if a<0:
            assert priced[0]['edge']<0 and 'class="el-e neg"' in el.table_html(priced,unpriced)


@pytest.mark.parametrize('change',[{'selection':'No'},{'selection':'Over'},{'selection':pd.NA},
                                   {'market':'player_points'},{'market':None}])
def test_only_actual_affirmative_anytime_contract(change):
    prices,rep=prepared([quote(**change)])
    assert not prices and rep['accepted']==0


@pytest.mark.parametrize('value',[None,float('nan'),pd.NA,'','   ','<NA>','unknown',123])
def test_null_player_quote_and_model_never_crash_or_create_nameless_prices(value):
    prices,rep=prepared([quote(player=value)])
    assert not prices and rep['accepted']==0
    priced,unpriced=el.model_rows([result([player(value)])],scope.PriceBook())
    assert not priced and not unpriced


def test_accent_spacing_case_punctuation_and_conservative_initials():
    for official,book in [('Tim Stützle','  TIM  STUTZLE '),('J.T. Miller','JT Miller'),('Jonathan Tanner Miller','J.T. Miller')]:
        prices,rep=prepared([quote(player=book)], [result([player(official)])])
        assert rep['accepted']==1
        assert len(el.model_rows([result([player(official)])],prices)[0])==1
    # Two different full names sharing initials are NOT aliases.
    assert not prepared([quote(player='Chris McDavid')])[0]
    both=[player('John Smith',1),player('James Smith',2)]
    assert not prepared([quote(player='J Smith')],[result(both)])[0]
    both[1]['team']='COL'
    assert prepared([quote(player='J Smith',team='EDM')],[result(both)])[1]['accepted']==1


def test_duplicate_full_names_require_team_or_explicit_nhl_namespace_id():
    rs=[result([player('Joe Smith',1),player('Joe Smith',2,'COL')])]
    assert not prepared([quote(player='Joe Smith')],rs)[0]
    assert not prepared([quote(player='Joe Smith',player_id='1',player_id_namespace='provider')],rs)[0]
    assert prepared([quote(player='Joe Smith',nhl_player_id='1')],rs)[1]['accepted']==1
    assert not prepared([quote(player='Different Person',nhl_player_id='1')],rs)[0]
    assert not prepared([quote(player='Joe Smith',nhl_player_id='1',team='COL')],rs)[0]


def test_no_same_name_cross_game_date_or_conflicting_team_attachment():
    rs=[result(),result([player(pid=2,team='TOR')],game='2026020002',away='TOR',home='BOS')]
    prices,rep=prepared(results=rs)
    priced,up=el.model_rows(rs,prices)
    assert len(priced)==1 and priced[0]['pid']==1 and [p['pid'] for p in up]==[2]
    for change in ({'commence_time':'2026-11-08T23:00:00Z'}, {'away_team':'Boston Bruins'},
                   {'nhl_game_id':'2026020999'}, {'nhl_game_id':'2026020001','home_team':'Boston Bruins'},
                   {'nhl_game_id':'2026020001','home_team':'Not a team'}):
        assert not prepared([quote(**change)])[0]


def test_utc_boundary_uses_canonical_eastern_game_date_not_quote_date():
    at='2026-11-08T02:00:00Z'  # Nov7 ET
    rs=[result(start=at)]
    assert prepared([quote(commence_time=at)],rs)[1]['accepted']==1
    assert not prepared([quote(commence_time=at,game_date='2026-11-08')],rs)[0]
    assert not scope.prepare(pd.DataFrame([quote(commence_time=at)]),rs,'2026-11-08')[0]


def test_csv_requires_mapping_and_has_honest_import_provenance():
    q=quote();q.pop('home_team');q.pop('away_team');q.pop('commence_time')
    assert not prepared([q],source='Uploaded CSV')[0]  # quote timestamp is NOT event date
    for mapping in ({'nhl_game_id':'2026020001'},{'team':'EDM','game_date':DAY}):
        prices,rep=prepared([{**q,**mapping}],source='Uploaded CSV')
        assert rep['accepted']==1
        assert next(iter(prices.values()))['source']=='imported CSV'
        assert 'imported prices, not an automatic live' in scope.status_html(rep)
    assert not prepared([q],source='Combine both')[0]


@pytest.mark.parametrize('change',[{'updated_at':None},{'updated_at':'invalid'},{'sportsbook':pd.NA},
                                   {'american_odds':20},{'american_odds':True},{'american_odds':float('inf')}])
def test_invalid_price_metadata_excluded(change):
    assert not prepared([quote(**change)])[0]


class Response:
    def __init__(self,body=None,status=200,bad_json=False):
        self.body,self.status_code,self.bad_json=body,status,bad_json
    def json(self):
        if self.bad_json:
            raise ValueError('DO_NOT_LEAK_RAW_RESPONSE')
        return deepcopy(self.body)


class Transport:
    def __init__(self,mode='valid'):
        self.mode,self.calls=mode,[]
    def get(self,url,params,timeout):
        event=url.endswith('/odds')
        self.calls.append('event' if event else 'events')
        if self.mode in ('timeout','network'):
            cls=requests.Timeout if self.mode=='timeout' else requests.ConnectionError
            raise cls('https://provider/?apiKey=DO_NOT_LEAK_RAW_RESPONSE')
        if self.mode.isdigit():
            return Response(status=int(self.mode))
        if self.mode=='bad_json':
            return Response(bad_json=True)
        if not event:
            return Response([] if self.mode=='no_events' else [{'id':'opaque-provider-id',
                'home_team':'Colorado Avalanche','away_team':'Edmonton Oilers','commence_time':TIME}])
        if self.mode=='event403':
            return Response(status=403)
        markets=[] if self.mode in ('empty','live_omitted') else [{'key':'player_points' if self.mode=='wrong_market' else 'player_goal_scorer_anytime',
            'last_update':'2026-11-07T22:55:00Z','outcomes':[{'description':'Connor McDavid','name':'Yes','price':220}]}]
        return Response({'bookmakers':[{'title':'Audit Book','markets':markets}]})


def fetched(transport,cache=None):
    if cache:
        return cache.get(lambda key,**kw:api.fetch_odds(key,session=transport,**kw),KEY,'us','player_goal_scorer_anytime')
    return api.fetch_odds(KEY,session=transport)


@pytest.mark.parametrize('mode,code,ttl',[('401','auth',300),('403','auth',300),('429','quota',60),
                                         ('503','unavailable',30),('timeout','timeout',30),('network','network',30),('bad_json','malformed',30)])
def test_typed_safe_errors_cooldown_without_rerun_hammering(mode,code,ttl):
    now=[0];cache=QuoteCache(clock=lambda:now[0]);t=Transport(mode)
    for _ in range(2):
        with pytest.raises(api.OddsFeedError) as e:
            fetched(t,cache)
        assert e.value.code==code and e.value.status['cache_seconds']==ttl
        assert 'DO_NOT_LEAK' not in str(e.value)
        html=scope.status_html({'source':'Automatic API','received':0,'accepted':0,'excluded':{}},e.value.status)
        assert KEY not in html and 'DO_NOT_LEAK' not in html and 'apiKey' not in html
    assert len(t.calls)==1
    now[0]=ttl+1;t.mode='valid'
    assert not fetched(t,cache)[0].empty


@pytest.mark.parametrize('mode',['empty','no_events','live_omitted','event403'])
def test_empty_and_event_error_not_cached_as_30_min_healthy_success(mode):
    now=[0];cache=QuoteCache(clock=lambda:now[0]);t=Transport(mode)
    frame,warnings=fetched(t,cache)
    assert frame.empty and frame.attrs['feed_status']['state']!='ok'
    wait=frame.attrs['feed_status']['cache_seconds']
    assert wait<=300
    calls=len(t.calls);t.mode='valid';fetched(t,cache)
    assert len(t.calls)==calls
    now[0]=wait+1
    assert not fetched(t,cache)[0].empty


def test_healthy_success_cached_30_minutes_and_key_isolation():
    now=[0];cache=QuoteCache(clock=lambda:now[0]);t=Transport()
    frame,_=fetched(t,cache);assert frame.attrs['feed_status']['cache_seconds']==1800
    fetched(t,cache);assert t.calls==['events','event']
    # No token literal retained in identity keys.
    assert KEY not in repr(list(cache.entries)) and KEY not in repr(list(cache.events))
    now[0]=1801;fetched(t,cache);assert len(t.calls)==4


def test_partial_retry_does_not_refetch_healthy_paid_events():
    class Partial(Transport):
        def get(self,url,params,timeout):
            if url.endswith('/events'):
                self.calls.append('events');return Response([{'id':'good'},{'id':'failed'}])
            which='failed' if '/failed/' in url else 'good'
            self.calls.append(which)
            if which=='failed' and self.mode=='partial':
                raise requests.Timeout('secret-url')
            return Response({'bookmakers':[{'title':'Audit Book','markets':[{'key':'player_goal_scorer_anytime',
                'last_update':'2026-11-07T22:55:00Z','outcomes':[{'description':'Connor McDavid','name':'Yes','price':220}]}]}]})
    now=[0];cache=QuoteCache(clock=lambda:now[0]);t=Partial('partial')
    frame,warnings=fetched(t,cache)
    assert len(frame)==1 and warnings and frame.attrs['feed_status']['state']=='partial'
    assert frame.attrs['feed_status']['failed_events']==1
    t.mode='valid';now[0]=61
    frame,warnings=fetched(t,cache)
    assert len(frame)==2 and not warnings
    assert t.calls.count('good')==1 and t.calls.count('failed')==2
    assert frame.attrs['feed_status']['event_requests']==1


def test_quote_schema_nulls_and_best_consensus_frames_not_mistaken_for_raw():
    for value in (None,[],pd.DataFrame(),pd.DataFrame([{'player':'Someone','best_odds':220}])):
        prices,rep=scope.prepare(value,[result()],DAY)
        assert not prices
    prices,rep=prepared([quote(_quote_origin='provider'),quote(_quote_origin='csv',sportsbook='Other')],source='Combine both')
    assert rep['origins']=={'provider':1,'csv':1}
    assert next(iter(prices.values()))['source']=='provider + imported CSV'


def app_source():
    tree=ast.parse(Path('app.py').read_text())
    start=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.FunctionDef) and n.name=='np_quote_cache')
    end=next(i for i,n in enumerate(tree.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_np_edge_quotes' for t in n.targets))
    loader=ast.unparse(ast.Module(body=tree.body[start:end+1],type_ignores=[]))
    return '''
import streamlit as st
import pandas as pd
from test_v60_edgelab import Transport, result, DAY, KEY
import odds_api_v45 as api
from odds_api_v45 import OddsFeedError
import edgelab_v58 as elv58
import edgelab_prices_v60 as scope
import v55_ui as v5
import ui_theme_v53 as ui
import scorers_tonight_v58 as sctn
import xg_v59 as xgm
np_day=DAY
_v56_results=[result(phase='live' if st.session_state.get('case')=='live_omitted' else 'pregame')]
def fetch_odds(key,**kw):
 return api.fetch_odds(key,session=Transport(st.session_state.get('case','valid')),**kw)
'''+loader+'''
st.session_state['shared_schema']=list(_np_shared_quotes.columns)
exec(compile(open('tabs/edgelab.py').read(),'tabs/edgelab.py','exec'),globals())
'''


@pytest.mark.parametrize('mode',['missing','401','403','429','503','timeout','network','bad_json','no_events','empty','live_omitted','event403','wrong_market','valid'])
def test_actual_edgelab_tab_and_shared_loader_render_correct_safe_status(mode):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_resource.clear()
    app=AppTest.from_string(app_source(),default_timeout=30)
    app.session_state['case']=mode
    if mode!='missing':
        app.secrets['ODDS_API_KEY']=KEY
    app.run()
    assert not app.exception
    assert '_quote_origin' not in app.session_state['shared_schema']
    html=' '.join(m.value for m in app.markdown)+' '+' '.join(h.value for h in app.get('html'))
    assert 'EdgeLab price feed status' in html and 'Received' in html
    assert KEY not in html and 'DO_NOT_LEAK' not in html
    if mode=='valid':
        assert el.NO_PRICES_TITLE not in html and '+1.7 pts' in html
    else:
        assert el.NO_PRICES_TITLE in html
    if mode in ('401','403','event403'):
        assert '401/403' in html and 'No provider key:' not in html
    if mode=='429':assert 'quota / rate limit' in html
    if mode=='missing':assert 'top-level ODDS_API_KEY' in html
    if mode=='wrong_market':assert 'unsupported market' in html


@pytest.mark.parametrize('change',[{'source':'DEMO'},{'source':'Synthetic'},{'source':'Simulated'},{'demo':True},{'line':1.5}])
def test_explicit_demo_prices_and_unsupported_lines_are_not_live(change):
    assert not prepared([quote(**change)])[0]


def test_malformed_event_list_or_payload_returns_safe_typed_diagnostics():
    class Broken(Transport):
        def get(self,url,params,timeout):
            if url.endswith('/events'):
                return Response({'raw_secret':'DO_NOT_LEAK'})
            return Response([])
    with pytest.raises(api.OddsFeedError) as exc:
        fetched(Broken())
    assert exc.value.code=='malformed' and 'DO_NOT_LEAK' not in str(exc.value)
    class EventBroken(Transport):
        def get(self,url,params,timeout):
            return Response([]) if url.endswith('/odds') else super().get(url,params,timeout)
    frame,warnings=fetched(EventBroken(),QuoteCache())
    assert frame.empty and frame.attrs['feed_status']['state']=='malformed'
    assert warnings and 'DO_NOT_LEAK' not in json.dumps(frame.attrs)


def test_scoped_tab_null_source_frame_and_csv_schema_warning_render():
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    for frame in (pd.DataFrame([quote(player=pd.NA)]),pd.DataFrame([{'player':'Unknown','best_odds':220}])):
        st.cache_resource.clear()
        app=AppTest.from_string(app_source())
        app.session_state['v46_source']='Uploaded CSV'
        app.session_state['playbook_odds_data']=frame
        app.run()
        assert not app.exception
        html=' '.join(h.value for h in app.get('html'))+' '+' '.join(m.value for m in app.markdown)
        assert 'Uploaded CSV selected' in html and 'CSV mapping:' in html
        assert el.NO_PRICES_TITLE in html and 'No provider key:' not in html


def test_configuration_types_do_not_issue_provider_requests():
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    for key in (False,123,{'nested':'DO_NOT_LEAK'}):
        st.cache_resource.clear()
        app=AppTest.from_string(app_source());app.secrets['ODDS_API_KEY']=key;app.run()
        assert not app.exception
        html=' '.join(h.value for h in app.get('html'))
        assert 'Invalid provider key configuration' in html and 'DO_NOT_LEAK' not in html
    with pytest.raises(api.OddsFeedError) as e:
        api.fetch_odds(123,session=Transport())
    assert e.value.code=='configuration'


@pytest.mark.parametrize('width',[320,390])
def test_mobile_feed_status_scoped_and_unbroken_tokens_wrap(width):
    html=scope.status_html({'source':'Uploaded CSV','received':1,'accepted':0,'excluded':{'missing event mapping':1}})
    assert '.v58-el .el-feed{' in html and 'max-width:100%' in html and 'overflow-wrap:anywhere' in html
    # Existing EdgeLab table remains in its local horizontal-scroll wrapper, not a page-width fixed overlay.
    table=el.table_html(*el.model_rows([result()],scope.PriceBook()))
    assert '<div class="el-wrap"><table class="el-t">' in table
    assert f'width:{width}px' not in html and 'position:fixed' not in html


def test_slow_failure_cooldown_starts_after_io_not_before():
    now=[0];cache=QuoteCache(clock=lambda:now[0]);calls=[]
    def slow(key,**kw):
        calls.append(1);now[0]+=1000
        raise api.OddsFeedError('safe timeout',code='timeout')
    with pytest.raises(api.OddsFeedError):cache.get(slow,KEY,'us','anytime')
    with pytest.raises(api.OddsFeedError) as e:cache.get(slow,KEY,'us','anytime')
    assert len(calls)==1 and e.value.status['retry_after_seconds']==30
    def slow_event():
        calls.append(2);now[0]+=1000
        raise api.OddsFeedError('safe timeout',code='timeout')
    for _ in range(2):
        with pytest.raises(api.OddsFeedError):cache.event_get(('safe-hash','us','anytime'),'event',slow_event)
    assert calls.count(2)==1
