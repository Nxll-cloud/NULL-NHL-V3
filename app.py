"""NULL NHL V3: source-first NHL slate and pregame player performance."""
from datetime import date, datetime, timezone
import pandas as pd
import requests
import streamlit as st
from nhl_data import get_schedule, load_team, SEASON

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
st.caption('Only completed games BEFORE the selected slate date are counted. No future-game leakage.')
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
st.info('Not available yet: model calibration, goalie confirmation, lineup verification, and opponent-defense adjustments are required.')
st.subheader('Historical Predictions')
st.info('No saved predictions yet. Future backtests must use pregame snapshots.')
st.subheader('Experimental Storyline & Numerology Signals')
st.caption('Not implemented. These signals will be separated from evidence-based probability estimates.')
