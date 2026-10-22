"""NULL NHL V3.2: source-first NHL slate and descriptive player form."""
from datetime import date, datetime, timezone
import pandas as pd
import requests
import streamlit as st
from nhl_data import get_schedule, load_team, SEASON
from rankings import rank_players
from matchups import defense_summary, attach_matchups
from backtesting import make_snapshot, score_snapshot, top_k_metrics
from signals import build_signals, universal_day
from auto_signals import fetch_metadata
from storylines_v36 import build_storylines, combined_table
from storyline_v37 import select_storyline_watch
from storyline_v38 import fetch_history, merge_history
from data_integrity_v381 import merge_profile_batches, coverage_audit
from diagnostics_v382 import diagnostic_summary
from schedule_validation_v384 import audit_schedule
from roster_schedule_v385 import audit_roster_and_history
from history_v386 import fetch_multi_history, merge_multi_history, missing_player_ids
from storyline_v387 import separate_leaders
from ranking_integrity_v3871 import assign_statistical_ranks, validate_statistical_ranks

st.set_page_config(page_title='NULL NHL V3.8.7.1', page_icon='🏒', layout='wide')
st.markdown("""<style>.stApp{background:#0d0d17;color:#f2f0ff}h1,h2,h3{color:#c4a5ff}div.stButton>button{background:#6f3cc3;color:white;border-radius:10px}</style>""", unsafe_allow_html=True)
st.title('NULL NHL V3.8.7.1')
storyline_top = st.container()
with storyline_top:
    st.subheader('🏆 NULL NHL — Four Distinct Leaders')
    st.caption('Evidence-first, pre-slate storylines. Former-team and injury/news claims are not inferred.')
st.caption('Verified NHL data | Pregame player form | Model probabilities pending')
selected_date = st.date_input('NHL slate date', date.today())
day = selected_date.isoformat()

@st.cache_data(ttl=900, show_spinner=False)
def schedule_cached(day):
    return get_schedule(day)

@st.cache_data(ttl=3600, show_spinner=False)
def team_cached(team, day):
    return load_team(team, day, SEASON)

@st.cache_data(ttl=3600, show_spinner=False)
def defense_cached(team, day):
    return defense_summary(team, day, SEASON)

if st.button('Refresh NHL Data'):
    schedule_cached.clear()
    team_cached.clear()
    defense_cached.clear()

try:
    games = schedule_cached(day)
    st.caption(f'Source: NHL public API | Displayed at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC')
    st.caption(f'https://api-web.nhle.com/v1/schedule/{day}')
    st.subheader('Full NHL Slate')
    if games:
        st.dataframe(pd.DataFrame(games), hide_index=True, use_container_width=True)
        st.metric('Slate Games', len(games))
    else:
        st.info('No games found for this date.')
except (requests.RequestException, ValueError, KeyError) as exc:
    st.error(f'Schedule request failed: {exc}')
    games = []

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
                st.caption(f'Source: NHL roster and player game-log endpoints | Season {SEASON}')
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

st.divider()
st.subheader('V3.2 Goal-Scorer Rankings')
st.caption('Descriptive form index, NOT a scoring probability. Opponent goals/shots allowed '
           'adjust the form index by at most 15% where coverage is sufficient. '
           'Goalie starters are unconfirmed and no goalie adjustment is applied.')
