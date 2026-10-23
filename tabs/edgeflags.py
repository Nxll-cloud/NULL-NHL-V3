"""Null's Playbook V5.6 · Edge Flags tab. Executed by tabs.run_tab() inside the app's namespace.
Each game is paired with its top-ranked next-goal shooter; edge = model p (1 - exp(-lambda), V5.6 model, no Form)
minus the implied probability of the opening anytime-goal line (EdgeLab american_to_implied). See edgeflags_v56."""

st.markdown(v5.tab_head('NULL’S PLAYBOOK · EDGE','Edge Flags','Top next-goal shooter per game vs his opening anytime line · edge = model p − implied',
    chips=[('Model p = 1 − e^(−λ)','odds'),('No Form in p','team'),('Not betting advice','warn')],tone='odds'),unsafe_allow_html=True)
_ef_store=st.session_state.setdefault('v56_openers',{}).setdefault(np_day,{})
_ef_live=eflags.opening_lines(_np_shared_quotes)
eflags.remember_openers(_ef_store,_ef_live)
_ef_demo=not _ef_store
_ef_lines=eflags.demo_lines(_v56_priors) if _ef_demo else _ef_store
_ef_label=eflags.DEMO_LABEL if _ef_demo else 'Opening line = earliest observed quote this session ('+_np_source+')'
_c1,_c2,_c3=st.columns(3)
with _c1: _ef_min=st.slider('Flag when edge ≥ (pts)',0.0,10.0,eflags.MIN_EDGE*100,0.5,key='v56_ef_min')/100
with _c2: _ef_sort=st.toggle('Flagged games first',value=True,key='v56_ef_sort')
with _c3: _ef_top=st.selectbox('Shooters per game',[3,5,8],index=1,key='v56_ef_top')
if _ef_demo:
    st.warning('DEMO lines: no ODDS_API_KEY in Streamlit secrets and no uploaded CSV, so these opening prices are synthetic '
               '(season goals/game + 5% vig), not sportsbook prices. Add a key or a CSV on the Odds tab for real lines.')
_ef_cards=[]
_ef_rec=sctn.active(st.session_state,np_day)  # V5.9: scored-tonight badge (display only; settled rows stay unflagged)
_ef_all=[]
for r in _v56_results:
    rows=eflags.edges_for_game(r['result'],_ef_lines,min_edge=_ef_min,top_n=_ef_top)
    flag=eflags.game_flag(rows)
    _ef_cards.append((r,rows,flag))
    _ef_all+=[dict(x,game=f'{r["slate"]["away"]} @ {r["slate"]["home"]}',state=r['result']['phase']) for x in rows]
if _ef_sort:
    _ef_cards.sort(key=lambda c:(not c[2]['flagged'],-(c[2]['top']['edge'] or -1) if c[2]['top'] and c[2]['top']['edge'] is not None else 1))
_ef_n=sum(c[2]['flagged'] for c in _ef_cards)
st.markdown(ui.stat_strip([('Games',len(_ef_cards),'odds'),('Flagged',_ef_n,'warn' if _ef_n else 'muted'),
    ('Lines',('DEMO ' if _ef_demo else '')+str(len(_ef_lines)),'warn' if _ef_demo else 'team'),('Threshold',f'{_ef_min*100:.1f} pts','gem')]),unsafe_allow_html=True)
if not _ef_cards:
    st.info('No NHL games for this date.')
else:
    v5.html_block(st,'<div class="efgrid">'+''.join(v56.edge_card(r['slate'],f,rows,SEASON,(r['label'] or r['result']['phase'].title())+' · '+_ef_label,scored=_ef_rec)
                                                   for r,rows,f in _ef_cards)+'</div>')
    with st.expander('All rows'):
        _ef_df=pd.DataFrame(_ef_all)
        if not _ef_df.empty:
            st.dataframe(sctn.mark_frame_by_id(_ef_df[['game','state','rank','name','team','lambda','model_p','american','implied','edge','settled','flag','line_source','pid']],_ef_rec,'pid'),
                         hide_index=True,width='stretch')
st.caption('λ: pregame = prior shots/game × shrunk sh% (k=50); live = the player’s current scoring rate × remaining minutes; final = no flag. '
           'A player who already scored is settled (anytime prop won) and never flagged. Openers: the Odds API current-odds endpoint has no '
           'historical openers, so the opener is the first quote this session saw (kept with remember_openers). Moneyline is not flagged: the model has no win-probability part. '
           'Model estimates are uncalibrated; entertainment and research only.')
st.markdown(ui.footer("NULL’S PLAYBOOK · EDGE FLAGS"),unsafe_allow_html=True)
