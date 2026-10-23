"""Null's Playbook V5.6 · Live Next Goal tab. Executed by tabs.run_tab() inside the app's namespace.

Real games: official PBP polled per game (30 s live, slower pregame, stops when final) through cached, never-raising
fetchers; the body is a Streamlit fragment with run_every when a game is live (guarded), else a Refresh button.
DEMO replay: real past PBP fixture (test_fixtures_v56/pbp_2026020162.json), stepped event by event, labelled DEMO."""

st.markdown(v5.tab_head('NULL’S PLAYBOOK · LIVE','Live Next Goal','Who scores the next goal · official NHL play-by-play · xG + shrunk shooting % + pace blend · competing risk',
    chips=[(f'{_v56_live_n} live','hot' if _v56_live_n else 'muted'),('30 s live cadence','odds'),('Model estimate · uncalibrated','warn')],tone='hot'),unsafe_allow_html=True)
_ng_c1,_ng_c2,_ng_c3,_ng_c4=st.columns([2,2,2,1])
with _ng_c1:
    _ng_filter=st.segmented_control('Show',['All','Live','Pregame','Final'],default='All',key='v56_ng_filter') if hasattr(st,'segmented_control') else st.radio('Show',['All','Live','Pregame','Final'],horizontal=True,key='v56_ng_filter')
with _ng_c2:
    _ng_form=st.toggle('Bounded Form multiplier (0.9–1.1)',value=False,key='v56_ng_form',help='Form % is an index, never a probability; this only nudges a skater’s rate by at most ±10%.')
with _ng_c3:
    _ng_auto=st.toggle('Auto-refresh while live',value=True,key='v56_ng_auto')
with _ng_c4:
    st.button('↻ Refresh',key='v56_ng_refresh',on_click=lambda: st.session_state.__setitem__('v56_force_refresh',True),width='stretch')
_ng_top=st.select_slider('Shooters per game',[5,8,12],value=8,key='v56_ng_top')


def _ng_panels(force=False):
    """Recompute from the pollers (fragment reruns poll again; the cache and poller cadence bound the network)."""
    if force:
        pbp, _ = v56_collect(False)
    else:
        pbp = _v56_pbp
    res = lstate.slate_results(_v56_games, _v56_priors, v56_scores_cached(np_day)[0] if force else _v56_scores, pbp,
                               st.session_state.setdefault('v56_rank_mem_form' if _ng_form else 'v56_rank_mem', {}), use_form=_ng_form)
    want = {'All': None, 'Live': 'live', 'Pregame': 'pregame', 'Final': 'final'}.get(_ng_filter or 'All')
    shown = 0
    for r in sorted(res, key=lambda r: {'live': 0, 'shootout': 1, 'pregame': 2, 'final': 3}.get(r['result']['phase'], 9)):
        if want and r['result']['phase'] != want:
            continue
        shown += 1
        note = (r['note'] + ' ' if r['note'] else '') + 'Arrows: ' + r['result'].get('rank_basis', '') + '.'
        if r['result']['phase'] == 'final':
            note += ' Final: no further goal is possible, so next-goal % is 0; the list keeps the final shot leaders.'
        v5.html_block(st, v56.nextgoal_panel(r['result'], SEASON, r['label'], v56_updated(r['slate']['game_id']), top=_ng_top, note=note, venue=r['slate'].get('venue'), scored=sctn.active(st.session_state, np_day)))
    if not shown:
        st.info('No games in this state on the selected slate.' if _v56_games else 'No NHL games for this date.')
    st.caption(f'Last checked {datetime.now(timezone.utc).strftime("%H:%M:%S UTC")} · score feed: {"ok" if not _v56_scores_err else _v56_scores_err}'
               f' · {len(pbp)} play-by-play feed(s) loaded')


_ng_live=_v56_live_n>0 and _ng_auto and hasattr(st,'fragment')
if _ng_live:
    @st.fragment(run_every='30s')
    def _ng_live_fragment():
        _ng_panels(force=True)
    _ng_live_fragment()
