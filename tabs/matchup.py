"""Null's Playbook V5.6 · matchup tab. Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""
# ============================================================ V5.4 Matchup Center
def _mc_set_query(key):
    if hasattr(st, 'query_params'):
        try:
            if key: st.query_params['matchup'] = key
            elif 'matchup' in st.query_params: del st.query_params['matchup']
        except Exception:
            pass

def _mc_open(key):
    st.session_state['v54_mc_game'] = key
    st.session_state['v54_mc_select'] = key
    _mc_set_query(key)

def _mc_back():
    st.session_state['v54_mc_game'] = None
    st.session_state['v54_mc_select'] = '—'
    _mc_set_query(None)

def _mc_pick():
    _sel = st.session_state.get('v54_mc_select')
    st.session_state['v54_mc_game'] = None if _sel in (None, '—') else _sel
    _mc_set_query(st.session_state['v54_mc_game'])

st.markdown(v5.tab_head('NULL’S PLAYBOOK · MATCHUP CENTER','Matchup Center','Start from a pick · open its game · see both rosters’ targets, the goalies they face, live next-goal odds and real H2H',
    chips=[(f'📅 {np_day}','muted'),(f'{len(mc.slate_games(np_games))} games','odds')]),unsafe_allow_html=True)
_mc_games = mc.slate_games(np_games)
_mc_keys = [g['key'] for g in _mc_games]
if 'v54_mc_game' not in st.session_state and hasattr(st, 'query_params'):
    try:
        _qp = st.query_params.get('matchup')
        st.session_state['v54_mc_game'] = _qp if _qp in _mc_keys else None
    except Exception:
        st.session_state['v54_mc_game'] = None
_mc_intel, _ = intel_from_state(st.session_state, np_day)
_mc_picks = intel_four_picks(_mc_intel)
st.markdown(ui.section('Player intelligence picks','Same four picks as Home and Research · open a card’s game below','🧠','overlap'),unsafe_allow_html=True)
_mc_cols = st.columns(4)
for _col,(_k,_l) in zip(_mc_cols, INTEL_LABELS):
    _g = mc.game_for_pick(_mc_picks.get(_k), np_games)
    with _col:  # card and its button share a column, so they stay together when columns stack on mobile
        st.markdown(ui.intel_row([ui.intel_card(_k,_l,_mc_picks.get(_k),season=SEASON)], solo=True),unsafe_allow_html=True)
        if _g:
            st.button(f'Open {_g["focus_team"]} vs {_g["opponent"]}', key=f'v54_mc_open_{_k}', on_click=_mc_open, args=(_g['key'],), use_container_width=True)
        elif _mc_picks.get(_k):
            st.caption('This player’s game is not on the loaded slate.')
        else:
            st.caption('No pick yet for this category.')
_labels = {'—': 'Choose any slate game…'}
_labels.update({g['key']: f'{g["away"]} @ {g["home"]} · {format_game_time(g["start"])}' for g in _mc_games})
if st.session_state.get('v54_mc_select') not in ['—'] + _mc_keys:
    st.session_state['v54_mc_select'] = st.session_state.get('v54_mc_game') if st.session_state.get('v54_mc_game') in _mc_keys else '—'
st.selectbox('Open any game on the slate', ['—'] + _mc_keys, format_func=lambda k: _labels.get(k, k), key='v54_mc_select', on_change=_mc_pick)
_sel_key = st.session_state.get('v54_mc_game')
_game = mc.find_game(np_games, _sel_key) if _sel_key else None
if _sel_key and _game is None:
    st.warning('That matchup is not on the selected slate. Choose another game.')
    st.button('← Back to overview', key='v54_mc_back_missing', on_click=_mc_back)
elif _game is None:
    if not _mc_games:
        st.info('No NHL games are scheduled for this date. Pick another date on Home.')
    else:
        # V5.5: the same scoreboard component as Home (starter dots from the shared starters cache).
        v5.html_block(st,v5.scoreboard({'games':_mc_games,'starters':_v5_st,'scores':lstate.tile_scores(_v56_results)},datetime.now(timezone.utc)))
        # V5.6: MOVED from Research. V5.4 Goalies · Goals Allowed (descriptive; rankings unchanged; same helpers/keys).
        with st.container():
            st.markdown(ui.section('Goalies: Goals Allowed','Per team, by goalie · season to date · NHL club-stats','🥅','odds'),unsafe_allow_html=True)
            _gk_all=st.checkbox('Show all NHL teams (not just tonight’s slate)',value=False,key='v54_gk_all')
            _gk_teams=sorted(mc.TEAM_NAMES) if _gk_all else sorted({t for g in _mc_games for t in (g['away'],g['home'])})
            if not _gk_teams:
                st.info('No teams on this slate. Pick a date with games, or show all NHL teams.')
            else:
                _gk_rows,_gk_err=goalies_cached(tuple(_gk_teams),SEASON)
                _gk_sort=st.radio('Sort teams by',list(gk.SORTS),horizontal=True,key='v54_gk_sort')
                _gk_sum=gk.sort_summary(gk.team_summary(_gk_rows,_gk_teams),_gk_sort)
                st.markdown('<div class="np-gk-legend"><span><i style="background:#fb923c"></i>Leaky (top third) · more goals allowed = more scoring chances for shooters facing them</span>'
                            '<span><i style="background:#38bdf8"></i>Stingy (bottom third)</span><span><i style="background:#64748b"></i>Middle / no data</span></div>',unsafe_allow_html=True)
                _gk_df=gk.goalie_frame(_gk_rows)
                _cards=[]
                for _i,_r in _gk_sum.iterrows():
                    _g=_gk_df[_gk_df['Team']==_r['Team']].sort_values(['GA','GP'],ascending=[False,False]).to_dict('records') if not _gk_df.empty else []
                    _cards.append(ui.goalie_card(_r['Team'],mc.TEAM_NAMES.get(_r['Team'],_r['Team']),_r,_g,_r['Tone'],_i+1))
                st.markdown('<div class="np-gk-grid">'+''.join(_cards)+'</div>',unsafe_allow_html=True)
                st.caption('Source: NHL official API club-stats/{team}/'+SEASON+'/2 (regular season, team-specific: a traded goalie is listed under each club). '
                           'GAA = GA × 60 / time on ice (— when no ice time). Season-to-date at fetch time, cached 30 min. Not used in any ranking.')
                if _gk_err:
                    with st.expander(f'{len(_gk_err)} goalie requests failed'):
                        st.write(_gk_err)
        # V5.6: every goalie vs the opposing threats (next-goal model), reverse view and REAL H2H flags.
        _v56_teams=tuple(sorted({t for g in _mc_games for t in (g['away'],g['home'])}))
        _v56_gk_rows,_v56_gk_err=goalies_cached(_v56_teams,SEASON)
        _v56_h2h=v56_h2h_cached(tuple((g['away'],g['home']) for g in _mc_games),np_day,SEASON)
        _v56_cov=h2h.coverage_label(SEASON,games=sum(d['games'] for d in _v56_h2h.values()))
        st.markdown(ui.section('Goalies vs tonight’s threats','Opposing shooters ranked by V5.6 next-goal % · H2H from real NHL play-by-play ('+_v56_cov+')','🧤','warn'),unsafe_allow_html=True)
        _v56_sort=st.toggle('Sort games by H2H flag',value=False,key='v56_mc_sort_flag')
        _v56_views=[]
        for _g in _mc_games:
            _r=_v56_by_key.get(_g['key'])
            if _r is not None:
                _v56_views.append((_g,mcg.game_view(_g,_r['result'],_r['game'],(_v5_st or {}).get(_g['key'],{}),_v56_gk_rows,_v56_h2h.get((_g['away'],_g['home'])),priors=_v56_priors)))
        _v56_nflag=sum(len(v['flags']) for _,v in _v56_views)
        st.caption(f'🚩 {_v56_nflag} H2H flag(s): a top-3 next-goal shooter facing a goalie he has scored on in a real meeting of these two clubs {_v56_cov}.')
        for _g,_v in mcg.sort_games(_v56_views,_v56_sort):
            _gl=f'{_g["away"]} @ {_g["home"]}'
            _d=_v56_h2h.get((_g['away'],_g['home'])) or {}
            _cards=''.join(v56.goalie_threats(_v['goalies'][_t],_t,_v['threats'][_t],SEASON,h2h.coverage_label(SEASON,games=_d.get('games',0)))
                           for _t in (_g['away'],_g['home']) if _v['goalies'].get(_t))
            v5.html_block(st,f'<section class="sec"><div class="sh"><h3>{v5.esc(_gl)} {"🚩"*len(_v["flags"])}</h3><p>Threats ranked by {v5.esc(_v["basis"])}</p></div>'
                          +v56.h2h_flag(_v['flags'],_gl)+f'<div class="gtgrid">{_cards or "<p>No goalie data for this game.</p>"}</div></section>')
            with st.expander(f'Reverse view · {_gl}: each top shooter’s hardest goalie'):
                v5.html_block(st,v56.reverse_view(_v['reverse'],SEASON))
        st.caption('Goalie in net: play-by-play goalieInNetId when the game has started, else the starter feed (confirmed/probable), else the club’s season games-started leader (labelled). '
                   'Hardest goalie = lowest goals per H2H shot on goal with ≥3 shots; otherwise the opposing club’s best season SV%. '
                   'Coverage limit: only meetings between these two clubs are scanned, so history from other matchups (e.g. before a trade) is not included.')
else:
    st.button('← Back to overview', key='v54_mc_back', on_click=_mc_back)
    v5.html_block(st,v5.versus_bar(_game,datetime.now(timezone.utc)))  # V5.5 versus hero (live countdown from the real start time)
    st.markdown(ui.section('Player targets by matchup','Both rosters · ranked by Form % · badges show which signals agree','🎯','team'),unsafe_allow_html=True)
    _gk_rows,_gk_err = goalies_cached((_game['away'],_game['home']),SEASON)
    _st_map,_st_err,_st_at = starters_cached(np_day, ((_game['key'],_game['game_id'],_game['away'],_game['home'],_game['status']),))
    _starters = _st_map.get(_game['key'], {})
    try:
        _mc_ranked = assign_statistical_ranks(np_ranked.copy()) if np_ready else None
    except (ValueError, KeyError, TypeError):
        _mc_ranked = None
    _pick_ids = [p.get('Player ID') for p in _mc_picks.values() if p]
    _targets = mc.matchup_targets(_home_targets, _game, _mc_ranked, _np_shared_discrepancies, _trk_badges, _pick_ids)
    _weak = mc.weaker_goalie_side(_gk_rows, _game)
    _order = [_weak] + [t for t in (_game['away'], _game['home']) if t != _weak] if _weak else [_game['away'], _game['home']]
    _cols = st.columns(2)
    for _col, _team in zip(_cols, _order):
        _opp = _game['home'] if _team == _game['away'] else _game['away']
        with _col:
            st.markdown(ui.team_head(_team, mc.TEAM_NAMES.get(_team, _team), f'Shooters facing {_opp} goaltending'),unsafe_allow_html=True)
            if _team == _weak:
                st.markdown('<span class="np-mc-side">▲ FACES THE LEAKIER GOALIE (BY GAA)</span>',unsafe_allow_html=True)
            _s = _starters.get(_opp)
            if _s and _s.get('status') in ('confirmed','probable'):
                st.markdown(ui.goalie_spotlight(_opp, pgk.match_stats(_s, _gk_rows), 'starter', _s, _s.get('fetched_at')),unsafe_allow_html=True)
            st.markdown(ui.goalie_spotlight(_opp, mc.leakiest_goalie(_gk_rows, _opp), 'leaky', starter_known=bool(_s and _s.get('status') in ('confirmed','probable'))),unsafe_allow_html=True)
            _list = _targets.get(_team, [])
            if _list:
                st.markdown(''.join(ui.target_card(i, p, _team, SEASON) for i, p in enumerate(_list, 1)),unsafe_allow_html=True)
            else:
                st.info('Player targets appear once this slate’s rankings load.' if not np_ready else 'No ranked players for this team.')
    # V5.6: Live Next Goal panel + this game's goalie threats / reverse view / H2H flags.
    _v56_r=_v56_by_key.get(_game['key'])
    if _v56_r is not None:
        v5.html_block(st,v56.nextgoal_panel(_v56_r['result'],SEASON,_v56_r['label'],v56_updated(_game['game_id']),note=_v56_r['note']+' Arrows: '+_v56_r['result'].get('rank_basis','')+'.',title='Live Next Goal'))
        _v56_h=v56_h2h_cached(((_game['away'],_game['home']),),np_day,SEASON).get((_game['away'],_game['home'])) or {}
        _v56_v=mcg.game_view(_game,_v56_r['result'],_v56_r['game'],_starters,_gk_rows,_v56_h,priors=_v56_priors)
        _v56_c=h2h.coverage_label(SEASON,games=_v56_h.get('games',0))
        st.markdown(ui.section('Goalies vs threats','Opposing shooters by next-goal % · real H2H '+_v56_c,'🧤','warn'),unsafe_allow_html=True)
        v5.html_block(st,v56.h2h_flag(_v56_v['flags'],f'{_game["away"]} @ {_game["home"]}')+'<div class="gtgrid">'
                      +''.join(v56.goalie_threats(_v56_v['goalies'][_t],_t,_v56_v['threats'][_t],SEASON,_v56_c) for _t in (_game['away'],_game['home']) if _v56_v['goalies'].get(_t))+'</div>'
                      +'<h4 class="np-rv-h">Reverse view · each shooter’s hardest goalie</h4>'+v56.reverse_view(_v56_v['reverse'],SEASON))
    st.caption('Starter status comes only from the feeds (NHL boxscore starter flag once a game begins; ESPN probables pregame), cached 5 min. '
               'The leakiest-goalie card is team season stats and is never labelled the starter. Badges: Stats = top-20 Form; Numbers = ≥2 symbolic matches; '
               'Overlap = both; Odds = validated price gap. None is a scoring probability.')
    if _gk_err or _st_err:
        with st.expander('Data warnings'):
            st.write(list(_gk_err) + list(_st_err))
st.markdown(ui.footer("NULL’S PLAYBOOK · MATCHUP CENTER"),unsafe_allow_html=True)
