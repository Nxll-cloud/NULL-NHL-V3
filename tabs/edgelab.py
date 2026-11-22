"""Null's Playbook V6.2 · EdgeLab tab = Anytime goal · tonight's patterns (scorer_patterns_v62), its ONLY content (t233).

The former EdgeLab view (model p vs mapped anytime-goal quotes, price-feed status, edge table) is no longer rendered here.
Its shared modules stay because other pages use them: edgelab_prices_v60 (Home price-gap leader, Odds board) and
edgelab_v58 / edgelab_v55 (price helpers, Edge Flags). Executed by tabs.run_tab() inside the app's namespace."""
import scorer_patterns_v62 as _ag
import accuracy_v58 as _ag_acc

st.markdown(v5.tab_head('NULL’S PLAYBOOK · EDGELAB', 'Anytime goal · tonight’s patterns',
    'Chance each skater still in play scores 1+ goal tonight · recent-games fit updated by tonight’s scorers',
    chips=[('Probability estimate', 'odds'), ('Tonight’s scorers = live input', 'team'), ('Not betting advice', 'warn')], tone='odds'),
    unsafe_allow_html=True)


@st.cache_data(ttl=3 * 3600, show_spinner=False, max_entries=2)
def _ag_patterns(day, sig):
    """Recent-games joint fit; sig = window file names + mtimes, so a newly scored night re-fits at once (small result)."""
    return _ag.build_patterns(day)


try:
    _ag_rank_df = st.session_state.get('signals_ranked')
    _ag_rows = (_ag_rank_df.to_dict('records') if isinstance(_ag_rank_df, pd.DataFrame) and st.session_state.get('signals_day') == np_day
                else ((np_snapshot or {}).get('rankings') or []))
    _ag_games = (np_snapshot or {}).get('games') or []
    _ag_pat = _ag_patterns(np_day, _ag.signature(np_day))
    _ag_feed = _ag.fetch_score(np_day)   # 60 s process cache while games are unfinished
    _ag_lv = _ag.tonight_live(_ag_feed, globals().get('_v56_pbp'))
    _ag_lv['feed_ok'] = _ag_feed is not None
    _ag_trows = _ag.tonight_rows(_ag_rows, _ag_games, _ag_pat, _ag_lv, globals().get('_v56_results') or [],
                                 _ag_acc.load_entry(np_day) if _ag_pat.get('status') == 'ok' else None)
    _ag_w = _ag.update_tonight(_ag_pat, _ag_trows) if _ag_pat.get('status') == 'ok' else {}
    _ag_preds, _ag_info = _ag.predict(_ag_trows, _ag_w, _ag_lv) if _ag_w else ([], {})
    _ag_sc, _ag_shared = _ag.scorer_profile(_ag_trows)
    v5.html_block(getattr(st, '_st', st), _ag.section_html(_ag_pat, _ag_preds, _ag_info, _ag_w, _ag_sc, _ag_shared, _ag_lv, np_day))
except Exception as _ag_exc:   # never break the app
    st.markdown(v5.empty_state('Anytime-goal estimates unavailable', f'{type(_ag_exc).__name__}: recent or tonight’s scorer data could not be read.'),
                unsafe_allow_html=True)
if xgm.attribution(globals().get('_v56_results') or []):   # the app Model chance (an input here) uses shot quality
    st.caption(xgm.attribution(_v56_results) + ' (the Model chance used here uses shot quality; non-commercial use, see MoneyPuck terms).')
st.markdown(ui.footer("NULL’S PLAYBOOK · EDGELAB"), unsafe_allow_html=True)
