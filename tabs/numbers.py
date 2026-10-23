"""Null's Playbook V5.8 · numbers tab (V5.8 layout: numbers_v58_ui; values/logic unchanged). Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""
import html as _num_html
_day_num=num_universal_day(np_day)
st.markdown(v5.tab_head('NULL’S PLAYBOOK · NUMBERS','Numerology & Gematria','Daily numbers · team names · game arenas · player name roots',
    chips=[(f'Universal day {_day_num}','gem'),('D = day','day'),('T = team','team'),('A = arena','arena'),('Entertainment only','warn')],tone='gem'),unsafe_allow_html=True)
# V5.8: one hero (tab head), then "Tonight's numbers" (day number + ciphers, each with its plain meaning), then grouped controls.
st.caption('Symbolic patterns for entertainment only. These values do not predict scoring or betting outcomes.')
try:
    _games_num=np_snapshot['games'] if np_snapshot is not None else schedule_cached(np_day)
except (requests.RequestException,ValueError,KeyError):
    _games_num=[]
    st.warning('Unable to retrieve the schedule for this date.')
_analyses=[num_analyze_game(g,np_day,_TEAM_NAMES) for g in _games_num]
_nb_ranked=st.session_state.get('signals_ranked')
_nb_ok=isinstance(_nb_ranked,pd.DataFrame) and st.session_state.get('signals_day')==np_day
_nb_all=numboard.slate_boards(num_slate_targets(_analyses,_nb_ranked,np_day)) if (_nb_ok and _analyses) else None
v5.html_block(st,numv58.tonight_strip(np_day,_day_num,_analyses,_nb_all),extra_class='v58-num')
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
            _nb_mp={str(_r.get('pid')):ng.p_anytime(_r.get('lam_game',0)) for _r in (_v56_rows or [])}  # model P for the TOP PICK tie-break
            v5.html_block(st,numv58.boards_html(_nb_boards,_day_num,_nb_mp),extra_class='v58-num')
            st.caption('Threat score = round(100 × (3·D + 2·A + 1·T) / 18): D = day-number matches, A = arena matches, T = team matches, each 0–3 methods (English, reduction, reverse). '
                       'Tiers by raw points: ≥6 blaze · 4–5 hot · 2–3 warm · 1 mild · 0 cool. Arena glows when any player in the game matches it. Badge = players with a score above 0. '
                       'Same matches as Player Targets (unchanged); entertainment only, not a scoring probability.')
    elif _num_view=='Games':
        for r in _analyses:
            a,h=r['away_values'],r['home_values']
            away,home=_num_html.escape(r['away']),_num_html.escape(r['home'])
            venue=_num_html.escape(r['arena'] or 'Arena unavailable')
            venue_number=r['arena_values']['ordinal_root'] if r['arena_values'] else '—'
            matches=''.join(ui.badge(m,'gem') for m in r['matches'][:3]) or ui.badge('No direct day-number matches','muted')
            start=format_game_time(r['start'])
            st.markdown(f'<div class="np-num-match"><div class="np-num-top"><span>{start}</span><span>{venue}</span></div><div class="np-num-versus"><div>{ui.logo(away,52)}<b>{away}</b><small>ENG {a["ordinal_root"]} · RED {a["reduction_root"]} · REV {a["reverse_root"]}</small></div><div class="np-num-center"><strong>{_day_num}</strong><small>DAY</small><span>VS</span><strong class="np-num-green">{venue_number}</strong><small>ARENA</small></div><div>{ui.logo(home,52)}<b>{home}</b><small>ENG {h["ordinal_root"]} · RED {h["reduction_root"]} · REV {h["reverse_root"]}</small></div></div><div class="np-num-foot">{matches}</div></div>',unsafe_allow_html=True)
            with st.expander(f'View details · {away} @ {home}'):
                for label,name,v in [('Away team',r['away_name'],a),('Home team',r['home_name'],h),('Arena',r['arena'],r['arena_values'])]:
                    if v is None:
                        st.caption('Arena name unavailable from game schedule.')
                    else:
                        st.markdown(f'**{label}: {name}**')
                        st.caption(f'English ordinal {v["ordinal"]} → {v["ordinal_root"]} · Full reduction {v["reduction"]} → {v["reduction_root"]} · Reverse {v["reverse"]} → {v["reverse_root"]}')
    elif _num_view=='Player Targets':
        _ranked_targets=st.session_state.get('signals_ranked')
        if not (isinstance(_ranked_targets,pd.DataFrame) and st.session_state.get('signals_day')==np_day):
            _ranked_targets=None
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
                    st.markdown(ui.target_row(ix,t['player'],code,t['player_id'],t['matches'],t['form'],len(t['day']),len(t['team_matches']),len(t['arena_matches']),season=SEASON),unsafe_allow_html=True)
                    with st.expander(f'Why {t["player"]}? · {code}',expanded=False):
                        st.caption(f'Player full-name roots: English {t["values"]["ordinal_root"]}, reduction {t["values"]["reduction_root"]}, reverse {t["values"]["reverse_root"]}.')
                        st.write(f'Day {_day_num}: {", ".join(t["day"]) or "no match"}')
                        st.write(f'Team: {", ".join(t["team_matches"]) or "no match"}')
                        st.write(f'Arena: {", ".join(t["arena_matches"]) or "no match"}')
                        st.caption('Coincidence counts are not probabilities; Form % is a separate statistical signal.')
                if len(ordered)>_limit:
                    with st.expander(f'See {len(ordered)-_limit} more · {code}'):
                        for t in ordered[_limit:]:
                            st.write(f'{t["player"]} · {t["matches"]} matches · Form {ui.format_form_pct(t["form"])}')
            for item in _targets:
                r=item['game']; away,home=r['away'],r['home']
                venue=_num_html.escape(r['arena'] or 'Venue unavailable')
                st.markdown(ui.matchup_bar(away,home,format_game_time(r['start']),r['arena']),unsafe_allow_html=True)
                _away_col,_home_col=st.columns(2,gap='small')
                with _away_col: _v50_team(away,r['away_name'],item['away_targets'])
                with _home_col: _v50_team(home,r['home_name'],item['home_targets'])
                st.divider()
            with st.expander('What do D, T and A mean?'):
                st.write('D = Universal Day; T = team-name gematria; A = arena-name gematria. The number beside each letter counts matching methods (English ordinal, reduction, reverse).')
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
        ranked=st.session_state.get('signals_ranked')
        if isinstance(ranked,pd.DataFrame) and not ranked.empty and st.session_state.get('signals_day')==np_day and 'Player' in ranked:
            matched=[]
            for _,player in ranked.iterrows():
                v=num_gematria(player.get('Player',''))
                methods=[k.replace('_root','').replace('_',' ') for k in ('ordinal_root','reduction_root','reverse_root') if v[k]==_day_num]
                if methods:
                    matched.append({'Player':player['Player'],'Team':player.get('Team',''),'Matching methods':', '.join(methods)})
            st.dataframe(pd.DataFrame(matched,columns=['Player','Team','Matching methods']),hide_index=True,use_container_width=True)
            st.caption('Number matches only, not goal-scoring recommendations.')
        else:
            st.info('Player names will appear after rankings for this date are loaded.')
    else:
        st.metric('Day-number alignments',sum(len(r['matches']) for r in _analyses))
        st.write('Alignments count exact digit-root matches across team and arena names. A higher count does not imply a better scoring chance.')
