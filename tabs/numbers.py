"""Null's Playbook V5.8 · numbers tab (V5.8 layout: numbers_v58_ui; values/logic unchanged). Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""
import html as _num_html
_day_num=num_universal_day(np_day)
st.markdown(v5.tab_head('NULL’S PLAYBOOK · NUMBERS','Numerology & Gematria','Daily numbers · team names · game arenas · player name roots',
    chips=[(f'Universal day {_day_num}','gem'),('D = day','day'),('T = team','team'),('A = arena','arena'),('Entertainment only','warn')],tone='gem'),unsafe_allow_html=True)
# V5.8: one hero (tab head), then "Tonight's numbers" (day number + ciphers, each with its plain meaning), then grouped controls.
st.caption('Symbolic patterns for entertainment only. These values do not predict scoring or betting outcomes.')
v5.html_block(st,numv58.reference_patterns_html(),extra_class='v58-num')  # Display-only reference; never a matching/scoring input.
import number_pattern_backtest_v60 as _num_audit
_num_audit.render(st)  # Saved historical summary only; no scoring/overlay inputs or runtime API fetch.
import daily_patterns_v60 as _num_dp
_num_daily,_num_daily_warn=_num_dp.load()  # registry data file; bad entries skipped with a visible warning
# t198: day picker (Mon–Sun of a week, default today ET) -> that day's pattern: saved registry entry if one exists, else auto-computed.
_num_today=_num_dp.today_et()
st.session_state.setdefault('v60_daily_anchor',_num_today); st.session_state.setdefault('v60_daily_sel',_num_today.isoformat())
@safe_callback   # V6.1: a failing control shows a toast, not an error page
def _num_goto(d):
    st.session_state['v60_daily_anchor']=d; st.session_state['v60_daily_sel']=d.isoformat()
    st.session_state.pop(_num_dp.picker_key(_num_dp.week_of(d)[0],'day'),None)
@safe_callback   # V6.1: a failing control shows a toast, not an error page
def _num_shift(n):
    import datetime as _ndt
    _num_goto(st.session_state['v60_daily_anchor']+_ndt.timedelta(days=7*n))
@safe_callback   # V6.1: a failing control shows a toast, not an error page
def _num_from_input():
    if st.session_state.get('v60_daily_date') is not None: _num_goto(st.session_state['v60_daily_date'])
_num_week=_num_dp.week_of(st.session_state['v60_daily_anchor'])
_num_isos=[d.isoformat() for d in _num_week]
_num_default=(_num_isos.index(st.session_state['v60_daily_sel']) if st.session_state['v60_daily_sel'] in _num_isos else
              _num_isos.index(_num_today.isoformat()) if _num_today.isoformat() in _num_isos else 0)
_num_pick=st.container(border=True)
with _num_pick:
    st.markdown(f'**Daily pattern** · week of {_num_week[0].strftime("%b")} {_num_week[0].day} – {_num_week[-1].strftime("%b")} {_num_week[-1].day}')
    _num_day=st.radio('Pattern day',_num_week,index=_num_default,format_func=lambda d:_num_dp.day_label(d)+(' · today' if d==_num_today else ''),
                      horizontal=True,label_visibility='collapsed',key=_num_dp.picker_key(_num_week[0],'day'))
    st.session_state['v60_daily_sel']=_num_day.isoformat()
    with st.expander('Other weeks or dates'):
        _num_n1,_num_n2,_num_n3=st.columns(3)
        _num_n1.button('‹ Prev week',on_click=_num_shift,args=(-1,),width='stretch',key='v60_daily_prev')
        _num_n2.button('This week',on_click=_num_goto,args=(_num_today,),width='stretch',key='v60_daily_now')
        _num_n3.button('Next week ›',on_click=_num_shift,args=(1,),width='stretch',key='v60_daily_next')
        st.date_input('Jump to date',value=None,key='v60_daily_date',on_change=_num_from_input,format='YYYY-MM-DD')
        st.caption('Saved entries (override the formula): '+(', '.join(e['date'] for e in _num_daily) or 'none'))
_num_entry=_num_dp.entry_for(_num_day,_num_daily)
v5.html_block(st,numv58.daily_patterns_html([_num_entry],_num_daily_warn),extra_class='v58-num')  # display only
try:
    _games_num=np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day)
except (requests.RequestException,ValueError,KeyError):
    _games_num=[]
    st.warning('Unable to retrieve the schedule for this date.')
_analyses=[num_analyze_game(g,np_day,_TEAM_NAMES) for g in _games_num]
_nb_ranked=st.session_state.get('signals_ranked')
_nb_ok=isinstance(_nb_ranked,pd.DataFrame) and st.session_state.get('signals_day')==np_day
import jersey_v61 as _num_jy
if _nb_ok:  # t201: render-time fallback for snapshots saved before the Jersey column (cached NHL roster map, by Player ID; never raises)
    _nb_ranked=_num_jy.fill_frame(_nb_ranked,lambda _t:v55_rosters_cached(_t)[0])
import lifepath_v61 as _num_lp
if _nb_ok:  # t209: same render-time fallback for birthdates (cached NHL roster feed + landing fallback, by Player ID; never raises)
    _nb_ranked=_num_lp.fill_frame(_nb_ranked,lambda _t,_p:v61_births_cached(_t,_p))
# Exclude anyone listed injured on the ESPN feed (silent; on fetch failure leave the frame as-is, log only).
# Applied once here so every Numbers ranking, filter, overlay and table built from _nb_ranked / _gm_targets omits them.
# Does not mutate session_state['signals_ranked'] or rewrite historical gematria logs.
import numbers_injury_v62 as _num_inj
if _nb_ok:
    _nb_ranked=_num_inj.apply(_nb_ranked)
_gm_targets=num_slate_targets(_analyses,_nb_ranked,np_day) if (_nb_ok and _analyses) else None
_nb_all=numboard.slate_boards(_gm_targets) if _gm_targets is not None else None
import pos_tag_v59 as _postag
_num_pmap=_postag.pos_map(_nb_ranked) if _nb_ok else None  # V5.9: real NHL positionCode from rankings -> compact tag after names (display only)
v5.html_block(st,numv58.tonight_strip(np_day,_day_num,_analyses,_nb_all),extra_class='v58-num')
# t209/t210/t212: Life Path layer. Independent, default-off overlay (By Game rows + match table) and an always-visible,
# read-only Life Path match table for the slate date's pattern (saved entry if present, else auto-computed).
_num_lp_entry=_num_dp.entry_for(np_day,_num_daily)
_num_lp_box=st.container(border=True)
with _num_lp_box:
    st.markdown('**Life Path overlay** · OFF by default; independent of the daily pattern filter')
    _num_lp_on=st.toggle(f'Show Life Path (birthdate numerology) vs {_num_lp_entry["label"]} ({_num_lp_entry["date"]}) · '
                         +', '.join(str(_n) for _n in _num_lp_entry['numbers']),value=False,key=_num_lp.toggle_key(np_day))
    _num_lp_applied=sorted(st.session_state.get(_num_dp.applied_key(np_day)) or ())
    _num_lp_sel=([_num_lp_entry]+[_num_dp.entry_for(_i,_num_daily) for _i in _num_lp_applied if _i!=_num_lp_entry['date']]) if _num_lp_on else None
    st.caption(_num_lp.CAPTION+' ON: By Game rows are filtered to Life Path matches (union with any applied daily pattern) and the '
               'Date & arena match rows show each player’s Life Path. Rankings, threat scores and badges are unchanged.')
    _num_lp_rows,_num_lp_n,_num_lp_miss=_num_lp.table_rows(_gm_targets,_num_lp_entry) if _gm_targets is not None else ([],0,0)
    _num_lp_fk=_num_lp.filter_key(np_day)
    _num_lp_fc,_num_lp_gc=st.columns([3,2],vertical_alignment='bottom')
    with _num_lp_gc:
        _num_lp_g=st.toggle(_num_lp.GROUP_LABEL,value=False,key=_num_lp.group_key(np_day))
    with _num_lp_fc:
        _num_lp_f=(st.segmented_control('Life Path matches',list(_num_lp.FILTERS),default='All',key=_num_lp_fk) if hasattr(st,'segmented_control')
                   else st.radio('Life Path matches',list(_num_lp.FILTERS),horizontal=True,key=_num_lp_fk)) or 'All'
    st.caption(_num_lp.FILTER_CAPTION)
    v5.html_block(st,(_num_lp.table_html(_num_lp_rows,_num_lp_entry,_num_lp_n,_num_lp_miss,loaded=_gm_targets is not None) if _num_lp_f=='All' and not _num_lp_g
                      else _num_lp.table_html(_num_lp.filter_rows(_num_lp_rows,_num_lp_entry,_num_lp_f),_num_lp_entry,_num_lp_n,_num_lp_miss,
                                              loaded=_gm_targets is not None,which=_num_lp_f,total=len(_num_lp_rows),group=_num_lp_g)),extra_class='v58-num')
if _analyses:  # V5.8: Player | Match type (date / arena) | Number
    if np_flags.show_gem_history(st.secrets):  # V5.9: saved-history strip (last 3 nights' arena-match scorers); hidden on any error
        try:
            v5.html_block(st,gemlog.strip_html(gemlog.last_n_days(3,'arena',np_day),pmap=_num_pmap),extra_class='v58-num')
        except Exception:
            pass
    v5.html_block(st,(gmx.table_html(*gmx.match_table(_gm_targets,_day_num),_day_num,loaded=_gm_targets is not None,pmap=_num_pmap,lifepath=_num_lp_sel)
                      if _num_lp_sel else gmx.table_html(*gmx.match_table(_gm_targets,_day_num),_day_num,loaded=_gm_targets is not None,pmap=_num_pmap)),extra_class='v58-num')
with st.expander('ⓘ How numbers are calculated'):
    st.write('Universal day: sum every digit of YYYY-MM-DD and reduce to one digit. English ordinal: A=1 through Z=26. Full reduction: reduce each letter to a single digit, sum, and reduce again. Reverse ordinal: A=26 through Z=1. Punctuation and spaces are ignored. Arena names come from the game schedule.')
if not _analyses:
    st.info('No scheduled NHL games found for the selected date.')
else:
    st.markdown(ui.stat_strip([('Games',len(_analyses),'odds'),('Teams',len({t for r in _analyses for t in (r['away'],r['home'])}),'team'),
        ('Arenas',f'{sum(bool(r["arena"]) for r in _analyses)}/{len(_analyses)}','arena'),('Day alignments',sum(len(r['matches']) for r in _analyses),'gem')]),unsafe_allow_html=True)
    # V5.6: 'By Game' (default) groups every ranked player under his game with a documented threat score (numboard_v56).
    _num_ctl=st.container(border=True)
    with _num_ctl:
        _num_view=st.radio('Explore',['By Game','Games','Player Targets','Team Numbers','Arena Numbers','Player Matches','Insights'],horizontal=True,key='v48_view')
        if _num_view=='By Game' and _nb_ok:
            _nb_c1,_nb_c2=st.columns(2)
            with _nb_c1: _nb_limit=st.selectbox('Players per game',[8,15,'All'],key='v56_nb_limit')
            with _nb_c2: _nb_sort=st.toggle('Sort games by threat count',value=False,key='v56_nb_sort')
    if _num_view=='By Game':
        if not _nb_ok:
            st.info('Load the slate snapshot to see players grouped by game.')
        else:
            _nb_boards=numboard.slate_boards(num_slate_targets(_analyses,_nb_ranked,np_day),None if _nb_limit=='All' else int(_nb_limit))
            if _nb_sort:
                _nb_boards=sorted(_nb_boards,key=lambda b:-b['badge'])
            _nb_mp=numv58.model_p_from_results(_v56_results)  # model P (pid -> p_anytime(lam_game)) for the TOP PICK tie-break only
            st.markdown('**Daily pattern filter** · OFF by default; pick a day above, then turn it on to show only matching current rows')
            _num_applied=st.session_state.setdefault(_num_dp.applied_key(np_day),set())  # per slate; survives switching picker days
            @safe_callback   # V6.1: a failing control shows a toast, not an error page
            def _num_apply(k,iso,ak):
                (st.session_state[ak].add if st.session_state.get(k) else st.session_state[ak].discard)(iso)
            _num_tk=_num_dp.toggle_key(np_day,_num_entry['date'])
            st.toggle(f'Apply {_num_entry["label"]} ({_num_entry["date"]}) · '+', '.join(str(_n) for _n in _num_entry['numbers']),
                      value=_num_entry['date'] in _num_applied,key=_num_tk,on_change=_num_apply,args=(_num_tk,_num_entry['date'],_num_dp.applied_key(np_day)))
            _num_sel=[_num_dp.entry_for(_iso,_num_daily) for _iso in sorted(_num_applied)]
            _num_overlay=bool(_num_sel)
            _num_others=[_e for _e in _num_sel if _e['date']!=_num_entry['date']]
            if _num_others:
                st.caption('Also applied (pick that day to turn it off): '+'; '.join(f'{_e["label"]} ({_e["date"]})' for _e in _num_others))
            st.caption(_num_dp.RULE+' Jersey matching is new and was not part of the historical backtest. Several ON = union (a row matching any selected pattern is shown, labelled with each match).')
            st.caption('By Game player rows only, after the existing per-game limit and top-pick pinning. '
                       'No replacement picks or reranking; threat badges and pick labels keep their baseline meaning. '
                       'Other views and the other listed reference patterns are unchanged.')
            if _num_lp_sel:   # t210: Life Path overlay on (union with any applied daily pattern)
                _num_base_count,_num_match_count=numv58.overlay_counts(_nb_boards,_nb_mp,patterns=_num_sel,lifepath=_num_lp_sel)
                st.caption(f'Overlay ON (Life Path{" + "+str(len(_num_sel))+" daily selected" if _num_sel else ""}) · Baseline: {_num_base_count} selections · '
                           f'Matching: {_num_match_count} · Shown: {_num_match_count}')
                _num_board_html=numv58.boards_html(_nb_boards,_day_num,_nb_mp,pmap=_num_pmap,overlay=_num_sel,lifepath=_num_lp_sel)
            else:
                _num_base_count,_num_match_count=numv58.overlay_counts(_nb_boards,_nb_mp,patterns=_num_sel)
                st.caption(f'Overlay {"ON ("+str(len(_num_sel))+" selected)" if _num_overlay else "OFF"} · Baseline: {_num_base_count} selections · '
                           f'Matching: {_num_match_count} · Shown: {_num_match_count if _num_overlay else _num_base_count}')
                _num_board_html=(numv58.boards_html(_nb_boards,_day_num,_nb_mp,pmap=_num_pmap,overlay=_num_sel) if _num_overlay else
                                 numv58.boards_html(_nb_boards,_day_num,_nb_mp,pmap=_num_pmap))
            v5.html_block(st,_num_board_html,extra_class='v58-num')
            st.caption('Threat score = min(100, round(100 × (3·D + 2·A + 1·T + 2·J) / 6)): D = day-number match, A = arena match, T = team match, '
                       'J = jersey match (raw sweater number is one of the slate date’s pattern numbers; new, additive only, not part of the historical backtest), each counted once (0 or 1). '
                       'The three ciphers are not independent: reduction always gives the same digit as English, and reverse mirrors English (the two always add up to 9), so each name has one number, and the day match uses the English digit only. '
                       'Tiers by raw points: 5–8 blaze · 3–4 hot · 2 warm · 1 mild · 0 cool. Eng = the full name’s English total before reducing, used to order equal scores. Arena glows when any player in the game matches it. Badge = players with a score above 0. '
                       'Same matches as Player Targets (unchanged); entertainment only, not a scoring probability.')
    elif _num_view=='Games':
        for r in _analyses:
            a,h=r['away_values'],r['home_values']
            away,home=_num_html.escape(r['away']),_num_html.escape(r['home'])
            venue=(f'<span class="np-vn" title="{_num_html.escape(vn.clean(r["arena"]))}">{vn.PIN} {_num_html.escape(vn.clean(r["arena"]))}</span>' if vn.clean(r['arena']) else '')   # V5.8: no arena -> no line
            venue_number=r['arena_values']['ordinal_root'] if r['arena_values'] else '—'
            matches=''.join(ui.badge(m,'gem') for m in r['matches'][:3]) or ui.badge('No direct day-number matches','muted')
            start=format_game_time(r['start'])
            st.markdown(f'<div class="np-num-match"><div class="np-num-top"><span>{start}</span>{venue}</div><div class="np-num-versus"><div>{ui.logo(away,52)}<b>{away}</b><small>ENG {a["ordinal_root"]} · RED {a["reduction_root"]} · REV {a["reverse_root"]}</small></div><div class="np-num-center"><strong>{_day_num}</strong><small>DAY</small><span>VS</span><strong class="np-num-green">{venue_number}</strong><small>ARENA</small></div><div>{ui.logo(home,52)}<b>{home}</b><small>ENG {h["ordinal_root"]} · RED {h["reduction_root"]} · REV {h["reverse_root"]}</small></div></div><div class="np-num-foot">{matches}</div></div>',unsafe_allow_html=True)
            with st.expander(f'View details · {away} @ {home}'):
                for label,name,v in [('Away team',r['away_name'],a),('Home team',r['home_name'],h),('Arena',r['arena'],r['arena_values'])]:
                    if v is None:
                        st.caption('Arena name unavailable from game schedule.')
                    else:
                        st.markdown(f'**{label}: {name}**')
                        st.caption(f'English ordinal {v["ordinal"]} → {v["ordinal_root"]} · Full reduction {v["reduction"]} → {v["reduction_root"]} · Reverse {v["reverse"]} → {v["reverse_root"]}')
    elif _num_view=='Player Targets':
        _ranked_targets=_nb_ranked if _nb_ok else None  # t201: same frame as By Game (jersey fallback applied)
        st.markdown(ui.section('Team player targets','Every matchup · both teams · numerical patterns','🎯','gem'),unsafe_allow_html=True)
        if _ranked_targets is None:
            st.info('Load the slate snapshot to see player targets for each team.')
        else:
            _mode=st.segmented_control('Player view',['Numbers','Statistics','Overlap'],default='Numbers',key='v50_mode')
            _c1,_c2=st.columns(2)
            with _c1: _limit=st.selectbox('Players per team',[3,5,10],key='v50_limit')
            with _c2: _only_matches=st.toggle('Matches only',value=False,key='v50_matches_only')
            _targets=num_slate_targets(_analyses,_ranked_targets,np_day)
            def _v50_sort(targets):
                candidates=[t for t in targets if t['matches']>0] if _only_matches else list(targets)
                if _mode=='Statistics':
                    candidates.sort(key=lambda t:(-t['form'],-t['matches'],t['player']))
                elif _mode=='Overlap':
                    candidates.sort(key=lambda t:(-int(t['matches']>0 and t['form']>0),-t['matches'],-t['form'],t['player']))
                return candidates
            def _v50_team(code,name,targets):
                ordered=_v50_sort(targets)
                st.markdown(ui.team_head(code,name,f'{len(ordered)} roster players shown in ranking'),unsafe_allow_html=True)
                for ix,t in enumerate(ordered[:_limit],1):
                    st.markdown(ui.target_row(ix,t['player'],code,t['player_id'],t['matches'],t['form'],len(t['day']),len(t['team_matches']),len(t['arena_matches']),season=SEASON,pos_tag=_postag.tag_for(_num_pmap,t['player_id'],code,t['player'])+_num_jy.tag(t)+_num_lp.tag(t)),unsafe_allow_html=True)
                    _wpc=_postag.lookup(_num_pmap,t['player_id'],code,t['player'])
                    with st.expander(f'Why {t["player"]}{" ("+_wpc+")" if _wpc else ""}? · {code}',expanded=False):
                        st.caption(f'Player full-name roots: English {t["values"]["ordinal_root"]}, reduction {t["values"]["reduction_root"]}, reverse {t["values"]["reverse_root"]} · Jersey {_num_jy.text(t.get("jersey"))} · Life Path {_num_lp.text(t.get("life_path"))}'+(f' (born {t["birth_date"]})' if t.get('birth_date') else '')+'.')
                        st.write(f'Jersey: {", ".join(t.get("jersey_hit") or []) or "no match"} (raw number vs the day’s pattern numbers; new, not backtested)')
                        st.write(f'Day {_day_num}: {", ".join(t["day"]) or "no match"}')
                        st.write(f'Team: {", ".join(t["team_matches"]) or "no match"}')
                        st.write(f'Arena: {", ".join(t["arena_matches"]) or "no match"}')
                        st.caption('Coincidence counts are not probabilities; Form % is a separate statistical signal.')
                if len(ordered)>_limit:
                    with st.expander(f'See {len(ordered)-_limit} more · {code}'):
                        for t in ordered[_limit:]:
                            _pc=_postag.lookup(_num_pmap,t['player_id'],code,t['player'])
                            st.write(f'{t["player"]} {_num_jy.text(t.get("jersey"))} · LP {_num_lp.text(t.get("life_path"))}{" ("+_pc+")" if _pc else ""} · {t["matches"]} matches · Form {ui.format_form_pct(t["form"])}')
            for item in _targets:
                r=item['game']; away,home=r['away'],r['home']
                st.markdown(ui.matchup_bar(away,home,format_game_time(r['start']),r['arena']),unsafe_allow_html=True)
                _away_col,_home_col=st.columns(2,gap='small')
                with _away_col: _v50_team(away,r['away_name'],item['away_targets'])
                with _home_col: _v50_team(home,r['home_name'],item['home_targets'])
                st.divider()
            with st.expander('What do D, T and A mean?'):
                st.write('D = Universal Day; T = team-name gematria; A = arena-name gematria. The number beside each letter is 1 when the player’s name number matches (each counted once: reduction always equals English and reverse mirrors English, so they are not separate matches; the day match uses the English digit only, a Reverse digit equal to the day does not count).')
                st.write('Numbers ranks symbolic coincidences. Statistics ranks the existing Form index (shown as Form %). Overlap brings players with both numerical matches and a positive statistical score to the top; it is not a calibrated goal probability.')
            st.caption('Recreational numerical patterns only. Not verified predictors of goals or betting outcomes.')
    elif _num_view=='Team Numbers':
        teams={r['away']:(r['away_name'],r['away_values']) for r in _analyses}
        teams.update({r['home']:(r['home_name'],r['home_values']) for r in _analyses})
        for code,(name,v) in sorted(teams.items()):
            st.markdown(ui.num_value_row(name,v,'team'),unsafe_allow_html=True)
    elif _num_view=='Arena Numbers':
        for r in _analyses:
            v=r['arena_values']
            if v:
                st.markdown(ui.num_value_row(r['arena'],v,'arena'),unsafe_allow_html=True)
            else:
                st.caption(f'{r["away"]} @ {r["home"]}: Arena unavailable')
    elif _num_view=='Player Matches':
        ranked=_nb_ranked if _nb_ok else None  # t201: jersey fallback applied
        if isinstance(ranked,pd.DataFrame) and not ranked.empty and st.session_state.get('signals_day')==np_day and 'Player' in ranked:
            matched=[]
            for _,player in ranked.iterrows():
                v=num_gematria(player.get('Player',''))
                methods=[k.replace('_root','').replace('_',' ') for k in ('ordinal_root','reduction_root') if v[k]==_day_num]  # English only (== reduction); Reverse never counts for the day
                if methods:
                    matched.append({'Player':player['Player'],'Jersey':_num_jy.text(player.get('Jersey')),'Life Path':_num_lp.text(_num_lp.chain(player.get(_num_lp.COLUMN))),'Pos':_postag.code(player.get('Position')) or '','Team':player.get('Team',''),'Matching methods':', '.join(methods)})
            st.dataframe(pd.DataFrame(matched,columns=['Player','Jersey','Life Path','Pos','Team','Matching methods']),hide_index=True,use_container_width=True)
            st.caption('Number matches only, not goal-scoring recommendations.')
        else:
            st.info('Player names will appear after rankings for this date are loaded.')
    else:
        st.metric('Day-number alignments',sum(len(r['matches']) for r in _analyses))
        st.write('Alignments count exact digit-root matches across team and arena names. A higher count does not imply a better scoring chance.')
# V5.9: Position gematria curiosity layer (self-contained, collapsed; computed at render time; feeds no score, rank, tier, TOP PICK or match table).
import position_gematria_v59 as _posgem
with st.expander('Position gematria · curiosity layer'):
    v5.html_block(st,_posgem.table_html(),extra_class='v58-num')
# V5.9: All-layer matches (curiosity layer, collapsed; display only — day + position label + arena + a Reverse and an English hit, all at once).
import all_layers_v59 as _alllay, scorers_tonight_v58 as _al_sc
with st.expander('All-layer matches · curiosity layer'):
    _al_rec=_al_sc.active(st.session_state,np_day)
    _al_full,_al_close=_alllay.rows(_gm_targets,_day_num,_num_pmap,_al_rec,numv58.model_p_from_results(_v56_results)) if _gm_targets is not None else ([],[])
    v5.html_block(st,_alllay.table_html(_al_full,_al_close,_day_num,loaded=_gm_targets is not None,demo=bool((_al_rec or {}).get('demo'))),extra_class='v58-num')
# V5.9: Position + gematria layers (curiosity layer, collapsed; display only — reuses tonight's targets and the scorers record; feeds nothing back).
import position_layers_v59 as _poslay, scorers_tonight_v58 as _pl_sc
with st.expander('Position + gematria layers · curiosity layer'):
    _pl_rec=_pl_sc.active(st.session_state,np_day)
    _pl_rows,_pl_none=_poslay.rows(_gm_targets,_day_num,_num_pmap,_pl_rec,numv58.model_p_from_results(_v56_results)) if _gm_targets is not None else ([],0)
    v5.html_block(st,_poslay.table_html(_pl_rows,_pl_none,_day_num,loaded=_gm_targets is not None,demo=bool((_pl_rec or {}).get('demo'))),extra_class='v58-num')
