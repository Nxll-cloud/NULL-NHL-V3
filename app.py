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

st.set_page_config(page_title='NULL NHL V3.5', page_icon='🏒', layout='wide')
st.markdown("""<style>.stApp{background:#0d0d17;color:#f2f0ff}h1,h2,h3{color:#c4a5ff}div.stButton>button{background:#6f3cc3;color:white;border-radius:10px}</style>""", unsafe_allow_html=True)
st.title('NULL NHL V3.5')
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
        ranked = attach_matchups(ranked, games, defensive, adjust=use_defense)
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
st.caption('NHL player landing profiles supply birthdays and current jersey numbers. Arena names come from the NHL schedule. No injuries, revenge games, milestones or confirmed lineups are inferred automatically.')
auto_limit = st.select_slider('NHL profiles to fetch (top-ranked players)', options=[10, 25, 50, 100], value=50)
if st.button('Fetch NHL player biographies and arenas'):
    if 'signals_ranked' not in st.session_state or st.session_state.get('signals_day') != day:
        st.warning('Run Rank Entire Slate first.')
    else:
        with st.spinner('Retrieving source-linked NHL profiles...'):
            data, errors = fetch_metadata(st.session_state['signals_ranked'].to_dict('records'), day, games, max_players=auto_limit)
        st.session_state['auto_signal_metadata'] = pd.DataFrame(data)
        st.session_state['auto_signal_day'] = day
        st.success(f'Fetched {len(data)} profiles; {len(errors)} unavailable.')
        if errors:
            with st.expander('Profile retrieval errors'):
                st.write(errors)
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
    st.download_button('Download experimental signals CSV', signals.to_csv(index=False),
                       file_name=f'null-experimental-signals-{day}.csv', mime='text/csv')
else:
    st.info('Run Rank Entire Slate for this date to populate the experimental signals table.')