if games:
    min_games = st.slider('Minimum prior games per player', 1, 10, 3)
    use_defense = st.checkbox('Apply opponent defense adjustment', value=True)
    if st.button('Rank Entire Slate', type='primary'):
        teams_to_load = sorted({g[t] for g in games for t in ('Home', 'Away') if g.get(t)})
        all_rows, all_errors = [], []
        progress = st.progress(0, text='Loading all teams')
        for i, team_code in enumerate(teams_to_load, start=1):
            try:
                team_rows, team_errors = team_cached(team_code, day)
                all_rows.extend(team_rows)
                all_errors.extend([f'{team_code}: {e}' for e in team_errors])
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                all_errors.append(f'{team_code}: {exc}')
            progress.progress(i / len(teams_to_load), text=f'Loaded {i}/{len(teams_to_load)} teams')
        ranked = rank_players(all_rows, min_games)
        defensive, defense_errors = {}, []
        for team_code in teams_to_load:
            try:
                defensive[team_code] = defense_cached(team_code, day)
            except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                defense_errors.append(f'{team_code}: {exc}')
        ranked = assign_statistical_ranks(attach_matchups(ranked, games, defensive, adjust=use_defense)).to_dict('records')
        coverage = pd.DataFrame([
            {k:v for k,v in d.items() if k != 'Error details'}
            for d in defensive.values()
        ])
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
            try:
                snapshot = make_snapshot(ranked, games, day)
                st.download_button('Save PRE-GAME snapshot CSV (keep this file)',
                                   snapshot.to_csv(index=False),
                                   file_name=f'null-pregame-{day}.csv', mime='text/csv')
                st.caption('Snapshot is saved to YOUR device only. Download before the first puck drop. '
                           'A later download cannot recreate a genuine pregame prediction.')
            except (KeyError, ValueError, TypeError) as exc:
                st.info(f'Pregame snapshot unavailable: {exc}')
            st.dataframe(pd.DataFrame(ranked), hide_index=True, use_container_width=True)
            st.download_button('Download rankings CSV', pd.DataFrame(ranked).to_csv(index=False),
                               file_name=f'null-nhl-v3-2-{day}.csv', mime='text/csv')
            st.caption('Statistical sleepers (NOT verified betting longshots): players outside the top 20 '
                       'with at least 2 shots per game over the last 5 games.')
            watch = [r for r in ranked[20:] if r['Shots/G L5'] >= 2]
            if watch:
                st.dataframe(pd.DataFrame(watch[:20]), hide_index=True, use_container_width=True)
            else:
                st.info('No players met the longshot-watchlist rule.')
        else:
            st.warning('No eligible players found.')
        if all_errors:
            st.warning(f'{len(all_errors)} player/team requests failed; ranking coverage is incomplete.')
            with st.expander('Missing-data details'):
                st.write(all_errors)
        st.warning('Current roster membership is not historical lineup verification. '
                   'Do not use this ranking as a historical pregame prediction or calibrated probability.')