else:
    _ng_panels()
    if _v56_live_n and not _ng_auto:
        st.caption('Auto-refresh is off: use ↻ Refresh for a new poll.')

# ---------------------------------------------------------------- DEMO replay (real past PBP, stepped)
st.markdown(ui.section('DEMO replay','Real NHL play-by-play of a finished game, replayed shot by shot · arrows compare with the previous step','🎬','gem'),unsafe_allow_html=True)
try:
    _ng_demo=ng.parse_pbp(lf.load_demo())
except (OSError, ValueError) as _exc:
    _ng_demo=None
    st.warning(f'DEMO fixture unavailable: {type(_exc).__name__}')
if _ng_demo is not None:
    _ng_n=len(_ng_demo['events'])
    st.session_state.setdefault('v56_demo_step',min(40,_ng_n))
    def _ng_step(d):
        st.session_state['v56_demo_step']=max(0,min(_ng_n,st.session_state.get('v56_demo_step',0)+d))
    _b=st.columns([1,1,1,1,6])
    _b[0].button('⏮',key='v56_demo_first',on_click=lambda: st.session_state.__setitem__('v56_demo_step',0),help='Start (pregame prior)')
    _b[1].button('◀',key='v56_demo_prev',on_click=_ng_step,args=(-1,),help='Previous shot event')
    _b[2].button('▶',key='v56_demo_next',on_click=_ng_step,args=(1,),help='Next shot event')
    _b[3].button('⏭',key='v56_demo_last',on_click=lambda: st.session_state.__setitem__('v56_demo_step',_ng_n),help='Final')
    with _b[4]:
        st.slider('Replay event',0,_ng_n,key='v56_demo_step')
    _k=st.session_state['v56_demo_step']
    _g_now=ng.truncate(_ng_demo,_k) if _k>0 else ng.pregame_game(_ng_demo['game_id'],_ng_demo['away'],_ng_demo['home'],_ng_demo.get('start'))
    _g_prev=ng.truncate(_ng_demo,_k-1) if _k>1 else ng.pregame_game(_ng_demo['game_id'],_ng_demo['away'],_ng_demo['home'])
    _r_prev=ng.model(_g_prev,_v56_priors,use_form=_ng_form)
    _r_now=ng.model(_g_now,_v56_priors,use_form=_ng_form)
    ng.rerank(_r_now['players'],ng.rerank(_r_prev['players'],None) if _k>0 else None)
    _r_now['rank_basis']='vs previous replay step' if _k>0 else 'pregame prior'
    _ev=_ng_demo['events'][_k-1] if _k>0 else None
    _ev_txt=(f'Event {_k}/{_ng_n}: {"P"+str(_ev["period"]) if _ev["ptype"]=="REG" else _ev["ptype"]} {_ev["secs"]//60:02d}:{_ev["secs"]%60:02d} · {_ev["kind"].upper()} · '
             f'{(_ng_demo["roster"].get(_ev["shooter"]) or {}).get("name",_ev["shooter"])} ({_ev["team"]}) · {_ev["strength"]} · xG {_ev["xg"]:.2f}') if _ev else 'Before puck drop: pregame prior.'
    v5.html_block(st,v56.nextgoal_panel(_r_now,SEASON,lstate.game_label(_g_now),None,demo=True,top=_ng_top,
                  title=f'DEMO · {_ng_demo["away"]} @ {_ng_demo["home"]}',note=lf.DEMO_LABEL+'. '+_ev_txt+'. Arrows: '+_r_now['rank_basis']+'.'))
with st.expander('ⓘ How the next-goal model works'):
    st.markdown(ng.__doc__)
st.caption('Next-goal % is a model estimate from shot counts, shot quality and season priors; it is not calibrated and not betting advice.')
if xgm.attribution(_v56_results): st.caption(xgm.attribution(_v56_results)+' (model chances use shot quality; non-commercial use, see MoneyPuck terms).')  # V5.9 credit
st.markdown(ui.footer("NULL’S PLAYBOOK · LIVE NEXT GOAL"),unsafe_allow_html=True)
