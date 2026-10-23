"""Null's Playbook V5.6 · track tab. Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""
# ============================================================ V5.4 Track Record
st.markdown(v5.tab_head('NULL’S PLAYBOOK · TRACK RECORD','Track Record','Every pick saved per slate · graded against final results · learns slowly and transparently',
    chips=[(f'📅 {np_day}','muted'),('Local SQLite store','stat')]),unsafe_allow_html=True)
_tconn,_tevals,_trecs,_terr = np_track_state()
if _tconn is None:
    st.error(f'Prediction store unavailable: {_terr}')
else:
    if any(e.get('demo') for e in _tevals):
        st.warning('DEMO DATA: this store contains seeded demonstration slates, not real results.')
    st.caption(f'Store: {trk.db_path()} · Streamlit Community Cloud storage is ephemeral (lost on reboot/redeploy); export JSON below to keep history.')
    # V5.8: the accuracy rings + per-slate bars moved here from Home (single home for every track-record element).
    v5.html_block(st, v5.track_section(v5state.track_summary(_tevals, trk.rolling), 'Accuracy summary'), extra_class='v58-track')
    _status = st.session_state.get('v54_trk_status')
    _info = trk.slate_info(_tconn, np_day)
    _c1,_c2 = st.columns([3,2])
    with _c1:
        st.markdown(ui.section('Predictions for '+np_day,'Auto-saved for today and future slates · locked at first puck drop','🔒','stat'),unsafe_allow_html=True)
        if _info:
            st.caption(('🔒 Locked '+str(_info['locked_at'])[:16].replace('T',' ')+' UTC') if _info['locked'] else '🟡 Saved, not locked yet (re-saved when rankings change)')
        else:
            st.caption('No predictions saved for this slate yet.')
        if _status and _status.get('status') == 'error':
            st.warning('Auto-save failed: ' + str(_status.get('error')))
    with _c2:
        if st.button('🔒 Lock predictions', key='v54_lock', disabled=bool(_info and _info['locked']), use_container_width=True):
            try:
                if not _info:
                    if not np_ready:
                        raise trk.TrackerError('Rankings for this slate are not loaded yet.')
                    trk.save_predictions(_tconn, np_day, trk.build_prediction_rows(assign_statistical_ranks(np_ranked.copy()), _home_leaders, np_games,
                                         home_gematria_shortlist(_home_targets,5)), n_games=len(np_games), lock=True, retro=np_day < np_eastern_today().isoformat())
                else:
                    trk.lock_slate(_tconn, np_day)
                st.success('Predictions locked. They will not be overwritten.')
            except (trk.TrackerError, ValueError, KeyError, TypeError) as _exc:
                st.warning(str(_exc))
    if _tevals:
        st.markdown(ui.section('Recent slates','Newest first · pending slates are excluded from every rate','🗂️','overlap'),unsafe_allow_html=True)
        st.markdown('<div class="np-slates">'+''.join(ui.slate_card(e) for e in sorted(_tevals,key=lambda e:e['day'],reverse=True)[:9])+'</div>',unsafe_allow_html=True)
        _trend = trk.trend(_tevals)
        if not _trend.empty:
            st.markdown(ui.section('Hit-rate trend','Per slate and rolling 7 slates (%)','📈','stat'),unsafe_allow_html=True)
            st.line_chart((_trend.set_index('Slate')*100).round(1))
        st.markdown(ui.section('By source','Stats · Numbers · Odds · Overlap picks','🧩','gem'),unsafe_allow_html=True)
        _src = trk.source_breakdown(_tevals)
        _src['Hit rate'] = _src['Hit rate'].map(lambda v: None if v is None else round(v*100,1))
        st.dataframe(_src, hide_index=True, use_container_width=True, column_config={'Hit rate': st.column_config.NumberColumn('Hit rate', format='%.1f%%')})
        st.markdown(ui.section('Player leaderboard','Shrunk hit rate (prior strength 10) · badges need ≥3 graded picks','🏅','odds'),unsafe_allow_html=True)
        if _trecs.empty:
            st.info('No graded picks yet.')
        else:
            _show = _trecs.drop(columns=['player_key']).copy()
            for _c in ('Hit rate','Shrunk rate'): _show[_c] = (_show[_c]*100).round(1)
            _show['Adjustment'] = (_show['Adjustment']*100).round(1)
            if 'Badge' in _show: _show['Badge'] = _show['Badge'].fillna('—')
            st.dataframe(_show.head(25), hide_index=True, use_container_width=True, column_config={
                'Hit rate': st.column_config.NumberColumn('Hit rate', format='%.1f%%'),
                'Shrunk rate': st.column_config.NumberColumn('Shrunk rate', format='%.1f%%'),
                'Adjustment': st.column_config.NumberColumn('Adj (toggle ON)', format='%+.1f%%')})
        # V5.8: moved from Home - the opt-in ±5% track-record adjustment of the statistical leaderboard (logic unchanged).
        st.markdown(ui.section('Track-adjusted leaderboard','Statistical top ten · optional bounded (±5%) adjustment from graded picks','⚖️','stat'),unsafe_allow_html=True)
        if not np_ready:
            st.info('Rankings for this slate are not loaded yet.')
        else:
            _adjust=st.toggle('Use track record to adjust rankings',value=False,key='v54_track_adjust',
                              help='OFF (default): rankings are unchanged and track record only adds badges. ON: this leaderboard is re-sorted by a bounded (±5%) track-record adjustment.')
            try:
                _tr_view=assign_statistical_ranks(np_ranked.copy())
            except (ValueError,KeyError,TypeError):
                _tr_view=None
            if _tr_view is not None:
                _tr_src=trk.apply_track_record(_tr_view.sort_values('Statistical rank'),_trecs,enabled=_adjust)
                _tr_cols=[c for c in ['Statistical rank','Player','Team','V3.2 Adjusted Index','Shots/G L5','Track adj'] if c in _tr_src]
                _tr_board=ui.with_form_pct(_tr_src[_tr_cols].head(10)).drop(columns=['V3.2 Adjusted Index'])
                _tr_cfg={'Statistical rank':st.column_config.NumberColumn('Rank',format='#%d',width='small'),
                    'Shots/G L5':st.column_config.NumberColumn('Shots/G · L5',format='%.1f'),
                    'Track adj':st.column_config.NumberColumn('Track adj',format='%+.3f')}
                _tr_cfg.update(ui.form_pct_config(st,progress=True))
                st.dataframe(_tr_board,hide_index=True,use_container_width=True,column_config=_tr_cfg)
                if _adjust: st.caption('Track-record adjustment ON: order uses the raw V3.2 index × (1 + adj), adj capped at ±5% with ≥3 graded picks. Home leaders and rankings are unchanged.')
    else:
        st.info('No history yet. Predictions are saved automatically when a slate’s rankings load; enter results after games are final.')
    st.markdown(ui.section('Enter results','Manual entry per game · or import final NHL results','✍️','team'),unsafe_allow_html=True)
    _tg = mc.slate_games(np_games)
    if not _tg:
        st.info('No games on this slate to enter results for.')
    else:
        with st.form('v54_results_form'):
            _gsel = st.selectbox('Game', [g['key'] for g in _tg], format_func=lambda k: next((f"{g['away']} @ {g['home']}" for g in _tg if g['key']==k), k), key='v54_res_game')
            _gg = next(g for g in _tg if g['key']==_gsel)
            _roster = []
            if np_ready:
                for _, _r in np_ranked[np_ranked['Team'].isin([_gg['away'],_gg['home']])].iterrows():
                    _roster.append({'player': str(_r['Player']), 'player_id': ui.player_id(_r.get('Player ID')), 'team': str(_r['Team'])})
            _roster.sort(key=lambda p: (p['team'], p['player']))
            _ms = st.multiselect('Goal scorers (roster)', list(range(len(_roster))), format_func=lambda i: f"{_roster[i]['player']} · {_roster[i]['team']}", key='v54_res_ms')
            _free = st.text_area('Other scorers (free text, one per line or comma-separated)', key='v54_res_free', help='Matched to the roster by accent-insensitive name; unmatched names are saved by name.')
            _final = st.checkbox('Game is final', value=True, key='v54_res_final')
            _sub = st.form_submit_button('Save results')
        if _sub:
            _names = [n for n in re.split(r'[\n,;]+', _free or '') if n.strip()]
            _matched, _unmatched = trk.resolve_names(_names, _roster)
            _scorers = [{**_roster[i], 'goals': 1} for i in _ms] + [{**m, 'goals': 1} for m in _matched] + [{'player': n.strip(), 'goals': 1, 'team': ''} for n in _unmatched]
            try:
                _n = trk.record_game_results(_tconn, np_day, _gg['game_id'] or _gg['key'], _scorers, source='manual', final=_final)
                st.success(f'Saved {_n} scorer(s) for {_gg["away"]} @ {_gg["home"]}.')
                if _unmatched:
                    st.warning('Saved by name (no unique roster match): ' + ', '.join(_unmatched))
            except trk.TrackerError as _exc:
                st.warning(str(_exc))
        if st.button('⬇️ Import final results from NHL', key='v54_nhl_import'):
            _done, _skip = 0, []
            for _g in _tg:
                try:
                    _events, _is_final = trk.fetch_final_goals(_g['game_id'])
                except trk.TrackerError as _exc:
                    _skip.append(str(_exc)); continue
                if not _is_final:
                    _skip.append(f"{_g['away']} @ {_g['home']}: not final yet"); continue
                _sc = trk.events_to_scorers(_events).get(str(_g['game_id']), [])
                trk.record_game_results(_tconn, np_day, _g['game_id'], _sc, source='nhl', final=True); _done += 1
            st.success(f'Imported {_done} final game(s).') if _done else st.info('No final games imported.')
            if _skip:
                with st.expander(f'{len(_skip)} game(s) skipped'):
                    st.write(_skip)
    _e1,_e2 = st.columns(2)
    with _e1:
        st.download_button('Export history (JSON)', trk.export_json(_tconn), file_name='nulls_playbook_track_record.json', mime='application/json', key='v54_export')
        _t_months=trk.months(_tconn)
        if _t_months:  # V5.5: small per-month exports (GitHub-friendly); nothing is deleted
            _t_m=st.selectbox('Month to export',_t_months,key='v55_export_month')
            st.download_button(f'Export {_t_m} (JSON)', trk.export_month_json(_tconn,_t_m), file_name=f'nulls_playbook_track_{_t_m}.json', mime='application/json', key='v55_export_month_btn')
    with _e2:
        _imp = st.file_uploader('Import history (JSON)', type=['json'], key='v54_import')
        if _imp is not None and st.button('Merge import', key='v54_import_go'):
            try:
                trk.import_json(_tconn, _imp.getvalue().decode('utf-8'))
                st.success('History merged (locked slates kept as they were).')
            except (trk.TrackerError, ValueError, UnicodeDecodeError) as _exc:
                st.warning(f'Import failed: {_exc}')
    with st.expander('How grading and learning work'):
        st.markdown('- **Pick**: the four Home leaders, the statistical top 10, the gematria top 5. Ranks 11–15 are a watch band.\n'
                    '- **Hit**: a pick who scored ≥1 goal in a final game. **Near-miss**: a watch-band player who scored, or a pick with an assist but no goal.\n'
                    '- **Unpredicted**: a scorer in a final game who was not a pick. Pending games/slates are excluded from rates.\n'
                    '- **Learning**: shrunk rate = (hits + 10·p0)/(picks + 10); adjustment = clamp(0.5·(shrunk−p0)/p0, ±5%), only with ≥3 graded picks; '
                    'applied only when “Use track record to adjust rankings” is ON (default OFF).')
st.markdown(ui.footer("NULL’S PLAYBOOK · TRACK RECORD"),unsafe_allow_html=True)
