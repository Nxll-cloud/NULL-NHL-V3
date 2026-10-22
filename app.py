"""NULL NHL V3: source-first NHL slate and pregame player performance."""
from datetime import date, datetime, timezone
import pandas as pd
import requests
import streamlit as st
from nhl_data import get_schedule, load_team, SEASON
from rankings import rank_players

st.set_page_config(page_title='NULL NHL V3', page_icon='🏒', layout='wide')
st.markdown('''<style>.stApp{background:#0d0d17;color:#f2f0ff}h1,h2,h3{color:#c4a5ff}div.stButton>button{background:#6f3cc3;color:white;border-radius:10px}</style>''', unsafe_allow_html=True)
st.title('NULL NHL V3')
st.caption('Verified NHL data | Pregame player form | Model probabilities pending')
selected_date = st.date_input('NHL slate date', date.today())
day = selected_date.isoformat()

@st.cache_data(ttl=900, show_spinner=False)
def schedule_cached(day):
    return get_schedule(day)

@st.cache_data(ttl=3600, show_spinner=False)
def team_cached(team, day):
    return load_team(team, day, SEASON)

if st.button('Refresh NHL Data'):
    schedule_cached.clear()
    team_cached.clear()

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
st.subheader('V3 Goal-Scorer Rankings')
st.caption('Descriptive form index only. Not a goal probability, confidence score, or betting recommendation. '
           'No goalie, defense, lineup, injury, or odds adjustments are included.')
if games:
    min_games = st.slider('Minimum prior games per player', 1, 10, 3)
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
        st.metric('Teams requested', len(teams_to_load))
        st.metric('Players eligible for form ranking', len(ranked))
        if ranked:
            st.dataframe(pd.DataFrame(ranked), hide_index=True, use_container_width=True)
            st.download_button('Download rankings CSV', pd.DataFrame(ranked).to_csv(index=False),
                               file_name=f'null-nhl-form-{day}.csv', mime='text/csv')
            st.caption('Longshot watchlist (descriptive only): eligible players outside the top 20 '
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
st.subheader('Historical Predictions')
st.info('No saved predictions yet. Future backtests must use pregame snapshots.')
st.subheader('Experimental Storyline & Numerology Signals')
st.caption('Not implemented. These signals will be separated from evidence-based probability estimates.')
