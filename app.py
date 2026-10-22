
import streamlit as st
import pandas as pd
import requests
from datetime import date, datetime, timezone

st.set_page_config(
    page_title="NULL NHL V3",
    page_icon="🏒",
    layout="wide",
)

st.markdown("""
<style>
.stApp {background-color: #0d0d17; color: #f2f0ff;}
h1, h2, h3 {color: #c4a5ff;}
div.stButton > button {
    background-color: #6f3cc3;
    color: white;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

st.title("NULL NHL V3")
st.caption("NHL goal-scorer analytics | Verified data")

selected_date = st.date_input("NHL slate date", date.today())

@st.cache_data(ttl=900)
def get_schedule(day):
    url = f"https://api-web.nhle.com/v1/schedule/{day}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json(), url

if st.button("Refresh NHL Data"):
    get_schedule.clear()

try:
    data, source_url = get_schedule(selected_date.isoformat())
    games = []

    for week in data.get("gameWeek", []):
        if week.get("date") != selected_date.isoformat():
            continue

        for game in week.get("games", []):
            away = game.get("awayTeam", {})
            home = game.get("homeTeam", {})

            games.append({
                "Game ID": game.get("id"),
                "Away": away.get("abbrev", "Unknown"),
                "Home": home.get("abbrev", "Unknown"),
                "Start (UTC)": game.get("startTimeUTC", ""),
                "Status": game.get("gameState", "Unknown"),
            })

    st.caption(
        "Source: NHL public API | Retrieved: "
        + datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M UTC"
        )
    )
    st.caption(source_url)

    st.subheader("Full NHL Slate")

    if games:
        df = pd.DataFrame(games)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.metric("Slate Games", len(games))
    else:
        st.info("No NHL games found for this date.")

except (requests.RequestException, ValueError) as error:
    st.error(f"NHL data unavailable: {error}")

st.divider()
st.subheader("V3 Goal-Scorer Rankings")
st.info("Pending verified player statistics and model integration.")

st.subheader("Goalie Matchups")
st.info("Pending confirmed goalie and defensive data.")

st.subheader("Historical Predictions")
st.info("Prediction tracking will be added next.")

st.subheader("Model Status")
st.warning("Goal-scoring predictions are not yet calculated.")
