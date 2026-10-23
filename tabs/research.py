"""Null's Playbook V5.6 · research tab. Executed by tabs.run_tab() inside the app's namespace (split from app.py, unchanged logic)."""
storyline_top = st.container()
with storyline_top:
    st.markdown(v5.tab_head('NULL’S PLAYBOOK · RESEARCH','Research','Four distinct leaders · evidence-first, pre-slate storylines. Former-team and injury/news claims are not inferred.',
        chips=[(f'📅 {np_day}','muted'),('Not calibrated probabilities','warn')],tone='stat'),unsafe_allow_html=True)
    if st.session_state.get('v531_history_error'):
        st.warning(f"History unavailable: {st.session_state['v531_history_error']}")
    _v531_job=st.session_state.get('v43_history_job')
    if _v531_job and _v531_job.get('day')==np_day and not _v531_job['future'].done():
        st.caption('⏳ Three-season opponent history is updating separately. Rankings remain usable.')
# V5.8: everything rendered below 'Top 10 Statistical Sleepers' is display-gated by FEATURE_RESEARCH_EXTRAS
# (feature_flags_v58, default off). Computations that feed Home/other tabs (rankings, intel, history job) still run.
_rx = np_flags.show_research_extras(st.secrets)
day = np_day
if _rx:
    st.caption('Scheduled 30-minute snapshots when available · live fallback for unsaved dates · three prior seasons · not calibrated probabilities')
    # V5.6: the 'Goalies: Goals Allowed' section moved to Matchup Center (same helpers, now next to tonight's threats and H2H).
    st.caption('🥅 Goalies: Goals Allowed now lives in 🎯 Matchup Center, next to each goalie’s opposing threats and real H2H history.')

    if st.button('↻ Refresh now', key='v42_manual_refresh'):
        schedule_cached.clear()
        team_cached.clear()
        defense_cached.clear()
        historical_cached.clear()
        st.session_state.pop('v42_last_rank', None)
        st.info('A saved snapshot is active when available. To force a fresh complete slate, run the GitHub Actions workflow.')
        st.session_state.pop('v42_history_attempt', None)
        st.session_state.pop('v43_history_completed', None)
        st.rerun()

try:
    games = np_snapshot['games'] if np_snapshot is not None else schedule_cached(day)
    if _rx:
        st.caption(f'Data updated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC')

        st.subheader('Full NHL Slate')
        if games:
            st.markdown('#### 🏒 Matchup Center')
            # Official NHL team logos; a broken image does not affect data retrieval.
            import html as _html
            for offset in range(0,min(len(games),12),3):
                cols=st.columns(min(3,len(games)-offset))
                for col,game in zip(cols,games[offset:offset+3]):
                    away=_html.escape(str(game.get('Away','')))
                    home=_html.escape(str(game.get('Home','')))
                    with col:
                        st.markdown(f'''<div class="np-player" style="min-height:100px;text-align:center"><div class="np-muted">{_html.escape(format_game_time(game.get('Start (UTC)')))}</div><div style="display:flex;justify-content:center;align-items:center;gap:13px;margin-top:9px"><img alt="{away}" src="https://assets.nhle.com/logos/nhl/svg/{away}_light.svg" style="height:38px;width:38px;object-fit:contain"/><b>{away} vs {home}</b><img alt="{home}" src="https://assets.nhle.com/logos/nhl/svg/{home}_light.svg" style="height:38px;width:38px;object-fit:contain"/></div>{ui.arena_line(game.get('Venue'))}</div>''',unsafe_allow_html=True)
            with st.expander('Full NHL slate data'):
                st.dataframe(pd.DataFrame(games), hide_index=True, use_container_width=True)
            st.metric('Slate Games', len(games))
        else:
            st.info('No games found for this date.')
except (requests.RequestException, ValueError, KeyError) as exc:
    if _rx:
        st.error(f'Schedule request failed: {exc}')
    games = []

