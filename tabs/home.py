"""Null's Playbook V5.6 · home tab. Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""

import html as _np_html
if np_snapshot is not None:
    st.caption('🟢 Saved rankings updated: '+str(np_snapshot['updated_at'])[:19].replace('T',' ')+' UTC · '+str(len(np_snapshot['rankings']))+' players · auto slate snapshots, 30-minute updates')
    if np_snapshot.get('errors'):
        st.caption(f'⚠️ {len(np_snapshot["errors"])} data retrieval warnings in saved snapshot')
else:
    st.warning('No scheduled snapshot for this date yet. Live fallback may take 30 seconds or longer. Run the GitHub workflow to precompute it.')
history_status(np_day, quiet=True)  # V5.3.1: Home never shows history/coverage status
if st.session_state.get('v42_last_rank') and st.session_state.get('signals_day')==np_day:
    st.caption('Rankings last updated: '+st.session_state['v42_last_rank']['at'].astimezone(ZoneInfo('America/New_York')).strftime('%b %-d, %-I:%M %p ET'))
try:
    np_games=np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day)
except (requests.RequestException, ValueError, KeyError, TypeError) as np_err:
    np_games=[]
    st.warning(f'Unable to load matchups: {np_err}')
np_games=[g for g in (np_games or []) if isinstance(g,dict)]
np_ranked=st.session_state.get('signals_ranked')
np_ready=isinstance(np_ranked,pd.DataFrame) and not np_ranked.empty and st.session_state.get('signals_day')==np_day
_trk_conn,_trk_evals,_trk_records,_trk_err=np_track_state()
_trk_badges=trk.badge_lookup(_trk_records)
if not np_games:
    st.info('No NHL games are scheduled for this date. Pick another date above.')
# V5.2: four genuinely distinct leaders, computed from the selected day's slate.
_home_targets=home_all_targets(np_games,np_ranked if np_ready else None,np_day)
_home_leaders=home_choose_leaders(np_ranked if np_ready else None,_home_targets,_np_shared_discrepancies)
# V5.4: Research's Player Intelligence picks, from the SAME shared function.
_np_intel,_=intel_from_state(st.session_state,np_day)
_np_picks=intel_four_picks(_np_intel)
# V5.5: one designed fragment (hero, board, leaders + intelligence, track rings, featured matchup) bound to live data.
try:
    _v5_ranked=assign_statistical_ranks(np_ranked.copy()) if np_ready else None
except (ValueError,KeyError,TypeError):
    _v5_ranked=None
_v5_mg=mc.slate_games(np_games)
_v5_lead=_home_leaders.get('statistical')
_v5_fg=(mc.game_for_pick({'Team':_v5_lead.get('team'),'opponent':_v5_lead.get('opponent')},np_games) if _v5_lead else None) or (_v5_mg[0] if _v5_mg else None)
_v5_gk,_v5_gk_err=goalies_cached((_v5_fg['away'],_v5_fg['home']),SEASON) if _v5_fg else ([],[])
_v5_st,_v5_st_err,_v5_st_at=starters_cached(np_day,tuple((g['key'],g['game_id'],g['away'],g['home'],g['status']) for g in _v5_mg)) if _v5_mg else ({},[],None)
_v5_state=v5state.build_state(day=np_day,season=SEASON,games=np_games,ranked=np_ranked if np_ready else None,targets=_home_targets,
    leaders=_home_leaders,picks=_np_picks,ranked_with_stat=_v5_ranked,goalie_rows=_v5_gk,starters=_v5_st,starters_fetched_at=_v5_st_at,
    discrepancies=_np_shared_discrepancies,track=v5state.track_summary(_trk_evals,trk.rolling),
    snapshot_at=np_snapshot['updated_at'] if np_snapshot is not None else None,
    rosters_fn=v55_rosters_cached,logs_fn=v55_logs_cached,price_label=price_label,track_badges=_trk_badges)
# V5.6: board tiles carry live/final scores and the official game state (score endpoint, else play-by-play).
_v5_state['scores']=lstate.tile_scores(_v56_results)
for _g in (_v5_state.get('games') or [])+([_v5_state['featured']] if _v5_state.get('featured') else []):
    _sc=_v56_scores.get(str(_g.get('game_id') or ''))
    if _sc and _sc.get('state'):
        _g['status']=_sc['state']
v5.html_block(st,v5.render_home(_v5_state,datetime.now(timezone.utc)))
if _v56_results:  # V5.6: Home live strip (score + current next-goal leader per game)
    v5.html_block(st,v56.live_strip(lstate.strip_items(_v56_results)))
# V5.4: auto-save today's/future predictions (idempotent; never touches a locked slate).
if _trk_conn is not None and np_ready and np_day>=np_eastern_today().isoformat():
    try:
        _trk_rows=trk.build_prediction_rows(assign_statistical_ranks(np_ranked.copy()),_home_leaders,np_games,home_gematria_shortlist(_home_targets,5))
        _trk_sig=(np_day,tuple(sorted((r['player_key'],r['source'],r['rank']) for r in _trk_rows)))
        if st.session_state.get('v54_trk_sig')!=_trk_sig:
            _starts=[g.get('Start (UTC)') for g in np_games if g.get('Start (UTC)')]
            _first=min(_starts) if _starts else None
            _lock=bool(_first) and datetime.now(timezone.utc)>=datetime.fromisoformat(str(_first).replace('Z','+00:00'))
            _res=trk.save_predictions(_trk_conn,np_day,_trk_rows,n_games=len(np_games),lock=_lock)
            st.session_state['v54_trk_sig']=_trk_sig
            st.session_state['v54_trk_status']=_res
    except Exception as _trk_exc:  # tracking must never break Home
        st.session_state['v54_trk_status']={'status':'error','error':str(_trk_exc)}
st.markdown(ui.day_banner(np_day,num_universal_day(np_day)),unsafe_allow_html=True)
st.markdown(ui.section('Strongest gematria alignments','Top ten symbolic matches across the slate · D = day, T = team, A = arena','🔮','gem'),unsafe_allow_html=True)
_gem_cards=[ui.gem_card(_i,_p['player'],_p['team'],_p.get('player_id',''),_p['matches'],_p['form'],len(_p['day']),len(_p['team_matches']),len(_p['arena_matches']),season=SEASON)
            for _i,_p in enumerate(home_gematria_shortlist(_home_targets,10),1)]
if _gem_cards: st.markdown('<div class="np-hscroll">'+''.join(_gem_cards)+'</div>',unsafe_allow_html=True)
else: st.info('Player gematria rankings will appear when this slate’s roster rankings are available.')
st.caption('Gematria matches are numerical coincidences, not evidence of a higher likelihood of scoring.')
if _home_targets:
    st.markdown(ui.section('Player targets by matchup','Both teams are grouped under each game · expand for the top numerical matches per roster','🎯','team'),unsafe_allow_html=True)
    for _match in _home_targets:
        _g=_match['game'];_away=_g['away'];_home=_g['home']
        with st.expander(f'{_away}  vs  {_home} · {format_game_time(_g.get("start"))} · {_g["arena"] or "Venue unavailable"}'):
            _cols=st.columns(2)
            for _col,_side,_code in zip(_cols,('away','home'),(_away,_home)):
                with _col:
                    _rows=[ui.team_head(_code,_g.get(_side+'_name') or _code,'Top numerical matches')]
                    for _ix,_p in enumerate(_match[_side+'_targets'][:3],1):
                        _rows.append(ui.target_row(_ix,_p['player'],_code,_p.get('player_id',''),_p['matches'],_p['form'],len(_p['day']),len(_p['team_matches']),len(_p['arena_matches']),season=SEASON))
                    st.markdown(''.join(_rows),unsafe_allow_html=True)
if not np_ready:
    if np_games:
        st.info('⏳ Automatically loading the full NHL slate. This may take a few minutes on first load.')
else:
    try:
        np_view=assign_statistical_ranks(np_ranked.copy())
    except (ValueError,KeyError,TypeError) as _rank_err:
        np_view=None
        st.warning(f'Statistical rankings could not be validated for display: {_rank_err}')
    if np_view is not None:
        np_view=merge_history(np_view, st.session_state.get('history_v38') if st.session_state.get('history_v38_day')==np_day else None)
        np_view=merge_multi_history(np_view, st.session_state.get('history_v386') if st.session_state.get('history_v386_day')==np_day else None)
        st.markdown(ui.section('Top statistical candidates','Ranked by the V3.2 adjusted index · shown as Form %','⚡','stat'),unsafe_allow_html=True)
        np_cards=[]
        for _,r in np_view.sort_values('Statistical rank').head(8).iterrows():
            t=r.get('Team','');rank=int(r.get('Statistical rank',0))
            np_cards.append(f'<div class="np-feature"><div class="np-feature-top"><span class="np-rank">#{rank}</span>{ui.avatar(ui.mug_url(t,r.get("Player ID"),SEASON),"lg")}</div>'
                            f'<b>{ui.esc(r.get("Player",""))}</b><small>{ui.logo(t,16)} {ui.esc(t)} · Rank #{rank}</small>'
                            f'<div class="np-feature-score">{ui.format_form_pct(r.get("V3.2 Adjusted Index"))}<span> FORM %</span></div></div>')
        st.markdown('<div class="np-feature-scroll">'+''.join(np_cards)+'</div>',unsafe_allow_html=True)
        st.markdown(ui.section('Statistical leaderboard','Top ten · Form % = share of the 100-point form benchmark (clipped at 100%)','📊','stat'),unsafe_allow_html=True)
        _adjust=st.toggle('Use track record to adjust rankings',value=False,key='v54_track_adjust',
                          help='OFF (default): rankings are unchanged and track record only adds badges. ON: this leaderboard is re-sorted by a bounded (±5%) track-record adjustment.') if hasattr(st,'toggle') else st.checkbox('Use track record to adjust rankings',value=False,key='v54_track_adjust')
        _board_src=trk.apply_track_record(np_view.sort_values('Statistical rank'),_trk_records,enabled=_adjust)
        np_cols=[c for c in ['Statistical rank','Player','Team','V3.2 Adjusted Index','Shots/G L5','Track adj'] if c in _board_src]
        _board=ui.with_form_pct(_board_src[np_cols].head(10)).drop(columns=['V3.2 Adjusted Index'])
        _cfg={'Statistical rank':st.column_config.NumberColumn('Rank',format='#%d',width='small'),
            'Shots/G L5':st.column_config.NumberColumn('Shots/G · L5',format='%.1f'),
            'Track adj':st.column_config.NumberColumn('Track adj',format='%+.3f')}
        _cfg.update(ui.form_pct_config(st,progress=True))
        st.dataframe(_board,hide_index=True,use_container_width=True,column_config=_cfg)
        if _adjust: st.caption('Track-record adjustment ON: order uses the raw V3.2 index × (1 + adj), adj capped at ±5% with ≥3 graded picks. The four leaders above are unchanged.')
        # V5.3.1: historical coverage is shown in Research only, never on Home.
st.markdown(ui.section('Sportsbook price intelligence','Best available anytime-goal prices across books','📈','odds'),unsafe_allow_html=True)
if not _np_shared_discrepancies.empty:
    st.caption(f"{len(_np_shared_clean):,} validated quotes · {_np_shared_clean['sportsbook'].nunique()} sportsbooks · {len(_np_shared_discrepancies)} comparable props")
    _np_home_best=_np_shared_discrepancies.assign(_gap=pd.to_numeric(_np_shared_discrepancies['decimal_price_improvement_pct'],errors='coerce')).sort_values('_gap',ascending=False,na_position='last').head(3)
    _rows=[]
    for _,_np_o in _np_home_best.iterrows():
        _rows.append(f'<div class="np-orow"><div><b>{ui.esc(_np_o["player"])}</b><br/><small>{ui.esc(_np_o["best_sportsbook"])} · +{ui.fmt_num(_np_o["_gap"])}% payout gap</small></div><strong>{ui.esc(price_label(_np_o["best_odds"]))}</strong></div>')
    st.markdown(''.join(_rows),unsafe_allow_html=True)
    st.caption('Open Odds for full comparisons. Prices are not verified player identities or scoring probabilities.')
elif _np_live_error:
    st.warning(f'Odds feed unavailable: {_np_live_error}')
elif _np_shared_error:
    st.warning(f'Odds validation issue: {_np_shared_error}')
elif _np_key and _np_source != 'Uploaded CSV':
    st.info('Odds API connected, but no comparable goal-scorer quotes are currently available. Check Odds for coverage details.')
else:
    st.info('No odds feed configured for this source. Add ODDS_API_KEY to Streamlit Secrets or upload a CSV in Odds.')
st.markdown(ui.footer("NULL’S PLAYBOOK · HOME · MATCHUP CENTER · ODDS · RESEARCH · NUMBERS · TRACK RECORD"),unsafe_allow_html=True)