else:
    st.info('Select a date with games to calculate full-slate form rankings.')
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
                st.dataframe(scored, hide_index=True, use_container_width=True)
                st.download_button('Download scored snapshot CSV', scored.to_csv(index=False),
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
metadata = None
if meta_file is not None:
    try:
        metadata = pd.read_csv(meta_file, dtype=str).fillna('')
        if 'Player ID' not in metadata.columns:
            st.warning('Metadata needs a Player ID column; metadata ignored.')
            metadata = None
    except (ValueError, pd.errors.ParserError) as exc:
        st.warning(f'Metadata could not be loaded: {exc}')
if st.session_state.get('auto_signal_day') == day and 'auto_signal_metadata' in st.session_state:
    automatic = st.session_state['auto_signal_metadata']
    if metadata is None:
        metadata = automatic
    else:
        metadata = pd.concat([metadata, automatic], ignore_index=True).drop_duplicates(subset=['Player ID'], keep='first')
if 'signals_ranked' in st.session_state and st.session_state.get('signals_day') == day:
    signals = build_signals(st.session_state['signals_ranked'], day, metadata)
    st.caption(f'{len(signals)} players evaluated. Pattern overlap counts are descriptive, '
               'not confidence scores. Missing biographical data remains unavailable.')
    st.dataframe(signals, hide_index=True, use_container_width=True)
    storylines = build_storylines(st.session_state['signals_ranked'], metadata if metadata is not None else pd.DataFrame(), day)
    combined = combined_table(st.session_state['signals_ranked'], signals, storylines)
    combined = merge_history(combined, st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None)
    combined = merge_multi_history(combined, st.session_state.get('history_v386') if st.session_state.get('history_v386_day') == day else None)
    validate_statistical_ranks(combined)
    top_stories, storyline_sleepers, featured = select_storyline_watch(combined)
    v387 = separate_leaders(combined)
    with storyline_top:
        st.caption('Statistical form, sourced storyline strength, top-20 overlap and descriptive sleeper are separate rankings. None is a calibrated scoring probability.')
        labels = [('statistical','📊 Top Statistical Goalscorer'),('storyline','📚 Top Storyline Candidate'),('overlap','🔗 Best Statistical + Storyline Overlap'),('longshots','🎯 Strongest Statistical Sleeper')]
        for key, label in labels:
            lead = v387['leaders'][key]
            st.markdown('#### ' + label)
            if lead is None:
                st.info('No eligible player with the currently loaded evidence. Fetch historical opponent logs for wider coverage.')
                continue
            st.markdown(f"**{lead['Player']} — {lead['Team']}**")
            c1,c2,c3 = st.columns(3)
            c1.metric('Statistical rank',int(lead['Statistical rank']))
            c2.metric('Storyline evidence points',f"{lead['Storyline evidence score']:.2f}")
            c3.metric('Storyline flags',int(lead['Storyline count']))
            st.caption(f"Opponent history: {('not loaded / insufficient' if lead['Historical coverage'] != 'Complete, >=3 meetings' else str(int(lead['Historical opponent goals'])) + ' goals, ' + str(int(lead['Historical opponent shots'])) + ' shots in ' + str(int(lead['Historical opponent GP'])) + ' games')}; {lead['Historical coverage']}. Shots/G last five: {lead['Shots/G L5']:.2f}. Adjusted form index: {lead['V3.2 Adjusted Index']:.1f}.")
            st.write('**Evidence:**',lead.get('Verified data flags','Not available'))
            if pd.notna(lead.get('Evidence URLs')) and str(lead.get('Evidence URLs')).strip():
                st.caption('Sources: '+str(lead['Evidence URLs']))
        st.caption('Storyline evidence points are an explicitly heuristic display index: 2 per historical goal (max 10), 6 × historical goals/game (max 1.5), historical shots/10 (max 50 shots), plus 1.5 per sourced flag (max 5). Historical components require complete requested seasons and ≥3 meetings. They are NOT validated predictive weights.')
        for key,title in [('statistical','Top 10 Statistical'),('storyline','Top 10 Storylines'),('overlap','Top 10 Overlap'),('longshots','Top 10 Statistical Sleepers')]:
            st.subheader(title)
            frame=v387[key]
            if frame.empty: st.info('No eligible players in currently loaded data.')
            else:
                cols=['Player','Team','Statistical rank','Storyline rank','Storyline evidence score','Storyline count','Historical opponent GP','Historical opponent goals','Historical opponent shots','Shots/G L5','Verified data flags']
                st.dataframe(frame[[c for c in cols if c in frame]],hide_index=True,use_container_width=True)
                st.download_button('Download '+title+' CSV',frame.to_csv(index=False),file_name=f'null-v387-{key}-{day}.csv',mime='text/csv',key=f'v387_{key}')
        covered = combined['Historical data status'].eq('Complete').sum() if 'Historical data status' in combined else 0
        st.caption(f'Historical coverage: {covered}/{len(combined)} players. Incomplete coverage can change storyline and overlap leaders; fetch all players before relying on the full-slate comparison.')
    st.download_button('Download top 10 storyline watchlist CSV', top_stories.to_csv(index=False), file_name=f'null-v381-top10-{day}.csv', mime='text/csv')
    st.subheader('V3.8.2 Data Integrity Audit')
    audit = coverage_audit(combined, st.session_state.get('auto_signal_metadata') if st.session_state.get('auto_signal_day') == day else None,
                           st.session_state.get('history_v38') if st.session_state.get('history_v38_day') == day else None)
    st.dataframe(pd.DataFrame([audit]), hide_index=True, use_container_width=True)
    if audit['Histories fetched'] < audit['Eligible players']:
        st.info('Opponent-history coverage is partial; zero flags on unfetched players do not mean no storyline.')
    st.download_button('Download ALL evaluated players + storyline evidence CSV', combined.to_csv(index=False),
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
    st.subheader('V3.8.6 Multi-Season Opponent Storylines')
    st.caption('Previous NHL regular seasons only, with per-season source links and missing-data warnings. Descriptive history is NOT a calibrated goalscorer probability.')
    v386_count = st.select_slider('Players for multi-season history',options=[10,25,50,100,250,500],value=50,key='v386_count')
    v386_years = st.selectbox('Previous seasons to inspect',options=[1,2,3],index=2,key='v386_years')
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
    st.dataframe(filtered, hide_index=True, use_container_width=True)
    st.download_button('Download combined V3.6 CSV', filtered.to_csv(index=False), file_name=f'null-v36-combined-{day}.csv', mime='text/csv')
    st.download_button('Download experimental signals CSV', signals.to_csv(index=False),
                       file_name=f'null-experimental-signals-{day}.csv', mime='text/csv')
else:
    st.info('Run Rank Entire Slate for this date to populate the experimental signals table.')