if _rx:
    st.divider()
    st.subheader('Player Statistics Explorer')
    st.caption('Only regular-season game-log entries dated before the selected slate date are counted. '
               'This prevents date leakage but does not independently verify game completion or historical roster membership.')
    if games:
        teams = sorted({g[t] for g in games for t in ('Home','Away') if g.get(t)})
        team = st.selectbox('Team on slate', teams)
        if st.button('Load Player Statistics'):
            try:
                with st.spinner('Loading NHL player game logs...'):
                    rows, errors = team_cached(team, day)
                if rows:
                    st.dataframe(pd.DataFrame(rows).drop(columns=['id']), hide_index=True, use_container_width=True)
                    st.caption(f'Roster and player statistics · Season {SEASON}')
                    flagged = sum(r['Data status'] == 'Needs review' for r in rows)
                    missing = sum(r['GP'] == 0 for r in rows)
                    c1, c2, c3 = st.columns(3)
                    c1.metric('Players loaded', len(rows))
                    c2.metric('Flagged records', flagged)
                    c3.metric('No prior games', missing)
                    if flagged or errors:
                        st.warning('Incomplete or questionable records detected. Do not use for prediction backtests.')
                    st.caption('Historical roster caveat: the current roster endpoint may include players '
                               'who were not on this team on the selected date. Historical membership is not verified.')
                else:
                    st.warning('No player game logs returned.')
                if errors:
                    st.warning(f'{len(errors)} players could not be loaded; incomplete coverage.')
                    with st.expander('Request errors'):
                        st.write(errors)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                st.error(f'Player data request failed: {exc}')
    else:
        st.info('Choose a date with games to explore player statistics.')
if _rx:
    st.divider()
    st.subheader('V3.2 Goal-Scorer Rankings')
    st.caption('Goal-scoring Form % is a relative index (share of the 100-point benchmark, clipped at 100%), NOT a scoring probability. Opponent goals/shots allowed '
               'adjust the Form index (shown as Form %) by at most 15% where coverage is sufficient. '
               'Form % has no goalie adjustment. "Starting goalie" is the opponent starter from the same probable-starter source as Matchup Center '
               '(Unconfirmed only when no source lists one); "Goalie adjustment" is the next-goal model\'s SV% step for that starter.')
