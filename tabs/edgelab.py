"""Null's Playbook V5.8 · EdgeLab tab (read-only). Executed by tabs.run_tab() inside the app's namespace.
Model p = the Edge Flags computation (edgeflags_v56.player_lambda + live_nextgoal_v56.p_anytime on the shared
_v56_results); implied = edgelab_v55.american_to_implied of the LIVE price (latest quote per book, averaged across
books). No manual entry, no bankroll / sizing, no moneylines, no DEMO prices. See edgelab_v58."""
# ============================================================ V5.8 EdgeLab (read-only)
st.markdown(v5.tab_head('NULL’S PLAYBOOK · EDGELAB','EdgeLab','Next-goal model chance vs the live anytime-goal price · edge = model p − implied',
    chips=[('Model p = 1 − e^(−λ)','odds'),('Live price, not the opener','team'),('Read-only · not betting advice','warn')],tone='odds'),unsafe_allow_html=True)
_el_prices=elv58.live_prices(_np_shared_quotes)
_el_scorers=sctn.active(st.session_state,np_day)
_el_scored=set((_el_scorers or {}).get('players',{}).keys())
_el_priced,_el_unpriced=elv58.model_rows(_v56_results,_el_prices,_el_scored)
_el_over=sum(r['result']['phase'] in elv58.OVER for r in _v56_results)
_el_books=sorted({b for v in _el_prices.values() for b in v['book_names']})
_el_at=max((v['at'] for v in _el_prices.values() if v['at']),default=None)
st.markdown(ui.stat_strip([('Priced players',len(_el_priced),'odds' if _el_priced else 'muted'),
    ('Positive edge',sum(r['edge']>0 for r in _el_priced),'ok' if any(r['edge']>0 for r in _el_priced) else 'muted'),
    ('Books',len(_el_books),'team'),('Updated',elv58.fmt_time(_el_at),'gem')]),unsafe_allow_html=True)
if not _el_prices:
    st.markdown(v5.empty_state(elv58.NO_PRICES_TITLE,'EdgeLab never invents prices. The model chance for every slate skater is still listed below, without an edge.','$'),unsafe_allow_html=True)
if not _v56_results:
    st.info('No NHL games for this date.')
elif not (_el_priced or _el_unpriced):
    st.markdown(v5.empty_state('Nothing open to price','Every game is final (or every listed skater has already scored).','◎'),unsafe_allow_html=True)
else:
    v5.html_block(st,elv58.table_html(_el_priced,_el_unpriced,logo=lambda t:v5.logo(t,'el-lg'),limit_unpriced=None if not _el_prices else 30),extra_class='v58-el')
    if _el_prices and len(_el_unpriced)>30:
        with st.expander(f'All {len(_el_unpriced)} players without a live price'):
            st.dataframe(pd.DataFrame([{'Player':r['name'],'Team':r['team'],'Game':r['game'],'Model p':round(r['model_p']*100,1)} for r in _el_unpriced]),hide_index=True,width='stretch')
if _el_scored:
    _el_sc=sorted(_el_scorers['players'].values(),key=lambda x:(-x['goals'],x['name']))
    st.markdown(v5.inline('<p class="el-settled"><span>Settled · already scored, left out of the edges:</span> '+' · '.join(f'<b>{v5.esc(x["name"])}</b>' for x in _el_sc)+'</p>','v58-el'),unsafe_allow_html=True)
st.caption(('Live price = each sportsbook’s latest anytime-goal quote for the player, averaged across books ('+', '.join(_el_books)+'; source: '+_np_source+'). ' if _el_books else '')+
           'Edge Flags compares the same model with the opener (earliest quote seen); EdgeLab uses the current price. '
           'λ: pregame = prior shots/game × shrunk sh%; live = current scoring rate × remaining minutes. Final/shootout games'+
           (f' ({_el_over} tonight)' if _el_over else '')+' and players who already scored are left out. No moneylines: the model has no win probability. '
           'Form % is never used as a probability. Model estimates are uncalibrated; entertainment and research only.')
if xgm.attribution(_v56_results): st.caption(xgm.attribution(_v56_results)+' (model chances use shot quality; non-commercial use, see MoneyPuck terms).')  # V5.9 credit
st.markdown(ui.footer("NULL’S PLAYBOOK · EDGELAB"),unsafe_allow_html=True)
