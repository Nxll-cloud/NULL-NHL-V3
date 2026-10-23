"""Null's Playbook V5.6 · odds tab. Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""
import html as _odds_html
_odds_src_now=st.session_state.get('v46_source','Automatic API')
st.markdown(v5.tab_head('NULL’S PLAYBOOK · ODDS INTELLIGENCE','Odds Intelligence','Find the strongest prices. Compare the market. Follow your model.',
    chips=[(f'Source · {_odds_src_now}','odds'),('API connected' if _np_key else 'No API key · CSV import available','ok' if _np_key else 'warn'),('Anytime goal scorer','muted')],tone='odds'),unsafe_allow_html=True)
api_df=_np_live_quotes
if _np_live_error:
    st.warning(f'Live prices unavailable: {_np_live_error}')
elif not _np_key:
    st.info('Connect your odds feed in app secrets to enable automatic price comparison. CSV import is also available.')
elif _np_live_warnings:
    st.caption(f'Coverage notice: {len(_np_live_warnings)} events could not be retrieved.')
with st.expander('⚙️ Import & display preferences',expanded=False):
    source_choice=st.radio('Odds source',['Automatic API','Uploaded CSV','Combine both'],horizontal=False,key='v46_source')
    uploaded_odds=st.file_uploader('Optional CSV odds import',type=['csv'],key='playbook_odds_upload')
    if uploaded_odds is not None:
        try:
            st.session_state['playbook_odds_data']=pd.read_csv(uploaded_odds,dtype={'event_id':str,'line':str})
        except (ValueError,UnicodeError) as exc:
            st.warning(f'CSV could not be read: {exc}')
    st.download_button('CSV template',CSV_TEMPLATE,file_name='playbook_odds_template.csv',mime='text/csv')
    st.caption('Quote coverage depends on your data subscription. Credentials and technical source fields are not displayed.')
source_choice=st.session_state.get('v46_source','Automatic API')
csv_df=st.session_state.get('playbook_odds_data')
selected_frames=[]
if source_choice in ('Automatic API','Combine both') and isinstance(api_df,pd.DataFrame) and not api_df.empty:
    selected_frames.append(api_df)
if source_choice in ('Uploaded CSV','Combine both') and isinstance(csv_df,pd.DataFrame) and not csv_df.empty:
    selected_frames.append(csv_df)
if selected_frames:
    raw_quotes=pd.concat(selected_frames,ignore_index=True)
    try:
        price_rows,discrepancies=compare_odds(raw_quotes)
        audit=quote_audit(raw_quotes,price_rows)
        st.session_state['v46_odds_count']=int(price_rows['sportsbook'].nunique())
        _best_gap=pd.to_numeric(discrepancies.get('decimal_price_improvement_pct'),errors='coerce') if not discrepancies.empty else pd.Series(dtype=float)
        st.markdown(ui.stat_strip([('Sportsbooks',int(price_rows['sportsbook'].nunique()),'odds'),('Matched props',len(discrepancies),'overlap'),
            ('Valid quotes',f'{len(price_rows):,}','muted'),('Largest gap',(ui.fmt_num(_best_gap.max())+'%') if _best_gap.notna().any() else '—','stat')]),unsafe_allow_html=True)
        if audit['excluded_or_consolidated']:
            st.caption(f"{audit['received']:,} received · {audit['accepted']:,} retained · {audit['excluded_or_consolidated']:,} excluded or duplicate quotes consolidated")
        else:
            st.caption(f"{audit['accepted']:,} validated quotes")
        if discrepancies.empty:
            st.info('No identical player props currently have prices from at least two sportsbooks.')
        else:
            model_ranked=st.session_state.get('signals_ranked')
            if not (isinstance(model_ranked,pd.DataFrame) and st.session_state.get('signals_day')==np_day):
                model_ranked=None
            combined=attach_model(discrepancies,model_ranked)
            st.markdown(ui.section('Market scanner','Identical event, market and line compared across books','📈','odds'),unsafe_allow_html=True)
            st.caption('Identity verification is required before a price gap can be considered actionable. Name-only provider quotes are unverified.')
            f1,f2,f3,f4=st.columns(4)
            with f1:
                view_mode=st.selectbox('Sort by',['Biggest discrepancy','Model-backed','Longshots'],key='v46_mode')
            with f2:
                book_min=st.selectbox('Books compared',[2,3,4,5],key='v46_min_books')
            with f3:
                rank_limit=st.selectbox('Statistical shortlist',['All players','Top 25','Top 50','Top 100'],key='v47_rank_filter')
            with f4:
                identity_view=st.selectbox('Identity review',['All quotes (unverified)','Flagged name collisions only'],key='v47_identity_view')
            show=combined[combined['sportsbooks_compared']>=book_min]
            if rank_limit!='All players':
                show=show[pd.to_numeric(show['model_rank'],errors='coerce')<=int(rank_limit.split()[-1])]
            if identity_view=='Flagged name collisions only':
                show=show[show['identity_status'].str.startswith('Ambiguous',na=False)]
            show=order_opportunities(show,view_mode)
            st.caption('Price gaps compare identical events and markets. A large gap does not establish positive expected value.')
            if show.empty:
                st.info('No props match these filters.')
            else:
                _overview=show.head(30)[[c for c in ['player','team','best_odds','best_sportsbook','worst_odds','worst_sportsbook','sportsbooks_compared','decimal_price_improvement_pct','model_rank'] if c in show]].copy()
                for _c in ('best_odds','worst_odds'):
                    if _c in _overview: _overview[_c]=_overview[_c].map(price_label)
                _overview['decimal_price_improvement_pct']=pd.to_numeric(_overview['decimal_price_improvement_pct'],errors='coerce')
                _gmax=float(_overview['decimal_price_improvement_pct'].max()) if _overview['decimal_price_improvement_pct'].notna().any() else 0.0
                with st.expander('📋 Compact comparison table',expanded=False):
                    st.dataframe(_overview,hide_index=True,use_container_width=True,column_config={
                        'player':'Player','team':'Team','best_odds':'Best','best_sportsbook':'Best book','worst_odds':'Low','worst_sportsbook':'Low book',
                        'sportsbooks_compared':st.column_config.NumberColumn('Books',format='%d'),
                        'decimal_price_improvement_pct':st.column_config.ProgressColumn('Payout gap',format='%.1f%%',min_value=0.0,max_value=max(_gmax,1.0)),
                        'model_rank':st.column_config.NumberColumn('Model rank',format='#%d')})
                for ix,(_,r) in enumerate(show.head(30).iterrows()):
                    rank=pd.to_numeric(r.get('model_rank'),errors='coerce')
                    rank_text=f"Model #{int(rank)}" if pd.notna(rank) else "Model rank unavailable"
                    _team=r.get('team','')
                    _team='' if pd.isna(_team) else _team
                    st.markdown(ui.odds_card(r['player'],_team,r.get('player_id',''),price_label(r['best_odds']),r['best_sportsbook'],price_label(r['worst_odds']),r['worst_sportsbook'],
                        r['decimal_price_improvement_pct'],r['sportsbooks_compared'],rank_text,r.get('identity_status','Unverified'),season=SEASON),unsafe_allow_html=True)
                    with st.expander(f'Compare all sportsbook prices · {r["player"]}',expanded=False):
                        options=quotes_for_market(price_rows,r)
                        options=options[['sportsbook','american_odds','updated_at']].copy()
                        options.columns=['Sportsbook','American odds','Updated (UTC)']
                        options['American odds']=options['American odds'].map(price_label)
                        options['Updated (UTC)']=pd.to_datetime(options['Updated (UTC)'],utc=True,errors='coerce').dt.strftime('%b %d · %H:%M UTC')
                        st.dataframe(options,hide_index=True,use_container_width=True)
                if len(show)>30:
                    st.caption(f'Showing 30 of {len(show)} opportunities. Download the complete comparison below.')
                st.download_button('Export all comparisons',show.to_csv(index=False),file_name='nulls_playbook_v46_odds.csv',mime='text/csv')
            if model_ranked is None:
                st.caption('Model rankings for the selected date are not loaded yet; price discrepancies remain available.')
    except ValueError as exc:
        st.warning(f'Unable to validate current quotes: {exc}')
else:
    st.info('No sportsbook quotes available for the selected source.')