if games:
    min_games = st.slider('Minimum prior games per player', 1, 10, 3) if _rx else 3
    use_defense = st.checkbox('Apply opponent defense adjustment', value=True) if _rx else True
    # Auto-run on first open, selected-date change, or after the 30-minute interval.
    # Never silently replace an older pregame snapshot with a current-time reconstruction.
    _v42_key=(day,int(min_games),bool(use_defense))
    _v42_last=st.session_state.get('v42_last_rank')
    _v42_due=(np_snapshot is None and (not _v42_last or _v42_last.get('key')!=_v42_key
              or datetime.now(timezone.utc)-_v42_last['at']>=timedelta(minutes=30)
              or st.session_state.get('signals_day')!=day))
    if games and _v42_due:
        if _rx: st.info('⏳ Auto-analyzing all teams for the selected date…')
        teams_to_load = sorted({g[t] for g in games for t in ('Home', 'Away') if g.get(t)})
        all_rows, all_errors = [], []
        progress = st.progress(0, text='Loading all teams') if _rx else None
        # Fetch independent team rosters concurrently instead of serially.
        # Keep worker count modest to avoid overwhelming the NHL endpoints.
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs={pool.submit(team_cached, code, day):code for code in teams_to_load}
            for i, job in enumerate(as_completed(jobs), start=1):
                team_code=jobs[job]
                try:
                    team_rows, team_errors=job.result()
                    all_rows.extend(team_rows)
                    all_errors.extend([f'{team_code}: {e}' for e in team_errors])
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    all_errors.append(f'{team_code}: {exc}')
                if progress is not None: progress.progress(i/len(teams_to_load),text=f'Loaded {i}/{len(teams_to_load)} teams')
        ranked = rank_players(all_rows, min_games)
        defensive, defense_errors = {}, []
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs={pool.submit(defense_cached, code, day):code for code in teams_to_load}
            for job in as_completed(jobs):
                team_code=jobs[job]
                try:
                    defensive[team_code]=job.result()
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    defense_errors.append(f'{team_code}: {exc}')
        ranked = assign_statistical_ranks(attach_matchups(ranked, games, defensive, adjust=use_defense)).to_dict('records')
        ranked = np_goalie_columns(pd.DataFrame(ranked), day, games).to_dict('records') if ranked else ranked  # V5.8: shared starter source
        coverage = pd.DataFrame([
            {k:v for k,v in d.items() if k != 'Error details'}
            for d in defensive.values()
        ])
        if _rx:
            st.metric('Teams requested', len(teams_to_load))
            st.metric('Players eligible for form ranking', len(ranked))
            st.metric('Opponent defenses retrieved', len(defensive))
            st.caption('Defensive rates are goals/shots allowed per completed game, using up to 10 '
                       'games before the slate date. Goalies are NOT confirmed.')
            if not coverage.empty:
                with st.expander('Defensive data coverage and audit'):
                    st.dataframe(coverage, hide_index=True, use_container_width=True)
            if defense_errors:
                st.warning(f'{len(defense_errors)} defensive team requests failed.')
                with st.expander('Defensive request errors'):
                    st.write(defense_errors)
            partial = [d['Opponent'] for d in defensive.values()
                       if d['Games verified'] < d['Games found']]
            if partial:
                st.warning(f'Incomplete defensive boxscore coverage: {", ".join(partial)}')
            if not defensive:
                st.warning('No opponent defensive context available. Form rankings are unadjusted.')
        if ranked:
            st.session_state['signals_ranked'] = pd.DataFrame(ranked)
            st.session_state['signals_day'] = day
            st.session_state['v42_last_rank']={'key':_v42_key,'at':datetime.now(timezone.utc)}
            st.session_state['v42_needs_home_refresh']=True
            if _rx:
                try:
                    snapshot = make_snapshot(ranked, games, day)
                    st.download_button('Save PRE-GAME snapshot CSV (keep this file)',
                                       snapshot.to_csv(index=False),
                                       file_name=f'null-pregame-{day}.csv', mime='text/csv')
                    st.caption('Snapshot is saved to YOUR device only. Download before the first puck drop. '
                               'A later download cannot recreate a genuine pregame prediction.')
                except (KeyError, ValueError, TypeError) as exc:
                    st.info(f'Pregame snapshot unavailable: {exc}')
                st.dataframe(ui.with_form_pct(pd.DataFrame(ranked)), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
                st.download_button('Download rankings CSV', ui.with_form_pct(pd.DataFrame(ranked)).to_csv(index=False),
                                   file_name=f'null-nhl-v3-2-{day}.csv', mime='text/csv')
                st.caption('Statistical sleepers (NOT verified betting longshots): players outside the top 20 '
                           'with at least 2 shots per game over the last 5 games.')
                watch = [r for r in ranked[20:] if r['Shots/G L5'] >= 2]
                if watch:
                    st.dataframe(ui.with_form_pct(pd.DataFrame(watch[:20])), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
                else:
                    st.info('No players met the longshot-watchlist rule.')
        elif _rx:
            st.warning('No eligible players found.')
        if _rx:
            if all_errors:
                st.warning(f'{len(all_errors)} player/team requests failed; ranking coverage is incomplete.')
                with st.expander('Missing-data details'):
                    st.write(all_errors)
            st.warning('Current roster membership is not historical lineup verification. '
                       'Do not use this ranking as a historical pregame prediction or calibrated probability.')
elif _rx:
    st.info('Select a date with games to calculate full-slate form rankings.')
if _rx:
    st.divider()
    st.subheader('V3.3 Historical Backtesting')
    st.caption('Upload a CSV saved before the first game started. The app does not persist snapshots. '
               'This evaluates eligible roster-based predictions, not historically verified lineups.')
    uploaded = st.file_uploader('Upload a pregame snapshot CSV', type=['csv'])
    if uploaded is not None:
        try:
            saved = pd.read_csv(uploaded)
            st.caption(f'Loaded {len(saved)} snapshot rows. Outcomes require completed NHL boxscores.')
            if st.button('Score snapshot against final NHL boxscores'):
                with st.spinner('Checking final boxscores...'):
                    scored, failures = score_snapshot(saved)
                if failures:
                    st.warning('Some games could not be verified. Incomplete results are excluded from metrics.')
                    with st.expander('Boxscore errors'):
                        st.write(failures)
                if not scored.empty:
                    st.dataframe(top_k_metrics(scored), hide_index=True, use_container_width=True)
                    st.dataframe(ui.with_form_pct(scored), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
                    st.download_button('Download scored snapshot CSV', ui.with_form_pct(scored).to_csv(index=False),
                                       file_name='null-scored-snapshot.csv', mime='text/csv')
                    st.caption('Top-K hit rate = players scoring at least one goal / K; not betting ROI, '
                               'calibration, or proof of predictive improvement.')
                else:
                    st.warning('No completed, verifiable games were available.')
        except (ValueError, KeyError, TypeError, pd.errors.ParserError) as exc:
            st.error(f'Snapshot could not be processed: {exc}')
    st.divider()
    st.subheader('V3.5 Auto Storyline, Numerology & Gematria')
    st.caption('Exploratory patterns only. NOT goal probabilities, predictive evidence, or betting edges. '
               'This section does not change the statistical rankings or backtests.')
    st.write(f'Universal day (YYYYMMDD digit reduction): **{universal_day(day)}**')
    st.caption('Name Pythagorean: A=1 through I=9, repeating. English ordinal: A=1 through Z=26. '
               'All totals reduce to 1–9 without master-number exceptions. ASCII letters only.')
    st.caption('Optional metadata CSV columns: Player ID, Jersey, Birth date (YYYY-MM-DD), Arena, '
               'Verified storyline, Source URL. Only sourced storyline text is displayed. '
               'Names, arena spellings, and birthdays require independent verification.')
    st.caption('NHL player profiles supply birthdays and current jersey numbers; arenas come from schedules. Historical team membership, news, injuries, former-team matches and milestones remain unverified.')
    auto_limit = st.select_slider('NHL profiles to fetch (top-ranked players)', options=[10, 25, 50, 100, 250, 500], value=500)
    if st.button('Fetch NHL player biographies and arenas'):
        if 'signals_ranked' not in st.session_state or st.session_state.get('signals_day') != day:
            st.warning('Run Rank Entire Slate first.')
        else:
            with st.spinner('Retrieving source-linked NHL profiles...'):
                data, errors = fetch_metadata(st.session_state['signals_ranked'].to_dict('records'), day, games, max_players=auto_limit)
            prior = st.session_state.get('auto_signal_metadata', pd.DataFrame()) if st.session_state.get('auto_signal_day') == day else pd.DataFrame()
            st.session_state['auto_signal_metadata'] = merge_profile_batches(prior, pd.DataFrame(data))
            st.session_state['auto_signal_day'] = day
            st.success(f'Fetched {len(data)} profiles; {len(errors)} unavailable.')
            if errors:
                with st.expander('Profile retrieval errors'):
                    st.write(errors)
    st.subheader('V3.8 Opponent History & Season Milestone Evidence')
    st.caption('Fetch pre-slate regular-season NHL game logs. Opponent flags require at least 2 prior meetings and 2 goals; season milestones mean one goal from 10, 20, 30, etc. Not career milestones.')
    history_limit = st.select_slider('Players for opponent history (top ranked)', options=[10, 25, 50, 100, 250, 500], value=50, key='history_limit')
    if st.button('Fetch opponent history and milestone evidence'):
        if 'signals_ranked' not in st.session_state or st.session_state.get('signals_day') != day:
            st.warning('Rank Entire Slate first.')
        else:
            with st.spinner('Fetching pre-slate NHL game logs...'):
                history_data, history_errors = fetch_history(st.session_state['signals_ranked'].to_dict('records'), games, day, max_players=history_limit)
            prior_history = st.session_state.get('history_v38', pd.DataFrame()) if st.session_state.get('history_v38_day') == day else pd.DataFrame()
            st.session_state['history_v38'] = merge_profile_batches(prior_history, history_data)
            st.session_state['history_v38_day'] = day
            st.success(f'History retrieved for {len(history_data)} players; {len(history_errors)} unavailable.')
            if history_errors:
                with st.expander('History fetch errors'):
                    st.write(history_errors)
    meta_file = st.file_uploader('Optional additional sourced storyline metadata CSV', type=['csv'], key='signal_meta')
else:
    meta_file = None
# V5.4: one shared pipeline (player_intelligence_v54) feeds Research and the Home featured row.
_intel, _intel_warnings = intel_from_state(st.session_state, day)
if _rx:
    for _w in _intel_warnings:
        st.warning(_w)
if _intel is not None:
    signals = _intel['signals']
    if _rx:
        st.caption(f'{len(signals)} players evaluated. Pattern overlap counts are descriptive, '
                   'not confidence scores. Missing biographical data remains unavailable.')
        st.dataframe(ui.with_form_pct(signals), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
    storylines = _intel['storylines']
    combined = _intel['combined']
    top_stories, storyline_sleepers, featured = _intel['top_stories'], _intel['storyline_sleepers'], _intel['featured']
    v387 = _intel['v387']
    with storyline_top:
        coverage_stats = historical_coverage(combined)
        st.markdown('#### 📋 Historical Data Coverage')
        st.progress(coverage_stats['fraction'])
        cov1, cov2, cov3 = st.columns(3)
        cov1.metric('Complete histories', f"{coverage_stats['complete']}/{coverage_stats['total']}")
        cov2.metric('Partial / unavailable', coverage_stats['partial'])
        cov3.metric('Not fetched', coverage_stats['not_fetched'])
        st.caption(f"{coverage_stats['percent']:.1f}% of ranked players have complete requested-season history. Only complete records count toward historical storyline evidence; incomplete coverage may change the leaders.")
        st.caption('Statistical form, sourced storyline strength, top-20 overlap and descriptive sleeper are separate rankings. None is a calibrated scoring probability.')
        st.markdown('### Player Intelligence')
        st.caption('Four independent leaders · statistical form and historical storylines are not scoring probabilities')
        labels = INTEL_LABELS
        for key,label in labels:
            lead=v387['leaders'][key]
            if lead is None:
                st.info(f'{label}: insufficient data for this date')
                continue
            import html
            pid=lead.get('Player ID')
            pid=str(int(pid)) if pd.notna(pid) and str(pid).replace('.0','').isdigit() else ''
            team=html.escape(str(lead.get('Team','')))
            name=html.escape(str(lead.get('Player','')))
            rank=int(lead['Statistical rank'])
            form=float(lead['V3.2 Adjusted Index'])
            shots=float(lead['Shots/G L5'])
            flags=int(lead['Storyline count'])
            evidence=float(lead['Storyline evidence score'])
            history_ok=lead.get('Historical coverage')=='Complete, >=3 meetings'
            gp=int(lead['Historical opponent GP']) if history_ok else 0
            goals=int(lead['Historical opponent goals']) if history_ok else 0
            photo=f'<img class="np-research-photo" src="https://assets.nhle.com/mugs/nhl/{SEASON}/{team}/{pid}.png" alt="Player portrait" loading="lazy"/>' if pid else '<div class="np-research-placeholder">🏒</div>'
            history_text=f'{goals} goals in {gp} previous meetings' if history_ok else 'Opponent history unavailable or insufficient'
            st.markdown(f"""<div class="np-research-card"><div class="np-research-eyebrow">{label}</div><div class="np-research-row">{photo}<div class="np-research-person"><div class="np-research-name">{name}</div><div class="np-research-team">{team} · Statistical rank #{rank}</div><div class="np-research-form">{ui.format_form_pct(form)} <small>GOAL-SCORING FORM %</small></div></div></div><div class="np-research-stats"><div><b>{shots:.1f}</b><small>Shots/game · L5</small></div><div><b>{goals if history_ok else '—'}</b><small>Opponent goals</small></div><div><b>{flags}</b><small>Storyline flags</small></div></div><div class="np-research-note">{history_text} · {evidence:.1f} storyline points</div></div>""",unsafe_allow_html=True)
            with st.expander(f'Detailed analysis · {lead.get("Player", "Player")}',expanded=False):
                st.caption(f'Statistical rank #{rank} · Goal-scoring Form {ui.format_form_pct(form)} ({form:.1f} pts) · Storyline evidence {evidence:.2f}')
                st.write('**Evidence:**',lead.get('Verified data flags','Not available'))
                st.caption('Historical opponent data: '+str(lead.get('Historical coverage','Unavailable')))
                st.caption('Form % is a relative statistical index (share of the 100-point benchmark), not a goal probability. Storyline evidence is a separate heuristic.')
        st.caption('Storyline evidence points are an explicitly heuristic display index: 2 per historical goal (max 10), 6 × historical goals/game (max 1.5), historical shots/10 (max 50 shots), plus 1.5 per sourced flag (max 5). Historical components require complete requested seasons and ≥3 meetings. They are NOT validated predictive weights.')
        for key,title in [('statistical','Top 10 Statistical'),('storyline','Top 10 Storylines'),('overlap','Top 10 Overlap'),('longshots','Top 10 Statistical Sleepers')]:
            st.subheader(title)
            frame=v387[key]
            if frame.empty: st.info('No eligible players in currently loaded data.')
            else:
                cols=['Player','Team','Statistical rank','Storyline rank','Storyline evidence score','Storyline count','Historical opponent GP','Historical opponent goals','Historical opponent shots','Shots/G L5','Verified data flags']
                _t10=ui.with_form_pct(frame[[c for c in cols+['Player ID'] if c in frame]])  # V5.9: scored-tonight badge by id
                st.dataframe(sctn.mark_frame_by_id(_t10,sctn.active(st.session_state,day),'Player ID'),hide_index=True,use_container_width=True,column_config=ui.form_pct_config(st))
                st.download_button('Download '+title+' CSV',ui.with_form_pct(frame).to_csv(index=False),file_name=f'null-v387-{key}-{day}.csv',mime='text/csv',key=f'v387_{key}')
    if _rx:
        st.download_button('Download top 10 storyline watchlist CSV', ui.with_form_pct(top_stories).to_csv(index=False), file_name=f'null-v381-top10-{day}.csv', mime='text/csv')
        st.subheader('V3.8.2 Data Integrity Audit')
        audit = coverage_audit(combined, st.session_state.get('auto_signal_metadata') if st.session_state.get('auto_signal_day') == day else None,
                               st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None)
        st.dataframe(pd.DataFrame([audit]), hide_index=True, use_container_width=True)
        if audit['Histories fetched'] < audit['Eligible players']:
            st.info('Opponent-history coverage is partial; zero flags on unfetched players do not mean no storyline.')
        st.download_button('Download ALL evaluated players + storyline evidence CSV', ui.with_form_pct(combined).to_csv(index=False),
                           file_name=f'null-v381-full-storylines-{day}.csv', mime='text/csv')
        st.download_button('Download data coverage audit CSV', pd.DataFrame([audit]).to_csv(index=False),
                           file_name=f'null-v381-audit-{day}.csv', mime='text/csv')
        st.subheader('V3.8.2 Opponent, Milestone & Birthday Diagnostics')
        st.caption('These checks distinguish no detected opponent meetings from missing game logs. Near-milestones (2–3 goals away) are informational watch items, not verified storyline flags.')
        history_for_audit = st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None
        profiles_for_audit = st.session_state.get('auto_signal_metadata') if st.session_state.get('auto_signal_day') == day else None
        diagnostic = diagnostic_summary(combined, profiles_for_audit, history_for_audit, day)
        st.dataframe(pd.DataFrame([diagnostic]), hide_index=True, use_container_width=True)
        if diagnostic['Histories fetched'] and diagnostic['Total prior opponent meetings'] == 0:
            st.warning('Zero prior opponent meetings found. This can be normal early in the season, but check NHL game-log opponent codes before drawing conclusions.')
        if history_for_audit is not None and not history_for_audit.empty:
            diagnostic_cols = ['Player','Team','Player ID','Opponent','Vs opponent GP','Vs opponent goals','Log rows received','Log rows valid pre-slate','Log rows excluded','Opponent match method','Opponent normalized','Raw opponent samples','Distinct raw opponent values','Rows missing opponent code','Opponent match diagnostic','Season goals (log)','Milestone distance','Milestone watch (not a flag)','V3.8 status']
            st.dataframe(history_for_audit[[c for c in diagnostic_cols if c in history_for_audit]], hide_index=True, use_container_width=True)
            st.download_button('Download opponent-history diagnostics CSV', history_for_audit.to_csv(index=False), file_name=f'null-v382-opponent-diagnostics-{day}.csv', mime='text/csv')
        st.subheader('V3.8.4 Official Schedule & Player Assignment Audit')
        st.caption('Cross-checks the displayed slate against the official NHL schedule, then checks prior completed team meetings. A player may have zero personal games even when the teams met earlier.')
        if st.button('Validate official schedule and opponent assignments'):
            with st.spinner('Checking official slate and prior team schedules...'):
                try:
                    schedule_games, schedule_players, schedule_errors = audit_schedule(
                        st.session_state['signals_ranked'].to_dict('records'), games, day)
                    st.session_state['schedule_v384'] = (schedule_games, schedule_players, schedule_errors)
                    st.session_state['schedule_v384_day'] = day
                except Exception as exc:
                    st.error(f'Schedule validation unavailable: {type(exc).__name__}: {exc}')
        if st.session_state.get('schedule_v384_day') == day and 'schedule_v384' in st.session_state:
            sg, sp, se = st.session_state['schedule_v384']
            st.dataframe(sg, hide_index=True, use_container_width=True)
            st.dataframe(sp, hide_index=True, use_container_width=True)
            if se:
                st.warning(f'{len(se)} team schedule(s) could not be retrieved; their historical counts are unavailable, not zero.')
                with st.expander('Team schedule errors'):
                    st.write(se)
            st.download_button('Download V3.8.4 schedule and player audit CSV', sp.to_csv(index=False),
                               file_name=f'null-v384-schedule-audit-{day}.csv', mime='text/csv')
        st.subheader('V3.8.5 Roster & Historical Schedule Verification')
        st.caption('Checks NHL season-roster membership by player ID and counts completed pre-slate team games. Season-roster membership does not establish the player was on that team on the selected historical date.')
        if st.button('Verify player rosters and historical schedule coverage'):
            with st.spinner('Fetching independent team rosters and schedules...'):
                try:
                    rp, rt, re = audit_roster_and_history(st.session_state['signals_ranked'].to_dict('records'),games,day)
                    st.session_state['v385_audit']=(rp,rt,re)
                    st.session_state['v385_day']=day
                except Exception as exc:
                    st.error(f'V3.8.5 audit unavailable: {type(exc).__name__}: {exc}')
        if st.session_state.get('v385_day')==day and 'v385_audit' in st.session_state:
            rp,rt,re=st.session_state['v385_audit']
            st.metric('Players checked',len(rp))
            if not rp.empty:
                st.metric('Players not found on assigned roster',int((rp['Roster membership']=='NOT FOUND on assigned team roster').sum()))
                st.dataframe(rp,hide_index=True,use_container_width=True)
                st.download_button('Download V3.8.5 player roster audit CSV',rp.to_csv(index=False),file_name=f'null-v385-roster-{day}.csv',mime='text/csv')
            if not rt.empty:
                st.dataframe(rt,hide_index=True,use_container_width=True)
                st.download_button('Download V3.8.5 team schedule coverage CSV',rt.to_csv(index=False),file_name=f'null-v385-team-coverage-{day}.csv',mime='text/csv')
            if re:
                st.warning(f'{len(re)} retrieval/validation errors; unavailable data is not counted as zero.')
                with st.expander('V3.8.5 retrieval errors'): st.write(re)
    # V4.2: three prior seasons for the ENTIRE ranked slate, automatically.
    _v42_ranked=st.session_state.get('signals_ranked')
    if isinstance(_v42_ranked,pd.DataFrame) and not _v42_ranked.empty and st.session_state.get('signals_day')==day:
        _v42_ids=tuple(_v42_ranked['Player ID'].astype(str).tolist())
        _v42_games_sig=tuple(sorted(str(g.get('Game ID','')) for g in games))
        _v42_hist_key=(day,3,_v42_ids,_v42_games_sig)
        if st.session_state.get('history_v386_day') != day and st.session_state.get('v42_history_attempt')!=_v42_hist_key:
            st.session_state['v42_history_attempt']=_v42_hist_key
            # Return control to the page immediately. The completed future is
            # collected by the 10-second status fragment at the top of Home.
            job=history_executor().submit(historical_cached, day, 3, _v42_ids,
                _v42_games_sig, _v42_ranked.to_dict('records'), games)
            st.session_state['v43_history_job']={'day':day,'key':_v42_hist_key,'future':job}
        if _rx and st.session_state.get('history_v386_day')!=day:
            st.caption('Three-season opponent history is updating separately; statistical rankings are available.')
    if _rx:
        st.subheader('V3.8.6 Multi-Season Opponent Storylines')
        st.caption('Previous NHL regular seasons only, with per-season source links and missing-data warnings. Descriptive history is NOT a calibrated goalscorer probability.')
        v386_count = st.select_slider('Players for manual history recheck',options=[10,25,50,100,250,500],value=500,key='v386_count')
        v386_years = st.selectbox('Previous seasons to inspect manually',options=[1,2,3],index=2,key='v386_years')
        if st.button('Fetch multi-season opponent history'):
            with st.spinner('Retrieving prior-season player game logs...'):
                try:
                    h386, e386 = fetch_multi_history(st.session_state['signals_ranked'].to_dict('records'),games,day,max_players=v386_count,years=v386_years)
                    if st.session_state.get('history_v386_day')==day and st.session_state.get('history_v386_years')==v386_years:
                        h386=merge_profile_batches(st.session_state.get('history_v386'),h386)
                    st.session_state['history_v386']=h386
                    st.session_state['history_v386_day']=day
                    st.session_state['history_v386_years']=v386_years
                    st.session_state['history_v386_errors']=e386
                    st.rerun()  # Re-render the four leader cards above with newly fetched evidence.
                    st.success(f'{len(h386)} player histories loaded; {len(e386)} season retrieval errors.')
                except Exception as exc:
                    st.error(f'Multi-season history unavailable: {type(exc).__name__}: {exc}')
        if st.session_state.get('history_v386_day')==day and st.session_state.get('history_v386_years')==v386_years:
            h386=st.session_state['history_v386']
            if not h386.empty:
                st.metric('Players with complete prior-season data',int((h386['Historical data status']=='Complete').sum()))
                st.metric('Historical storyline flags',int(h386['Historical storyline flag'].fillna('').ne('').sum()))
                st.dataframe(h386,hide_index=True,use_container_width=True)
                st.download_button('Download V3.8.6 historical opponent evidence CSV',h386.to_csv(index=False),file_name=f'null-v386-historical-{day}.csv',mime='text/csv')
            if st.session_state.get('history_v386_errors'):
                st.warning('Some season logs were unavailable; partial history is not treated as zero.')
                with st.expander('Multi-season retrieval errors'): st.write(st.session_state['history_v386_errors'])
        if st.session_state.get('v385_day')==day and 'v385_audit' in st.session_state:
            missing=missing_player_ids(st.session_state['signals_ranked'],st.session_state['v385_audit'][0])
            if missing:
                st.warning(f'{len(missing)} ranked player(s) missing from V3.8.5 roster audit:')
                st.dataframe(pd.DataFrame(missing),hide_index=True,use_container_width=True)
            else:
                st.caption('All currently ranked player IDs are present in the V3.8.5 roster audit.')
        st.download_button('Download V3.8.2 audit CSV', pd.DataFrame([diagnostic]).to_csv(index=False), file_name=f'null-v382-audit-{day}.csv', mime='text/csv')
        st.subheader('V3.8.2 Combined Statistical + Experimental Explorer')
        st.caption('Statistical form and experimental overlaps are separate columns. Neither is a calibrated goal probability. Former-team, milestone and news claims are marked unverified.')
        only_stories = st.checkbox('Show only sourced storyline flags', value=False)
        minimum_overlap = st.slider('Minimum experimental pattern overlaps', 0, 5, 0)
        longshot_only = st.checkbox('Statistical sleeper watch (outside top 20, L5 shots/game >= 2)', value=False)
        # Statistical rank was assigned before any storyline merge; never overwrite it here.
        filtered = combined[combined['Pattern overlaps'] >= minimum_overlap]
        if only_stories: filtered = filtered[filtered['Storyline count'] > 0]
        if longshot_only: filtered = filtered[(filtered['Statistical rank'] > 20) & (filtered['Shots/G L5'] >= 2)]
        st.dataframe(ui.with_form_pct(filtered), hide_index=True, use_container_width=True, column_config=ui.form_pct_config(st))
        st.download_button('Download combined V3.6 CSV', ui.with_form_pct(filtered).to_csv(index=False), file_name=f'null-v36-combined-{day}.csv', mime='text/csv')
        st.download_button('Download experimental signals CSV', ui.with_form_pct(signals).to_csv(index=False),
                           file_name=f'null-experimental-signals-{day}.csv', mime='text/csv')
else:
    st.info('Run Rank Entire Slate for this date to populate the experimental signals table.')


# V4.8 recreational number analysis; not used by statistical rankings.
_TEAM_NAMES = {'ANA':'Anaheim Ducks','BOS':'Boston Bruins','BUF':'Buffalo Sabres','CAR':'Carolina Hurricanes','CBJ':'Columbus Blue Jackets','CGY':'Calgary Flames','CHI':'Chicago Blackhawks','COL':'Colorado Avalanche','DAL':'Dallas Stars','DET':'Detroit Red Wings','EDM':'Edmonton Oilers','FLA':'Florida Panthers','LAK':'Los Angeles Kings','MIN':'Minnesota Wild','MTL':'Montreal Canadiens','NJD':'New Jersey Devils','NSH':'Nashville Predators','NYI':'New York Islanders','NYR':'New York Rangers','OTT':'Ottawa Senators','PHI':'Philadelphia Flyers','PIT':'Pittsburgh Penguins','SEA':'Seattle Kraken','SJS':'San Jose Sharks','STL':'St Louis Blues','TBL':'Tampa Bay Lightning','TOR':'Toronto Maple Leafs','UTA':'Utah Mammoth','VAN':'Vancouver Canucks','VGK':'Vegas Golden Knights','WPG':'Winnipeg Jets','WSH':'Washington Capitals'}
